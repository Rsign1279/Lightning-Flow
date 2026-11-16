# Decisions before implementation

Research checkouts: `../../work/research/`. Both primary repositories were present as shallow clones and inspected before application code. No reference application code is copied.

| Reference | Inspected revision | License |
|---|---|---|
| https://github.com/OpenWhispr/openwhispr | cb08c411dd008c57e4f0a8193756d6b5812479fd | MIT, 2024 OpenWhispr Team |
| https://github.com/nayballs/Yap | ede2ab449073c189f1677f81ade1a3b1d456afb9 | MIT, 2026 nayballs |

OpenWhispr's README/package.json describe Electron/React with native helpers, whisper.cpp and sherpa-onnx. `src/helpers/whisperServer.js` owns a persistent inference server with bounded startup and GPU failure reporting. `parakeetServer.js` splits at pauses and caps segments. `audioManager.js` keeps an AudioContext. `hotkeyManager.js` routes global shortcuts. `clipboard.js` and `resources/windows-fast-paste.c` show why paste modifiers, clipboard lifetime, foreground focus and elevated applications require care. Settings/startup/build live in Electron main-process helpers and electron-builder scripts. Its complete product carries far more services and UI than this loop needs.

Yap's `docs/architecture/dictation.md`, `dictation/mic.rs`, `dictation/stt.rs`, `pasting/text_injector.rs` and Cargo.toml describe CPAL capture, a warm ASR engine, a bounded pre-roll, background partials, dictionary/cleanup/delivery passes and app-specific paste. Mic opens on demand: holding it indefinitely changes Bluetooth headset profiles and burns idle CPU. Current Cargo features use whisper.cpp Vulkan and ONNX Runtime DirectML, not CUDA. Vendored transcribe-rs includes Parakeet DirectML fixes (decoder/joiner/preprocessor placement), so generic claims that Parakeet is entirely on GPU need verification. Tauri handles settings/startup/NSIS packaging. Those systems are intentionally excluded here.

## Selected architecture

Python 3.11 plus ctypes Win32 APIs, PortAudio/sounddevice, NumPy and faster-whisper/CTranslate2. Avoid a desktop web runtime and extra server serialization for the baseline. Main thread runs Windows message pump and lightweight hooks. Separate capture thread opens input only during recording; ASR thread loads once and warms once. Queues and recording duration are bounded. Silence/maximum-duration segmentation allows decoding earlier segments while the user continues speaking; this is chunked incremental decoding, not token streaming. Console partials are provisional; insertion waits for recording end and all segments.

Use CUDA explicitly, validate provider and run a warm-up inference before advertising readiness. Load local models only at runtime; downloads happen only through an explicit prepare command. Baseline tiny.en/base.en FP16 or INT8 must be measured rather than ranked in advance. RTX 5070 driver detected: 610.88; advertised CUDA driver compatibility 13.3 is not itself a CUDA toolkit. Bundle DLL search paths from isolated cuBLAS/cuDNN packages.

Use SendInput Unicode rather than temporary clipboard replacement. Capture foreground window, focused control, caret rectangle, and input/focus epochs at recording start. Reject delivery after typing, clicks, focus changes or a changed caret. Never reactivate a previous window or backspace over existing content. Reject an existing selection in native Edit controls; custom controls remain best effort. Win32 does not provide a transactional cross-application insertion API: an external process can still change its field without observable focus/input. Treat uncertain delivery as recoverable, never retry automatically. Native Ctrl+Z remains target-owned.

Potential bottlenecks: GPU contention (11.6/12 GB initially occupied), CUDA library cold initialization, autoregressive Whisper decoder, device-open latency, forced chunk boundaries and per-character input in long text. Small-model accuracy is not assumed. No claim of Wispr-equivalent quality or a 300ms first partial. Parakeet vs faster-whisper, LLM enhancement, VAD model tuning and broad app compatibility belong to subsequent measured work.
