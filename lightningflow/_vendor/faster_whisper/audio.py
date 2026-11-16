"""PCM WAV decoding for LightningFlow; no PyAV or FFmpeg dependency.

Microphone input is already float32 16 kHz. File benchmarks intentionally
accept only PCM16 WAV at the target sample rate to keep the dependency set
permissive and the measurement reproducible.
"""
import wave
import numpy as np

def decode_audio(input_file, sampling_rate=16000, split_stereo=False):
    if hasattr(input_file, '__fspath__'):
        input_file = str(input_file)
    with wave.open(input_file, 'rb') as stream:
        if stream.getsampwidth() != 2 or stream.getframerate() != sampling_rate or stream.getcomptype() != 'NONE':
            raise ValueError(f'Use uncompressed PCM16 WAV at {sampling_rate} Hz; compressed audio/resampling is outside this slice.')
        channels = stream.getnchannels()
        samples = np.frombuffer(stream.readframes(stream.getnframes()), dtype='<i2').astype(np.float32)/32768.
    samples = samples.reshape(-1, channels)
    if split_stereo:
        if channels != 2:
            raise ValueError('Stereo separation requires a two-channel PCM WAV.')
        return samples[:,0].copy(), samples[:,1].copy()
    return samples.mean(axis=1)

def pad_or_trim(array, length=3000, *, axis=-1):
    if array.shape[axis] > length:
        array = array.take(indices=range(length), axis=axis)
    if array.shape[axis] < length:
        widths = [(0,0)] * array.ndim
        widths[axis] = (0, length-array.shape[axis])
        array = np.pad(array, widths)
    return array
