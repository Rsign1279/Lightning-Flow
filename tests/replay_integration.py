"""Full app test with real CUDA and real Windows input, replayed audio source.

The capture stream is replaced ONLY inside this test. Production has no fake
engine/device option. This does not claim acoustic microphone ASR validation.
"""
import ctypes as C
from pathlib import Path
import json
import threading
import time
import numpy as np
from lightningflow._vendor.faster_whisper.audio import decode_audio
from lightningflow import app
from lightningflow.cli import parser
from lightningflow.audio import RATE, BLOCK
from lightningflow.win32 import u, k, send_virtual_keys, pump
import windows_integration as native

class ReplayStream:
    samples = None
    def __init__(self, **kwargs):
        self.offset = 0
    def start(self):
        pass
    def read(self, frames):
        time.sleep(frames/RATE*.15)
        data = self.samples[self.offset:self.offset+frames]
        self.offset += frames
        return np.pad(data,(0,max(0,frames-len(data))))[:,None], False
    def close(self):
        pass

def run():
    audio = decode_audio("benchmarks/synthetic.wav",sampling_rate=RATE)
    ReplayStream.samples = audio
    # Finish slow GPU initialization before briefly opening the test window.
    real_engine = app.CudaASR(Path("models/tiny.en"), "float16")
    original = u.GetForegroundWindow()
    hwnd = u.CreateWindowExW(0,"EDIT","",0x10CF0000|0xC4|0x1000,100,100,640,160,None,None,k.GetModuleHandleW(None),None)
    assert hwnd
    current = k.GetCurrentThreadId()
    foreground = u.GetWindowThreadProcessId(original,None)
    attached = u.AttachThreadInput(current,foreground,True)
    try:
        u.SetForegroundWindow(hwnd)
        u.SetFocus(hwnd)
        native.settle(.2)
    finally:
        if attached:
            u.AttachThreadInput(current,foreground,False)
    native.settle()
    assert u.GetForegroundWindow()==hwnd, f"Fixture {hwnd} must own foreground ({u.GetForegroundWindow()}) before sending keys"
    # Do not conflict with the user's running LightningFlow instance.
    instance = app.Dictation(parser().parse_args(['run', '--toggle-vk','0x81',
        '--retry-vk','0x82','--cancel-vk','0x83','--quit-vk','0x84','--save-vk','0x85']))
    errors=[]
    outcome={}
    original_insert = instance.guard.insert
    def observed_insert(text,target):
        from dataclasses import asdict
        outcome["target_at_start"]=asdict(target)
        outcome["target_at_delivery"]=asdict(instance.guard.snapshot())
        return original_insert(text,target)
    instance.guard.insert=observed_insert
    def drive():
        try:
            deadline=time.perf_counter()+45
            while not instance.ready:
                if time.perf_counter()>deadline:
                    raise RuntimeError("CUDA worker never became ready")
                time.sleep(.01)
            send_virtual_keys([0x11,0x12,0x81])
            time.sleep(len(audio)/RATE*.15+.3)
            stop=time.perf_counter()
            send_virtual_keys([0x11,0x12,0x81])
            deadline=time.perf_counter()+20
            while instance.last is None or instance.active is not None:
                if time.perf_counter()>deadline:
                    raise RuntimeError("App did not finish replay dictation")
                time.sleep(.005)
            content=C.create_unicode_buffer(2048)
            while time.perf_counter()<deadline:
                u.GetWindowTextW(hwnd,content,2048)
                if instance.last.text and content.value==instance.last.text:
                    break
                time.sleep(.005)
            assert content.value==instance.last.text and content.value, f"Incomplete insertion: {content.value!r}"
            session=instance.last
            outcome.update({"hotkey_to_replay_capture_to_cuda_to_input":True,
                "source":"Accelerated (0.15x wall time) replay of local SAPI fixture, NOT physical microphone speech; not a microphone latency benchmark",
                "inserted_text":content.value,
                "stop_hotkey_to_observed_text_ms":(time.perf_counter()-stop)*1000,
                "first_partial_ms":(session.first_partial-session.began)*1000,
                "asr_decode_ms":session.decode_ms,
                "provider":"CUDA / CTranslate2"})
        except Exception as exc:
            errors.append(str(exc))
        finally:
            send_virtual_keys([0x11,0x12,0x84])
    real_stream=app.sd.InputStream
    real_options=app.input_options
    real_constructor=app.CudaASR
    app.sd.InputStream=ReplayStream
    app.input_options=lambda _: {}
    app.CudaASR=lambda *_: real_engine
    driver=threading.Thread(target=drive,daemon=True)
    try:
        driver.start()
        code=instance.run()
        driver.join(timeout=2)
        if errors:
            Path("results/replay-failure.json").write_text(json.dumps({"errors":errors,**outcome},indent=2))
        assert code==0 and not errors, errors
        return outcome
    finally:
        app.sd.InputStream=real_stream
        app.input_options=real_options
        app.CudaASR=real_constructor
        u.DestroyWindow(hwnd)
        u.SetForegroundWindow(original)

if __name__=="__main__":
    result=run()
    Path("results/replay-integration-0.1.1.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
