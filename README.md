# LightningFlow

**Open-source, local-first Windows dictation with resident NVIDIA GPU transcription.**

Hold a shortcut, speak, release, and insert text into a supported focused editor. Double-tap for hands-free recording. No account or subscription. Original application code is MIT licensed.

LightningFlow is an independent project. It does not use Wispr Flow code, branding, assets or private services. It is an early release, not a promise of perfect recognition or universal app compatibility.

## What works

- Native desktop window, tray integration, light/dark themes and a nonactivating audio-responsive recording capsule. Normal use needs no terminal.
- Persistent faster-whisper/CTranslate2 CUDA inference in an owned isolated child. The app refuses silent CPU fallback.
- Hold-to-talk, double-tap hands-free, release-to-stop, cancellation and explicit retry. Choose Ctrl+Win in Settings / Shortcuts; fresh profiles default to Ctrl+Alt+F8 until changed.
- Start a new recording while earlier transcription finishes; a bounded queue preserves delivery order and verifies the target again.
- Provisional live previews; final recognition retains the larger audio windows and only verified final text is inserted.
- Personal vocabulary, explicit corrections, Clean/Verbatim modes and conservative spoken date/time/number corrections. Code, quotes and ambiguous corrections are preserved.
- Guarded native/clipboard/Unicode insertion, prose-boundary spacing, clipboard preservation and recoverable failures. No blind automatic retries or focus restoration to an old application.
- Optional loopback Ollama or llama.cpp formatting. Default delivery does not wait: later edits are copyable suggestions in the log. Waiting within a configured budget is an explicit option.
- Windows-user DPAPI-protected settings and optional transcript history. No telemetry or automatic audio uploads. Release checks are opt-in; installers never execute automatically.
- Opt-in encrypted recovery for completed failed recordings, with explicit retranscription on the resident GPU into the log. Live microphone capture is not crash-journaled.
- English and multilingual Whisper model choices. Multilingual recognition requires a multilingual model; English-specific cleanup is disabled for other languages. Non-English quality has not been benchmarked here.

## Install

Use an installer from [GitHub Releases](https://github.com/Rsign1279/Lightning-Flow/releases), when available. **Current builds are unsigned.** Check the published SHA-256; a checksum is an integrity check, not a trusted publisher signature.

Windows 11 x64, Python 3.11/3.12 x64 or uv, a compatible NVIDIA driver and CUDA-capable GPU are required. The installer creates a local runtime; NVIDIA packages can require roughly 1.4 GB of initial downloads. Choose/download a speech model explicitly during onboarding. After setup, dictation works offline. Close other dictation apps using the same shortcut before running LightningFlow.

## Build from source

```powershell
git clone https://github.com/Rsign1279/Lightning-Flow.git
cd Lightning-Flow
.\Setup.ps1 -Model tiny.en
.\Build.ps1
.\Build-Desktop.ps1
.\Build-Installer.ps1
```

Open `LightningFlow.vbs` or `desktop-dist\LightningFlow\LightningFlow.exe`. Build output is ignored by Git. `Setup.ps1` is the explicit dependency/model download step; it uses uv if installed and otherwise Python/pip. Source, tests, model verification, build scripts and installer configuration are included. Large speech weights and NVIDIA runtimes are installed separately under their upstream licenses.

## Validation

293 automated tests pass locally. The 0.6.1 CUDA replay run passed 100 hold and 100 hands-free sessions with one model initialization and zero audio appends after stop. A final long run processed 30 minutes of synthetic audio in each mode with matching transcripts and zero observed NVIDIA TDR events. Native GPU-child exits in both modes retained captured audio/text, and direct/isolated decoder comparisons produced identical test output. These were synthetic PCM and production gesture callbacks, not physical Windows-key injection or human-speech accuracy certification. See the release evidence for timing scope, concurrent-load results and the remaining driver-reset uncertainty.

See [0.6.1 GPU crash handling and evidence](FIXES_0.6.1.md), [0.6.0 fixes](FIXES_0.6.0.md), [0.5.0 fixes](FIXES_0.5.0.md), [architecture](ARCHITECTURE.md), [installation](INSTALLATION.md), [privacy](PRIVACY.md), [security](SECURITY.md), [contributing](CONTRIBUTING.md), and [license notices](LICENSE_NOTICES.md).

## Known boundaries

Cross-application editing is not atomic. Moving the caret, changing focus or editing the document may deliberately block insertion; recover the text from the app. Password/read-only/inaccessible/elevated fields can refuse delivery. Physical Ctrl+Win, broad editor coverage, real human accuracy and 30-minute wall-clock recording still need manual validation. The original NVIDIA reset triggered a native allocator-cleanup abort. Version 0.6.1 isolates native GPU failure and retains capture/text; the underlying driver-reset trigger remains unproven. Parakeet and whisper.cpp are not implemented. There is no meeting notetaker, cloud sync or team account service. General-purpose prose rewriting is intentionally constrained to preserve content. A trusted code-signing certificate and an independent security review are not included.

Original source: [MIT](LICENSE). NVIDIA CUDA libraries and Windows are external proprietary platform dependencies; this does not make the entire GPU/OS stack open source.
