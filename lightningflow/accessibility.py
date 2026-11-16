"""Read-only UI Automation on a dedicated, bounded worker.

Never SetFocus or SetValue: editing stays in the target application's input
path. An unavailable/stalled provider causes a recoverable refusal.
"""
from dataclasses import dataclass
import queue
import threading
import time

MAX_TEXT = 262144

@dataclass(frozen=True)
class AccessibleText:
    runtime_id: tuple
    process: int
    text: str
    start: int
    end: int

def _read(automation, module):
    element = automation.GetFocusedElement()
    if not element or not element.CurrentHasKeyboardFocus:
        raise RuntimeError('No accessible focused text field')
    if element.CurrentIsPassword or not element.CurrentIsEnabled:
        raise RuntimeError('Password/disabled target refused')
    # Web contenteditable providers sometimes identify as Custom/Pane. The
    # actual editable TextPattern, not a control-type label, is authoritative.
    pattern = element.GetCurrentPattern(10014).QueryInterface(module.IUIAutomationTextPattern)
    if pattern.DocumentRange.GetAttributeValue(40015):  # IsReadOnly
        raise RuntimeError('Read-only target refused')
    selections = pattern.GetSelection()
    if selections.Length != 1:
        raise RuntimeError('Target does not expose one caret/selection')
    selection = selections.GetElement(0)
    document = pattern.DocumentRange
    text = document.GetText(MAX_TEXT + 1)
    if len(text) > MAX_TEXT:
        raise RuntimeError('Accessible document exceeds the safe verification limit')
    before = document.Clone()
    before.MoveEndpointByRange(1, selection, 0)
    prefix = before.GetText(MAX_TEXT + 1)
    selected = selection.GetText(MAX_TEXT + 1)
    # Prefer the editable ValuePattern where available; selection still comes
    # from TextPattern. Never SetValue or guess inconsistent offsets.
    value_pattern=None
    try:
        value_pattern=element.GetCurrentPattern(10002).QueryInterface(module.IUIAutomationValuePattern)
    except Exception:pass
    if value_pattern is not None:
        if value_pattern.CurrentIsReadOnly:raise RuntimeError('Read-only target refused')
        value=value_pattern.CurrentValue
        if isinstance(value,str):
            # Legacy Value providers can cap a value at exactly 4096 UTF-16
            # units while TextPattern still exposes the complete document.
            # Accept only that compatible prefix truncation, never arbitrary
            # disagreement. The full TextPattern/caret checks remain required.
            truncated=(len(value.encode('utf-16-le'))==8192 and len(value)<len(text)
                       and text.startswith(value) and text.startswith(prefix))
            if not truncated:text=value
    normalize=lambda value:value.replace('\r\n','\n').replace('\r','\n')
    text,prefix,selected=map(normalize,(text,prefix,selected))
    # Chromium exposes one extra terminal paragraph for an empty final line.
    # Only remove that single sentinel immediately after a collapsed caret;
    # never trim general document whitespace or a remaining real paragraph.
    if (value_pattern is not None and getattr(element,'CurrentFrameworkId','')=='Chrome'
            and not selected and prefix.endswith('\n') and text==prefix+'\n'):
        text=prefix
    if len(text)>MAX_TEXT:raise RuntimeError('Accessible document exceeds the safe verification limit')
    if not text.startswith(prefix) or text[len(prefix):len(prefix)+len(selected)] != selected:
        raise RuntimeError('Text provider returned inconsistent selection ranges')
    return AccessibleText(tuple(element.GetRuntimeId()), element.CurrentProcessId,
                          text, len(prefix), len(prefix) + len(selected))

class AutomationProbe:
    def __init__(self):
        self.requests = queue.Queue(maxsize=1)
        self.closed = threading.Event()
        self.thread = None
        self.busy = False

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._run, name='read-only-uia', daemon=True)
            self.thread.start()

    def _run(self):
        try:
            import comtypes
            import comtypes.client
            # comtypes initializes its importing thread. Reinitialize explicitly
            # in MTA so Windows providers can marshal without a UI thread loop.
            comtypes.CoUninitialize()
            comtypes.CoInitializeEx(0)
            module = comtypes.client.GetModule('UIAutomationCore.dll')
            automation = comtypes.client.CreateObject(module.CUIAutomation8, interface=module.IUIAutomation2)
            automation.AutoSetFocus = False
            automation.ConnectionTimeout = 150
            automation.TransactionTimeout = 150
            startup_error = None
        except Exception as exc:
            startup_error = str(exc)
        try:
            while not self.closed.is_set():
                try:
                    done, response = self.requests.get(timeout=.1)
                except queue.Empty:
                    continue
                try:
                    if startup_error:
                        raise RuntimeError(startup_error)
                    response.append(_read(automation, module))
                except Exception:
                    # Provider exception messages can contain document text.
                    response.append(RuntimeError('This field does not expose readable text and caret through Windows accessibility'))
                finally:
                    self.busy = False
                    done.set()
        finally:
            if not startup_error:
                comtypes.CoUninitialize()

    def read(self, timeout=.45, service=lambda: None):
        self.start()
        if self.busy:
            raise RuntimeError('Accessibility provider is still busy; transcript retained')
        self.busy = True
        done, response = threading.Event(), []
        self.requests.put_nowait((done, response))
        deadline = time.perf_counter() + timeout
        while not done.is_set():
            service()
            if time.perf_counter() >= deadline:
                raise RuntimeError('Accessibility provider timed out; transcript retained')
            done.wait(.001)
        result = response[0]
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed.set()
