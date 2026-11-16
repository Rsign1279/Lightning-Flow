# LightningFlow desktop 0.4.0

## Recording

The default Ctrl+Alt+F8 shortcut is hold-only. Taps shorter than 120 ms have no microphone, target-inspection, overlay or log side effects. Hold past that threshold to record, then release F8 or any Ctrl/Alt modifier to finish immediately. Repeated held-key messages cannot toggle recording. Double taps do not lock recording in this mode.

The release hook queues stop directly and stamps an audio cutoff on the session. A read already in flight after that cutoff is discarded, so new audio cannot extend the transcript after release. The GPU finishes only the audio already captured. No silence timeout or double-press grace period delays finalization. There is still real hardware/model/OS latency; release does not erase captured speech or cancel its final GPU decode.

The shortcut loop polls at 1 ms while armed/held, and the GUI event loop at 8 ms. Audio meters update at up to 50 Hz. The recording capsule appears at high opacity on the first paint, with a short remaining transition; its RMS envelope uses 12-ms attack and 70-ms release. The separate combined/toggle modes remain optional under Shortcuts, but are not the default. Existing 0.3 controls migrate to hold-only.

Completed transcripts automatically appear in Log, including transcripts retained after a delivery failure. Persistent local history has been enabled for this user; it stores plaintext transcripts, not audio. It remains opt-in for other installations and can be disabled/cleared in Settings. Enabling it saves already-visible session entries too. The log retains the latest 200 entries.

## Recording capsule

A compact dark rounded capsule appears above the taskbar without taking focus. It uses smoothed audio RMS levels for recording, a traveling waveform for transcription, clear paused/locked states and a short fade. Animations stop when hidden and honor the Windows client-area animation setting. A 1-ms timer request is scoped to the visible animated overlay and released after it hides. Meter updates run at up to 40 Hz and interpolation at approximately 60 Hz.

## Writing into applications

Native Edit/RichEdit controls receive an undoable targeted insertion with full readback. Accessible editors use a temporary clipboard paste with exact text/caret/runtime-identity readback. Text, HTML, registered memory formats, DIBs and bitmap copies are preserved within a 16-MiB/64-format bound. Restoration is armed after Windows closes/synthesizes clipboard formats. A newer user copy wins. Unsupported rich formats or a busy clipboard select bounded Unicode typing before any paste is attempted. A partial or uncertain paste is never followed by automatic retransmission.

Keep the focused field and cursor unchanged until delivery. Unsupported, password, read-only, selected or elevated fields retain the transcript for recovery. Use the target application's Ctrl+Z for undo where supported. No universal cross-app revision/undo guarantee is made. Inaccessible custom editors and terminal emulators are not certified.

## Workspace

Dictation shows current state, audio level, a practice recorder and the latest transcript. History supports search/copy/export and recovery audio export. Models offers local model selection, explicit downloads, hash verification and deletion. Microphone provides input selection and a five-second unsaved test. Writing style offers Raw, Smart cleanup, Professional, Casual, Technical and Custom with conservative local cleanup. Dictionary uses exact boundary matching. Performance displays actual provider/hardware and recorded metrics. Privacy & settings controls history, theme, overlay, tray behavior, login startup, limits and runtime repair.

Runtime repair, setup and uninstall run their command-line helpers hidden; no terminal is part of normal interaction. Optional login startup is off until selected. Opening the app again brings its existing window forward. The tray menu queues its actions for Tk rather than reentering Tk from a native callback.

## Packaging

`Build-Desktop.ps1` makes `desktop-dist/LightningFlow/LightningFlow.exe` with the Windows GUI subsystem and a separate engine source folder. A machine-specific `runtime.json` makes this checkout usable on the current PC. `Build-Installer.ps1` omits that manifest, model weights and CUDA libraries; setup creates an independent runtime. Binaries are unsigned. See INSTALLATION.md for fresh-machine prerequisites.

## Visual update 0.4.0

Home uses a compact warm-violet recording panel with real shortcut keycaps, readable latest text and recent log entries. The latest saved nonempty transcript is restored into Home on launch. The transcript timeline groups by date and keeps Copy/Open close to each entry. Appearance is available in the top bar, with synchronized selectors. Everyday navigation is reduced to Home, Log, Writing style, Dictionary and Settings; setup and diagnostics live under Settings. Original line icons and a new violet application mark are rendered locally. The recording capsule is 294×64 logical pixels, keeping its 16-ms animation schedule and immediate first paint. No shortcut, capture, GPU, cleanup, input-guard or clipboard logic changed in this visual release.

## 0.4.1 log performance fix

The 100-cycle test exposed a slow log-rendering path. The log now reuses ten cards with Previous/Next controls; search still covers all saved entries. New recordings refresh the existing cards instead of rebuilding the whole log. Both the original 100-cycle run and another 100-cycle verification completed without dictation failures. See TEST_100.md for the raw scopes, timings and remaining navigation costs. Audio capture, GPU inference, shortcut gestures and text insertion are unchanged.
