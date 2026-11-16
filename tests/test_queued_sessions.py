from dataclasses import replace
import threading
import time
import numpy as np
import pytest
from lightningflow.app import Dictation,Session
from lightningflow.cli import parser
from lightningflow.win32 import Target,EditText,Delivery,spaced_insertion,expected_text
from lightningflow.desktop.worker import build_backend
from lightningflow.desktop.state import Settings,Preferences


def backend(tmp_path,monkeypatch):
    path=tmp_path/'settings.json';Preferences(path).save(Settings(recording_shortcut='ctrl_win',activation='smart'))
    engine=build_backend(path,tmp_path/'models');engine.ready=True
    monkeypatch.setattr(engine.guard,'identity',lambda:None)
    monkeypatch.setattr('lightningflow.desktop.worker.send',lambda *_a,**_k:None)
    return engine


def stop_hold(engine):
    engine.gesture.pressed_at=time.perf_counter()-1
    engine.recording_edge('release')


def test_new_hold_can_start_while_prior_asr_is_finishing(tmp_path,monkeypatch):
    engine=backend(tmp_path,monkeypatch)
    engine.recording_edge('press');first=engine.active;stop_hold(engine)
    engine.recording_edge('press');second=engine.active
    assert first is not second and engine.recording and len(engine.sessions)==2
    assert first.capture_until and not second.capture_until


def test_queue_cap_refuses_without_replacing_recorded_sessions(tmp_path,monkeypatch):
    engine=backend(tmp_path,monkeypatch)
    for _ in range(3):engine.recording_edge('press');stop_hold(engine)
    original=list(engine.sessions);engine.recording_edge('press')
    assert len(engine.sessions)==3 and all(a is b for a,b in zip(original,engine.sessions))
    assert not engine.recording


def test_three_rapid_locked_sessions_fit_capture_command_queue(tmp_path,monkeypatch):
    engine=backend(tmp_path,monkeypatch)
    for _ in range(3):
        engine.recording_edge('press');engine.recording_edge('release')
        engine.recording_edge('press');engine.recording_edge('release')
        assert engine.gesture.state=='locked' and engine.recording
        engine.recording_edge('press');engine.recording_edge('release')
    assert len(engine.sessions)==3 and engine.commands.qsize()==12 and not engine.recording


def test_recording_limit_resets_gesture_before_asr_finishes(tmp_path,monkeypatch):
    engine=backend(tmp_path,monkeypatch);engine.recording_edge('press');item=engine.active
    item.stopped=time.perf_counter();engine.on_tick()
    assert not engine.recording and engine.gesture.state=='idle'
    engine.recording_edge('press');assert engine.active is not item and engine.recording


def test_old_microphone_open_event_cannot_change_new_recording_ui(tmp_path,monkeypatch):
    engine=backend(tmp_path,monkeypatch);messages=[]
    monkeypatch.setattr('lightningflow.desktop.worker.send',lambda kind,**value:messages.append((kind,value)))
    old=engine.new_session(None);engine.active=engine.new_session(None)
    engine.emit('listening',old);assert not messages


def test_cancelled_old_result_cannot_clear_new_recording_ui(tmp_path,monkeypatch):
    engine=backend(tmp_path,monkeypatch);messages=[]
    monkeypatch.setattr('lightningflow.desktop.worker.send',lambda kind,**value:messages.append((kind,value)))
    engine.recording_edge('press');old=engine.active;stop_hold(engine)
    engine.recording_edge('press');current=engine.active;old.cancelled=True
    engine.deliver(old)
    assert engine.active is current and engine.recording and engine.gesture.state=='held'
    assert not any(kind=='cancelled' or value.get('state')=='ready' for kind,value in messages)


