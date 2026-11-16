# Ctrl + Win: 100 tests of each mode

Tested the installed LightningFlow 0.4.3 engine on the RTX 5070, using the current base.en / float16 configuration and the enabled personal vocabulary.

**200/200 functional dictation cycles completed: 100 hold-to-talk and 100 double-tap locked recordings.**

- 200 unique completed transcripts persisted and reopened in an isolated test log.
- Left/right Ctrl and Windows keys, both press orders, alternate release orders, retained-modifier/full-release double taps, actual short tap gaps, and repeat key messages were exercised.
- No stuck recording, duplicate result, post-stop audio append, pending job or unclosed stream was detected.
- 300 microphone-stream replays opened and 300 closed, including pause/resume on double taps.
- One model initialized for the entire test and paired benchmark. One cached vocabulary hint remained resident.
- Warm mean process RSS changed by +19.91 MiB between cycles 21–40 and the final 20 cycles. This includes test instrumentation, not just product code.

## Personalized vocabulary

- All 188 imported vocabulary entries were preserved when supplied correctly.
- All 68 automatically capitalized spellings matched their expected forms.
- All 8 active rules passed both a matching-context and an unrelated-context check; number, code and cross-sentence preservation checks passed.
- Every recording used the enabled profile. Hinted silence emitted no text.
- The synthetic technical speech repeatedly recognized the supplied full name, project, dataset, validation acronym and CUDA. The RTX 5070 phrase was misrecognized as “RTX 5000 and 70” by the selected base.en model. The application did not guess a replacement for those numbers. Vocabulary hints do not guarantee recognition of every spoken term.

## Timing

Times below are production dispatcher timings with accelerated replay. They are not physical-keyboard, microphone or text-insertion latency.

| Mode | Start callback median | Stop callback median | Stop callback P95 |
| --- | ---: | ---: | ---: |
| Hold | 0.340 ms | 0.023 ms | 0.036 ms |
| Double-tap lock | 0.340 ms | 0.025 ms | 0.063 ms |

Personalization was then compared on/off in **100 ABBA/BAAB blocks** (50 per synthetic recording, 400 measured decodes). Each block averages two measurements of each condition, balancing linear load drift. All decodes use the same production inference thread and warmed resident CUDA model. Both conditions use the same Clean-mode processing and no LLM. These timings include decoding plus local postprocessing.

| Fixture | Off median / P95 | On median / P95 | Paired median change | 95% bootstrap interval |
| --- | ---: | ---: | ---: | ---: |
| 1 | 155.06 / 215.31 ms | 142.91 / 200.82 ms | -12.19 ms | -17.52 to +0.49 ms |
| 2 | 223.76 / 291.19 ms | 221.22 / 295.80 ms | +11.86 ms | -5.51 to +16.34 ms |

Off/on medians and P95 above use the 100 individual decodes per fixture per condition. Paired changes and bootstrap intervals use the 50 ABBA/BAAB block contrasts per fixture. The practical latency budget used here is an upper 95% bootstrap bound of 5 ms on the paired median increase and no more than 20 ms increase in individual-decode P95 total time. This finite sample cannot prove literally zero overhead or guarantee latency under different GPU loads. The running user app and other GPU processes were left available.

The general fixture met that strict budget; the technical fixture did not. Its paired block median was about 12 ms slower, with uncertainty spanning a small improvement to about a 16 ms penalty. The individual-decode medians were slightly faster with personalization, so the results do not establish a uniform fixed slowdown. They also do not certify the requested zero slowdown.

Local vocabulary postprocessing alone took a median of 0.297 ms for fixture 1, 0.436 ms for fixture 2.

A follow-up randomized probe tested 64, 96, 128 and 192 hint-token budgets, 12 decodes per fixture per budget. No smaller budget was faster on both fixtures; 64/96 tokens also worsened the ordinary fixture WER. The current 192-token budget and chosen base.en model were therefore preserved. [Probe measurements](results/personalization-hint-budget-probe-0.4.3.json).

## Limits and reproducibility

This exercises the packaged production modifier dispatcher and capture/GPU/processing/log pipeline with synthetic PCM replay. No actual Windows keys were injected, no global hook behavior or Start menu behavior was certified, no user microphone was recorded, and no text was inserted into external apps. GUI animation FPS and a 30-minute session were not tested. These are synthetic-speech recognition results, not accuracy on the user’s voice. Personal history and clipboard were untouched.

**144 pytest checks passed** in addition to this soak. No production code or model setting was changed and no application restart was needed.

An initial 200-cycle run completed its recordings and comparisons but its test process failed during CUDA interpreter teardown. A short diagnostic traced the harness problem to using/retaining the inference model on a second thread. The harness now sends benchmark requests through the production inference queue and leaves model ownership on that thread. A shutdown smoke check exited normally, and the entire 200-cycle suite was repeated with that correction. The current report is the repeated run; the initial raw measurements are retained separately.

Run from the project directory:

```powershell
.venv\Scripts\python.exe -m tests.ctrl_win_soak --per-mode 100 --manifest C:\privateixtures.json --output results\ctrl-win-soak-local.json
```

The manifest points to mono 16 kHz PCM16 WAV files and UTF-8 reference texts. It needs an installed packaged engine, local model and an enabled personal profile. Test logs remain under the workspace work directory. Reports contain aggregate measurements, not personal profile contents or complete transcripts.

[Raw cycles and paired timings](results/ctrl-win-soak-100-each-0.4.3.json) · [Vocabulary rule checks](results/personalized-vocabulary-regression-0.4.3.json)
