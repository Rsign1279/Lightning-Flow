# LightningFlow 0.1.1 — insertion and focus repair

The delivery path now confirms what reached the intended field. GPU loading, inference, microphone capture and segmentation are unchanged.

## Root causes and changes

1. Every global foreground/object-focus notification incremented the invalidation counter, including duplicate notifications and background providers. Caret rectangles were also compared as identity. The guard now filters old/irrelevant focus events and compares foreground/focused HWNDs, process/thread identity, readable document content and actual selection. UI Automation adds runtime identity for accessible elements inside a shared browser/editor HWND. Geometry remains diagnostic only.
2. A large Unicode SendInput batch was declared successful just because Windows queued it. Native Edit/RichEdit controls now use targeted EM_REPLACESEL, a native undo transaction and full document readback. Other accessible Edit/Document controls use Unicode batches of 128 characters with field identity and exact text/caret readback after every batch. Unicode surrogate pairs are not split. No clipboard write, foreground stealing, selected-text overwrite or whole-field SetValue is used. Uncertain/partial insertion is reported, never automatically retried.
3. Synchronous SendMessage could wait forever on an unresponsive editor. Native calls now use SendMessageTimeout; UI Automation runs on one bounded background worker with connection/transaction deadlines. A stalled provider does not block GPU inference or create unlimited workers.
4. A pending retry did not own the active-session slot and could overlap a new recording; retry delivery also replaced the original failed audio with an empty retry buffer. Pending deliveries now occupy one cancellable slot until completion, respect modifier release, and preserve source audio on failure/cancellation. New cancelled dictations preserve the previous recoverable recording. No confirmed receipt means no audio deletion.

An unreadable target no longer prevents GPU dictation. Recording/transcription can finish locally; automatic insertion is refused and the transcript stays available for export or explicit retry in a supported field.

## Evidence

- Reproductions written before the fixes failed for transient caret geometry and loss of the original recording on retry. Both pass with the fixes.
- `25 passed` in the automated suite, including pending retry/new-recording exclusion, cancellation, held modifiers, changed text/selection, background events, UTF-16 positions, unconfirmed delivery, unsupported-field recovery, correctly arming a new session before accessibility callbacks, and stopping Unicode batches after a focus change.
- Real Win32 integration: duplicate and background WinEvent notifications accepted; changed content, selection overwrite and stale target refused; long Unicode paragraphs inserted and undone exactly; a control-imposed text limit detected as truncation; clipboard unchanged; native global hotkeys and conflicts verified.
- Cross-process integration: targeted native delivery, actual UI Automation provider, 380-character multi-batch Unicode insertion and full text readback passed. Native and UIA stalled-target errors returned in about 150–165 ms. The fixture is a disposable editor process, never an existing user document.
- Real CUDA replay: hotkey → replayed PCM → resident RTX 5070 inference → exact native readback passed. Final synthetic fixture observation: about 47 ms from stop hotkey to complete text; this accelerated replay is not a physical microphone latency measurement.
- GPU regression: tiny.en FP16, three decodes of the included 8.835-second fixture, median about 74 ms; unchanged transcript. This is a small synthetic speed check, not a human accuracy result.
- SHA-256 comparison confirms `asr.py` and `audio.py` are byte-for-byte unchanged. AST comparisons confirm `Dictation.infer`, `capture` and `enqueue` are unchanged. See `results/gpu-path-integrity-0.1.1.json`.

Raw results: `results/windows-integration-0.1.1.json`, `accessibility-integration-0.1.1.json`, `replay-integration-0.1.1.json`, `gpu-regression-0.1.1.json`. The original performance report/results are historical 0.1.0 baseline measurements.

## Practical limits

This fixes verified delivery and false focus invalidation; it does not certify every third-party application's accessibility implementation. Unsupported fields are refused for automatic insertion. Programmatic field mutation or focus changes during an input call cannot be made globally transactional by Win32. After any partial/uncertain result, inspect the field before retrying. No automatic fallback risks duplicate text.

Native insertion measured about 3.5 ms in the fixture. The Unicode/UIA route measured approximately 5.7 seconds for 380 characters with other global keyboard-hook applications running, including the old LightningFlow instance. Its exact readback passed, but this route is not universally low latency. Other applications' hooks can delay every injected event; this repair does not change their processes. Browser/Word/VS Code compatibility and human microphone accuracy remain uncertified.

Restart the currently running LightningFlow instance to load 0.1.1. Ctrl+Alt+Q quits; open Start-LightningFlow.cmd and wait for READY. Ctrl+Alt+F8 still toggles dictation; Ctrl+Alt+F9 retries. The existing GPU models and precision stay the same.

Status: **DONE_WITH_CONCERNS** — reproduced bugs fixed; automated/native/UIA/CUDA verification passed; broad application compatibility and Unicode latency remain limited as above.

## API references

[SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput) reports queued events and is subject to UIPI. [EM_REPLACESEL](https://learn.microsoft.com/en-us/windows/win32/controls/em-replacesel) supports native insertion and undo. [SendMessageTimeout](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendmessagetimeoutw) bounds cross-thread message waits. [IUIAutomation2](https://learn.microsoft.com/en-us/windows/win32/api/uiautomationclient/nn-uiautomationclient-iuiautomation2) provides provider deadlines and an AutoSetFocus setting, which this implementation disables.
