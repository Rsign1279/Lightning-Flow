import itertools
import time
import pytest
from lightningflow.desktop.chords import ControlWindowsChord
from lightningflow.desktop.state import Preferences, Settings
from lightningflow.desktop.worker import build_backend


@pytest.mark.parametrize('ctrl,win,win_first,ctrl_first_release',list(itertools.product((0xA2,0xA3),(0x5B,0x5C),(False,True),(False,True))))
def test_sided_modifiers_and_orders(ctrl,win,win_first,ctrl_first_release):
    chord=ControlWindowsChord()
    first,second=(win,ctrl) if win_first else (ctrl,win)
    assert chord.feed(first,True)==(None,False)
    edge,suppressed=chord.feed(second,True)
    assert edge=='press' and suppressed==(second==win)
    assert chord.feed(second,True)[0] is None
    first,second=(ctrl,win) if ctrl_first_release else (win,ctrl)
    assert chord.feed(first,False)==('release',first==win and not win_first)
    assert chord.feed(second,False)==(None,second==win and not win_first)
    assert not chord.held and not chord.consumed_windows
    assert chord.feed(win,True)==(None,False)  # Ordinary Win remains usable.
    assert chord.feed(win,False)==(None,False)


def test_redundant_sided_modifier_does_not_release_until_group_is_up():
    chord=ControlWindowsChord()
    for key in (0xA2,0x5B,0xA3,0x5C): chord.feed(key,True)
    assert chord.feed(0xA2,False)[0] is None
    assert chord.feed(0x5B,False)==(None,True)
    assert chord.feed(0xA3,False)[0]=='release'
    assert chord.feed(0x5C,False)==(None,True)
    assert not chord.consumed_windows


@pytest.fixture
def backend(tmp_path,monkeypatch):
    path=tmp_path/'settings.json'
    Preferences(path).save(Settings(recording_shortcut='ctrl_win',activation='smart',max_seconds=1800))
    engine=build_backend(path,tmp_path/'models')
    engine.ready=True
    monkeypatch.setattr('lightningflow.desktop.worker.send',lambda *a,**kw:None)
    monkeypatch.setattr(engine.guard,'identity',lambda:None)
    monkeypatch.setattr('lightningflow.win32.u.GetAsyncKeyState',lambda _:0)
    return engine


def edge(engine,vk,down): return engine.guard.key_event(vk,down)


@pytest.mark.parametrize('release',[0xA2,0x5B])
def test_hold_releases_capture_in_same_callback(backend,release):
    edge(backend,0xA2,True);assert edge(backend,0x5B,True)
    assert backend.commands.get_nowait()[0]=='start'
    backend.gesture.pressed_at=time.perf_counter()-1
    now=time.perf_counter()
    edge(backend,release,False)
    assert not backend.recording
    assert backend.active.capture_until>=now
    assert backend.commands.get_nowait()[0]=='stop'
    assert backend.guard.epoch==0


def test_double_tap_stays_locked_then_third_tap_stops(backend):
    edge(backend,0xA2,True)
    edge(backend,0x5B,True);edge(backend,0x5B,False)
    assert backend.gesture.state=='waiting'
    edge(backend,0x5B,True);edge(backend,0x5B,False)
    assert backend.recording and backend.gesture.state=='locked'
    assert not backend.active.capture_until
    backend.gesture_actions(backend.gesture.tick(time.perf_counter()+1800))
    assert backend.recording  # No double-tap timer in locked mode.
    edge(backend,0x5B,True)
    assert not backend.recording and backend.active.capture_until
    assert [backend.commands.get_nowait()[0] for _ in range(4)]==['start','pause','resume','stop']
    assert backend.guard.epoch==0 and backend.args.max_seconds==1800


def test_old_recording_key_does_not_start_and_own_input_ignored(backend):
    backend.key_down(0x77,True);backend.handle_hotkey(1)
    assert backend.commands.empty()
    backend.guard.key_event(0xA2,True,own=True)
    backend.guard.key_event(0x5B,True,own=True)
    assert backend.commands.empty()
    backend.guard.key_event(ord('X'),True)
    assert backend.guard.epoch==1


def test_single_tap_pauses_then_finalizes_without_second_tap(backend):
    edge(backend,0x5B,True);edge(backend,0xA3,True);edge(backend,0xA3,False)
    assert backend.active.capture_paused_at
    backend.gesture_actions(backend.gesture.tick(time.perf_counter()+1))
    assert not backend.recording and backend.active.capture_until
    assert [backend.commands.get_nowait()[0] for _ in range(3)]==['start','pause','stop']


def test_chord_is_inert_while_gpu_not_ready(backend):
    backend.ready=False
    edge(backend,0xA2,True);edge(backend,0x5B,True)
    edge(backend,0xA2,False);edge(backend,0x5B,False)
    assert backend.commands.empty() and backend.active is None


def test_recording_settings_roundtrip_and_limits(tmp_path):
    preferences=Preferences(tmp_path/'settings.json')
    preferences.save(Settings(recording_shortcut='ctrl_win',activation='smart',max_seconds=1800))
    settings=preferences.load()
    assert settings.recording_shortcut=='ctrl_win' and settings.activation=='smart' and settings.max_seconds==1800
    with pytest.raises(ValueError): Settings(max_seconds=3601).validate()
    with pytest.raises(ValueError): Settings(recording_shortcut='unknown').validate()
