"""Real cross-process UIA/Unicode delivery and hung-target timeout tests.

Forces the accessibility route on our disposable native provider so the
transport/readback is exercised without manipulating a user-owned app.
"""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psutil
from tests import windows_integration as native
import lightningflow.win32 as win
import lightningflow.accessibility as accessibility
from lightningflow.win32 import u, k, InputGuard, read_edit

def run():
    if '--require-idle' in sys.argv:
        class LastInput(C.Structure):_fields_=[('size',W.UINT),('tick',W.DWORD)]
        info=LastInput(C.sizeof(LastInput),0);deadline=time.perf_counter()+45
        while True:
            if u.GetLastInputInfo(C.byref(info)) and ((k.GetTickCount()-info.tick)&0xffffffff)>4000:break
            if time.perf_counter()>deadline:raise RuntimeError('Desktop stayed active; interactive fixture was not opened')
            time.sleep(.1)
    original=u.GetForegroundWindow()
    child=subprocess.Popen([sys.executable,'tests/editor_host.py'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                           text=True,creationflags=0x08000000)
    guard=InputGuard([])
    original_native=win.native_editor
    original_read=accessibility._read
    def diagnostic_read(automation,module):
        try:return original_read(automation,module)
        except RuntimeError as exc:
            print('Fixture provider refusal: '+str(exc),flush=True)
            element=automation.GetFocusedElement()
            if element.CurrentProcessId==pid.value:
                pattern=element.GetCurrentPattern(10014).QueryInterface(module.IUIAutomationTextPattern)
                document=pattern.DocumentRange;selection=pattern.GetSelection().GetElement(0)
                before=document.Clone();before.MoveEndpointByRange(1,selection,0)
                prefix=before.GetText(262145);doc=document.GetText(262145)
                value=element.GetCurrentPattern(10002).QueryInterface(module.IUIAutomationValuePattern).CurrentValue
                mismatch=next((i for i,(a,b) in enumerate(zip(value,prefix)) if a!=b),None)
                print({'fixture_lengths':{'document':len(doc),'prefix':len(prefix),'value':len(value)},
                    'doc_prefix_match':doc.startswith(prefix),'value_prefix_match':value.startswith(prefix),
                    'first_mismatch_index':mismatch,
                    'value_codes':list(map(ord,value[mismatch:mismatch+4])) if mismatch is not None else [],
                    'prefix_codes':list(map(ord,prefix[mismatch:mismatch+4])) if mismatch is not None else []},flush=True)
            raise
    accessibility._read=diagnostic_read
    def command(**data):
        child.stdin.write(json.dumps(data)+'\n')
        child.stdin.flush()
        return json.loads(child.stdout.readline())
    try:
        host=json.loads(child.stdout.readline())
        hwnd=host['hwnd']
        pid=W.DWORD()
        target_thread=u.GetWindowThreadProcessId(hwnd,C.byref(pid))
        assert pid.value==host['pid'] and (pid.value==child.pid or child.pid in
            [p.pid for p in psutil.Process(pid.value).parents()]), 'Only the test process may receive input'
        this_thread=k.GetCurrentThreadId()
        old_thread=u.GetWindowThreadProcessId(original,None)
        attached=[]
        try:
            for thread in set([old_thread,target_thread]):
                if thread != this_thread and u.AttachThreadInput(this_thread,thread,True):
                    attached.append(thread)
            u.SetForegroundWindow(hwnd)
            u.SetFocus(hwnd)
            native.settle(.1)
        finally:
            for thread in attached:
                u.AttachThreadInput(this_thread,thread,False)
        command(action='activate')
        guard.install()
        native.settle(.1)
        assert u.GetForegroundWindow()==hwnd, 'Fixture failed to take foreground; no input sent'
        command(action='set',text='prefix suffix',caret=6)
        target=guard.snapshot()
        receipt=guard.insert(' native',target)
        assert receipt.confirmed and read_edit(hwnd).text=='prefix native suffix'
        # Real UI Automation provider, real Unicode SendInput, full readback.
        command(action='set',text='prefix suffix',caret=6)
        win.native_editor=lambda _:False
        target=guard.snapshot()
        text=' CUDA 5070 — café 😀' * (600 if '--long-paste' in sys.argv else 20)
        guard.prefer_clipboard=True
        began=time.perf_counter()
        try: receipt=guard.insert(text,target)
        except RuntimeError:
            now=guard.identity()
            print({'fixture_target_identity':[target.foreground,target.focus,target.process,target.epoch],
                   'current_identity':[now.foreground,now.focus,now.process,now.epoch],
                   'invalidation_reason':guard.last_change},flush=True)
            raise
        paste_ms=(time.perf_counter()-began)*1000
        assert receipt.confirmed and read_edit(hwnd).text=='prefix'+text+' suffix'
        paste_method=receipt.method
        assert paste_method.startswith('Clipboard'),paste_method
        if '--paste-only' in sys.argv:
            return {'cross_process_clipboard_paste_and_uia_readback_verified':True,
                    'characters':len(text),'preferred_delivery_method':paste_method,
                    'preferred_delivery_ms':paste_ms,
                    'scope':'Disposable native editor forced through its real UIA provider'}
        command(action='set',text='prefix suffix',caret=6)
        native.settle(.08)
        assert u.GetForegroundWindow()==hwnd,'Fixture lost foreground after paste; no further input sent'
        target=guard.snapshot()
        guard.prefer_clipboard=False
        began=time.perf_counter()
        receipt=guard.insert(text,target)
        unicode_ms=(time.perf_counter()-began)*1000
        assert receipt.confirmed and receipt.method.startswith('Unicode')
        assert read_edit(hwnd).text=='prefix'+text+' suffix'
        # Same HWND, caret and focus, but application edits its own document.
        stale=guard.snapshot()
        command(action='set',text='programmatic edit',caret=6)
        assert not guard.valid(stale)
        win.native_editor=original_native
        # A hung cross-process field must not hang the dictation message loop.
        assert command(action='stall',seconds=1)['stalled']
        began=time.perf_counter()
        try:
            read_edit(hwnd)
            raise AssertionError('hung target did not time out')
        except RuntimeError:
            timeout_ms=(time.perf_counter()-began)*1000
            assert timeout_ms<500
        began=time.perf_counter()
        try:
            guard.probe.read(timeout=.25,service=guard.service_callbacks)
            raise AssertionError('hung UIA provider did not fail')
        except RuntimeError:
            uia_timeout_ms=(time.perf_counter()-began)*1000
            assert uia_timeout_ms<500
        return {'cross_process_native_verified':True,'real_uia_unicode_readback_verified':True,
                'preferred_delivery_method':paste_method,'preferred_delivery_ms':paste_ms,
                'uia_verified_unicode_characters':len(text),'uia_verified_unicode_ms':unicode_ms,
                'uia_programmatic_edit_rejected':True,'hung_native_target_timeout_ms':timeout_ms,
                'hung_uia_target_timeout_ms':uia_timeout_ms,
                'scope':'Disposable Win32 editor and its UIA provider; browser/Word/VS Code not certified'}
    finally:
        win.native_editor=original_native
        accessibility._read=original_read
        guard.close()
        restore=bool('hwnd' in locals() and u.GetForegroundWindow()==hwnd)
        if child.poll() is None:
            try:
                command(action='close')
                child.wait(timeout=3)
            except Exception:
                child.terminate()  # Our disposable fixture process only.
                child.wait(timeout=3)
        if original and restore:
            u.SetForegroundWindow(original)

if __name__=='__main__':
    result=run()
    Path('results/accessibility-long-0.5.0.json' if '--long-paste' in sys.argv else 'results/accessibility-integration-0.5.0.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
