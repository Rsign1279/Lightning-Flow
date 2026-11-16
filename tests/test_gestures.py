import queue
from dataclasses import replace
import pytest
from lightningflow.desktop.gestures import RecordingGesture
from lightningflow.desktop.state import Preferences, Settings
from lightningflow.desktop.worker import build_backend
from lightningflow.win32 import Target


def test_hold_release_finishes_without_double_press_delay():
    gesture=RecordingGesture()
    assert gesture.press(10)==('start',)
    assert gesture.press(10.4)==()  # key auto-repeat
    assert gesture.release(11)==('stop',)
    assert gesture.tick(12)==()


def test_double_press_locks_then_next_press_stops():
    gesture=RecordingGesture()
    assert gesture.press(0)==('start',)
    assert gesture.release(.08)==('pause',)
    assert gesture.press(.18)==('resume','locked')
    assert gesture.release(.24)==()
    assert gesture.tick(30)==()
    assert gesture.press(31)==('stop',)
    assert gesture.press(31.1)==()
    assert gesture.release(31.2)==()


def test_single_tap_closes_mic_before_waiting_for_second_tap():
    gesture=RecordingGesture()
    gesture.press(0)
    assert gesture.release(.05)==('pause',)
    assert gesture.tick(.36)==()
    assert gesture.tick(.38)==('stop',)
    assert gesture.tick(1)==()


def test_late_second_press_does_not_extend_recording():
    gesture=RecordingGesture()
    gesture.press(0); gesture.release(.05)
    assert gesture.press(.5)==('stop',)


def test_reset_during_any_gesture_allows_next_hold():
    for state in ('held','waiting','locked','finishing'):
        gesture=RecordingGesture(state=state,down=True)
        gesture.reset()
        assert gesture.release(1)==()
        assert gesture.press(2)==('start',)


@pytest.fixture
def backend(tmp_path,monkeypatch):
    config=tmp_path/'settings.json'
    Preferences(config).save(Settings(activation='smart'))
    engine=build_backend(config,tmp_path/'models')
    engine.ready=True
    monkeypatch.setattr('lightningflow.desktop.worker.send',lambda *a,**kw:None)
    monkeypatch.setattr(engine.guard,'identity',lambda:Target(1,2,(),0,3,4))
    return engine


def test_smart_capture_is_queued_before_any_provider_read(backend,monkeypatch):
    monkeypatch.setattr(backend.guard,'snapshot',lambda **kw:pytest.fail('provider called inside keyboard hook'))
    backend.key_down(backend.args.toggle_vk,True)
    action,session=backend.commands.get_nowait()
    assert action=='start' and session is backend.active and session.target is None
    backend.key_up(backend.args.toggle_vk)
    assert backend.commands.get_nowait()[0]=='pause'


def test_ordinary_shortcuts_and_repeat_notifications_cannot_duplicate_start(backend):
    backend.key_down(backend.args.toggle_vk,False)
    backend.handle_hotkey(1)
    assert backend.commands.empty()
    backend.key_down(backend.args.toggle_vk,True)
    backend.key_down(backend.args.toggle_vk,True)
    assert backend.commands.qsize()==1


@pytest.mark.parametrize('vk',[0x11,0x12,0xA2,0xA3,0xA4,0xA5,0x77])
def test_releasing_any_part_of_chord_pauses_short_tap(backend,vk):
    backend.key_down(backend.args.toggle_vk,True)
    backend.key_up(vk)
    assert [backend.commands.get_nowait()[0] for _ in range(2)]==['start','pause']
    backend.key_up(backend.args.toggle_vk)
    assert backend.commands.empty()


def test_target_change_during_initial_probe_never_retargets(backend,monkeypatch):
    backend.key_down(backend.args.toggle_vk,True)
    monkeypatch.setattr(backend.guard,'snapshot',lambda **kw:Target(99,2,(),1,3,4))
    backend.on_tick()
    assert backend.active.target is None


def test_saved_legacy_settings_migrate_to_hold_gesture(tmp_path):
    path=tmp_path/'settings.json'
    path.write_text('{"activation":"toggle"}')
    assert Preferences(path).load().activation=='hold'
