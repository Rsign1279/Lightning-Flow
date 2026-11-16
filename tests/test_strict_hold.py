import time
import pytest
from lightningflow.desktop.gestures import HoldToTalkGesture
from lightningflow.desktop.state import Preferences,Settings
from lightningflow.desktop.worker import build_backend
from lightningflow.win32 import Target


def test_a_tap_has_no_actions_and_no_delayed_start():
    gesture=HoldToTalkGesture()
    assert gesture.press(1)==()
    assert gesture.tick(1.08)==()
    assert gesture.release(1.09)==()
    assert gesture.tick(3)==()
    assert gesture.state=='idle'


def test_hold_starts_at_threshold_and_release_stops_in_same_call():
    gesture=HoldToTalkGesture()
    assert gesture.press(1)==()
    assert gesture.tick(1.119)==()
    assert gesture.tick(1.121)==('start',)
    assert gesture.press(2)==()  # Repeat never toggles or moves deadline.
    assert gesture.release(2.001)==('stop',)
    assert gesture.tick(3)==()


def test_double_taps_cannot_lock_or_start_recording():
    gesture=HoldToTalkGesture()
    for base in (1,1.18):
        assert gesture.press(base)==()
        assert gesture.release(base+.05)==()
    assert gesture.tick(2)==() and gesture.state=='idle'


def test_repeat_does_not_extend_hold_threshold():
    gesture=HoldToTalkGesture()
    gesture.press(1)
    gesture.press(1.09)
    assert gesture.tick(1.121)==('start',)


@pytest.fixture
def backend(tmp_path,monkeypatch):
    path=tmp_path/'settings.json'
    Preferences(path).save(Settings(activation='hold'))
    engine=build_backend(path,tmp_path/'models')
    engine.ready=True
    monkeypatch.setattr('lightningflow.desktop.worker.send',lambda *a,**kw:None)
    monkeypatch.setattr(engine.guard,'identity',lambda:Target(1,2,(),0,3,4))
    return engine


def test_tap_never_opens_microphone_or_inspects_target(backend,monkeypatch):
    monkeypatch.setattr(backend.guard,'identity',lambda:pytest.fail('tap inspected target'))
    backend.key_down(backend.args.toggle_vk,True)
    backend.handle_hotkey(1) # Registered message must not duplicate hook logic.
    backend.key_up(backend.args.toggle_vk)
    backend.on_tick()
    assert backend.active is None and backend.commands.empty() and backend.target_pending is None


@pytest.mark.parametrize('released',[0x77,0x11,0x12,0xA2,0xA3,0xA4,0xA5])
def test_any_chord_release_cuts_off_capture_without_command_bridge_delay(backend,released):
    backend.key_down(backend.args.toggle_vk,True)
    backend.gesture.deadline=time.perf_counter()-1
    backend.gesture_actions(backend.gesture.tick(time.perf_counter()))
    action,session=backend.commands.get_nowait()
    assert action=='start'
    before=time.perf_counter()
    backend.key_up(released)
    assert not backend.recording
    assert before<=session.capture_until<=time.perf_counter()
    assert backend.commands.get_nowait()[0]=='stop'
    assert backend.external.empty()
    backend.key_up(backend.args.toggle_vk)
    assert backend.commands.empty()


def test_older_controls_migrate_to_hold_only(tmp_path):
    path=tmp_path/'settings.json'
    path.write_text('{"activation":"smart","controls_revision":1}')
    assert Preferences(path).load().activation=='hold'


def test_mode_change_does_not_leave_old_gesture_armed(backend):
    backend.key_down(backend.args.toggle_vk,True)
    backend.settings.activation='toggle'
    backend.on_tick()
    assert backend.gesture.state=='idle' and backend.commands.empty()


def test_frame_that_finishes_after_release_is_never_transcribed(monkeypatch):
    import threading
    import numpy as np
    from lightningflow import app
    from lightningflow.cli import parser
    engine=app.Dictation(parser().parse_args(['run']))
    reading=threading.Event(); released=threading.Event(); closed=[]
    class Stream:
        def __init__(self,**_): pass
        def start(self): pass
        def read(self,_):
            reading.set()
            assert released.wait(2)
            return np.ones((320,1),dtype=np.float32),False
        def close(self): closed.append(True)
    monkeypatch.setattr(app,'input_options',lambda _: {})
    monkeypatch.setattr(app.sd,'InputStream',Stream)
    session=app.Session(None)
    engine.commands.put(('start',session))
    thread=threading.Thread(target=engine.capture)
    thread.start()
    try:
        assert reading.wait(2)
        session.capture_until=time.perf_counter()
        released.set()
        kind,finished,_=engine.jobs.get(timeout=2)
        assert kind=='finish' and finished is session
        assert not session.raw and not session.first_audio and not session.error
        assert closed and engine.jobs.empty()
    finally:
        engine.quit.set(); released.set(); thread.join(2)


def test_completed_transcripts_append_to_persistent_local_log(tmp_path):
    from lightningflow.desktop.state import History
    path=tmp_path/'log.sqlite3'
    log=History(path,True)
    log.add({'id':'first','text':'First completed recording','delivered':True})
    log.add({'id':'second','text':'Second completed recording','delivered':False})
    log.close()
    reopened=History(path,True)
    try:
        assert {row['id']:row['text'] for row in reopened.rows}=={
            'first':'First completed recording','second':'Second completed recording'}
    finally: reopened.close()


def test_enabling_log_saves_already_visible_session_transcripts(tmp_path):
    from lightningflow.desktop.state import History
    path=tmp_path/'log.sqlite3'
    log=History(path,False)
    log.add({'id':'before-enable','text':'Already visible'})
    log.configure(True)
    log.close()
    reopened=History(path,True)
    try: assert reopened.rows[0]['text']=='Already visible'
    finally: reopened.close()
