# 0.5.0 fixes and validation

This release addresses demonstrated defects from the November 15, 2026 review. Results are scoped measurements, not guarantees of perfect accuracy, meaning preservation or universal editor support.

## Priority fixes

- **Meaning preservation:** the optional formatting guard now requires an ordered semantic-token match rather than allowing partial word overlap. Removing `no`, `only`, modal/quantifier words, role prepositions, operators, names or numbers is rejected. Literal quotes/code are protected. Regression tests reproduce both audit failures. This intentionally restricts general-purpose rewriting.
- **Spoken corrections:** Clean mode resolves explicit same-type date/time/number corrections such as `tomorrow, actually Friday` and `8000, no, 8080`. Known vocabulary alternatives, including multiword names, require both alternatives to be known. Ambiguous/negated/literal speech stays unchanged. Verbatim keeps restarts; raw ASR is retained separately.
- **Spacing:** a collapsed-caret insertion adds conservative prose separators without modifying surrounding text. Explicit whitespace, paths/URLs, decimal/identifier continuations, CJK and mid-word insertions are preserved. Regression coverage includes UTF-16 positions around emoji.
- **Delay:** previews use bounded short windows and a replaceable pending request, with real decode/finalization jobs taking priority. The final decoder still uses the original authoritative segmentation and model configuration. Previews are labelled provisional and cannot enter external applications. Optional AI defaults to a nonblocking log suggestion; waiting before insertion is opt-in.

## Additional fixes

- Increased the former 16,000-byte non-native insertion cap to the bounded document verification limit. Exact focus, selection and readback requirements remain.
- A real long-paste test exposed legacy UIA ValuePattern truncation at 4,096 UTF-16 units. The reader now uses full TextPattern only for that compatible-prefix truncation; arbitrary disagreement still fails. The 11,400-character paste then passed full readback in the disposable cross-process provider. This was not a Chrome/Word certification.
- Preferences/profile and history payloads use current-user Windows DPAPI, with legacy migration and integrity checks. Explicit exports and existing backups remain outside this protection.
- Cached Home/Log widgets avoid repeated page destruction/reconstruction. Caches invalidate after settings saves; theme changes still rebuild where needed.
- Added multilingual Whisper model/language selection, opt-in GitHub release checks, packaged self-diagnostics and portable build/test paths. English remains the validated primary language; multilingual quality is unmeasured.
- Model setup pins the publisher's Hub revision and verifies LFS SHA-256 plus Git-object hashes before promoting a staged download. Existing tiny.en weights were checked against actual publisher metadata. These hashes are not independent signatures.
- Complete MIT source, dependencies/notices, installer configuration, CI/release workflows and public contributor/security/privacy guidance are included. Private configuration/history/audio is excluded.

## Observed results

Development machine: Windows x64, RTX 5070, NVIDIA driver 610.88. The main gesture soak used small.en/int8_float16 with enabled vocabulary; only aggregate nonpersonal results are stored.

| Check | Result | Scope |
| --- | --- | --- |
| Automated regression suite | 257 passed | Meaning, correction, spacing, preview bounds, DPAPI, model hash and release-check cases |
| Final Ctrl+Win replay soak | 100 hold + 100 locked passed | Production callbacks, real CUDA, isolated log; not physical keys |
| Model residency | One initialization in 200 sessions | No per-recording reload |
| Stream lifetime | 300 opens / 300 closes; no post-stop append | Includes double-tap pause/resume |
| Replay stop-to-result p95 | Hold 174.9 ms; locked 181.4 ms | Accelerated synthetic replay/scratchpad, not microphone/external input |
| Worker RSS warm change | +0.57 MiB | Finite run; not a leak/VRAM proof |
| Real-time replay first partial | 4,445 ms without preview; 923 ms with preview | Two sessions, same 8.835-second synthetic recording |
| Final text with/without preview | Identical | Two-session check, not human accuracy certification |
| Long clipboard insertion | 11,400 characters verified; 403 ms | Disposable editor forced through real UIA; full readback |
| Hidden Home/Log navigation | 200 switches; median 7.5 ms, p95 13.5 ms, max 49.2 ms | Cached real widgets; not every screen/compositor frame |
| Recording capsule | Median 16.1 ms, p95 17.1 ms, max 23.1 ms | Synthetic levels; no activation/callback errors |
| Desktop pipeline | GUI → IPC → CUDA → scratchpad/history passed | Nine screens, both themes; no callback errors |

A pre-release run also passed 200 gesture sessions before the final versioned run. These do not establish a 100% real-world success rate. The original final audio segmentation and CUDA WhisperModel constructor remain in place; previews add separately bounded work. A preview already executing on the GPU cannot be preempted, so actual latency depends on load. There is no justified sub-300-ms first-partial guarantee.

## Reproduce and evidence

See CONTRIBUTING.md. Reports: `results/ctrl-win-final-0.5.0.json`, `preview-latency-0.5.0.json`, `accessibility-long-0.5.0.json`, `navigation-cache-0.5.0.json`, `animation-0.5.0.json`, and `desktop-integration-0.5.0.json`. Models are installed separately. Physical modifier interception, an actual 30-minute microphone session, broad rich-editor coverage and human-speech benchmarks still need manual validation. Inaccessible/elevated/selected/changing targets can refuse insertion. No finite heuristic proves semantic equivalence. See ROADMAP.md for missing product equivalents and external code-signing/security-assessment requirements.
