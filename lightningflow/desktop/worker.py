"""Headless local engine. Stdout is JSON IPC, never a network service."""
import argparse
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import uuid

from .state import Preferences, Settings, MODELS
from .personalization import hint_text, prepare_transcript

_output=sys.stdout
_lock=threading.Lock()

def send(kind,**data):
    with _lock:
        _output.write(json.dumps({'event':kind,**data},ensure_ascii=True)+'\n')
        _output.flush()

class QuietOutput(io.TextIOBase):
    def write(self,text): return len(text)
    def flush(self): pass

def hardware():
    import platform
    import psutil
    from ..asr import gpu_snapshot
    process=psutil.Process()
    controller_rss=process.memory_info().rss
    engine_rss=controller_rss
    for child in process.children(recursive=True):
        try:engine_rss+=child.memory_info().rss
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    cpu=platform.processor()
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            cpu=winreg.QueryValueEx(key,'ProcessorNameString')[0].strip()
    except OSError: pass
    send('hardware',gpu=gpu_snapshot(),cpu=cpu,ram_gib=round(psutil.virtual_memory().total/1024**3,1),
         engine_ram_mib=round(engine_rss/1024**2,1),controller_ram_mib=round(controller_rss/1024**2,1),engine_pid=process.pid)

def devices():
    import sounddevice as sd
    rows=[]
    for index,item in enumerate(sd.query_devices()):
        if item['max_input_channels']:
            api=sd.query_hostapis(item['hostapi'])['name']
            if api=='Windows WASAPI': rows.append({'id':index,'name':item['name'],'api':api})
    if not rows:
        rows=[{'id':i,'name':d['name'],'api':sd.query_hostapis(d['hostapi'])['name']}
              for i,d in enumerate(sd.query_devices()) if d['max_input_channels']]
    send('devices',devices=rows)

