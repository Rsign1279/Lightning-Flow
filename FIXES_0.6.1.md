# LightningFlow 0.6.1 — isolated GPU failure handling

## Diagnosis

Local analysis of the original crash dump resolved the native stack to `ucrtbase!abort` / `terminate`, through `CudaAsyncAllocator::free`, `StorageView::~StorageView`, `WhisperReplica::encode` and CTranslate2's worker thread. Exception `0xc0000409`, subcode 7, was a fatal application exit after a C++ exception in cleanup. The Windows NVIDIA TDR reset preceded the abort. The application crash mechanism is identified; the original hardware/driver timeout trigger remains unproven.

The installed [CTranslate2 allocator implementation](https://github.com/OpenNMT/CTranslate2/blob/v4.8.5/src/cuda/allocator.cc) can throw during asynchronous frees. Its [storage destructor](https://github.com/OpenNMT/CTranslate2/blob/v4.8.5/src/storage_view.cc) calls that free operation. Python exception handling in the same process cannot catch this native termination. An isolated lost-context probe also showed failure with the alternative CUB allocator, so no allocator substitution was shipped.

## Fix

- Move resident GPU inference into an owned hidden child, preserving the existing CUDA model, precision, language, prompt handling, beam size, VAD and authoritative segmentation.
- Use bounded framed pipes and exact float32 audio. Preserve one model initialization during normal operation; no per-recording process/model reload.
- Own the actual interpreter before GPU initialization, including Windows Store launcher cases. Close its Windows job on shutdown or timeout.
- Detect unexpected native exits even between requests. Latch the runtime as failed, stop capture, retain audio/text and finalize outstanding sessions without automatic insertion or CPU fallback.
- Cover pipe writes as well as decoding with the inference deadline; a hung child cannot block the recording controller indefinitely.

## Evidence and limits

293 automated regression tests pass locally. Actual CUDA integration compared eight paired decodes per hint condition (32 total decodes) and obtained identical text with and without vocabulary hints. The sample's WER stayed 4.17%. A deliberate exit of the test-owned GPU child in each Ctrl+Win mode preserved captured audio and text, closed the microphone, kept control/capture threads alive and attempted no external insertion. Suspending an idle test-owned GPU interpreter exercised the complete timeout, including a blocked pipe write; it terminated that child and retained the parent in 384 ms with a 300 ms test deadline plus termination overhead.

The final 200-cycle test passed 100 hold and 100 hands-free recordings, with one model initialization, 200 persisted log records and zero post-stop audio appends. It ran concurrently with the long-audio test. Hold stop-to-result median/p95/max were 237/525/738 ms; hands-free were 219/478/915 ms. The 500 ms goal was not met at hold p95 under this concurrent load. The direct/isolated request comparison measured medians of 232/261 ms without a hint and 210/204 ms with a hint; eight pairs per condition and one synthetic fixture do not establish a universal speed ranking. These request timings include preprocessing/transport and exclude physical microphone, keyboard and external editor insertion.

Two complete isolated long runs processed 1,800 audio seconds per mode. The final run used one resident small.en / int8_float16 CUDA model, produced identical 27,014-character transcripts and final spoken markers, released delivered audio and observed zero post-stop audio appends. Windows event-log counting found **zero NVIDIA TDR events during the final run**. Stop-to-result was 57.8 ms for hold and 20.4 ms for hands-free, excluding external insertion. Actual wall times were 370.5 and 265.2 seconds with requested 0.08-scale pacing and concurrent tests; these are 30-minute audio durations, not 30-minute live microphone sessions. Peak sampled controller RSS was 185.6 MiB; summed process-tree RSS was 940.2 MiB, including shared pages counted per process. Physical Windows-key interception and human-speech accuracy remain separate validation. The passing packaged self-check exercised real CUDA startup and all nine screens in both themes.

The raw crash dump, debugger files, private paths and private vocabulary are excluded from publication. Windows denied access to the privileged kernel TDR reports in this session; the application dump was available for the abort diagnosis. The implementation does not change NVIDIA drivers, clocks, power settings or the Windows TDR registry. [Microsoft's TDR documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/timeout-detection-and-recovery) describes the OS reset mechanism; passing a finite test does not establish that all future driver resets have been eliminated.

## Reproduce

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m tests.gpu_isolation_integration
.venv\Scripts\python.exe -m tests.ctrl_win_soak --manifest benchmarks\manifest.json --model small.en --compute int8_float16 --per-mode 100 --pairs 20 --output results\ctrl-win-final-0.6.1.json
.\benchmarks\Generate-Long-Marker.ps1
.venv\Scripts\python.exe -m tests.long_recording_integration --seconds 1800 --speed 0.08 --output results\long-recordings-0.6.1.json
```
