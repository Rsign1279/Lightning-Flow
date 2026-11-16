# Contributing

Develop on Windows with Python 3.11/3.12 x64. Run Setup.ps1 explicitly to install the locked environment and a selected model. Use `.venv\Scripts\python.exe -m pytest -q` for the noninteractive suite. GPU/UI integration checks are opt-in and require their documented hardware/idle-desktop conditions.

Useful checks:

```powershell
.venv\Scripts\python.exe -m tests.preview_latency_integration --model tiny.en
.venv\Scripts\python.exe -m tests.ctrl_win_soak --manifest benchmarks\manifest.json --output results\ctrl-win-local.json --per-mode 100 --pairs 1
.venv\Scripts\python.exe -m tests.navigation_cache_integration
.venv\Scripts\python.exe -m tests.accessibility_integration --paste-only --long-paste --require-idle
```

The soak defaults to the nonpersonal example profile. Pass `--settings C:\private\settings.json` only for an explicit private-profile comparison. No microphone or external insertion occurs in the CUDA soak. Accessibility integration briefly foregrounds its own disposable editor and aborts on user input/focus changes; it does not edit your documents. The packaged executable supports `--self-check` for an isolated GUI/CUDA startup diagnostic without recording.

Keep physical-key/microphone latency distinct from callback/replay measurements. Preserve every failure/timeout and identify dataset, model, precision and scope. Do not claim user-voice accuracy from synthetic WER or claim cross-app reliability from mocks. Never weaken focus, selection, literal/number/qualification or clipboard guards just to make a test pass. Add regression coverage for actual bugs.

Do not commit `.venv`, `.runtime`, model weights, `.work`, user settings, history databases, recovery files, private recordings, tokens or certificates. Original contributions are under the repository's MIT license; preserve all upstream notices for incorporated code/assets.
