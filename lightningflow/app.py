import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass, field, replace
from pathlib import Path
import json
import queue
import threading
import time
import wave

import numpy as np
import sounddevice as sd
from .audio import RATE, BLOCK, Segmenter, PreviewBuffer, merge, input_options
from .asr_process import CudaASRProcess as CudaASR, GPUWorkerError
from .win32 import InputGuard, u
from . import __version__

@dataclass
class Session:
    target: object
    began: float = field(default_factory=time.perf_counter)
    stopped: float = 0
    capture_until: float = 0
    first_audio: float = 0
    first_partial: float = 0
    decode_ms: float = 0
    raw: list = field(default_factory=list)
    text: str = ""
    error: str = ""
    cancelled: bool = False
    retry_of: object = None
    delivered: bool = False
    delivery_error: str = ''
    metrics: dict = field(default_factory=dict)
    preview_epoch: int = 0
    provisional: str = ''
    capture_warning: str = ''
    ready_for_delivery: bool = False

class Dictation:
    def __init__(self, args):
        self.args = args
        # Three queued smart gestures can each issue start/pause/resume/stop
        # before the capture thread next runs. Keep that burst bounded and safe.
        self.commands = queue.Queue(maxsize=32)
        self.jobs = queue.Queue(maxsize=32)
        self.events = queue.Queue()
        self.previews = queue.Queue(maxsize=1)
        self.quit = threading.Event()
        self.bindings = {1:args.toggle_vk, 2:args.cancel_vk, 3:args.retry_vk, 4:args.quit_vk, 5:args.save_vk}
        if len(set(self.bindings.values())) != len(self.bindings):
            raise ValueError("Each action needs a distinct global shortcut")
        self.guard = InputGuard(self.bindings.values())
        self.active = self.last = None
        self.recording = False
        self.ready = False
        self.pending = None
        self.sessions = []
        self.gpu_error = ''

    def register_session(self,session):
        if not any(item is session for item in self.sessions):self.sessions.append(session)

    def can_start_recording(self):
        return (self.ready and not self.gpu_error and not self.recording and len(self.sessions)<3
                and not any(item.retry_of for item in self.sessions)
                and (self.active is None or any(item is self.active for item in self.sessions)))

    def rebase_queued_targets(self,session,receipt):
        """Advance only an identical captured caret after our confirmed insert."""
        old=session.target;after=getattr(receipt,'after_state',None)
        if old is None or after is None:return
        for item in self.sessions:
            target=item.target
            if item is session or target is None:continue
            if ((target.foreground,target.focus,target.process,target.epoch,target.native)==
                    (old.foreground,old.focus,old.process,old.epoch,old.native) and target.state==old.state):
                item.target=replace(target,state=after)

    def emit(self, event, value=None):
        self.events.put((event, value))

    def new_session(self, target):
        return Session(target)

    def on_tick(self):
        if self.gpu_error:
            self.ready=False
            if self.recording and self.active is not None:
                self.active.capture_until=time.perf_counter()
                self.commands.put_nowait(('stop',None))
                self.recording=False

    def latch_gpu_fault(self,session,reason):
        if not self.gpu_error:
            self.gpu_error=f'GPU transcription stopped: {reason}. Captured audio retained; export or save recovery audio before restarting the engine.'
            self.ready=False
            self.emit('gpu_fault',self.gpu_error)
        if session is not None:session.error=self.gpu_error

    def infer(self):
        try:
            engine = CudaASR(Path(self.args.models) / self.args.model, self.args.compute)
            engine.language=getattr(self.args,'language','en')
            self.emit("ready", f"{engine.provider}, {self.args.model}, {self.args.compute}; cold load/warm-up {engine.load_ms:.0f} ms")
        except Exception as exc:
            self.emit("fatal", f"GPU startup failed: {exc}. No CPU fallback attempted.")
            return
        try:self._infer_loop(engine)
        finally:
            close=getattr(engine,'close',None)
            if close:close()

    def _infer_loop(self,engine):
        while not self.quit.is_set():
            if getattr(engine,'failed',False) and not self.gpu_error:
                self.latch_gpu_fault(self.active,'The isolated CUDA process exited unexpectedly')
            try:
                kind, session, chunk = self.jobs.get(timeout=.02)
            except queue.Empty:
                try:session,epoch,samples=self.previews.get_nowait()
                except queue.Empty:continue
                # A real decode/finalization always takes priority over previews.
                if self.gpu_error or not self.jobs.empty() or session.cancelled or session.error or session.stopped or session.capture_until or epoch!=session.preview_epoch:continue
                try:
                    prompt=getattr(session,'asr_prompt','')
                    result=engine.transcribe(samples,initial_prompt=prompt) if prompt else engine.transcribe(samples)
                    if result and not session.cancelled and not session.stopped and not session.capture_until and epoch==session.preview_epoch:
                        session.first_partial=session.first_partial or time.perf_counter()
                        session.provisional=merge(session.text,result,True)
                        self.emit('preview',session)
                except GPUWorkerError as exc:
                    self.latch_gpu_fault(session,str(exc))
                except Exception:
                    # Preview failure must not poison the authoritative transcript.
                    pass
                continue
            if self.gpu_error and not session.cancelled:session.error=self.gpu_error
            if kind == "finish":
                self.emit("done", session)
            elif not session.cancelled and not session.error:
                try:
                    start = time.perf_counter()
                    prompt=getattr(session,'asr_prompt','')
                    result = engine.transcribe(chunk.audio,initial_prompt=prompt) if prompt else engine.transcribe(chunk.audio)
                    session.decode_ms += (time.perf_counter() - start) * 1000
                    session.text = merge(session.text, result, chunk.overlapped)
                    if result:
                        session.first_partial = session.first_partial or time.perf_counter()
                        self.emit("partial", session)
                except Exception as exc:
                    self.latch_gpu_fault(session,str(exc))

    def enqueue(self, kind, session, chunk=None):
        try:
            self.jobs.put_nowait((kind, session, chunk))
        except queue.Full:
            session.error = "ASR queue reached its limit. Audio retained in memory; press Ctrl+Alt+S after stop to export."
            if kind == "finish":
                # Preserve ordering: wait on this background capture thread only.
                while not self.quit.is_set():
                    try:
                        self.jobs.put((kind, session, chunk), timeout=.1)
                        break
                    except queue.Full:
                        pass

    def capture(self):
        stream = session = segmenter = None
        preview=PreviewBuffer()
        def finish():
            nonlocal stream, session
            if stream is not None:
                try:stream.close()
                except Exception:
                    if session is not None:session.capture_warning='Microphone could not close cleanly. Captured speech was retained.'
                stream = None
            if session is not None:
                session.preview_epoch+=1
                session.provisional=''
                chunk = segmenter.flush()
                if chunk is not None and not session.cancelled:
                    self.enqueue("chunk", session, chunk)
                session.stopped = time.perf_counter()
                self.enqueue("finish", session)
                session = None
        try:
            while not self.quit.is_set():
                try:
                    action, value = self.commands.get(timeout=.02 if stream is None else 0)
                except queue.Empty:
                    action = None
                if action == "start":
                    session = value
                    segmenter = Segmenter()
                    preview.reset()
                    try:
                        stream = sd.InputStream(**input_options(self.args.device), samplerate=RATE,
                                                channels=1, dtype="float32", blocksize=BLOCK,
                                                latency="low")
                        stream.start()
                        self.emit("listening", session)
                    except Exception as exc:
                        session.error = f"Microphone could not open: {exc}. Check Windows microphone permissions/device."
                        finish()
                elif action == "pause" and stream is not None:
                    try:
                        stream.close()
                        stream = None
                    except Exception:
                        session.capture_warning='Microphone failed while pausing. Captured speech was retained.'
                        self.emit('capture_stopped',session)
                        finish()
                elif action == "resume" and session is not None and stream is None:
                    try:
                        stream = sd.InputStream(**input_options(self.args.device), samplerate=RATE,
                                                channels=1, dtype="float32", blocksize=BLOCK,
                                                latency="low")
                        stream.start()
                        self.emit("listening", session)
                    except Exception as exc:
                        if session.raw:
                            session.capture_warning='Microphone could not resume. Captured speech was retained.'
                            self.emit('capture_stopped',session)
                        else:session.error='Microphone could not resume. Check the selected device.'
                        finish()
                elif action in ("stop", "cancel") and session is not None:
                    if action == "cancel":
                        session.cancelled = True
                    finish()
                if stream is not None:
                    try:
                        frame, overflow = stream.read(BLOCK)
                        # A read already in flight can complete after release.
                        # Discard that boundary frame; never feed post-release
                        # audio to the transcript or the recording meter.
                        if session.capture_until and time.perf_counter()>=session.capture_until:
                            finish()
                            continue
                        if getattr(session,'capture_paused_at',0):
                            continue  # A short tap has released; close on queued pause.
                        if overflow:
                            raise RuntimeError("Audio input overflow; this recording may have gaps")
                        session.first_audio = session.first_audio or time.perf_counter()
                        session.raw.append(frame[:, 0].copy())
                        chunk = segmenter.feed(frame[:, 0])
                        if chunk is not None:
                            session.preview_epoch+=1
                            session.provisional=''
                            preview.reset()
                            self.enqueue("chunk", session, chunk)
                        else:
                            samples=preview.feed(frame[:,0])
                            if samples is not None and getattr(getattr(self,'settings',None),'live_preview',True):
                                request=(session,session.preview_epoch,samples)
                                try:self.previews.get_nowait()
                                except queue.Empty:pass
                                try:self.previews.put_nowait(request)
                                except queue.Full:pass
                        if len(session.raw) * BLOCK >= self.args.max_seconds * RATE:
                            self.emit("notice", "Recording limit reached; finalizing.")
                            finish()
                    except Exception as exc:
                        if session is not None:
                            session.capture_warning = 'Microphone capture interrupted. Captured speech is available for recovery; reconnect the selected device before recording again.'
                            self.emit('capture_stopped',session)
                        finish()
        finally:
            if session is not None:
                session.cancelled = True
                finish()

    def save(self):
        session = self.last
        if not session:
            print("No previous recording to export.", flush=True)
            return
        folder = Path(self.args.recovery) / time.strftime("%Y%m%d-%H%M%S")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "transcript.txt").write_text(session.text, encoding="utf-8")
        if session.raw:
            data = np.concatenate(session.raw)
            with wave.open(str(folder / "recording.wav"), "wb") as wav:
                wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
                wav.writeframes((np.clip(data, -1, 1) * 32767).astype("<i2").tobytes())
        print(f"Exported locally: {folder.resolve()}", flush=True)

    def deliver(self, session):
        source = session.retry_of or session
        try:
            self._deliver(session, source)
        finally:
            # Publish completion only after delivery finishes. Retrying must not
            # replace the original failed recording with an empty audio buffer.
            if not session.cancelled:
                self.last = source
            if self.active is session:
                self.active = next((item for item in reversed(self.sessions) if item is not session),None)
                if self.active is None:self.recording=False
            self.sessions=[item for item in self.sessions if item is not session]

    def _deliver(self, session, source):
        if session.cancelled:
            if session.retry_of is None:
                session.raw.clear()
                session.text = ''
            print("Cancelled. No text inserted.", flush=True)
            return
        if session.error:
            print(f"ERROR: {session.error}\nAudio/text retained until next recording or exit. Ctrl+Alt+S exports locally.", flush=True)
            return
        if session.capture_warning and session.retry_of is None:
            session.delivery_error=session.capture_warning
            print('Captured speech retained after microphone interruption; inspect before inserting.',flush=True)
            return
        if not session.text:
            print("No speech detected. No text inserted.", flush=True)
            return
        try:
            start = time.perf_counter()
            receipt = self.guard.insert(session.text, session.target)
            if not receipt or not receipt.confirmed:
                raise RuntimeError('The target did not confirm delivery; transcript retained')
            now = time.perf_counter()
            metrics = {"audio_seconds": len(session.raw) * BLOCK / RATE,
                       "capture_first_frame_ms": (session.first_audio-session.began)*1000 if session.first_audio else None,
                       "first_partial_ms": (session.first_partial-session.began)*1000 if session.first_partial else None,
                       "decode_ms": session.decode_ms,
                       "stop_to_input_ms": (now-session.stopped)*1000,
                       "input_dispatch_ms": (now-start)*1000,
                       "provider": "CUDA / CTranslate2", "delivery_method": receipt.method}
            session.delivered = source.delivered = True
            session.metrics = metrics
            self.rebase_queued_targets(session,receipt)
            print("INSERTED (verified): " + session.text, flush=True)
            print(json.dumps(metrics), flush=True)
            # Successful recordings keep text only for explicit retry/export.
            source.raw.clear()
        except Exception as exc:
            session.delivery_error = str(exc)
            print(f"DELIVERY NOT CONFIRMED: {exc}\nRecovered text: {session.text}\nCheck the field before retrying; the export shortcut saves a local copy.", flush=True)

    def schedule_delivery(self, session):
        self.register_session(session)
        session.ready_for_delivery=True
        if self.active is None:self.active=session
        if self.active is session:self.recording=False
        if self.pending is None and self.sessions[0] is session:
            self.pending=(session,time.perf_counter()+1.5)

    def tick_delivery(self):
        if self.pending is None:
            if not self.sessions or not self.sessions[0].ready_for_delivery:return
            self.pending=(self.sessions[0],time.perf_counter()+1.5)
        session, deadline = self.pending
        held = any(u.GetAsyncKeyState(v) & 0x8000 for v in (0x10, 0x11, 0x12, 0x5B, 0x5C))
        if held and self.recording and self.active is not session:return
        if session.cancelled or not held or time.perf_counter() >= deadline:
            self.pending = None
            if held and not session.cancelled:
                session.error = 'Modifier keys are still held. Nothing inserted; release keys and retry.'
            self.deliver(session)

    def handle_hotkey(self, ident):
        if ident == 4:
            return False
        if ident == 1 and self.ready:
            if self.can_start_recording():
                try:
                    try:
                        target = self.guard.snapshot()
                    except RuntimeError as exc:
                        target = None
                        print(f'Automatic insertion unavailable: {exc}. Dictation will still be transcribed and retained.', flush=True)
                    session = self.new_session(target)
                    self.active = session
                    self.register_session(session)
                    self.commands.put_nowait(('start', session))
                    self.recording = True
                    print('Opening microphone…', flush=True)
                except Exception as exc:
                    self.active = None
                    print(f'Cannot start: {exc}', flush=True)
            elif self.recording:
                self.commands.put_nowait(('stop', None))
                self.recording = False
                print('Finalizing…', flush=True)
        elif ident == 2 and self.active:
            self.active.cancelled = True
            if self.recording:
                self.commands.put_nowait(('cancel', None))
                self.recording = False
        elif ident == 3 and self.active is None and self.pending is None and self.last and self.last.text:
            try:
                retry = Session(self.guard.snapshot(), text=self.last.text, retry_of=self.last)
                retry.stopped = time.perf_counter()
                self.schedule_delivery(retry)
            except Exception as exc:
                print(f'Retry unavailable: {exc}', flush=True)
        elif ident == 5:
            self.save()
        return True

    def run(self):
        bindings = self.bindings
        registered = []
        workers = []
        try:
            self.guard.install()
            for ident, vk in bindings.items():
                if ident == 1 and getattr(self.args,'recording_chord',False):
                    continue  # Modifier-only chords are owned by the ordered hook.
                if not u.RegisterHotKey(None, ident, 0x4003, vk):
                    flag = {1:'toggle',2:'cancel',3:'retry',4:'quit',5:'save'}[ident]
                    raise RuntimeError(f"Shortcut conflict for Ctrl+Alt+VK {vk:#x}. Use --{flag}-vk to change it.")
                registered.append(ident)
            workers = [threading.Thread(target=f, daemon=True) for f in (self.infer, self.capture)]
            for worker in workers:
                worker.start()
            def label(vk):
                return f"F{vk-0x6F}" if 0x70 <= vk <= 0x87 else 'Esc' if vk == 0x1B else chr(vk)
            print(f"LightningFlow {__version__}\nLoading GPU model. Microphone is closed.\n" + " | ".join(
                f"Ctrl+Alt+{label(vk)}: {name}" for vk,name in zip(bindings.values(),['toggle','cancel','retry text','quit','export'])), flush=True)
            msg = W.MSG()
            running = True
            while running:
                self.on_tick()
                while u.PeekMessageW(C.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x312:
                        if not self.handle_hotkey(int(msg.wParam)):
                            running = False
                            break
                    else:
                        u.TranslateMessage(C.byref(msg))
                        u.DispatchMessageW(C.byref(msg))
                while not self.events.empty():
                    event, value = self.events.get_nowait()
                    if event == "ready":
                        self.ready = not self.gpu_error
                        print("READY: " + value, flush=True)
                    elif event == "fatal":
                        print(value, flush=True)
                        return 1
                    elif event == 'gpu_fault':print(value,flush=True)
                    elif event == "done":
                        self.schedule_delivery(value)
                    elif event == "partial":
                        print("PARTIAL: " + value.text, flush=True)
                    elif event == 'capture_stopped':
                        if value is self.active:self.recording=False
                    elif event == 'preview':
                        if value is self.active and not value.capture_until:
                            print('PROVISIONAL: '+value.provisional,flush=True)
                    elif event == "listening":
                        print("RECORDING — microphone on", flush=True)
                    elif event == "notice":
                        self.recording = False
                        print(value, flush=True)
                if running:
                    self.tick_delivery()
                    time.sleep(.001 if getattr(getattr(self,'gesture',None),'state','') in ('armed','held','finishing') else .005)
        except KeyboardInterrupt:
            return 0
        finally:
            self.quit.set()
            if self.active:
                self.active.cancelled = True
            for session in self.sessions:session.cancelled=True
            for ident in registered:
                u.UnregisterHotKey(None, ident)
            self.guard.close()
            for worker in workers:
                worker.join(timeout=2)
        return 0
