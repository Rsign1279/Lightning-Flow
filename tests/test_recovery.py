import json
import threading
import time
import numpy as np
import pytest
from lightningflow.desktop.recovery import RecoveryStore,RecoveryWorker
from lightningflow.desktop.state import Settings
from tests.test_queued_sessions import backend


def audio(n=520):
    rng=np.random.default_rng(42)
    return list(rng.uniform(-1,1,(n,320)).astype('float32'))


def test_recovery_is_off_by_default():
    assert not Settings().retain_failed_audio


def test_native_crash_preview_is_explicitly_incomplete_and_never_delivered():
    from lightningflow.desktop.state import interrupted_preview
    assert interrupted_preview('',1) is None
    row=interrupted_preview('An unfinished thought',1)
    assert row['text']=='An unfinished thought' and not row['delivered'] and not row['audio_available']
    assert 'not a final transcript' in row['cleanup'] and 'incomplete or provisional' in row['error']


def test_exact_float_roundtrip_and_no_plaintext(tmp_path):
    store=RecoveryStore(tmp_path);frames=audio();ident='a'*32
    store.save(ident,frames,{'text':'confidential silver mountain'})
    restored,row=RecoveryStore(tmp_path).load(ident)
    assert np.array_equal(frames,restored) and row['text']=='confidential silver mountain'
    assert len(list((tmp_path/ident).glob('*.json')))==4
    assert all(b'confidential silver mountain' not in path.read_bytes() and b'"pcm"' not in path.read_bytes() for path in (tmp_path/ident).glob('*.json'))


def test_corrupt_chunk_retained_and_reported(tmp_path):
    store=RecoveryStore(tmp_path);ident='b'*32;store.save(ident,audio(1),{'text':'saved'})
    chunk=tmp_path/ident/'0000.json';chunk.write_text('{"pcm":"bad"}')
    with pytest.raises(ValueError,match='not protected'):store.load(ident)
    assert chunk.exists()


def test_unfinished_save_has_no_visible_manifest(tmp_path):
    store=RecoveryStore(tmp_path);ident='c'*32;calls=[]
    def valid():calls.append(1);return len(calls)<2
    with pytest.raises(InterruptedError):store.save(ident,audio(),{},valid)
    assert store.inventory()==([],[]) and not (tmp_path/ident).exists()


def test_clear_during_async_save_cannot_resurrect_audio(tmp_path,monkeypatch):
    worker=RecoveryWorker(tmp_path);entered=threading.Event();release=threading.Event()
    original=worker.store.save
    def save(*args,**kwargs):entered.set();assert release.wait(5);return original(*args,**kwargs)
    monkeypatch.setattr(worker.store,'save',save)
    assert worker.submit('save','d'*32,audio(1),{}) and entered.wait(5)
    worker.clear();release.set()
    thread=worker.thread;thread.join(5)
    assert not thread.is_alive() and worker.store.inventory()==([],[])


def test_five_recording_bound_and_preserve_unrelated_files(tmp_path):
    store=RecoveryStore(tmp_path);unrelated=tmp_path/'unrelated.txt';unrelated.write_text('keep')
    for index in range(6):evicted=store.save(f'{index:032x}',audio(1),{})
    assert evicted==['0'*32] and len(store.inventory()[0])==5
    store.clear();assert unrelated.read_text()=='keep' and store.inventory()==([],[])


@pytest.mark.parametrize('ident',['../outside','a'*31,'A'*32,None,'0'*32+'/../other'])
def test_path_escape_rejected(tmp_path,ident):
    with pytest.raises(ValueError):RecoveryStore(tmp_path).remove(ident)


def test_retry_audio_uses_same_inference_queue_and_scratchpad(tmp_path,monkeypatch):
    engine=backend(tmp_path,monkeypatch);source=engine.new_session(None);source.raw=audio(10);source.text='Old partial'
    engine.use_retained_audio('retranscribe',source)
    deadline=time.perf_counter()+5
    while not engine.jobs.qsize() and time.perf_counter()<deadline:time.sleep(.01)
    item=engine.active
    assert item.ident==source.ident and item.destination=='scratchpad' and not engine.recording
    assert np.array_equal(item.raw,source.raw) and source.text=='Old partial'
    deadline=time.perf_counter()+5;finished=False
    while time.perf_counter()<deadline:
        kind,session,chunk=engine.jobs.get(timeout=1)
        assert session is item
        if kind=='finish':finished=True;break
    assert finished


def test_disabled_recovery_never_writes_on_failed_delivery(tmp_path,monkeypatch):
    engine=backend(tmp_path,monkeypatch);source=engine.new_session(None);source.raw=audio(1);source.error='test failure'
    engine._deliver(source,source)
    assert engine.recovery.thread is None and not engine.recovery.store.root.exists()
