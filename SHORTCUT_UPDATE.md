# Ctrl + Win recording — 0.4.2

This PC uses **Ctrl + Win** with **Hold + double press** and a **30-minute** recording limit. Either left or right Ctrl and Windows key works, in either press order.

- Hold both keys and speak. After a hold longer than 200 ms, releasing either modifier group stops capture immediately; GPU processing finishes the captured audio.
- Double-tap the chord: release a short first press (up to 200 ms), then press again within 320 ms. Release the keys and keep speaking hands-free. Tap the chord again to stop.
- You can keep Ctrl held and tap Win twice, or release both between taps.
- A single short tap pauses the microphone immediately and finalizes after the 320 ms double-tap window. It may produce an empty recording. Hold-only mode remains available for ignoring short taps.
- The overlay identifies locked recording. Completed results continue to append to the enabled local log.

Settings → Shortcuts selects the recording chord and interaction separately. Other actions retain their Ctrl + Alt shortcuts. The old Ctrl + Alt + F8 recording shortcut is inactive while Ctrl + Win is selected. Modifier-only shortcuts use the existing ordered Windows low-level hook; RegisterHotKey cannot reserve/report conflicts for this chord. Avoid assigning the same chord in another utility. Ctrl-first chords consume Windows down/up as a pair. Win-first chords pass the corresponding Windows release, preserving the OS modifier state. Standalone Windows presses are passed through. Prefer Ctrl first when using the shortcut.

The session limit is configurable from 1 to 3600 seconds. Long sessions still decode bounded audio segments on the resident CUDA model. Audio is retained in RAM until delivery/recovery, so memory scales with duration (30 minutes of 16 kHz float32 mono PCM is about 110 MiB before object/segment overhead). No model reload is introduced.

## Validation

- 114 pytest checks passed, including 24 new modifier/gesture/settings regressions.
- 20 real CUDA replay sessions passed: 10 holds and 10 hands-free sessions, 20 unique persistent log records, one model initialization. [Raw results](results/ctrl-win-0.4.2.json).
- Replays exercise the production modifier event dispatcher, capture worker, GPU model, delivery scheduler and isolated log. They inject no OS input and do not capture the user's microphone or insert into other apps.
- Physical keyboard behavior, Start menu suppression on this desktop, and an actual 30-minute session still require manual validation. The Windows computer-use tool disallows Windows-key injection; no substitute global-input automation was used.
- ASR/model/segmentation code and the inference/enqueue functions are unchanged. The capture worker additionally discards an in-flight frame after the short-tap pause edge.

Build with `powershell -NoProfile -ExecutionPolicy Bypass -File Build-Desktop.ps1 -Output desktop-next`, then `Build-Installer.ps1 -Release desktop-next\LightningFlow`. Tests: `.venv\Scripts\python.exe -m pytest -q` and `.venv\Scripts\python.exe -m tests.ctrl_win_integration`.
