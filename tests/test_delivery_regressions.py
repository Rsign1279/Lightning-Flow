"""Reproductions for delivery bugs; no foreground windows or microphone needed."""
from dataclasses import replace
from lightningflow.win32 import InputGuard, Target
from lightningflow.win32 import EditText, Delivery, expected_text
from lightningflow.accessibility import AccessibleText
from lightningflow.app import Dictation, Session
from lightningflow.cli import parser
import pytest

def test_caret_geometry_is_not_target_identity(monkeypatch):
    guard = InputGuard([])
    original = Target(10, 20, (1, 1, 2, 17), 0)
    # Providers temporarily hide/recreate carets without changing the field.
    monkeypatch.setattr(guard, 'snapshot', lambda **_: replace(original, caret=(0,0,0,0)))
    assert guard.valid(original)

def test_retry_does_not_destroy_failed_recording(monkeypatch):
    instance = Dictation(parser().parse_args(['run']))
    original = Session(None, text='recover me', raw=[b'private recording'])
    instance.last = original
    monkeypatch.setattr(instance.guard, 'snapshot', lambda: None)
    monkeypatch.setattr(instance.guard, 'insert', lambda *_: (_ for _ in ()).throw(RuntimeError('wrong target')))
    monkeypatch.setattr('lightningflow.app.u.GetAsyncKeyState', lambda _: 0)
    instance.handle_hotkey(3)
    instance.tick_delivery()
    assert instance.last is original
    assert instance.last.raw == [b'private recording']

def test_pending_retry_blocks_a_new_recording_and_second_retry(monkeypatch):
    instance = Dictation(parser().parse_args(['run']))
    instance.ready = True
    instance.last = Session(None, text='recover me', raw=[b'audio'])
    monkeypatch.setattr(instance.guard, 'snapshot', lambda: None)
    instance.handle_hotkey(3)
    pending = instance.pending
    assert pending and instance.active is pending[0]
    instance.handle_hotkey(1)
    instance.handle_hotkey(3)
    assert instance.pending is pending and instance.commands.empty()
    assert instance.last.raw == [b'audio']

def test_pending_retry_can_be_cancelled_without_touching_original(monkeypatch):
    instance = Dictation(parser().parse_args(['run']))
    original = Session(None,text='recover',raw=[b'audio'])
    instance.last = original
    monkeypatch.setattr(instance.guard, 'snapshot', lambda: None)
    monkeypatch.setattr('lightningflow.app.u.GetAsyncKeyState', lambda _: 0)
    monkeypatch.setattr(instance.guard, 'insert', lambda *_: pytest.fail('cancelled retry inserted'))
    instance.handle_hotkey(3)
    instance.handle_hotkey(2)
    instance.tick_delivery()
    assert instance.pending is None and instance.active is None
    assert instance.last is original and original.raw == [b'audio']

def test_duplicate_and_background_focus_events_are_ignored(monkeypatch):
    guard = InputGuard([])
    target = Target(10,20,(1,1,2,17),0)
    guard.watched = target
    guard.watch_time = 1000
    monkeypatch.setattr(guard,'identity',lambda:target)
    guard.focus_event(0x8005, 999, timestamp=1001)
    guard.focus_event(0x8005, 20, timestamp=1002)
    guard.focus_event(3,10,timestamp=1003)
    guard.focus_event(3,999,timestamp=999)  # queued before recording started
    assert guard.epoch == 0
    guard.focus_event(3,999,timestamp=1004)
    assert guard.epoch == 1  # leaving and returning must still invalidate

@pytest.mark.parametrize('state', [EditText('changed',0,0), EditText('original',3,3)])
def test_actual_document_or_selection_change_invalidates_target(monkeypatch,state):
    guard=InputGuard([])
    original=Target(10,20,(0,0,0,0),0,state=EditText('original',0,0))
    monkeypatch.setattr(guard,'snapshot',lambda **_: replace(original,state=state))
    assert not guard.valid(original)

def test_native_expected_text_uses_utf16_positions():
    assert expected_text(EditText('😀 suffix',2,2), ' inserted') == '😀 inserted suffix'

def test_success_requires_a_delivery_receipt(monkeypatch):
    instance=Dictation(parser().parse_args(['run']))
    session=Session(None,text='hello',raw=[b'audio'])
    monkeypatch.setattr(instance.guard,'insert',lambda *_: None)
    instance.deliver(session)
    assert not session.delivered and session.raw == [b'audio']

def test_modifier_timeout_cannot_force_input(monkeypatch):
    instance=Dictation(parser().parse_args(['run']))
    session=Session(None,text='hello',raw=[b'audio'])
    instance.schedule_delivery(session)
    instance.pending=(session,0)
    monkeypatch.setattr('lightningflow.app.u.GetAsyncKeyState',lambda _: 0x8000)
    monkeypatch.setattr(instance.guard,'insert',lambda *_: pytest.fail('held modifiers inserted'))
    instance.tick_delivery()
    assert not session.delivered and session.raw == [b'audio']

def test_unreadable_field_does_not_disable_gpu_dictation(monkeypatch):
    instance=Dictation(parser().parse_args(['run']))
    instance.ready=True
    monkeypatch.setattr(instance.guard,'snapshot',lambda: (_ for _ in ()).throw(RuntimeError('unavailable provider')))
    instance.handle_hotkey(1)
    action,session=instance.commands.get_nowait()
    assert action=='start' and session is instance.active and session.target is None
    with pytest.raises(RuntimeError,match='No verified insertion target'):
        instance.guard.insert('retained transcript',session.target)

def test_focus_change_stops_unicode_after_one_bounded_batch(monkeypatch):
    guard=InputGuard([])
    guard.prefer_clipboard=False
    target=Target(10,20,(0,0,0,0),0,state=AccessibleText((1,),1,'',0,0))
    calls=[]
    monkeypatch.setattr(guard,'valid',lambda _: True)
    monkeypatch.setattr(guard,'service_callbacks',lambda: None)
    monkeypatch.setattr(guard,'identity',lambda: replace(target,foreground=99))
    monkeypatch.setattr('lightningflow.win32.u.GetAsyncKeyState',lambda _: 0)
    monkeypatch.setattr('lightningflow.win32.u.SendInput',lambda count,*_: calls.append(count) or count)
    with pytest.raises(RuntimeError,match='Focus/input changed'):
        guard.insert('a'*300,target)
    assert calls==[256]

def test_cancelled_new_recording_preserves_previous_recoverable_audio():
    instance=Dictation(parser().parse_args(['run']))
    previous=Session(None,text='previous',raw=[b'previous audio'])
    instance.last=previous
    current=Session(None,text='cancel me',raw=[b'cancel me'],cancelled=True)
    instance.deliver(current)
    assert instance.last is previous and previous.raw==[b'previous audio']
    assert not current.raw and not current.text

def test_new_session_arms_its_field_before_accessibility_queries(monkeypatch):
    guard=InputGuard([])
    guard.watched=Target(1,2,(0,0,0,0),0)
    current=Target(10,20,(0,0,0,0),0)
    monkeypatch.setattr(guard,'identity',lambda: replace(current,epoch=guard.epoch))
    monkeypatch.setattr('lightningflow.win32.native_editor',lambda _: False)
    def read(**_):
        # UIA marshaling services queued WinEvents. This duplicate belongs to
        # the new field, not the previous recording's target.
        guard.focus_event(0x8005,20)
        return AccessibleText((1,),1,'',0,0)
    monkeypatch.setattr(guard.probe,'read',read)
    captured=guard.snapshot()
    assert captured.foreground==10 and captured.epoch==0
