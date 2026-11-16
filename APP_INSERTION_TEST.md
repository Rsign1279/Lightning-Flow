# App insertion validation — 0.4.5

On November 11, 2026, all six live app/mode cases inserted the expected text and preserved the foreground window. Production target identity, document and selection verification also passed. Screenshots confirmed the appended text in disposable local documents; no user documents were edited.

| App | Mode | Verified insertion | Focus changes | Insertion/readback ms | Stop-to-input ms |
| --- | --- | --- | --- | --- | --- |
| VSCode | hold | Pass | 0 | 108.8 | 112.8 |
| VSCode | locked | Pass | 0 | 107.1 | 109.2 |
| Notepad | hold | Pass | 0 | 6.7 | 8.4 |
| Notepad | locked | Pass | 0 | 7.4 | 9.3 |
| Chrome | hold | Pass | 0 | 98.0 | 100.4 |
| Chrome | locked | Pass | 0 | 93.5 | 95.4 |

The real application controls were Notepad, a local Chrome textarea, and a VS Code plain-text editor. Hold/release and double-tap/locked recording were driven through production gesture callbacks. Existing synthetic speech was replayed into the production audio pipeline with the real resident CUDA/CTranslate2 base.en model and personalized hints. The nonactivating production overlay ran throughout each case. Foreground was sampled during recording and insertion; zero excursions were detected. These are individual timings, not percentile estimates. Accelerated audio replay allows incremental decoding to finish before stop; stop-to-input is not a fresh whole-recording ASR timing. Final GPU decode ranged from 84.3 to 95.7 ms.

Two readback defects were corrected: Rich Edit paragraph offsets used CR while WM_GETTEXT returned CRLF, and Chromium exposed a synthetic final paragraph on empty last lines. Verification now uses consistent native offsets and bounded editable-value readback with a narrowly scoped Chromium sentinel rule. Focus, selection, document identity and exact post-insertion checks remain required. No paste retry, SetFocus or SetValue was added. ASR, GPU configuration, model residency, vocabulary and gesture behavior are unchanged.

Automated validation: 194 tests passed, including Rich Edit UTF-16 offsets, classic Edit CRLF, Chromium terminal paragraphs, real blank paragraphs, read-only targets and inconsistent selection refusal.

Limitations: the automation API cannot hold/release a physical Windows-key chord. This validates production gesture handlers and actual app delivery, but physical Ctrl+Win interception and real microphone response require a manual check. Six cases do not establish all-app, long-session or percentile latency guarantees. No claim of improved accuracy is made; recognition code was unchanged.

Reproduce: create the disposable fixtures documented in tests/app_insertion_check.py, set LIGHTNINGFLOW_TEST_ENGINE to this source directory, and run `.venv\Scripts\python.exe -m tests.app_insertion_check`. Focus only the whitelisted test editor and write one case command to work/app-insertion-check/command.json. Use `{"action":"shutdown"}` when finished. Results: results/app-insertion-0.4.5.json.

Native offset references: [EM_GETSEL](https://learn.microsoft.com/en-us/windows/win32/controls/em-getsel) and [GETTEXTEX line ending options](https://learn.microsoft.com/en-us/windows/win32/api/richedit/ns-richedit-gettextex).
