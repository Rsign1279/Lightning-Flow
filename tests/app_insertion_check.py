"""Real app delivery fixture; UI setup/observation is done by Computer Use.

No OS shortcut injection or microphone capture. Only whitelisted disposable
editors may receive the production dictation delivery path.
"""
import ctypes as C
from dataclasses import asdict
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import numpy as np
import customtkinter as ctk

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,os.environ.get('LIGHTNINGFLOW_TEST_ENGINE',str(root)))
from lightningflow import app
from lightningflow.desktop import worker
from lightningflow.desktop.state import Preferences,Settings
from lightningflow.desktop.widgets import RecordingOverlay
from lightningflow._vendor.faster_whisper.audio import decode_audio
from lightningflow.win32 import read_edit,expected_text,class_name
from lightningflow import accessibility

original_read=accessibility._read
provider_seen=set()
def inspect_provider(automation,module):
    value=original_read(automation,module)
    key=(value.text,value.start,value.end)
    if value.text.startswith('LF_') and key not in provider_seen:
        provider_seen.add(key)
        element=automation.GetFocusedElement()
        pattern=element.GetCurrentPattern(10014).QueryInterface(module.IUIAutomationTextPattern)
        doc=pattern.DocumentRange;sel=pattern.GetSelection().GetElement(0)
        detail={'framework':element.CurrentFrameworkId,'start_vs_doc_end':sel.CompareEndpoints(0,doc,1),
                'end_vs_doc_end':sel.CompareEndpoints(1,doc,1),'text_tail':value.text[-20:],'start':value.start,'length':len(value.text)}
        try:
            val=element.GetCurrentPattern(10002).QueryInterface(module.IUIAutomationValuePattern).CurrentValue
            detail['value_tail']=val[-20:];detail['value_length']=len(val)
        except Exception as exc:detail['value_error']=str(exc)[:120]
        worker.send('test_provider',**detail)
    return value
accessibility._read=inspect_provider

directory=root/'.work/app-insertion-check'
events=queue.Queue();controls=queue.Queue();finished=threading.Event()
worker.send=lambda kind,**data:events.put({'event':kind,**data})
settings=Preferences(Path(os.environ['LOCALAPPDATA'])/'LightningFlow/settings.json').load()
settings.shortcuts={'toggle':0x83,'cancel':0x84,'retry':0x85,'quit':0x86,'save':0x87}
Preferences(directory/'settings.json').save(settings)

class Replay:
    samples=decode_audio(str(root/'benchmarks/synthetic.wav'));offset=0
    def __init__(self,**_):pass
    def start(self):pass
    def close(self):pass
    def read(self,n):
        time.sleep(n/16000*.15)
        value=self.samples[type(self).offset:type(self).offset+n];type(self).offset+=n
        return np.pad(value,(0,max(0,n-len(value))))[:,None],False
app.sd.InputStream=Replay;app.input_options=lambda _:{}