def test_confirmed_insert_rebases_only_identical_queued_target(monkeypatch):
    engine=Dictation(parser().parse_args(['run']))
    target=Target(10,20,(0,0,0,0),0,native=True,state=EditText('',0,0))
    first=Session(target,text='First.');second=Session(target,text='Second.')
    third=Session(replace(target,epoch=1),text='Unrelated')
    for item in (first,second,third):engine.register_session(item)
    engine.active=second;engine.recording=True;observed=[]
    def insert(text,target):
        payload=spaced_insertion(target.state,text)
        result=expected_text(target.state,payload);observed.append(result)
        return Delivery(True,'verified fixture',EditText(result,len(result),len(result)))
    monkeypatch.setattr(engine.guard,'insert',insert)
    monkeypatch.setattr('lightningflow.app.u.GetAsyncKeyState',lambda _:0)
    engine.schedule_delivery(first);engine.tick_delivery()
    assert engine.active is second and engine.recording
    assert second.target.state==EditText('First.',6,6)
    assert third.target.epoch==1 and third.target.state.text==''
    engine.recording=False;engine.schedule_delivery(second);engine.tick_delivery()
    assert observed==['First.','First. Second.']


def test_cleanup_completion_cannot_reorder_queued_delivery(monkeypatch):
    engine=Dictation(parser().parse_args(['run']))
    first=Session(None,text='first');second=Session(None,text='second')
    engine.register_session(first);engine.register_session(second)
    engine.schedule_delivery(second)
    monkeypatch.setattr('lightningflow.app.u.GetAsyncKeyState',lambda _:0)
    engine.tick_delivery();assert engine.pending is None
    engine.schedule_delivery(first);assert engine.pending[0] is first


def test_next_recording_modifiers_do_not_timeout_previous_text(monkeypatch):
    engine=Dictation(parser().parse_args(['run']))
    first=Session(None,text='first');second=Session(None)
    engine.register_session(first);engine.register_session(second)
    engine.active=second;engine.recording=True
    engine.schedule_delivery(first);engine.pending=(first,0)
    monkeypatch.setattr('lightningflow.app.u.GetAsyncKeyState',lambda _:0x8000)
    engine.tick_delivery()
    assert engine.pending[0] is first and not first.error


def test_prior_result_does_not_unlock_next_hands_free_session(tmp_path,monkeypatch):
    engine=backend(tmp_path,monkeypatch)
    first=engine.new_session(None);second=engine.new_session(None)
    first.destination='scratchpad';first.text='first'
    for item in (first,second):engine.register_session(item)
    engine.active=second;engine.recording=True;engine.gesture.state='locked'
    engine.schedule_delivery(first)
    monkeypatch.setattr('lightningflow.app.u.GetAsyncKeyState',lambda _:0)
    engine.tick_delivery()
    assert engine.active is second and engine.recording and engine.gesture.state=='locked'


def test_microphone_failure_finishes_valid_frames_for_gpu_recovery(monkeypatch):
    from lightningflow import app
    engine=Dictation(parser().parse_args(['run']));session=Session(None)
    class Stream:
        reads=0
        def __init__(self,**_):pass
        def start(self):pass
        def read(self,n):
            self.reads+=1
            if self.reads>5:raise RuntimeError('disconnected')
            return np.full((n,1),.1,dtype=np.float32),False
        def close(self):raise RuntimeError('device already gone')
    monkeypatch.setattr(app.sd,'InputStream',Stream);monkeypatch.setattr(app,'input_options',lambda _: {})
    engine.commands.put(('start',session));thread=threading.Thread(target=engine.capture);thread.start()
    try:
        kind,same,chunk=engine.jobs.get(timeout=2)
        assert kind=='chunk' and same is session and len(chunk.audio)==1600
        kind,same,_=engine.jobs.get(timeout=2)
        assert kind=='finish' and same is session and not session.error
        assert session.capture_warning and len(session.raw)==5
        session.text='Recovered captured words'
        engine.deliver(session)
        assert not session.delivered and session.delivery_error and session.raw
    finally:engine.quit.set();thread.join(2)
