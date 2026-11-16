# Changelog

## Unreleased — private GPU diagnostics

- Add a one-file, data-only, hash-verified WATCHDOG export helper with a hidden UAC launcher and isolated fixture tests.
- Exclude memory dumps and raw Windows trace/event reports from Git.
- Publish the redacted kernel investigation: the original NVIDIA timeout is confirmed; its underlying trigger remains unresolved. CUDA decoding and Ctrl+Win behavior are unchanged.

## 0.6.1

- Isolate resident CUDA inference in a hidden owned interpreter so native failures cannot terminate microphone capture and shortcut handling.
- Own the actual interpreter before GPU initialization, including Windows Store Python launcher cases.
- Preserve exact float32 transport, recognition model, precision, VAD, vocabulary and decoding settings.
- Bound complete inference requests, including pipe writes; latch failed runtimes, stop capture, retain audio/text and prevent incomplete insertion or CPU fallback.
- Add native-child-exit tests for both Ctrl+Win modes, blocked-pipe timeout tests, direct/isolated decoding comparisons and long-run NVIDIA event monitoring.
- Preserve the original crash evidence and distinguish the identified application abort from the unproven driver-reset trigger.

## 0.6.0

- Accept the next recording while prior transcription finishes, with a three-session ordered queue. Confirmed insertion can advance only identical captured targets; changed fields still refuse delivery.
- Stop release-to-record gestures immediately while keeping earlier results from resetting a newer recording indicator.
- Finalize already captured speech after microphone read, resume or close failures; retain incomplete dictation for review rather than pasting a cutoff sentence.
- Add opt-in Windows-user-encrypted recovery for completed failed recordings, exact float32 audio, bounded background storage, clear-during-save cancellation and explicit GPU retranscription into the log.
- Correct privacy/restart messaging and report recovery eviction. Preserve the existing GPU decoder, precision, model residency, authoritative segmentation and modifier-chord dispatcher.
- Retain explicitly incomplete previews after native engine exits; allow recovery-file deletion even with the engine offline. Report the unresolved driver-reset event encountered during long testing.
- Add reproducible long-audio, queued-session and device-fault integration tools. See FIXES_0.6.0.md for measured results and validation limits.

## 0.5.0

- Reject meaning-changing deletion of negation, qualifiers, content words or operators; retain ordered semantic evidence.
- Resolve explicit bounded spoken date/time/number and known-vocabulary corrections locally; preserve literals/ambiguous speech and Verbatim restarts.
- Add conservative insertion-boundary spacing and raise the former 8,000-code-unit transcript cap while retaining document/readback bounds.
- Handle compatible legacy ValuePattern truncation without discarding complete TextPattern verification.
- Add bounded provisional GPU previews; retain the authoritative segmentation and resident CUDA decoder.
- Default optional AI to background log suggestions; bounded pre-insertion waiting is explicit.
- Protect local preferences/history with Windows-user DPAPI and migrate legacy records.
- Reuse Home/Log widgets, add multilingual model/language selection, publisher-pinned model verification, opt-in release checks and packaged self-diagnostics.
- Include complete source, installer/build scripts, regression/integration tools, Windows CI/release workflows, privacy/security/contribution documentation and upstream licenses.

Earlier development reports remain in the repository as dated evidence; they do not override the current README or establish current performance guarantees.
