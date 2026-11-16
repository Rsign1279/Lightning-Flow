# 100 requested tests plus 100 verification cycles — 2026-11-08

**200 additional automated dictation cycles passed.** There were no failed or unattempted cycles, and no GUI callback exceptions. Each 100-cycle run also included 200 quick taps: **400 tap checks**, all ignored without capture or transcripts. Each run saved 100 unique transcript IDs and restored the exact same IDs after closing/reopening its isolated log. All nine screens and both themes were exercised across each run.

The tests used the hidden source desktop, real JSON IPC, production hold callbacks, accelerated PCM replay, actual resident CTranslate2 CUDA inference and SQLite persistence. There was one GPU model initialization per 100-cycle run. They did not open the physical microphone, send OS keyboard input, inspect user documents, use the clipboard or type into other applications. Production user settings and history were not used for test data.

## Issue found and fixed

The first run exposed a **3072-ms maximum GUI pause** during repeated page/theme/log rebuilding, despite all dictation cycles completing correctly. Profiling showed that building and destroying a large number of transcript cards on Tk's main thread was the main cost.

Version 0.4.1 renders ten reusable log cards with Previous/Next controls and searches the full stored history. Completing a recording refreshes those cards in place. The regression check reached all 100 entries, found an entry outside the first page, and verified card reuse after paging and a new completion. Initial navigation measured 144.62 ms; a page update measured at most **3.77 ms** in that isolated check. The original 90 unit/regression tests still passed.

After the fix, another **100 full dictation cycles passed**. The maximum GUI heartbeat gap fell to 695 ms under repeated full page/theme construction. This remaining navigation cost means the test does not establish a 16-ms response for every UI action or a stutter-free guarantee.

## Raw measurements

Values are median / p95 / maximum. Milliseconds unless noted.

| Measurement | First 100 | Verification 100 |
|---|---:|---:|
| Press → recording signal | 120.89 / 121.50 / 121.57 | 120.68 / 121.48 / 121.80 |
| Release callback → stop command | 0.04 / 0.05 / 0.15 | 0.04 / 0.10 / 0.33 |
| Release → completed test transcript | 3.21 / 3.60 / 4.49 | 3.44 / 330.55 / 373.63 |
| GPU decode | 77.48 / 86.98 / 92.50 | 92.43 / 556.40 / 648.48 |
| GUI heartbeat gap | 16.06 / 30.45 / 3072.35 | 16.08 / 30.47 / 694.67 |
| Worker tree RSS, MiB | 719.91 / 720.10 / 720.14 | 720.93 / 721.30 / 721.59 |
| GUI RSS, MiB | 64.69 / 76.04 / 76.17 | 60.03 / 61.12 / 61.22 |

Worker RSS change from cycles 11–20 to the final ten cycles: -0.67 MiB in the first run, +1.04 MiB in verification. This is finite-run process RSS, not VRAM or a long-term leak proof. Total elapsed time was 352.31 seconds, excluding profiling and the fix.

The recording-start measurement includes the intentional 120-ms tap threshold. Speech is decoded incrementally before release in this replay fixture, so completion times cannot be treated as acoustic microphone latency. The transcript comparison normalized case/punctuation and equivalent `3`/`three` forms. It measures repeatability on one synthetic sample, not general speech accuracy. GPU latency varied across the runs; other applications were not stopped to improve the numbers.

## Reproduce

```powershell
.venv\Scripts\python.exe -m tests.soak_100 --cycles 100
.venv\Scripts\python.exe -m tests.log_paging_integration
.venv\Scripts\python.exe -m pytest -q
```

The test-only worker disables actual shortcut registration, Windows input and real microphone capture in its own process. Normal production engine behavior is unchanged. Settings and synthetic SQLite logs are isolated under workspace `work/soak-100-*`; they are not packaged as user history. Physical hooks, microphone speech, arbitrary external app insertion and on-screen animation were not retested 200 times.

Raw reports: [first run](results/soak-100-20261108-151351.json), [verification run](results/soak-100-20261108-151939.json), [log paging regression](results/log-paging-0.4.1.json). The full source bundle includes the test scripts.
