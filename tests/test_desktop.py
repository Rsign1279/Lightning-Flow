from dataclasses import asdict
import json
import queue
import sqlite3
import pytest
from lightningflow.desktop.state import Settings,Preferences,History,apply_dictionary
from lightningflow.desktop.cleanup import meaning_guard,enhance

def test_private_defaults_do_not_create_history(tmp_path):
    settings=Settings()
    assert not settings.history_enabled and settings.cleanup_mode=='Raw' and not settings.startup
    history=History(tmp_path/'history.sqlite3',False)
    history.add({'text':'private thought'})
    history.close()
    assert not (tmp_path/'history.sqlite3').exists()

def test_settings_roundtrip_and_invalid_hotkey_rejected(tmp_path):
    store=Preferences(tmp_path/'settings.json')
    settings=Settings(theme='Light',activation='hold')
    store.save(settings)
    assert asdict(store.load())==asdict(settings)
    settings.shortcuts['retry']=settings.shortcuts['toggle']
    with pytest.raises(ValueError,match='distinct'): store.save(settings)
    assert store.load().activation=='hold'

def test_corrupt_preferences_are_backed_up_before_save(tmp_path):
    path=tmp_path/'settings.json'; path.write_text('{broken')
    store=Preferences(path)
    settings=store.load()
    assert store.error
    store.save(settings)
    backup=list(tmp_path.glob('settings-unreadable-*.json'))
    assert len(backup)==1 and backup[0].read_text()=='{broken'

def test_opt_in_history_persists_then_clear_works_even_when_off(tmp_path):
    path=tmp_path/'history.sqlite3'
    history=History(path,True)
    row=history.add({'text':'saved thought'})
    history.close()
    restored=History(path,True)
    assert restored.rows[0]['id']==row['id']
    restored.configure(False)
    restored.add({'text':'memory only'})
    restored.clear()
    restored.close()
    assert History(path,True).rows==[]

def test_history_off_stops_saving_future_rows(tmp_path):
    path=tmp_path/'history.sqlite3'
    history=History(path,True)
    history.add({'text':'persisted'})
    history.configure(False)
    history.add({'text':'not persisted'})
    assert [row['text'] for row in History(path,True).rows]==['persisted']

def test_exact_dictionary_preserves_boundaries_and_no_cascades():
    entries=[{'spoken':'esp thirty two','written':'ESP32-S3'}, {'spoken':'cuda','written':'CUDA'},
             {'spoken':'ESP32-S3','written':'not a cascade'}]
    assert apply_dictionary('esp thirty two uses cuda; scudamore stays.',entries)=='ESP32-S3 uses CUDA; scudamore stays.'

@pytest.mark.parametrize('raw,cleaned',[
    ('Meet at 3 on Friday.','Meet at 4 on Friday.'),
    ('We might use CUDA 12.','We will use CUDA 12.'),
    ('Do not send the report.','Send the report.'),
    ('Please send the report.','Please send the report to John.'),
    ('Use ESP32-S3 and CUDA.','Use ESP32-S3 and cuda.'),
    ('John likes Mary.','Mary likes John.'),
    ('John likes Mary.','John.'),
    ('Please send the project report to John on Friday.','Please send the project report on Friday.'),
    ('Please send the project report on Friday.','Please send the project report.'),
    ('Please send the project report tomorrow.','Please send the project report.'),
])
def test_cleanup_rejects_unsafe_changes(raw,cleaned):
    assert not meaning_guard(raw,cleaned)

def test_cleanup_accepts_conservative_filler_removal():
    assert meaning_guard('Um, please meet Friday at 3.','Please meet Friday at 3.')

def test_raw_mode_makes_no_local_network_request(monkeypatch):
    monkeypatch.setattr('lightningflow.desktop.cleanup.local_request',lambda *_a,**_k:pytest.fail('raw mode contacted a server'))
    assert enhance('hello',Settings())[0]=='hello'

def test_cloud_cleanup_is_refused_before_sending_transcript(monkeypatch):
    settings=Settings(cleanup_mode='Smart cleanup',cleanup_model='model:cloud')
    monkeypatch.setattr('lightningflow.desktop.cleanup.local_request',lambda *_a,**_k:pytest.fail('cloud model request'))
    with pytest.raises(ValueError,match='Cloud'): enhance('private',settings)

def test_remote_metadata_is_refused_before_chat(monkeypatch):
    calls=[]
    def request(provider,port,path,*args,**kwargs):
        calls.append(path)
        return {'remote_host':'https://example.invalid'}
    monkeypatch.setattr('lightningflow.desktop.cleanup.local_request',request)
    with pytest.raises(ValueError,match='Remote'): enhance('private',Settings(cleanup_mode='Smart cleanup',cleanup_model='custom'))
    assert calls==['/api/show']

def test_unrelated_key_release_cannot_start_or_stop_hold(tmp_path,monkeypatch):
    from lightningflow.desktop.worker import build_backend
    path=tmp_path/'settings.json'
    Preferences(path).save(Settings(activation='hold'))
    backend=build_backend(path,tmp_path/'models')
    backend.ready=True
    backend.key_down(backend.args.toggle_vk,True)
    backend.key_up(0x76)
    assert backend.external.empty()
    backend.key_up(backend.args.toggle_vk)
    assert backend.external.empty() and backend.commands.empty()
    assert backend.gesture.state=='idle'
    backend.settings.activation='toggle'
    backend.key_up(backend.args.toggle_vk)
    assert backend.external.empty()

def test_fast_hold_tap_cannot_miss_release(tmp_path,monkeypatch):
    from lightningflow.desktop.worker import build_backend
    path=tmp_path/'settings.json'
    Preferences(path).save(Settings(activation='hold'))
    backend=build_backend(path,tmp_path/'models')
    backend.ready=True
    monkeypatch.setattr(backend.guard,'snapshot',lambda:None)
    monkeypatch.setattr('lightningflow.desktop.worker.send',lambda *a,**k:None)
    monkeypatch.setattr('lightningflow.win32.u.GetAsyncKeyState',lambda _:0)
    backend.handle_hotkey(1)
    assert backend.external.empty() and backend.commands.empty() and backend.active is None

def test_history_write_failure_keeps_transcript_in_memory(tmp_path):
    history=History(tmp_path/'history.sqlite3',True)
    history.connection.execute('PRAGMA query_only=ON')
    row=history.add({'text':'must not disappear'})
    assert history.rows[0]['text']=='must not disappear'
    assert history.connection is None and history.error

def test_native_tray_callback_does_not_reenter_tk():
    from collections import deque
    from lightningflow.desktop.windows import Tray
    tray=Tray.__new__(Tray)
    tray.actions=deque()
    tray.root=None  # Touching Tk here would fail/crash inside the WndProc.
    assert tray._window_proc(0,0x8042,0,0x203)==0
    assert list(tray.actions)==['show']
