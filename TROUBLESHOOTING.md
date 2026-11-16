# Troubleshooting

- **Shortcut already in use:** quit the older dictation instance or choose another action key under Shortcuts. Never run the developer console and desktop app with the same shortcut simultaneously.
- **No words in the target:** check History. A changed field, selection, focus excursion or input revokes insertion. Copy the retained transcript or carefully retry at the intended cursor. Do not retry blindly after a possibly partial paste.
- **Unsupported/password/read-only/elevated field:** use Copy from History. The app does not bypass Windows integrity levels or overwrite unreadable content. A working native/API bridge is required for a custom editor to offer verified delivery.
- **Clipboard restoration issue:** delivery and restoration are tracked separately; the notice tells you when a successful insertion left the transcript on the clipboard. A new user copy is preserved. Metafile/palette or overly large clipboard data uses direct Unicode before any paste.
- **Slow direct typing:** another application's global hooks can delay SendInput. The verified clipboard route avoids per-character keyboard events where the clipboard can be safely preserved. Native controls use targeted messages.
- **Missing runtime:** Privacy & settings → Repair GPU runtime. This can download dependencies with consent. Setup, workers and repair helpers run hidden.
- **CUDA/VRAM errors:** inspect Performance for actual provider/error. ASR never silently falls back to CPU. Other GPU applications are not stopped automatically. Select a smaller model or free GPU resources yourself.
- **Microphone errors:** choose a connected input in Microphone, run its unsaved test, then retry. A failed capture retains available audio until explicit export or exit. No partial recording is automatically uploaded.
- **Locked recording:** press the shortcut again, or cancel with Ctrl+Alt+Esc. A normal hold ends when F8 or a Ctrl/Alt modifier is released. The overlay distinguishes locked, paused and processing states.

No application can guarantee failure-free insertion across every Windows app. Known limits and actual validation are in DESKTOP_VALIDATION.md.
