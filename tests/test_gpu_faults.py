import queue
import threading
from types import SimpleNamespace
import numpy as np
from lightningflow import app
from lightningflow.app import Dictation,Session
from lightningflow.cli import parser


def test_gpu_fault_latches_and_never_reuses_failed_runtime(monkeypatch):
    calls=[]
    class Faulty:
        provider='CUDA / CTranslate2';load_ms=0
        def __init__(self,*_):pass
        def transcribe(self,*_a,**_kw):calls.append(1);raise RuntimeError('CUDA context was destroyed')
    monkeypatch.setattr(app,'CudaASR',Faulty)
    engine=Dictation(parser().parse_args(['run']));first=Session(None);second=Session(None)
    chunk=SimpleNamespace(audio=np.ones(320,dtype=np.float32),overlapped=False)
    for item in (first,second):engine.enqueue('chunk',item,chunk);engine.enqueue('finish',item)
    thread=threading.Thread(target=engine.infer);thread.start();completed=[]
    try:
        while len(completed)<2:
            kind,value=engine.events.get(timeout=3)
            if kind=='done':completed.append(value)
        assert len(calls)==1 and first.error and second.error
        assert engine.gpu_error and not engine.ready
    finally:engine.quit.set();thread.join(3)


def test_gpu_fault_stops_capture_and_prevents_new_recordings():
    engine=Dictation(parser().parse_args(['run']));session=Session(None)
    engine.ready=True;engine.recording=True;engine.active=session;engine.register_session(session)
    engine.gpu_error='CUDA runtime exited unexpectedly';engine.on_tick()
    assert not engine.ready and not engine.recording and session.capture_until
    assert engine.commands.get_nowait()==('stop',None)
    assert not engine.can_start_recording() and not session.cancelled


def test_preview_native_failure_is_not_silently_ignored(monkeypatch):
    from lightningflow.asr_process import GPUWorkerError
    class Faulty:
        provider='CUDA / CTranslate2';load_ms=0
        def __init__(self,*_):pass
        def transcribe(self,*_a,**_kw):raise GPUWorkerError('CUDA child exited')
    monkeypatch.setattr(app,'CudaASR',Faulty)
    engine=Dictation(parser().parse_args(['run']));session=Session(None)
    engine.previews.put((session,0,np.ones(320,dtype=np.float32)))
    thread=threading.Thread(target=engine.infer);thread.start()
    try:
        while not engine.gpu_error:engine.events.get(timeout=3)
        assert session.error and not engine.ready
    finally:engine.quit.set();thread.join(3)


def test_gpu_failure_before_first_words_does_not_blame_microphone(tmp_path,monkeypatch):
    from lightningflow.desktop.worker import build_backend
    from lightningflow.desktop.state import Preferences,Settings
    path=tmp_path/'settings.json';Preferences(path).save(Settings())
    engine=build_backend(path,tmp_path/'models');messages=[]
    monkeypatch.setattr('lightningflow.desktop.worker.send',lambda kind,**data:messages.append((kind,data)))
    engine.gpu_error='GPU worker stopped. Export retained audio before restarting.'
    session=engine.new_session(None);session.error=engine.gpu_error;session.raw=[np.zeros(320,dtype=np.float32)]
    engine._deliver(session,session)
    statuses=[value for kind,value in messages if kind=='status']
    assert statuses[-1]['state']=='error' and statuses[-1]['message']==engine.gpu_error
