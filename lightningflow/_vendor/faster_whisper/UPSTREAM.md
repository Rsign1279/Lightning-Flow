# Vendored dependency

faster-whisper 1.2.1, SYSTRAN, MIT: https://github.com/SYSTRAN/faster-whisper/tree/v1.2.1

Source taken from the published faster-whisper 1.2.1 wheel. Original license is adjacent. Imports are namespaced into `lightningflow._vendor.faster_whisper`. `audio.py` is replaced with a small PCM16 WAV reader using Python's standard library and NumPy. No PyAV or FFmpeg is installed or required. Live transcription receives NumPy arrays.

The Silero VAD v6 ONNX asset ships unchanged from that wheel. Silero VAD is MIT: https://github.com/snakers4/silero-vad . Its license is included separately. The ASR runs on CUDA; the lightweight Silero VAD runs on CPU intentionally, not as an ASR fallback.

Model inference and feature extraction otherwise retain the upstream implementation. This adaptation removes general media import in exchange for a permissive dependency set for the dictation slice.
