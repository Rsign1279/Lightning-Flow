# Remaining work and validation boundaries

0.5.0 addresses the demonstrated meaning-guard holes, bounded spoken corrections, prose spacing, first-preview delay, long-text cap/readback, plaintext local storage and repeated Home/Log reconstruction. 0.6.0 adds a bounded ordered dictation queue, microphone-failure finalization and opt-in encrypted completed-recording recovery with GPU retranscription. Neither release proves universal accuracy, meaning preservation or compatibility.

- Validate physical Ctrl+Win behavior and Start-menu interaction on real keyboards; automation here does not inject the Windows key.
- Extend human-speech accuracy, accent/noise and meaning-preservation datasets; run a matched Wispr comparison only with authorized recordings and cloud use.
- Exercise actual 30-minute microphone sessions, hot-unplug/reconnect, sleep/wake and sustained VRAM contention. Accelerated replay is a separate scope.
- Investigate the NVIDIA TDR/native-runtime interruption observed in one long accelerated replay; its root cause remains unresolved. Version 0.6.1 contains the native GPU child failure and retains capture/text in the surviving controller. The initial driver timeout trigger is unproven; this is not a guarantee against display-driver resets.
- Expand real rich-editor/browser/Office/remote-desktop coverage. Keep refusal/recovery for inaccessible, elevated, selected or changing fields. Native target undo is supported; no universal cross-app undo promise.
- Broader command editing, rich snippets, app-specific styles, meeting notes, device sync and team features are not Wispr-equivalent implementations. Independent dictations can queue while earlier ASR/delivery finishes, up to three outstanding sessions; held modifiers defer external insertion. Ongoing capture is not crash-journaled.
- Parakeet/whisper.cpp and additional runtime backends are not implemented. Multilingual model selection is available, but non-English quality needs measurements.
- Trusted Windows signing requires a real maintainer certificate. Independent security assessment and managed enterprise compliance remain external work. Automatic installer execution stays disabled.
- Optional local AI remains conservatively constrained; formatting is not a general semantic guarantee. VRAM allocation by other applications/local model servers cannot be controlled by LightningFlow.
