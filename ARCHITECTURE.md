# Architecture — 0.6.1

The CustomTkinter Windows GUI owns settings, local history and status. A background control process owns Windows hooks, microphone capture, transcript assembly and guarded insertion. Resident CUDA inference runs in a further isolated child, reached by bounded local pipes. Inference never runs on Tk's event thread or inside the microphone/control process.

The CUDA child reports its actual interpreter PID before loading a model. The control worker verifies ownership and assigns that interpreter to a kill-on-close Windows Job Object before acknowledging initialization; this handles Windows Store Python launchers that can escape a launcher's job. Native stdout is redirected to diagnostic stderr so it cannot corrupt the framed protocol. Exact float32 samples, vocabulary hints, language and existing decoding options pass through the pipe without quantization. A bounded writer and reader enforce the full request deadline, including blocked pipe writes. The model stays loaded across dictations.

A GPU child exit, protocol failure or deadline latches the runtime as failed. Capture stops, already recorded audio/text is retained and queued sessions finalize as recoverable errors. The failed runtime is never reused, no CPU fallback occurs, and incomplete text is not pasted. Export retained audio before restarting the engine; encrypted recovery survives only if it was already enabled and its save completed. This contains the observed native abort; it does not prove that an underlying NVIDIA driver/hardware reset cannot recur.

```mermaid
flowchart LR
  Keys[Hold or double-tap shortcut] --> Capture[WASAPI capture]
  Capture --> Final[Authoritative bounded segments]
  Capture --> Preview[Bounded provisional window]
  Final --> GPU[Resident CUDA model]
  Preview --> GPU
  GPU --> Stable[Final transcript]
  GPU --> UI[Provisional UI only]
  Stable --> Rules[Vocabulary and conservative corrections]
  Rules --> Guard[Focus, document and caret verification]
  Guard --> Editor[Native edit or verified paste]
  Rules --> AI[Optional local formatting]
  AI --> Log[Copyable suggestion in local log]
```

Final segmentation remains 8-second maximum windows with silence endpoints and limited forced-split overlap. Previews start at 0.8 seconds of buffered audio, repeat at bounded intervals over at most four seconds, and use one replaceable pending request. Real jobs have queue priority. Previews cannot change final text or enter external applications. One preview already executing on the GPU cannot be preempted; disabling previews is supported in settings data for controlled benchmarking.

Ctrl+Win uses the ordered low-level modifier dispatcher. Hold release stops capture and discards an in-flight post-release frame. A short first press pauses capture while the double-tap timer runs; the second locks recording, the next press stops it. The basic dispatcher and timing model remain intact.

Meaning preservation uses an ordered semantic token sequence, protected literals, names, numbers and qualifiers. The local deterministic correction pass changes only explicit bounded values or known vocabulary alternatives. This is deliberately narrower than unrestricted language-model rewriting. Raw ASR remains available. The default AI path inserts deterministic text without waiting; optional delayed formatting is stored as a suggestion, never blindly backspaced into another app. An opt-in bounded wait remains available.

Insertion requires an unchanged target, collapsed selection and verified text. Native Edit/Rich Edit uses a target-owned undo transaction. Other supported controls use a temporary clipboard transaction or bounded Unicode events, with readback. No whole-field replacement or automatic focus recovery is used. Rich Edit UTF-16 paragraph offsets, Chromium final-paragraph sentinels and compatible legacy 4096-UTF-16-unit ValuePattern truncation have specific regression coverage. Documents and insertions remain bounded; unsafe or uncertain results are retained.

Settings are written atomically as user-bound Windows DPAPI envelopes. History payloads use the same protection; legacy plaintext rows migrate when opened by the new version. UI Home/Log pages reuse cached widgets. Inference is local-files-only; network access is limited to explicit model/runtime setup, configured loopback AI, and explicit/opt-in GitHub release metadata checks. See PRIVACY.md for the limits of these protections.