def backend():
    engine=worker.build_backend(directory/'settings.json',Path(settings.models_dir))
    original_insert=engine.guard.insert
    def inspect_insert(text,target):
        try:return original_insert(text,target)
        except Exception:
            if target and target.native:
                after=read_edit(target.focus)
                worker.send('test_native_diagnostic',window_class=class_name(target.focus),
                    before=target.state.__dict__,after=after.__dict__,expected=expected_text(target.state,text))
            elif target:
                try:
                    after=engine.guard.probe.read(service=engine.guard.service_callbacks)
                    worker.send('test_accessible_diagnostic',before=target.state.__dict__,after=after.__dict__,expected=expected_text(target.state,text))
                except Exception as exc:worker.send('test_accessible_diagnostic',error=str(exc))
            raise
    engine.guard.insert=inspect_insert
    normal=engine.on_tick;case=None
    def key(vk,down):engine.guard.key_event(vk,down)
    def tick():
        nonlocal case
        normal()
        if case:
            case['focus_samples']+=1
            if app.u.GetForegroundWindow()!=case['foreground']:case['focus_changes']+=1
            if engine.recording and Replay.offset>=len(Replay.samples)+1600 and time.perf_counter()-case['started']>.25:
                case['stop_at']=time.perf_counter()
                if case['mode']=='hold':key(0x5B,False);key(0xA2,False)
                else:key(0xA2,True);key(0x5B,True);key(0x5B,False);key(0xA2,False)
            if case.get('stop_at') and engine.active is None:
                worker.send('test_focus',app=case['app'],mode=case['mode'],samples=case['focus_samples'],
                    changes=case['focus_changes'],foreground_preserved=app.u.GetForegroundWindow()==case['foreground'])
                case=None
        try:command=controls.get_nowait()
        except queue.Empty:return
        if command['action']=='shutdown':engine.external.put(command);return
        if case or engine.active or not engine.ready:
            worker.send('test_error',message='Test worker busy/not ready');return
        name=command['app'];mode=command['mode']
        expected={'Notepad':('LightningFlow-Notepad-check','LF_NOTEPAD_TEST'),
                  'Chrome':('LightningFlow Chrome insertion test','LF_CHROME_TEST'),
                  'VSCode':('LightningFlow-VSCode-check','LF_VSCODE_TEST')}
        try:
            title,marker=expected[name]
            identity=engine.guard.identity()
            buffer=C.create_unicode_buffer(1024);app.u.GetWindowTextW(identity.foreground,buffer,len(buffer))
            if title not in buffer.value:raise RuntimeError('Disposable test window is not foreground')
            target=engine.guard.snapshot()
            if not target.state.text.startswith(marker):raise RuntimeError('Test marker missing; insertion refused')
            if target.state.start!=target.state.end:raise RuntimeError('Selection is not empty; insertion refused')
            Replay.offset=0
            case={'app':name,'mode':mode,'foreground':identity.foreground,'started':time.perf_counter(),
                  'focus_samples':0,'focus_changes':0}
            worker.send('test_begin',app=name,mode=mode)
            key(0xA2,True);key(0x5B,True)
            if mode=='locked':
                key(0x5B,False);key(0x5B,True);key(0x5B,False);key(0xA2,False)
                assert engine.gesture.state=='locked'
        except Exception as exc:
            case=None;worker.send('test_error',app=name,mode=mode,message=str(exc))
    engine.on_tick=tick
    try:engine.run()
    except Exception as exc:worker.send('test_error',message=str(exc))
    finally:finished.set()

ctk.set_appearance_mode(settings.theme)
ui=ctk.CTk();ui.withdraw();overlay=RecordingOverlay(ui)
history=[];last_stamp=0;deadline=time.perf_counter()+600
def poll():
    global last_stamp
    path=directory/'command.json'
    if path.exists() and path.stat().st_mtime_ns!=last_stamp:
        try:command=json.loads(path.read_text());last_stamp=path.stat().st_mtime_ns;controls.put(command)
        except (ValueError,OSError):pass
    while True:
        try:event=events.get_nowait()
        except queue.Empty:break
        kind=event['event']
        if kind=='status':
            state=event['state']
            if event.get('gesture'):overlay.set_gesture(event['gesture'])
            if state in ('starting','recording','paused','processing','enhancing'):overlay.show_state(state,'Ctrl + Win')
            else:overlay.hide()
        elif kind=='level':overlay.wave.set(event['level'],True)
        elif kind=='gesture':overlay.set_gesture(event['state'])
        if kind not in ('level','partial','hardware','devices'):
            history.append(event)
            (directory/'events.json').write_text(json.dumps(history,indent=2))
            print(json.dumps(event),flush=True)
    if finished.is_set():overlay.destroy();ui.destroy();return
    if time.perf_counter()>deadline:controls.put({'action':'shutdown'})
    ui.after(8,poll)
thread=threading.Thread(target=backend,daemon=True);thread.start()
ui.after(8,poll)
ui.mainloop();thread.join(5)