def build_backend(settings_path,models):
    import ctypes as C
    from ctypes import wintypes as W
    import numpy as np
    from ..app import Dictation, Session
    from ..audio import BLOCK, RATE, input_options
    from ..cli import parser
    from ..win32 import k,u
    from .cleanup import enhance
    from .gestures import RecordingGesture,HoldToTalkGesture

    class MeterFrames(list):
        def __init__(self):
            super().__init__()
            self.last=0
        def append(self,frame):
            super().append(frame)
            now=time.perf_counter()
            if now-self.last>=.018:
                self.last=now
                level=float(np.sqrt(np.mean(frame*frame)))
                send('level',level=min(1.,level*12),seconds=len(self)*BLOCK/RATE)

    class DesktopBackend(Dictation):
        def __init__(self):
            self.preferences=Preferences(settings_path)
            self.settings=self.preferences.load()
            self.asr_hint=hint_text(self.settings.voice_profile,self.settings.dictionary) if self.settings.personalization_enabled else ''
            args=parser().parse_args(['--models',str(models),'run','--model',self.settings.model,'--compute',self.settings.compute])
            args.device=self.settings.device
            args.language=self.settings.language
            args.max_seconds=self.settings.max_seconds
            args.recording_chord=self.settings.recording_shortcut=='ctrl_win'
            args.recovery=str(Path(settings_path).parent/'recovery')
            for name,value in self.settings.shortcuts.items(): setattr(args,name+'_vk',value)
            super().__init__(args)
            self.external=queue.Queue(maxsize=64)
            self.failed={}
            from .recovery import RecoveryWorker
            self.recovery=RecoveryWorker(Path(settings_path).parent/'recovery-audio')
            self.recovery_requests={}
            self.cleanup_result=queue.Queue(maxsize=1)
            self.cleanup_pending=None
            self.cleanup_busy=threading.Event()
            self.cleanup_completed=[]
            self.mic_cancel=threading.Event()
            self.mic_testing=False
            self.thread_id=k.GetCurrentThreadId()
            self.guard.on_key_up=self.key_up
            self.guard.on_key_down=self.key_down
            if args.recording_chord:
                from .chords import ControlWindowsChord
                self.guard.recording_chord=ControlWindowsChord()
                self.guard.on_recording_chord=self.recording_edge
            self.gesture_mode=self.settings.activation
            self.gesture=HoldToTalkGesture() if self.gesture_mode=='hold' else RecordingGesture()
            self.target_pending=None
            u.PostThreadMessageW.argtypes=[W.DWORD,W.UINT,W.WPARAM,W.LPARAM]

        def new_session(self,target):
            session=Session(target,raw=MeterFrames())
            session.ident=uuid.uuid4().hex
            session.destination='external'
            session.raw_text=''
            session.processing_settings=Settings(**asdict(self.settings))
            session.asr_prompt=self.asr_hint
            return session

        def emit(self,event,value=None):
            super().emit(event,value)
            if event=='ready' and self.settings.retain_failed_audio:self.recovery.submit('inventory')
            if event=='ready': send('status',state='ready',message='Ready to record',
                                    detail=value,model=self.args.model,provider='CUDA / CTranslate2')
            elif event=='fatal': send('status',state='error',message=str(value))
            elif event=='gpu_fault':send('status',state='error',message=str(value))
            elif event=='listening' and value is self.active and not self.gpu_error:
                state=self.gesture.state
                if state=='finishing': return
                send('status',state='paused' if state=='waiting' else 'recording',
                     message='Tap again to keep recording' if state=='waiting' else 'Listening',gesture=state)
            elif event=='partial' and value is self.active: send('partial',text=value.text)
            elif event=='preview' and value is self.active and not value.capture_until:
                send('partial',text=value.provisional,provisional=True)
            elif event=='notice':
                send('notice',message=str(value))

        def handle_hotkey(self,ident):
            if ident==1 and self.args.recording_chord: return True
            if ident==1 and self.settings.activation in ('smart','hold'):
                # The ordered hook edges own this gesture. WM_HOTKEY only
                # reserves the shortcut and detects conflicts with other apps.
                return True
            if ident==2: self.gesture.reset()
            if ident==1 and self.mic_testing:
                send('notice',message='Finish the microphone test before dictating.')
                return True
            before=self.active
            was_recording=self.recording
            requested=time.perf_counter()
            result=super().handle_hotkey(ident)
            if self.active is not None and before is not self.active:
                send('status',state='starting',message='Opening microphone…',destination='external')
                send('partial',text='')
            elif ident==1 and was_recording and not self.recording:
                if self.active: self.active.requested_stop=requested
                send('status',state='processing',message='Finishing your transcript…')
            return result

        def key_down(self,vk,chord):
            if self.args.recording_chord: return
            if self.settings.activation in ('smart','hold') and vk==self.args.toggle_vk and chord:
                if self.gesture.state=='idle' and (not self.can_start_recording() or self.mic_testing):
                    return
                self.gesture_actions(self.gesture.press(time.perf_counter()))

        def recording_edge(self,edge):
            if edge=='press':
                if self.gesture.state=='idle' and (not self.can_start_recording() or self.mic_testing):
                    send('notice',message='The dictation queue is busy. Wait for a result before starting another recording.')
                    return
                if self.settings.activation=='toggle':
                    before=self.recording
                    super().handle_hotkey(1)
                    if before and not self.recording and self.active:
                        self.active.capture_until=time.perf_counter()
                        send('status',state='processing',message='Transcribing…')
                    elif self.recording:
                        send('status',state='starting',message='Opening microphone…',gesture='locked')
                else: self.gesture_actions(self.gesture.press(time.perf_counter()))
            elif self.settings.activation!='toggle':
                self.gesture_actions(self.gesture.release(time.perf_counter()))

        def gesture_actions(self,actions):
            for action in actions:
                if action=='start':
                    if not self.can_start_recording():
                        self.gesture.reset()
                        return
                    requested=time.perf_counter()
                    send('status',state='starting',message='Opening microphone…',gesture='held')
                    send('partial',text='')
                    try:
                        identity=self.guard.identity()
                        self.guard.watched=identity
                        self.guard.watch_time=k.GetTickCount()
                    except RuntimeError: identity=None
                    session=self.new_session(None)
                    session.hotkey_at=requested
                    self.active=session
                    self.register_session(session)
                    self.recording=True
                    self.commands.put_nowait(('start',session))
                    # Capture starts independently of a potentially slow
                    # accessibility provider. No UIA call runs inside a hook.
                    if self.target_pending is None:self.target_pending=[]
                    self.target_pending.append((session,identity))
                elif action in ('pause','resume') and self.active is not None:
                    self.active.capture_paused_at=time.perf_counter() if action=='pause' else 0.
                    self.commands.put_nowait((action,None))
                    send('status',state='paused' if action=='pause' else 'recording',
                         message='Tap again to keep recording' if action=='pause' else 'Recording locked',
                         gesture='waiting' if action=='pause' else 'locked')
                elif action=='locked':
                    send('gesture',state='locked')
                elif action=='stop' and self.active is not None and self.recording:
                    self.active.requested_stop=time.perf_counter()
                    self.active.capture_until=self.active.requested_stop
                    self.commands.put_nowait(('stop',None))
                    self.recording=False
                    self.gesture.reset()
                    send('status',state='processing',message='Transcribing…')

        def key_up(self,vk):
            if self.args.recording_chord: return
            if self.settings.activation in ('smart','hold'):
                # Releasing any part of the chord also ends a hold. This
                # avoids a stuck recording when modifiers are released first.
                if vk in (self.args.toggle_vk,0x11,0x12,0xA2,0xA3,0xA4,0xA5):
                    self.gesture_actions(self.gesture.release(time.perf_counter()))
                return

        def schedule_delivery(self,session):
            if not getattr(session,'prepared',False) and not session.cancelled and not session.error:
                settings=getattr(session,'processing_settings',self.settings)
                session.prepared=True
                session.raw_text=getattr(session.retry_of,'raw_text',session.text) if session.retry_of else session.text
                if not session.retry_of:
                    session.text=prepare_transcript(session.text,settings)
                session.cleanup_note='Verbatim mode' if settings.transcript_style=='Verbatim' else 'Conservative local cleanup'
                if settings.transcript_style=='Clean' and settings.cleanup_mode!='Raw' and settings.cleanup_model and session.text and not session.retry_of:
                    if self.cleanup_busy.is_set():
                        session.cleanup_note='Local AI is busy; raw transcript kept'
                    else:
                        self.cleanup_busy.set()
                        if settings.wait_for_cleanup:
                            self.cleanup_pending=(session,time.perf_counter()+settings.cleanup_budget_ms/1000)
                        else:
                            session.cleanup_background=True
                            session.cleanup_note='Delivered immediately; local AI suggestion follows in the log'
                        if self.active is session:self.recording=False
                        if settings.wait_for_cleanup and not self.recording:
                            send('status',state='enhancing',message='Cleaning up locally. Raw text is ready.')
                            send('partial',text=session.text)
                        snapshot=Settings(**asdict(settings))
                        def clean():
                            try: answer,note=enhance(session.text,snapshot)
                            except Exception: answer,note=session.text,'Local cleanup unavailable; raw transcript kept'
                            try: self.cleanup_result.put_nowait((session,answer,note))
                            except queue.Full: pass
                            self.cleanup_busy.clear()
                        threading.Thread(target=clean,daemon=True).start()
                        if settings.wait_for_cleanup:return
            super().schedule_delivery(session)

        def _deliver(self,session,source):
            if self.active is session and not self.recording:self.gesture.reset()
            seconds=len(source.raw)*BLOCK/RATE
            if getattr(session,'destination','external')=='scratchpad' and not session.cancelled and not session.error and not session.capture_warning:
                session.delivered=source.delivered=True
                session.metrics={'provider':'CUDA / CTranslate2','decode_ms':session.decode_ms,
                    'audio_seconds':seconds,'stop_to_input_ms':(time.perf_counter()-session.stopped)*1000,
                    'delivery_method':'In-app scratchpad'}
                source.raw.clear()
            else:
                super()._deliver(session,source)
            if session.delivered and getattr(source,'requested_stop',0):
                session.metrics['end_to_end_finish_ms']=(time.perf_counter()-source.requested_stop)*1000
            if 'Clipboard restoration was blocked' in session.metrics.get('delivery_method',''):
                send('notice',message='Text delivered. Clipboard restoration was blocked; the clipboard may contain this transcript.')
            if session.cancelled:
                if not self.recording:
                    send('cancelled')
                    send('status',state='ready' if self.ready else 'error',message='Recording cancelled.')
                return
            ident=getattr(source,'ident',uuid.uuid4().hex)
            error=session.error or session.delivery_error
            if not session.delivered and source.raw:
                self.failed[ident]=source
                while len(self.failed)>5:
                    expired=next(iter(self.failed));self.failed.pop(expired)
                    if not self.settings.retain_failed_audio:
                        send('recovery_removed',ids=[expired])
                        send('notice',message='The oldest failed audio left the five-recording memory buffer. Its transcript remains in the log.')
            elif session.delivered:
                self.failed.pop(ident,None)
                if self.settings.retain_failed_audio:self.recovery.submit('remove',ident)
            row=dict(id=ident,text=session.text,raw=getattr(session,'raw_text',session.text),
                 delivered=session.delivered,destination=getattr(session,'destination','external'),
                 error=error,metrics=session.metrics,seconds=seconds,cleanup=getattr(session,'cleanup_note','Raw mode'),
                 audio_available=ident in self.failed,recording_in_progress=self.recording)
            send('result',**row)
            if not session.delivered and source.raw and self.settings.retain_failed_audio:
                if not self.recovery.submit('save',ident,list(source.raw),row):
                    send('notice',message='Recovery storage is busy. Audio remains in memory; export it before quitting.')
            session.result_emitted=True
            if self.recording:
                send('status',state='recording' if self.active.first_audio else 'starting',message='Recording the next dictation',gesture=self.gesture.state)
            elif len(self.sessions)>1:send('status',state='processing',message='Finishing queued dictations')
            else:
                send('status',state='ready' if self.ready else 'error',message=self.gpu_error or ('Ready to record' if session.delivered else
                     'No speech detected. Check your microphone or try again.' if not session.text else 'Transcript retained. Check the target before retrying.')
                     )

        def microphone_test(self):
            import sounddevice as sd
            self.mic_testing=True
            self.mic_cancel.clear()
            started=time.perf_counter()
            first=None
            peak=0.
            overflow_count=0
            try:
                with sd.InputStream(**input_options(self.settings.device),samplerate=RATE,channels=1,
                                    dtype='float32',blocksize=BLOCK,latency='low') as stream:
                    for n in range(250):
                        if self.mic_cancel.is_set() or self.quit.is_set(): break
                        frame,overflow=stream.read(BLOCK)
                        first=first or time.perf_counter()
                        level=float(np.sqrt(np.mean(frame*frame)))
                        peak=max(peak,float(np.max(np.abs(frame))))
                        overflow_count+=bool(overflow)
                        if n%4==0: send('mic_level',level=min(1.,level*12))
                send('mic_test',ok=True,first_frame_ms=round((first-started)*1000,1) if first else None,
                     peak=peak,overflows=overflow_count,message='Microphone test finished. No audio saved.')
            except Exception as exc: send('mic_test',ok=False,message=str(exc))
            finally:
                self.mic_testing=False
                send('mic_level',level=0)

        def on_tick(self):
            was_recording=self.recording
            super().on_tick()
            if self.gpu_error and was_recording:self.gesture.reset()
            for _ in range(8):
                try:generation,kind,value=self.recovery.results.get_nowait()
                except queue.Empty:break
                if generation!=self.recovery.generation:continue
                if kind=='error':
                    self.recovery_requests.clear()
                    send('notice',message='Recovery audio could not be processed: '+value+'. Existing files were kept where possible.')
                elif kind=='inventory':
                    rows,errors=value
                    send('recovered',rows=[dict(item['row'],audio_available=True) for item in rows])
                    if errors:send('notice',message=f'{len(errors)} retained recordings could not be read. Their files were kept.')
                elif kind=='saved' and value['evicted']:
                    send('recovery_removed',ids=value['evicted'])
                    send('notice',message='Old recovery audio was removed to enforce the five-recording / 1 GiB limit.')
                elif kind=='loaded':
                    ident,frames,row=value;action=self.recovery_requests.pop(ident,None)
                    if action:
                        source=self.new_session(None);source.ident=ident;source.raw=frames;source.text=row.get('text','')
                        self.failed[ident]=source
                        self.use_retained_audio(action,source)
            if self.active is not None and self.active.stopped and self.recording:
                self.recording=False;self.gesture.reset()
                send('status',state='processing',message='Recovering captured speech after microphone interruption' if self.active.capture_warning else 'Transcribing captured speech')
            if self.gesture_mode!=self.settings.activation and self.active is None:
                self.gesture_mode=self.settings.activation
                self.gesture=HoldToTalkGesture() if self.gesture_mode=='hold' else RecordingGesture()
            self.gesture_actions(self.gesture.tick(time.perf_counter()))
            if self.target_pending:
                pending=self.target_pending
                self.target_pending=None
                for session,identity in pending:
                    if identity is None or not any(item is session for item in self.sessions) or session.cancelled:continue
                    try:
                        target=self.guard.snapshot(track=False)
                        if (target.foreground,target.focus,target.process,target.epoch)==(
                                identity.foreground,identity.focus,identity.process,identity.epoch):
                            session.target=target
                        else: raise RuntimeError('Focus changed before the target could be verified')
                    except RuntimeError as exc:
                        send('notice',message=str(exc)+'. Transcript will remain available in the app.')
            answer=None
            try:
                completed=self.cleanup_result.get_nowait()
                if getattr(completed[0],'cleanup_background',False):self.cleanup_completed.append(completed)
                elif self.cleanup_pending and completed[0] is self.cleanup_pending[0]:answer=completed[1:]
            except queue.Empty:pass
            waiting=[]
            for old,text,note in self.cleanup_completed:
                if getattr(old,'result_emitted',False):
                    if not old.cancelled and text!=old.text:
                        send('suggestion',id=old.ident,text=text,note=note)
                else:waiting.append((old,text,note))
            self.cleanup_completed=waiting[-8:]
            if self.cleanup_pending:
                session,deadline=self.cleanup_pending
                if answer or session.cancelled or time.perf_counter()>=deadline:
                    self.cleanup_pending=None
                    if answer: session.text,session.cleanup_note=answer
                    else: session.cleanup_note='Cleanup exceeded its latency budget; raw transcript kept'
                    super().schedule_delivery(session)
            for _ in range(8):
                try: command=self.external.get_nowait()
                except queue.Empty: break
                action=command.get('action')
                if action=='shutdown':
                    self.mic_cancel.set()
                    u.PostThreadMessageW(self.thread_id,0x312,4,0)
                elif action=='configure':
                    retained_before=self.settings.retain_failed_audio
                    self.settings=self.preferences.load()
                    if retained_before and not self.settings.retain_failed_audio:
                        self.recovery.clear()
                        send('notice',message='Encrypted recovery files are being deleted. Failed audio in memory remains available until exit.')
                    self.asr_hint=hint_text(self.settings.voice_profile,self.settings.dictionary) if self.settings.personalization_enabled else ''
                elif action=='sandbox':
                    if self.ready and self.active is None and not self.mic_testing:
                        session=self.new_session(None)
                        session.destination='scratchpad'
                        self.active=session
                        self.register_session(session)
                        self.commands.put_nowait(('start',session))
                        self.recording=True
                        send('partial',text='')
                        send('status',state='starting',message='Opening microphone…',destination='scratchpad')
                elif action=='stop':
                    if self.recording:
                        self.gesture.state='finishing'
                        self.active.requested_stop=command.get('requested_at',time.perf_counter())
                        self.active.capture_until=self.active.requested_stop
                        self.commands.put_nowait(('stop',None)); self.recording=False
                        send('status',state='processing',message='Finishing your transcript…')
                elif action=='cancel':
                    self.gesture.reset()
                    self.handle_hotkey(2)
                    self.mic_cancel.set()
                elif action=='retry': self.handle_hotkey(3)
                elif action=='forget':
                    self.failed.clear()
                    self.last=None
                    self.recovery_requests.clear();self.recovery.clear()
                elif action in ('export_audio','retranscribe'):
                    session=self.failed.get(command.get('id'))
                    if session:self.use_retained_audio(action,session)
                    elif self.settings.retain_failed_audio:
                        ident=command.get('id')
                        if self.recovery.submit('load',ident):self.recovery_requests[ident]=action
                        else:send('notice',message='Recovery is busy. Try again shortly.')
                    else:send('notice',message='Audio is no longer held. Export the transcript from history.')
                elif action=='devices': threading.Thread(target=devices,daemon=True).start()
                elif action=='hardware': threading.Thread(target=hardware,daemon=True).start()
                elif action=='mic_test' and self.active is None and not self.mic_testing:
                    threading.Thread(target=self.microphone_test,daemon=True).start()

        def use_retained_audio(self,action,source):
            if action=='export_audio':
                # Explicit export is plaintext; run its disk work off the hook.
                frames=list(source.raw);text=source.text
                def export():
                    import wave
                    try:
                        folder=Path(self.args.recovery)/source.ident;folder.mkdir(parents=True,exist_ok=True)
                        (folder/'transcript.txt').write_text(text,encoding='utf-8')
                        with wave.open(str(folder/'recording.wav'),'wb') as wav:
                            wav.setparams((1,2,RATE,0,'NONE','not compressed'))
                            for frame in frames:wav.writeframesraw((np.clip(frame,-1,1)*32767).astype('<i2').tobytes())
                        send('notice',message=f'Audio and transcript exported to {folder}')
                    except Exception as exc:send('notice',message='Audio export failed: '+str(exc))
                threading.Thread(target=export,daemon=True).start()
                return
            if not self.can_start_recording() or self.sessions or self.mic_testing:
                send('notice',message='Finish current dictations before retranscribing retained audio.');return
            session=self.new_session(None);session.ident=source.ident;session.destination='scratchpad';session.raw=list(source.raw)
            session.stopped=time.perf_counter();self.active=session;self.register_session(session)
            send('status',state='processing',message='Retranscribing retained audio on the resident GPU')
            def replay():
                from ..audio import Segmenter
                segmenter=Segmenter()
                try:
                    def put(kind,chunk=None):
                        while not self.quit.is_set():
                            try:self.jobs.put((kind,session,chunk),timeout=.1);return
                            except queue.Full:pass
                    for frame in session.raw:
                        if self.quit.is_set() or session.cancelled:break
                        chunk=segmenter.feed(frame)
                        if chunk is not None:put('chunk',chunk)
                    chunk=segmenter.flush()
                    if chunk is not None:put('chunk',chunk)
                except Exception as exc:session.error='Retained audio could not be prepared: '+str(exc)
                finally:put('finish')
            threading.Thread(target=replay,daemon=True).start()

    return DesktopBackend()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--settings',required=True)
    parser.add_argument('--models',required=True)
    parser.add_argument('--task',choices=['engine','download','verify'],default='engine')
    parser.add_argument('--model',default='tiny.en')
    args=parser.parse_args()
    sys.stdout=QuietOutput()
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    if args.task!='download': os.environ['HF_HUB_OFFLINE']='1'
    else: os.environ.pop('HF_HUB_OFFLINE',None)
    try:
        if args.task=='download':
            if args.model not in MODELS: raise ValueError('Unknown model')
            from ..asr import prepare
            prepare(args.model,args.models)
            send('task_done',task='download',model=args.model,message='Model downloaded and local hashes recorded.')
            return 0
        if args.task=='verify':
            root=Path(args.models)/args.model
            manifest=json.loads((root/'sha256.json').read_text())
            for name,digest in manifest.items():
                with (root/name).open('rb') as stream:
                    if hashlib.file_digest(stream,'sha256').hexdigest()!=digest: raise RuntimeError(f'Hash mismatch: {name}')
            send('task_done',task='verify',model=args.model,message='Local model hashes match. This is not an independent publisher checksum.')
            return 0
        engine=build_backend(args.settings,args.models)
        def read():
            for line in sys.stdin:
                try: engine.external.put(json.loads(line),timeout=.5)
                except (ValueError,queue.Full): send('notice',message='An engine command could not be queued.')
            try: engine.external.put({'action':'shutdown'},timeout=.5)
            except queue.Full: pass
        threading.Thread(target=read,daemon=True).start()
        threading.Thread(target=devices,daemon=True).start()
        threading.Thread(target=hardware,daemon=True).start()
        send('status',state='loading',message='Loading your speech model onto the GPU…')
        return engine.run()
    except Exception as exc:
        message=str(exc)
        if 'Shortcut conflict' in message:
            import re
            from .state import key_label
            match=re.search(r'0x[0-9a-f]+',message)
            chord='Ctrl + Alt + '+key_label(int(match[0],16)) if match else 'A global shortcut'
            send('status',state='error',message=chord+' is already in use. Quit the older dictation instance or choose another key in Shortcuts.',detail=message)
        else: send('status',state='error',message=message)
        return 1
    finally: send('engine_exit',task=args.task)

if __name__=='__main__': raise SystemExit(main())
