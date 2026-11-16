import threading
import wave
import numpy as np
import pytest
from lightningflow.cli import parser
from lightningflow.app import Dictation, Session
from lightningflow._vendor.faster_whisper.audio import decode_audio

def test_wav_loader_does_not_silently_resample(tmp_path):
    path = tmp_path/'input.wav'
    with wave.open(str(path),'wb') as stream:
        stream.setparams((1,2,48000,0,'NONE','not compressed'))
        stream.writeframes(np.zeros(480,dtype='<i2').tobytes())
    with pytest.raises(ValueError,match='PCM16 WAV'):
        decode_audio(str(path))

def test_no_gpu_never_uses_cpu(monkeypatch,tmp_path):
    import ctranslate2
    from lightningflow.asr import CudaASR
    (tmp_path/'model.bin').touch()
    monkeypatch.setattr(ctranslate2,'get_cuda_device_count',lambda:0)
    with pytest.raises(RuntimeError,match='No CPU fallback'):
        CudaASR(tmp_path)

def test_missing_model_requires_explicit_prepare(tmp_path):
    from lightningflow.asr import CudaASR
    with pytest.raises(RuntimeError,match='prepare command'):
        CudaASR(tmp_path)

def test_microphone_failure_is_recoverable(monkeypatch):
    from lightningflow import app
    instance=Dictation(parser().parse_args(['run']))
    def denied(**kwargs):
        raise RuntimeError('Access denied')
    monkeypatch.setattr(app,'input_options',lambda _: {})
    monkeypatch.setattr(app.sd,'InputStream',denied)
    session=Session(None)
    instance.commands.put(('start',session))
    worker=threading.Thread(target=instance.capture)
    worker.start()
    try:
        kind, same, chunk=instance.jobs.get(timeout=2)
        assert kind=='finish' and same is session and 'Access denied' in session.error
    finally:
        instance.quit.set()
        worker.join(timeout=2)
    assert not worker.is_alive()

def test_cancel_cannot_insert_or_keep_audio():
    instance=Dictation(parser().parse_args(['run']))
    session=Session(None,cancelled=True,text='Do not insert',raw=[np.ones(320)])
    def forbidden(*_):
        pytest.fail('cancelled session tried to insert')
    instance.guard.insert=forbidden
    instance.deliver(session)
    assert not session.raw

def test_duplicate_shortcuts_rejected():
    args=parser().parse_args(['run','--retry-vk','0x77'])
    with pytest.raises(ValueError,match='distinct'):
        Dictation(args)
