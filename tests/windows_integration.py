"""Interactive desktop integration test, restricted to a newly created Edit window.

Run as a script. Briefly foregrounds an isolated test control, never types into
an existing user application. Does not start the microphone or ASR.
"""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import time
from lightningflow.win32 import u, k, INPUT, InputGuard, pump, send_virtual_keys

u.CreateWindowExW.argtypes = [W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,W.LPVOID]
u.CreateWindowExW.restype = W.HWND
u.SetForegroundWindow.argtypes = [W.HWND]
u.SetFocus.argtypes = [W.HWND]
u.DestroyWindow.argtypes = [W.HWND]
u.SetWindowTextW.argtypes = [W.HWND,W.LPCWSTR]
u.GetWindowTextW.argtypes = [W.HWND,W.LPWSTR,C.c_int]
u.GetClipboardSequenceNumber.restype = W.DWORD
u.AttachThreadInput.argtypes = [W.DWORD,W.DWORD,W.BOOL]
u.NotifyWinEvent.argtypes = [W.DWORD,W.HWND,W.LONG,W.LONG]
k.GetCurrentThreadId.restype = W.DWORD

def settle(seconds=.08):
    end = time.perf_counter()+seconds
    while time.perf_counter()<end:
        pump()
        time.sleep(.002)

def run():
    original = u.GetForegroundWindow()
    clip_before = u.GetClipboardSequenceNumber()
    hwnd = u.CreateWindowExW(0,"EDIT","",0x10CF0000|0xC4|0x1000,100,100,640,160,None,None,k.GetModuleHandleW(None),None)
    if not hwnd:
        raise C.WinError(C.get_last_error())
    guard = InputGuard([0x87])
    registered = False
    try:
        # Only the fixture uses AttachThreadInput, to activate its own window.
        # Production delivery never steals/restores another window's focus.
        current_thread = k.GetCurrentThreadId()
        foreground_thread = u.GetWindowThreadProcessId(original, None)
        attached = u.AttachThreadInput(current_thread, foreground_thread, True)
        try:
            u.SetForegroundWindow(hwnd)
            u.SetFocus(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(current_thread, foreground_thread, False)
        settle()
        guard.install()
        settle()
        target = guard.snapshot()
        assert target.focus == hwnd and target.foreground == hwnd, f"Test control {hwnd} could not take foreground ({target}); no input sent"
        background=u.CreateWindowExW(0,'EDIT','',0,0,0,100,50,None,None,k.GetModuleHandleW(None),None)
        try:
            u.NotifyWinEvent(0x8005,hwnd,-4,0)
            u.NotifyWinEvent(0x8005,background,-4,0)
            settle(.02)
            assert guard.valid(target), 'Duplicate/background focus notifications revoked the active target'
        finally:
            u.DestroyWindow(background)
        text = "LightningFlow CUDA 5070 — café."
        start = time.perf_counter()
        receipt = guard.insert(text, target)
        assert receipt.confirmed and receipt.method.startswith('native')
        dispatch_ms = (time.perf_counter()-start)*1000
        settle()
        content = C.create_unicode_buffer(1024)
        u.GetWindowTextW(hwnd, content, 1024)
        assert content.value == text, repr(content.value)
        # Reject stale epoch without sending a single event.
        stale = guard.snapshot()
        guard.epoch += 1
        try:
            guard.insert("SHOULD NEVER APPEAR", stale)
            raise AssertionError("stale target was accepted")
        except RuntimeError:
            pass
        # Native selection must not be overwritten.
        u.SendMessageW(hwnd, 0xB1, 0, 5)
        target = guard.snapshot()
        try:
            guard.insert("SHOULD NEVER APPEAR", target)
            raise AssertionError("selection was replaced")
        except RuntimeError:
            pass
        u.GetWindowTextW(hwnd, content, 1024)
        assert content.value == text
        # Programmatic changes with no typing/focus change also revoke delivery.
        stale = guard.snapshot()
        u.SetWindowTextW(hwnd, 'changed by the target application')
        assert not guard.valid(stale)
        # Long Unicode and paragraphs use one native undo transaction. Offsets
        # are UTF-16 code units, including surrogate pairs before the caret.
        baseline = '😀 existing suffix'
        u.SetWindowTextW(hwnd, baseline)
        u.SendMessageW(hwnd, 0xB1, 2, 2)
        target = guard.snapshot()
        payload = '\n' + ('CUDA 5070 — café 😀. ' * 80) + '\n'
        receipt = guard.insert(payload, target)
        assert receipt.confirmed
        expected = '😀' + payload.replace('\n', '\r\n') + ' existing suffix'
        long_content = C.create_unicode_buffer(4096)
        u.GetWindowTextW(hwnd, long_content, 4096)
        assert long_content.value == expected
        u.SendMessageW(hwnd, 0xC7, 0, 0)  # EM_UNDO
        u.GetWindowTextW(hwnd, long_content, 4096)
        assert long_content.value == baseline
        # A control-enforced character limit is an error, never false success.
        u.SetWindowTextW(hwnd, '')
        u.SendMessageW(hwnd, 0xC5, 4, 0)  # EM_LIMITTEXT
        target = guard.snapshot()
        try:
            guard.insert('this must be truncated', target)
            raise AssertionError('truncated input was reported as delivered')
        except RuntimeError as exc:
            assert 'truncated' in str(exc)
        # Exercise RegisterHotKey and actual SendInput -> WM_HOTKEY delivery.
        ident = 0xA011
        assert u.RegisterHotKey(None, ident, 0x4003, 0x87), "Ctrl+Alt+F24 conflict"
        registered = True
        assert not u.RegisterHotKey(None, ident+1, 0x4003, 0x87), "Conflict was not detected"
        began = time.perf_counter()
        send_virtual_keys([0x11,0x12,0x87])
        msg = W.MSG()
        received = False
        while time.perf_counter()-began < 1:
            while u.PeekMessageW(C.byref(msg),None,0,0,1):
                if msg.message==0x312 and msg.wParam==ident:
                    received=True
                    hotkey_ms=(time.perf_counter()-began)*1000
                else:
                    u.TranslateMessage(C.byref(msg))
                    u.DispatchMessageW(C.byref(msg))
            if received:
                break
            time.sleep(.001)
        assert received, "Global hotkey message not received"
        assert u.GetClipboardSequenceNumber()==clip_before, "Clipboard sequence changed"
        return {"unicode_input_verified":True,"stale_target_rejected":True,
                "selection_replacement_rejected":True,"global_hotkey_verified":True,
                "conflict_detected":True,"clipboard_untouched":True,
                "confirmed_native_delivery":True,"programmatic_edit_rejected":True,
                "duplicate_and_background_focus_events_ignored":True,
                "long_unicode_paragraphs_and_undo":True,"truncation_detected":True,
                "input_dispatch_ms":dispatch_ms,"hotkey_dispatch_ms":hotkey_ms,
                "scope":"New native Edit control only; broad application compatibility untested"}
    finally:
        if registered:
            u.UnregisterHotKey(None,0xA011)
        guard.close()
        u.DestroyWindow(hwnd)
        if original:
            u.SetForegroundWindow(original)

if __name__ == "__main__":
    result = run()
    Path("results").mkdir(exist_ok=True)
    Path("results/windows-integration-0.1.1.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
