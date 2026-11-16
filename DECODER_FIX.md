# RTX identifier and decoder latency fix — 0.4.4

The final transcription now renders the observed `RTX 5000 and 70` and streamed `RTX 500070` recognition variants as **RTX 5070** in singular hardware context. This requires that the target model already exists in the enabled personal vocabulary. The same rule preserves RTX 5090 as 5090. It does not replace bare numbers, quoted/explicit literal strings, code, separate-card lists, plural constructions or unrelated numeric measurements. The raw ASR text remains available in history.

This is a narrow identifier correction, not acoustic training or a general number rewrite. No model number is inferred from the installed GPU. Unknown model spellings are not mapped to the nearest known card.

## Latency change

Personalized decoding now skips timestamp tokens that LightningFlow does not consume. Audio segmentation, model, FP16 precision, 192-token hint, cache, GPU residency and greedy decoding stay unchanged. When no hint is present, the released decoder mode is retained: an experimental change to that path was rejected after a synthetic regression.

The final comparison used one warmed base.en / FP16 CUDA model, 100 balanced six-decode blocks (600 measured decodes), and the two original synthetic recordings. Paired deltas include GPU decoding and local text processing; negative means faster.

| Recording | Old personalized median | New personalized median | Paired change vs old personalized | 95% bootstrap interval |
| --- | ---: | ---: | ---: | ---: |
| 1 | 182.7 ms | 160.5 ms | -20.9 ms | -31.0 to -15.7 ms |
| 2 | 288.2 ms | 253.7 ms | -29.8 ms | -42.7 to -21.8 ms |

The new personalized path also beat the old no-personalization path on both recordings. Both confidence-interval upper bounds were below zero and P95 improved. This clears the previous practical budget: upper 95% median-penalty bound ≤5 ms and P95 penalty ≤20 ms. This is measured improvement on these samples, not a promise of zero latency under every GPU load. Other GPU processes were left available.

## Accuracy and controls

- **184 automated checks passed**, including the existing gesture, input safety, privacy and personalization regressions and new identifier/decoder cases.
- **26 base.en synthetic recordings** (14 clean, 12 with 20 dB noise, 1.1× playback speed or lower volume) had no worse word error rate than the released implementation, with personalization both enabled and disabled. The technical RTX 5070 and RTX 5090 recordings now have the intended identifiers. Some other recognition errors still exist; this does not certify accuracy on the user's voice.
- The optional tiny.en model also showed no worse WER on the 14 clean recordings. Hinted silence emitted no text.
- **100 hold-to-talk + 100 double-tap locked replay recordings passed**, with 200 unique completed log entries, one model load, balanced stream opens/closes, no stuck recording, duplicate completion, pending job or post-stop append. The long technical recording was streamed in both modes, with **20/20 explicit RTX 5070 checks passing**. Four focused recordings additionally verified the final no-hint decoder policy and clean shutdown.
- Hotkey, capture/segmentation, focus/input/clipboard, gesture and delivery-worker source files are byte-for-byte unchanged from installed 0.4.3. The current model, vocabulary, history and shortcut preferences are preserved.
- Hidden native UI construction passed in Light and Dark. No user microphone, clipboard or external app text field was used for these tests. Physical Windows-key/hook and Start menu behavior and a 30-minute recording remain manual checks.

## Reproduce and evidence

Run `.venv\Scripts\python.exe -m pytest -q`. To repeat the local synthetic decoder comparison, use a manifest of mono 16 kHz PCM16 WAV and UTF-8 reference files:

```powershell
.venv\Scripts\python.exe -m scripts.evaluate_decoder_update --manifest C:\private\fixtures.json --baseline-engine C:\private\released-engine --output results\decoder-validation.json --repeats 1 --blocks 100
```

Preserve the 0.4.3 engine when comparing a newer candidate. The comparison leaves model ownership on one thread and uses no cloud service. Private recordings, full transcripts and personal profile contents are excluded from aggregate reports and release archives.

[Final consolidated evidence](results/rtx-final-validation-0.4.4.json) · [Final accuracy policy](results/rtx-final-policy-validation-0.4.4.json) · [Raw timed comparison](results/rtx-timed-decoder-comparison-0.4.4.json) · [200-cycle control soak](results/rtx-control-soak-0.4.4.json) · [Control-path integrity](results/control-path-integrity-0.4.4.json).
