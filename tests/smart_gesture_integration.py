"""Real Windows hook edges -> replay capture -> CUDA -> disposable editor.

Only this fixture gets synthetic physical-style shortcut edges. Production has
no replay mode. The GPU model and text-delivery path are unmodified.
"""
import ctypes as C
import json
from pathlib import Path
import sys
import threading
import time
import numpy as np

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'tests'))
import windows_integration as native
from lightningflow import app
from lightningflow.audio import RATE
from lightningflow._vendor.faster_whisper.audio import decode_audio
from lightningflow.desktop import worker
from lightningflow.desktop.state import Preferences, Settings
from lightningflow.win32 import u,k,INPUT,UNION,KEY,read_edit


class ReplayStream:
    samples=None
    offset=0
    def __init__(self,**_): pass
    def start(self): pass
    def close(self): pass
    def read(self,n):
        time.sleep(n/RATE*.15)
        data=self.samples[self.offset:self.offset+n]
        type(self).offset+=n
        return np.pad(data,(0,max(0,n-len(data))))[:,None],False


def run():
    config=root/'.work/smart-gesture/settings.json'
    Preferences(config).save(Settings(activation='smart',shortcuts={'toggle':0x81,'retry':0x82,'cancel':0x83,'quit':0x84,'save':0x85}))
    backend=worker.build_backend(config,root/'models')
    samples=decode_audio(str(root/'benchmarks/synthetic.wav'))
    ReplayStream.samples=samples
    model=app.CudaASR(root/'models/tiny.en','float16')
    original_foreground=u.GetForegroundWindow()
    hwnd=u.CreateWindowExW(0,'EDIT','LightningFlow gesture fixture',0x10CF0000|0xC4|0x1000,100,100,680,180,None,None,k.GetModuleHandleW(None),None)
    assert hwnd
    current=k.GetCurrentThreadId()
    old_thread=u.GetWindowThreadProcessId(original_foreground,None)
    attached=u.AttachThreadInput(current,old_thread,True)
    try:
        u.SetForegroundWindow(hwnd); u.SetFocus(hwnd); native.settle(.15)
    finally:
        if attached: u.AttachThreadInput(current,old_thread,False)
    if '--wait-focus' in sys.argv:
        from lightningflow.win32 import pump
        ready=root/'.work/gesture-fixture-go'
        if ready.exists(): ready.unlink()
        print('WAITING FOR FIXTURE ACTIVATION',flush=True)
        deadline=time.perf_counter()+90
        while not ready.exists() and time.perf_counter()<deadline:
            pump(); time.sleep(.005)
        if ready.exists(): ready.unlink()
    assert u.GetForegroundWindow()==hwnd
    events=[]; errors=[]; results=[]
    old_send=worker.send
    def observe(kind,**data): events.append({'event':kind,'at':time.perf_counter(),**data})
    worker.send=observe
    def keys(vks,release=False):
        if not release: assert u.GetForegroundWindow()==hwnd,'Fixture lost foreground; no keys sent'
        items=[INPUT(1,UNION(ki=KEY(v,0,2 if release else 0,0,0))) for v in vks]
        array=(INPUT*len(items))(*items)
        assert u.SendInput(len(items),array,C.sizeof(INPUT))==len(items)
    def wait(predicate,seconds=20):
        deadline=time.perf_counter()+seconds
        while not predicate():
            if time.perf_counter()>deadline: raise AssertionError('Fixture timed out')
            time.sleep(.003)
    def press(): keys([0x11,0x12,0x81])
    def release(modifiers_first=False): keys([0x12,0x11,0x81] if modifiers_first else [0x81,0x12,0x11],True)
    def tap():
        press(); time.sleep(.05); release()
    def drive():
        try:
            wait(lambda:backend.ready)
            for scenario in ('hold','double_press_lock','modifiers_released_first'):
                ReplayStream.offset=0
                u.SetWindowTextW(hwnd,'')
                began=time.perf_counter()
                offset=len(events)
                if scenario=='double_press_lock':
                    tap(); time.sleep(.06); tap()
                    wait(lambda:backend.gesture.state=='locked')
                    assert backend.recording
                else:
                    press()
                    # Repeated action-key downs while held must not toggle.
                    keys([0x81]); keys([0x81])
                wait(lambda:ReplayStream.offset>=len(samples))
                stopped=time.perf_counter()
                if scenario=='double_press_lock': tap()
                else: release(scenario=='modifiers_released_first')
                wait(lambda:backend.active is None and backend.last is not None)
                session=backend.last
                assert session.delivered,session.delivery_error or session.error
                content=read_edit(hwnd).text
                assert content==session.text and 'project report' in content and 'CUDA' in content,content
                statuses=[e for e in events[offset:] if e['event']=='status']
                starting=next(e for e in statuses if e['state']=='starting')
                results.append({'scenario':scenario,'delivered':True,
                    'shortcut_to_start_signal_ms':(starting['at']-began)*1000,
                    'capture_first_frame_ms':session.metrics.get('capture_first_frame_ms'),
                    'release_to_delivery_ms':(time.perf_counter()-stopped)*1000,
                    'decode_ms':session.decode_ms,'method':session.metrics.get('delivery_method')})
        except Exception as exc: errors.append(str(exc))
        finally:
            try: release()
            finally: backend.external.put({'action':'shutdown'})
    old_stream=app.sd.InputStream; old_options=app.input_options; old_model=app.CudaASR
    app.sd.InputStream=ReplayStream; app.input_options=lambda _:{}; app.CudaASR=lambda *_:model
    thread=threading.Thread(target=drive,daemon=True)
    try:
        thread.start(); code=backend.run(); thread.join(timeout=3)
        assert not thread.is_alive() and code==0 and not errors,errors
        return {'real_hook_gestures':results,'provider':'CUDA / CTranslate2',
                'scope':'Disposable native editor; accelerated PCM replay, not an acoustic microphone benchmark'}
    finally:
        worker.send=old_send
        app.sd.InputStream=old_stream; app.input_options=old_options; app.CudaASR=old_model
        u.DestroyWindow(hwnd)
        if original_foreground: u.SetForegroundWindow(original_foreground)


if __name__=='__main__':
    result=run()
    (root/'results/smart-gestures-0.3.0.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
