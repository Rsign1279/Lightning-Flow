# Current release evidence

See [0.6.0 validation](FIXES_0.6.0.md) and its dated JSON reports for current results. The original vertical-slice measurements below are historical and do not describe the current feature set.

# 0.5.0 performance update

Current scoped results are in [FIXES_0.5.0.md](FIXES_0.5.0.md). Earlier reports below describe older releases and are not current universal guarantees.

---

# Hold-only responsiveness (0.3.1)

See DESKTOP_VALIDATION.md for the current measured checks. A deliberate 120-ms threshold rejects taps; release has no double-tap/silence wait. In the callback/replay fixture, stop commands took 0.021–0.024 ms, and captured text completed 11.79–13.24 ms after release. The real widget's isolated median frame was 16.27 ms, with a 51.47-ms hide transition. These scopes exclude physical keyboard/microphone latency and arbitrary target apps.

The earlier reports below are historical evidence, not current feature specifications.

---

# Current desktop performance (0.3.0)

The latest finite-run measurements are in DESKTOP_VALIDATION.md and results/*0.3.0.json. The animated recording capsule measured 16.21-ms median frames, 16.78-ms p95, 21.46-ms max. Real hook gesture tests signaled recording in 20–23 ms with actual CUDA transcription and native external insertion. The 380-character verified clipboard route took 427 ms in its fixture. These are scoped tests, not universal guarantees.

The following original vertical-slice report is retained as historical ASR baseline evidence. Its original feature-scope statements describe that earlier release, not the current desktop app.

---

# Performance report — 2026-11-08

Measured on this Windows PC: Ryzen 5 9600X, approximately 31.14 GiB usable RAM, RTX 5070 (12,227 MiB), driver 610.88, CUDA ASR through CTranslate2 4.8.5. CUDA 12 cuBLAS/cuDNN packages are isolated in .venv. NVIDIA's driver advertises CUDA compatibility 13.3; that is not a toolkit-version claim.

## ASR baseline

Local Windows SAPI synthesized the included 8.835-second, 16-kHz PCM16 fixture. Five sequential decodes per configuration, one resident model per process. Model load and warm-up are excluded from decode timings and recorded separately in JSON. All samples and outliers are retained. Explicit CUDA provider and an actual encoder/decoder warm-up were verified. Silero VAD runs on CPU intentionally.

| Model / precision | Median decode ms | Range ms | Median RTF | Lexical WER | Sampled process peak RSS MiB |
|---|---:|---:|---:|---:|---:|
| tiny.en / float16 | 100.0 | 81.5–631.5 | 0.0113 | 4.17% | 933.7 |
| tiny.en / int8_float16 | 108.8 | 104.8–1155.4 | 0.0123 | 8.33% | 925.6 |
| base.en / float16 | 95.1 | 76.3–113.3 | 0.0108 | 4.17% | 714.7 |

This is a tiny synthetic fixture, not an accuracy dataset. Case/punctuation are normalized; number spellings are not: the only FP16 word discrepancy was “three” → “3”. INT8 also produced “Kuda” instead of “CUDA”. These scores do not mean a human dictation accuracy percentage. No proper-noun/general accent/noise/meaning-preservation result is claimed.

GPU contention is material: other applications, including Ollama, occupied about 11.6–11.8 GiB and device utilization sometimes reached 98–99% before inference. Those applications were not stopped or unloaded. The final sample order slightly favored base.en FP16; earlier runs favored tiny.en FP16. Five contended runs do not establish a robust speed ranking. Tiny.en FP16 remains the minimum-size baseline; base.en FP16 is a selectable alternative. INT8 offered no demonstrated improvement here. Raw earlier measurements mentioned in progress updates were superseded after removing the FFmpeg dependency and regenerating the 16-kHz fixture.

CUDA/VAD load-and-warm time for final benchmark processes was approximately 0.58–0.97 seconds with a warm filesystem. The very first CUDA process earlier in the session took 9.41 seconds. No per-recording model reload occurs. Device-wide sampled GPU memory/utilization is stored in JSON and includes other processes; it is not attributed as LightningFlow peak VRAM. Sampling can miss short spikes. No memory stability/long-session claim is made.

## Microphone and Windows input

- Real webcam microphone, WASAPI: first frame **88.2 ms**, 1-second capture, zero overflows; audio neither saved nor uploaded.
- Initial MME first frame: **3770.6 ms**. The implementation now prefers the matching WASAPI device and uses shared-mode system conversion to 16 kHz. A direct WASAPI 16-kHz open without conversion failed; the final path was validated with conversion enabled.
- Native RegisterHotKey test: **2.48 ms** from synthetic key dispatch to observed WM_HOTKEY. This excludes physical keyboard/OS scheduling before SendInput.
- Native short UTF-16 insertion dispatch: **16.78 ms**. Entire test string read back from the new Edit control. Clipboard sequence unchanged; duplicate shortcut conflict, stale target and selected text replacement tested.
- Final application integration: registered toggle → accelerated PCM replay → real resident CUDA → guarded SendInput → **entire transcript read back**, passed. Observed stop-hotkey-to-complete-text **332.1 ms** in that artificial test; the source was replayed at 0.15× wall time. It is not a microphone end-to-end latency measurement. The test contains no fake inference and no production replay backend.
- Earlier desktop tests refused delivery when real user input/focus changed. This was correct guard behavior. Tests now keep the visible fixture brief; physical microphone speech recognition still requires an intentional human check.

## Verification and scope

11 automated tests passed: segmentation boundaries/limits, duplicate handling, WER/CER arithmetic, 64-bit SendInput layout, invalid WAV format, no-GPU rejection without fallback, missing model, denied microphone recovery, cancellation and shortcut collision. Native desktop and CUDA replay integration passed separately. Python compilation and wheel build succeeded. Both downloaded models matched their local SHA-256 installation manifests; no independent publisher checksum was available/claimed.

First partial under 300 ms is **not met** by this chunked architecture; endpointing can wait for 500 ms silence or up to eight seconds of speech before decoding a chunk. Console partials are not external live token streaming. No polished UI, Parakeet comparison, AI cleanup, hold-to-talk, installer validation, broad application compatibility, human-speech WER or extended memory soak was included in this requested vertical slice.

## Reproduce

See README.md for exact benchmark/test commands. Use the included fixture and reference to repeat the recorded workload. `benchmarks/Generate-Fixture.ps1` can regenerate it offline; the installed SAPI voice may change the waveform. Private PCM16 16-kHz WAV files and reference text can be passed to the same benchmark command. Re-run with lower GPU contention before choosing a model for everyday use; the application never changes other GPU processes itself.
