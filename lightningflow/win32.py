"""Native shortcuts and verified, focus-guarded Windows text delivery."""
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass, replace
import time
from .accessibility import AutomationProbe, AccessibleText, MAX_TEXT

u = C.WinDLL("user32", use_last_error=True)
k = C.WinDLL("kernel32", use_last_error=True)
PTR = C.c_size_t
LRESULT = C.c_ssize_t
HOOK = C.WINFUNCTYPE(LRESULT, C.c_int, W.WPARAM, W.LPARAM)
EVENT = C.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND, W.LONG, W.LONG, W.DWORD, W.DWORD)
OWN_INPUT = 0x4C464C57

class GUIINFO(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("flags", W.DWORD),
                ("hwndActive", W.HWND), ("hwndFocus", W.HWND),
                ("hwndCapture", W.HWND), ("hwndMenuOwner", W.HWND),
                ("hwndMoveSize", W.HWND), ("hwndCaret", W.HWND), ("rcCaret", W.RECT)]

class KEY(C.Structure):
    _fields_ = [("vk", W.WORD), ("scan", W.WORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("extra", PTR)]
class MOUSE(C.Structure):
    _fields_ = [("dx", W.LONG), ("dy", W.LONG), ("data", W.DWORD),
                ("flags", W.DWORD), ("time", W.DWORD), ("extra", PTR)]
class UNION(C.Union):
    _fields_ = [("ki", KEY), ("mi", MOUSE)]
class INPUT(C.Structure):
    _fields_ = [("type", W.DWORD), ("value", UNION)]
class KHOOK(C.Structure):
    _fields_ = [("vk", W.DWORD), ("scan", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("extra", PTR)]

u.GetForegroundWindow.restype = W.HWND
u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u.GetWindowThreadProcessId.restype = W.DWORD
u.GetGUIThreadInfo.argtypes = [W.DWORD, C.POINTER(GUIINFO)]
u.SendInput.argtypes = [W.UINT, C.POINTER(INPUT), C.c_int]
u.SendInput.restype = W.UINT
u.GetAsyncKeyState.argtypes = [C.c_int]
u.GetAsyncKeyState.restype = C.c_short
u.SetWindowsHookExW.argtypes = [C.c_int, HOOK, W.HINSTANCE, W.DWORD]
u.SetWindowsHookExW.restype = W.HANDLE
u.CallNextHookEx.argtypes = [W.HANDLE, C.c_int, W.WPARAM, W.LPARAM]
u.CallNextHookEx.restype = LRESULT
u.UnhookWindowsHookEx.argtypes = [W.HANDLE]
u.SetWinEventHook.argtypes = [W.DWORD, W.DWORD, W.HMODULE, EVENT, W.DWORD, W.DWORD, W.DWORD]
u.SetWinEventHook.restype = W.HANDLE
u.UnhookWinEvent.argtypes = [W.HANDLE]
u.RegisterHotKey.argtypes = [W.HWND, C.c_int, W.UINT, W.UINT]
u.UnregisterHotKey.argtypes = [W.HWND, C.c_int]
u.GetMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT]
u.PeekMessageW.argtypes = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT]
u.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
u.GetWindowLongW.argtypes = [W.HWND, C.c_int]
u.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u.SendMessageW.restype = LRESULT
u.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, C.POINTER(PTR)]
u.SendMessageTimeoutW.restype = LRESULT
u.IsWindow.argtypes = [W.HWND]
u.IsWindowEnabled.argtypes = [W.HWND]
k.GetTickCount.restype = W.DWORD
k.GetModuleHandleW.argtypes = [W.LPCWSTR]
k.GetModuleHandleW.restype = W.HMODULE

@dataclass(frozen=True)
class EditText:
    text: str
    start: int  # UTF-16 units, as returned by EM_GETSEL
    end: int

@dataclass(frozen=True)
class Target:
    foreground: int
    focus: int
    caret: tuple
    epoch: int
    process: int = 0
    thread: int = 0
    native: bool = False
    state: object = None

