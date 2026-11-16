# LightningFlow 0.6.0

## Behavior changes

The next recording can start while an earlier dictation finishes. Up to three sessions remain outstanding, delivered in capture order. Holding Ctrl+Win for a newer recording defers earlier external insertion until modifiers are released. A verified insertion advances a queued target only when its captured document, caret, focus, process and input epoch exactly match. User edits or focus changes still cause refusal and recovery; the app never restores an old target's focus.

Finishing an older result no longer resets a newer recording's gesture, preview or indicator. The original modifier-chord dispatcher and hold/double-tap state machines remain in use. Capture stops at the release/stop edge; already captured speech still needs final decoding.

Read, resume and close failures finalize already captured audio instead of discarding its final segment. Interrupted speech is transcribed and retained for review, not automatically inserted as a completed sentence.

Privacy settings now offer encrypted failed-recording recovery, disabled by default. Background storage preserves float32 samples exactly, capped at five recordings and 1 GiB. A manifest commits only completed saves. Turning recovery off or clearing history cancels pending saves and deletes stored recordings. Committed recordings can be reloaded after restart and explicitly retranscribed on the resident CUDA worker into the log. No recovered text is automatically pasted. Ongoing microphone capture and uncommitted saves are not crash-proof.

## Validation

- 282 automated regression tests passed locally, including ordered queue delivery, rapid three-session command bursts, target rebasing, failure finalization, DPAPI roundtrip, corruption refusal, storage bounds, path validation and clear-during-save cancellation.
- `results/ctrl-win-final-0.6.0.json`: 100 hold and 100 hands-free sessions, actual small.en / int8_float16 CUDA, one model initialization, 200 unique persisted log records, 300 stream opens/closes, zero post-stop audio appends. Stop-to-result p95 was 167.0 ms for hold and 159.5 ms for hands-free. These are accelerated synthetic scratchpad timings, excluding external insertion and physical microphone/keyboard behavior. Warm process RSS mean changed by +0.15 MiB in this run.
- Personalization stayed enabled on all 200 recordings; the public five-term example profile's canonical spellings and vocabulary were preserved. On/off paired checks retained the same synthetic WER, with no observed added total latency. This does not establish accuracy or latency for every term in a private profile or human recording.
- `results/queue-recovery-0.6.0.json`: two actual-CUDA dictations queued while decoding was deliberately held; ordering and identical text verified. A simulated microphone disconnect retained 8.84 seconds of audio and text, saved encrypted chunks, dropped the RAM copy, reloaded and retranscribed identical text on the same model. No external input was permitted.
- The live indicator ignored late microphone-open events from old sessions, and reaching the recording limit reset capture state without waiting for ASR. Unexpected native engine exits now retain available previews in the desktop log, explicitly marked incomplete/provisional; they are never auto-pasted.
- Packaged self-check passed actual CUDA startup and all nine screens in both themes. The GUI/IPC/GPU integration passed transcription, history, nonactivating overlay and simulated native-exit preview recovery with no callback errors. Synthetic indicator animation measured a 16.1 ms median frame interval and 17.7 ms p95; the maximum was 40.8 ms. Hidden Home/Log switching measured 7.7 ms median, 36.2 ms p95 and 91.8 ms maximum under concurrent GPU testing; this does not meet a universal 16 ms UI target.

One long-replay attempt at 0.08 wall scale terminated natively. Windows logged an NVIDIA `nvlddmkm` TDR reset/restart and a Python `ucrtbase.dll` failure with exception `0xc0000409` at the same time. The last progress report was 1,674.2 audio seconds, with 24 pending jobs. This attempt is a failure, retained in `results/long-recording-interruption-0.6.0.json`; it is not counted as a completed recording. The underlying driver timeout cause is unresolved, and neither retries nor a successful separate run establish that it is fixed. No driver/TDR registry changes or CPU fallback were applied. Live audio in a natively terminated worker is still subject to the retention limits described above.

The earlier development run completed 1,800 seconds of synthetic audio in each mode, retained the distinct final marker, produced identical 27,014-character transcripts (synthetic WER 4.16%), released audio and used one CUDA model. It predates the final recovery/UI changes and version bump; `results/long-recordings-development-0.6.0.json` preserves that distinction. Its approximately 197 seconds per mode are accelerated wall times, not 30 minutes of live microphone use. Its stop timing included reference scoring and is not an insertion-latency measurement. A later 0.12-scale rerun completed hold assertions and reached 695.3 seconds of locked audio before its process/session disappeared, without a new matching Windows crash/TDR event; the cause is unverified. That incomplete attempt is separately recorded and is not a final-build pass. Long-session stability therefore remains unresolved.

The authoritative Segmenter, CUDA model/loading configuration, precision selection, vocabulary processing and chord dispatcher are unchanged from 0.5.0. The full existing meaning-preservation, spoken-correction and spacing regression suite remains enabled.

## Reproduce

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m tests.ctrl_win_soak --manifest benchmarks\manifest.json --model small.en --compute int8_float16 --per-mode 100 --pairs 20 --output results\ctrl-win-final-0.6.0.json
.venv\Scripts\python.exe -m tests.gpu_queue_recovery
.\benchmarks\Generate-Long-Marker.ps1
.venv\Scripts\python.exe -m tests.long_recording_integration --seconds 1800 --speed 0.08
```

The long-recording tool streams 30 minutes of synthetic PCM per mode with a distinct final spoken marker. `--speed 1` requests real-time replay; smaller values accelerate that same audio duration. Physical Windows-key interception, real microphones, human accuracy, all-editor compatibility, certificate signing, enterprise assessment and the broader product features listed in ROADMAP.md remain separate work. No Wispr head-to-head superiority or universal correctness is claimed.
