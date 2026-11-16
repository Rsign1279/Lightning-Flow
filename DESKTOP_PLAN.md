# Desktop build

1. Wrap the proven CUDA/core dictation loop in a separate local engine process with a small JSON command/event bridge. Keep inference and safe insertion in that process; keep the GUI thread free.
2. Build a CustomTkinter desktop shell: onboarding, dashboard/scratchpad, history, speech model management, microphone test, optional local AI cleanup, exact dictionary, shortcuts, performance and privacy/settings. Persistent settings and opt-in local history; no invented statistics.
3. Add a non-activating recording overlay, native system tray, keyboard navigation, light/dark themes, single-instance behavior and graceful shutdown.
4. Package a real Windows GUI executable plus runtime setup/installation scripts. Runtime/model downloads are explicit. Existing GPU environment is reused on this PC.
5. Run the core suite, new settings/history/cleanup/IPC tests, actual GPU desktop replay, GUI interaction/visual checks and packaged executable smoke tests. Document limitations honestly.