@dataclass(frozen=True)
class Delivery:
    confirmed: bool
    method: str
    after_state: object = None

def message(hwnd, code, wp=0, lp=0, timeout=150):
    result = PTR()
    C.set_last_error(0)
    if not u.SendMessageTimeoutW(hwnd, code, wp, lp, 0x22, timeout, C.byref(result)):
        raise RuntimeError('Target did not respond or blocked the request; delivery is not confirmed')
    return result.value

def class_name(hwnd):
    name = C.create_unicode_buffer(128)
    u.GetClassNameW(hwnd, name, len(name))
    return name.value.casefold()

def native_editor(hwnd):
    name = class_name(hwnd)
    return name == 'edit' or name.startswith('richedit')

def read_edit(hwnd):
    if not u.IsWindow(hwnd) or not u.IsWindowEnabled(hwnd):
        raise RuntimeError('Target field was closed or disabled')
    style = u.GetWindowLongW(hwnd, -16)
    if style & (0x20 | 0x800):
        raise RuntimeError('Password/read-only target refused')
    size = message(hwnd, 0xE)  # WM_GETTEXTLENGTH
    if size > MAX_TEXT:
        raise RuntimeError('Target text exceeds the safe verification limit')
    buffer = C.create_unicode_buffer(size + 2)
    message(hwnd, 0xD, size + 2, C.addressof(buffer))
    a, b = W.DWORD(), W.DWORD()
    message(hwnd, 0xB0, C.addressof(a), C.addressof(b))
    text=buffer.value
    if class_name(hwnd).startswith('richedit'):
        # Rich Edit selections count one CR per paragraph; WM_GETTEXT expands
        # it to CRLF. Use the same UTF-16 coordinate space for verification.
        # WM_GETTEXT is marshalled across processes, unlike custom WM_USER
        # messages with caller-local GETTEXTEX pointers.
        text=text.replace('\r\n','\r')
    if max(a.value,b.value)>len(text.encode('utf-16-le'))//2:
        raise RuntimeError('Target selection exceeds the verified text range')
    return EditText(text, a.value, b.value)

def expected_text(state, text):
    if isinstance(state, EditText):
        data = state.text.encode('utf-16-le')
        return (data[:state.start*2] + text.encode('utf-16-le') + data[state.end*2:]).decode('utf-16-le')
    return state.text[:state.start] + text + state.text[state.end:]

def spaced_insertion(state,text):
    from .text_processing import boundary_spacing
    if isinstance(state,EditText):
        data=state.text.encode('utf-16-le')
        prefix=data[:state.start*2].decode('utf-16-le')
        suffix=data[state.end*2:].decode('utf-16-le')
    else:prefix,suffix=state.text[:state.start],state.text[state.end:]
    return boundary_spacing(prefix,suffix,text)

