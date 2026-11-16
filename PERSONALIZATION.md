# Personal vocabulary — 0.4.3

The supplied version 1.0 bank imports **188 unique terms** and **8 reviewed contextual rules**. JSON is the structured source; the compact TXT ranks recognized vocabulary terms. Markdown is reference prose. Biography, remembered metrics, speech-pattern instructions and arbitrary document instructions are not sent to Whisper or the cleanup model. No acoustic model is trained.

## Use

Open **Dictionary → Personal vocabulary** to import the JSON. A sibling `whisper_initial_prompt.txt`, when present, ranks vocabulary already in that JSON. An exported normalized profile can also be reimported. Enable/disable, export and remove controls are on the same screen. Import does not upload the profile or download a model.

Open **Writing style** to select:

- **Clean**: remove standalone hesitation sounds locally. Keep meaningful words such as “like,” “right,” “actually,” negation, uncertainty, emphasis and spoken restarts. Broader grammar editing remains optional through the existing explicitly configured local AI provider, subject to preservation checks and timeout.
- **Verbatim**: retain fillers, restarts and repetitions, bypass AI rewriting, and still apply enabled preferred vocabulary and explicit dictionary rules. This retains Whisper's wording; it does not guarantee that the acoustic recognition itself is exact.

Completed log entries retain **raw ASR text** alongside the processed text. Personalization uses a snapshot for each recording; edits apply to the next recording. No live external-field revision is introduced.

## Correction policy

Known spellings receive exact capitalization where safe. Ambiguous project names and phonetic aliases require nearby context in the same clause. Code fences, inline code and partial underscored/hyphenated identifier matches are excluded from imported corrections. The manual dictionary remains a separate user-authored exact replacement feature.

Four suggested rules are deliberately not activated: the two endpoint rules add an unspoken acronym, one abbreviates a full institution name, and one maps an ordinary word to a person's name without sufficient evidence. These need explicit user correction rather than a fuzzy global substitution.

**Teach a correction** saves an exact heard phrase, preferred spelling and required nearby context phrase only when the user presses Save. Corrections do not cascade and cannot change digit values. They can be removed individually or exported with the profile. There is no unsupervised learning, automatic harvesting from other apps, or additional audio retention.

## GPU and latency

Whisper receives an `initial_prompt` capped at **192 actual tokenizer tokens**, keeping the highest-priority terms first. Tokenization explicitly excludes special control tokens. Tokens are cached for at most four distinct hints. No forced text prefix is used. The existing CUDA model, FP16 configuration, streaming segmentation and GPU residency stay in place; personalization adds no model reload or cloud dependency.

The 188-term bank exceeds Whisper's bounded context, so not every term fits in each decode. ASR hints are a bias, not a guarantee; disable the profile and compare on corrected recordings if it hurts your speech. Profile data resides in per-user local settings and is excluded from the desktop bundle, installer, wheel, source archive and public benchmark output. Exported profiles are plaintext files chosen by the user. Removing the profile does not erase separately saved transcript history or the user's original input files.

## Observed validation

- **144 automated checks passed**, including 30 personalization regressions.
- Hidden native UI construction passed in Light/Dark on Home, Dictionary, Writing style, Shortcuts and Settings.
- **10 personalized replay dictations** completed: 5 holds and 5 locked recordings, 10 persistent test log entries, one real resident CUDA model initialization. No global key injection, user microphone capture, clipboard mutation or external text insertion was used.
- Two synthetic recordings were decoded three times with and without the profile using `tiny.en`, FP16, actual CUDA. Median decoder times: fixture 1 baseline **70.2 ms**, personalized **57.9 ms**; technical fixture baseline **91.9 ms**, personalized **80.7 ms**. This small sample does not establish a general speed improvement.
- Raw normalized WER on the technical synthetic fixture was **0.2414** without hints and **0.0690** with hints. The existing synthetic fixture remained **0.0417** in both modes. These are synthetic-speech results, not accuracy on the user's voice. Digit-vs-word variants count as WER differences; strict digit matching is reported separately. Postprocessing preserved recognized digits in every comparison. Hinted silence emitted no text.
- Real microphone accuracy, physical Ctrl + Win behavior, Windows Start menu behavior, and a full 30-minute recording still require manual validation. The Ctrl + Win update remains included; it stops capture on hold release and supports double-tap lock/next-tap stop.

Raw aggregate evidence: [GPU comparison](results/personalization-0.4.3.json), [pipeline](results/personalized-pipeline-0.4.3.json), [UI](results/personalization-ui-0.4.3.json). Private names, prompts, source bank, synthetic personalized audio and transcripts are not in these reports.

## Reproduce locally

Run `.venv\Scripts\python.exe -m pytest -q` from the project directory. For a private GPU comparison, use:

```powershell
.venv\Scripts\python.exe -m scripts.benchmark_personalization --bank C:\private\bank.json --prompt C:\private\whisper_initial_prompt.txt --manifest C:\private\fixtures.json --models models --output results\personalization-local.json
```

The manifest is an array of objects with `audio` and `reference` file paths. Audio must be mono 16 kHz PCM16 WAV, and each reference is a UTF-8 text file. The script reports aggregate errors and timings without including profile contents or transcripts. Use real corrected speech before judging individual recognition accuracy.

Build the staged desktop with `powershell -NoProfile -ExecutionPolicy Bypass -File Build-Desktop.ps1 -Output desktop-next`, then build its installer with `Build-Installer.ps1 -Release desktop-next\LightningFlow`. Models and private settings are not embedded in the installer.