class InputGuard:
    def __init__(self, hotkey_vks):
        self.epoch = 0
        self.last_change = ''
        self.hotkey_vks = set(hotkey_vks)
        self.hooks = []
        self.callbacks = []
        self.watched = None
        self.watch_time = 0
        self.probe = AutomationProbe()
        self.prefer_clipboard = True
        self.recording_chord = None

    def key_event(self, vk, down, own=False):
        if own: return False
        suppress = False
        if self.recording_chord is not None:
            edge, suppress = self.recording_chord.feed(vk, down)
            callback = getattr(self, 'on_recording_chord', None)
            if edge and callback is not None: callback(edge)
        chord = bool(u.GetAsyncKeyState(0x11) & 0x8000 and u.GetAsyncKeyState(0x12) & 0x8000)
        callback = getattr(self, 'on_key_down' if down else 'on_key_up', None)
        if callback is not None:
            if down: callback(vk, chord)
            else: callback(vk)
        modifiers = {0x10,0x11,0x12,0x5B,0x5C,0xA0,0xA1,0xA2,0xA3,0xA4,0xA5}
        if down and vk not in modifiers and not (chord and vk in self.hotkey_vks):
            self.epoch += 1
            self.last_change = 'keyboard input'
        return suppress

    def install(self):
        def keyboard(code, message, ptr):
            if code >= 0 and message in (0x100,0x104,0x101,0x105):
                key = C.cast(ptr, C.POINTER(KHOOK)).contents
                if self.key_event(key.vk,message in (0x100,0x104),key.extra == OWN_INPUT):
                    return 1
            return u.CallNextHookEx(None, code, message, ptr)
        def mouse(code, message, ptr):
            if code >= 0 and message in (0x201, 0x204, 0x207, 0x20A, 0x20B, 0x20E):
                self.epoch += 1
                self.last_change='mouse input'
            return u.CallNextHookEx(None, code, message, ptr)
        def focus(handle, event, hwnd, obj, child, thread, timestamp):
            self.focus_event(event, hwnd, obj, child, timestamp)
        self.callbacks = [HOOK(keyboard), HOOK(mouse), EVENT(focus)]
        module = k.GetModuleHandleW(None)
        try:
            for kind, cb in zip((13, 14), self.callbacks):
                handle = u.SetWindowsHookExW(kind, cb, module, 0)
                if not handle:
                    raise C.WinError(C.get_last_error())
                self.hooks.append(handle)
            self.events = [u.SetWinEventHook(event, event, None, self.callbacks[2], 0, 0, 0)
                           for event in (3, 0x8005)]
            if not all(self.events):
                raise C.WinError(C.get_last_error())
            self.probe.start()
        except Exception:
            self.close()
            raise

    def identity(self):
        foreground = u.GetForegroundWindow()
        info = GUIINFO(cbSize=C.sizeof(GUIINFO))
        process = W.DWORD()
        thread = u.GetWindowThreadProcessId(foreground, C.byref(process))
        if not foreground or not u.GetGUIThreadInfo(thread, C.byref(info)) or not info.hwndFocus:
            raise RuntimeError("No focused text target detected. Transcript will stay in memory.")
        r = info.rcCaret
        return Target(foreground, info.hwndFocus, (r.left, r.top, r.right, r.bottom), self.epoch, process.value, thread)

    def focus_event(self, event, hwnd, obj=0, child=0, timestamp=0):
        """Ignore duplicates, old events and background providers; never ignore an excursion."""
        target = self.watched
        if target is None:
            return
        if timestamp and C.c_int32(timestamp - self.watch_time).value < 0:
            return
        if event == 3:
            if hwnd and hwnd != target.foreground:
                self.epoch += 1
                self.last_change='foreground window'
        elif event == 0x8005:
            try:
                current = self.identity()
                if current.foreground != target.foreground or current.focus != target.focus:
                    self.epoch += 1
                    self.last_change='focused control'
            except RuntimeError:
                self.epoch += 1

    def snapshot(self, track=True):
        began = k.GetTickCount()
        current = self.identity()
        if track:
            # Arm the NEW field before slow provider reads. Leaving the previous
            # session armed here misclassifies this field's queued focus events.
            self.watched = current
            self.watch_time = began
        native = native_editor(current.focus)
        state = read_edit(current.focus) if native else self.probe.read(service=self.service_callbacks)
        after = self.identity()
        if (current.foreground, current.focus, current.process, current.epoch) != (after.foreground, after.focus, after.process, after.epoch):
            raise RuntimeError('Focus changed while capturing the target; nothing inserted'+(' ('+self.last_change+')' if self.last_change else ''))
        target = Target(current.foreground, current.focus, current.caret, current.epoch,
                        current.process, current.thread, native, state)
        if track:
            self.watched = target
            self.watch_time = began
        return target

    def service_callbacks(self):
        # Peek without removal services nonqueued hook/WinEvent callbacks while
        # preserving WM_HOTKEY for the application's state machine.
        msg = W.MSG()
        # One Peek per sleep would throttle hundreds of injected hook callbacks
        # and can trip Windows' low-level hook timeout. Service a bounded burst.
        for _ in range(32):
            u.PeekMessageW(C.byref(msg), None, 0, 0, 0)

    def valid(self, target):
        try:
            current = self.snapshot(track=False)
            # Caret coordinates may blink/disappear/shift with scrolling. The
            # actual selection and document revision, not geometry, are decisive.
            return (current.foreground, current.focus, current.process, current.thread,
                    current.epoch, current.native, current.state) == (
                    target.foreground, target.focus, target.process, target.thread,
                    target.epoch, target.native, target.state)
        except RuntimeError:
            return False

    def insert(self, text, target):
        if target is None:
            raise RuntimeError('No verified insertion target. Transcript retained for export or explicit retry in a supported field.')
        if not self.valid(target):
            raise RuntimeError("Target changed while recording/processing. Nothing inserted; use retry at the intended cursor.")
        if any(u.GetAsyncKeyState(v) & 0x8000 for v in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
            raise RuntimeError("Release modifier keys before insertion; transcript is available to retry.")
        if target.state is None or target.state.start != target.state.end:
            raise RuntimeError('Selection would be replaced or caret is unreadable. Deselect and retry.')
        if '\x00' in text:
            raise RuntimeError('Embedded NUL is not supported; transcript retained')
        text=spaced_insertion(target.state,text)
        if len(expected_text(target.state,text).encode('utf-16-le'))>MAX_TEXT*2:
            raise RuntimeError('Resulting document exceeds the safe verification limit; transcript retained for export')
        if target.native:
            if not u.GetWindowLongW(target.focus, -16) & 4 and ('\r' in text or '\n' in text):
                raise RuntimeError('Multiline transcript cannot be inserted into this single-line field')
            newline='\r' if class_name(target.focus).startswith('richedit') else '\r\n'
            text = text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', newline)
            expected = expected_text(target.state, text)
            payload = C.create_unicode_buffer(text)
            if not self.valid(target):
                raise RuntimeError('Target changed before insertion; nothing inserted')
            # Target the actual editor directly, with a native undo transaction.
            # No keyboard queue, no clipboard and no whole-field replacement.
            message(target.focus, 0xC2, 1, C.addressof(payload))  # EM_REPLACESEL
            actual = read_edit(target.focus)
            if actual.text != expected:
                raise RuntimeError('Target rejected, truncated or changed the insertion; check the field before retrying')
            if actual.start!=actual.end or actual.start!=target.state.start+len(text.encode('utf-16-le'))//2:
                raise RuntimeError('Caret changed during native insertion; inspect the field before retrying')
            return Delivery(True, 'native edit message + readback',actual)
        if len(text.encode('utf-16-le')) > MAX_TEXT*2:
            raise RuntimeError('Transcript exceeds the safe Unicode insertion limit; retained for export')
        if self.prefer_clipboard:
            from .clipboard import PasteClipboard, ClipboardUnavailable
            transaction=PasteClipboard(text,self.service_callbacks)
            try:
                transaction.__enter__()
            except ClipboardUnavailable:
                # No paste has occurred. Direct Unicode is the safe fallback
                # when rich clipboard content cannot be preserved.
                pass
            else:
                try:
                    if not self.valid(target):
                        raise RuntimeError('Target changed before paste; nothing inserted')
                    if any(u.GetAsyncKeyState(v)&0x8000 for v in (0x10,0x11,0x12,0x5B,0x5C)):
                        raise RuntimeError('Modifier pressed before paste; transcript retained')
                    send_virtual_keys([0x11,0x56])
                    actual=self.verify_accessible(target,text)
                finally:
                    transaction.__exit__(None,None,None)
                method='Clipboard paste + accessibility readback'
                if transaction.restore_note: method+='; '+transaction.restore_note
                return Delivery(True,method,actual)
        working = target
        for offset in range(0, len(text), 128):
            # Split on Python characters, never between a UTF-16 surrogate pair.
            chunk = text[offset:offset+128]
            expected = expected_text(target.state, text[:offset+len(chunk)])
            if not self.valid(working):
                raise RuntimeError('Target changed before the next input batch; partial delivery is possible; inspect before retrying')
            units = chunk.encode('utf-16-le')
            inputs = []
            for i in range(0,len(units),2):
                code = int.from_bytes(units[i:i+2],'little')
                for flags in (4,6):
                    inputs.append(INPUT(1,UNION(ki=KEY(0,code,flags,0,OWN_INPUT))))
            arr = (INPUT * len(inputs))(*inputs)
            sent = u.SendInput(len(arr), arr, C.sizeof(INPUT))
            if sent != len(arr):
                raise RuntimeError(f'SendInput accepted {sent}/{len(arr)} events. Partial delivery or an elevated target is possible; no automatic retry.')
            # Verify every bounded batch before submitting more text. No fallback
            # or retransmission occurs after an uncertain/partial delivery.
            deadline = time.perf_counter() + .75
            while time.perf_counter() < deadline:
                self.service_callbacks()
                current = self.identity()
                if (current.foreground,current.focus,self.epoch) != (target.foreground,target.focus,target.epoch):
                    raise RuntimeError('Focus/input changed during delivery; partial insertion is possible; do not retry blindly')
                actual = self.probe.read(service=self.service_callbacks)
                if (actual.runtime_id,actual.process) != (target.state.runtime_id,target.state.process):
                    raise RuntimeError('Accessible text field changed during delivery; transcript retained')
                if actual.text == expected:
                    if actual.start != actual.end or actual.start != target.state.start+offset+len(chunk):
                        raise RuntimeError('Caret changed during delivery; inspect the field before retrying')
                    working = replace(target,state=actual)
                    break
                time.sleep(.01)
            else:
                raise RuntimeError('Text delivery could not be verified; inspect the target before retrying')
        return Delivery(True, 'Unicode input + accessibility readback',working.state)

    def verify_accessible(self,target,text):
        expected=expected_text(target.state,text)
        deadline=time.perf_counter()+1.25
        while time.perf_counter()<deadline:
            self.service_callbacks()
            current=self.identity()
            if (current.foreground,current.focus,current.process,self.epoch)!=(
                    target.foreground,target.focus,target.process,target.epoch):
                raise RuntimeError('Focus/input changed during paste; inspect the target before retrying')
            actual=self.probe.read(service=self.service_callbacks)
            if (actual.runtime_id,actual.process)!=(target.state.runtime_id,target.state.process):
                raise RuntimeError('Accessible editor changed during paste; transcript retained')
            if actual.text==expected:
                if actual.start!=actual.end or actual.start!=target.state.start+len(text):
                    raise RuntimeError('Caret changed during paste; inspect the target before retrying')
                return actual
            time.sleep(.008)
        raise RuntimeError('Paste could not be verified. Transcript retained; inspect the field before retrying')

    def close(self):
        for handle in self.hooks:
            u.UnhookWindowsHookEx(handle)
        for handle in getattr(self, "events", []):
            if handle:
                u.UnhookWinEvent(handle)
        self.hooks.clear()
        self.events = []
        self.watched = None
        self.probe.close()

def send_virtual_keys(keys):
    """For the isolated integration fixture, and native Ctrl+Z if needed."""
    events = [INPUT(1, UNION(ki=KEY(v, 0, 0, 0, OWN_INPUT))) for v in keys]
    events += [INPUT(1, UNION(ki=KEY(v, 0, 2, 0, OWN_INPUT))) for v in reversed(keys)]
    arr = (INPUT * len(events))(*events)
    if u.SendInput(len(arr), arr, C.sizeof(INPUT)) != len(arr):
        raise C.WinError(C.get_last_error())

def pump():
    msg = W.MSG()
    while u.PeekMessageW(C.byref(msg), None, 0, 0, 1):
        u.TranslateMessage(C.byref(msg))
        u.DispatchMessageW(C.byref(msg))
