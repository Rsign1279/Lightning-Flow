"""Modifier event dispatcher -> replay audio -> real resident CUDA -> local log.

No global input, microphone, user clipboard or external insertion is used.
"""
import json
from pathlib import Path
import queue
import re
import threading
import time
from lightningflow import app
from lightningflow.desktop import worker
from lightningflow.desktop.state import Preferences,Settings,History
from .hold_integration import ReplayStream

root=Path(__file__).resolve().parents[1]


def run(count=20,profile=None):
    directory=root/'.work/ctrl-win-integration'
    Preferences(directory/'settings.json').save(Settings(recording_shortcut='ctrl_win',activation='smart',history_enabled=True,max_seconds=1800,
        voice_profile=profile or {},personalization_enabled=bool(profile)))
    engine=worker.build_backend(directory/'settings.json',root/'models')
    engine.guard.identity=lambda:None
    events=[]
    worker.send=lambda kind,**data:events.append({'event':kind,'at':time.perf_counter(),**data})
    app.sd.InputStream=ReplayStream;app.input_options=lambda _:{}
    app.u.GetAsyncKeyState=lambda _:0
    initialization=[];real_asr=app.CudaASR
    def asr(*args,**kwargs):
        initialization.append(True)
        return real_asr(*args,**kwargs)
    app.CudaASR=asr
    log=History(directory/'log.sqlite3',True);log.clear()
    threads=[threading.Thread(target=f,daemon=True) for f in (engine.infer,engine.capture)]
    def tick():
        engine.on_tick()
        while True:
            try:kind,value=engine.events.get_nowait()
            except queue.Empty:break
            if kind=='ready':engine.ready=True
            if kind=='fatal':raise RuntimeError(value)
            if kind=='done':engine.schedule_delivery(value)
        engine.tick_delivery()
        time.sleep(.001)
    def wait(predicate,limit=30):
        deadline=time.perf_counter()+limit
        while not predicate():
            assert time.perf_counter()<deadline,'Ctrl+Win integration timed out'
            tick()
    def key(vk,down):return engine.guard.key_event(vk,down)
    expected=(root/'benchmarks/reference.txt').read_text()
    normalize=lambda s:re.sub(r'[^a-z0-9 ]','',s.casefold().replace('3','three')).split()
    results=[]
    try:
        for thread in threads:thread.start()
        wait(lambda:engine.ready)
        for index in range(count):
            ReplayStream.offset=0
            ctrl=(0xA2,0xA3)[index%2];win=(0x5B,0x5C)[index//2%2]
            first,second=(ctrl,win) if index%3 else (win,ctrl)
            key(first,True);key(second,True)
            session=engine.active;assert session
            session.destination='scratchpad'
            locked=bool(index%2)
            if locked:
                key(second,False)
                assert engine.gesture.state=='waiting' and session.capture_paused_at
                key(second,True);key(second,False);key(first,False)
                assert engine.gesture.state=='locked' and engine.recording
                assert not session.capture_paused_at and not session.capture_until
            wait(lambda:ReplayStream.offset>=len(ReplayStream.samples)+1600)
            # A hold is >200 ms; avoid dependence on test machine throughput.
            if not locked:engine.gesture.pressed_at=min(engine.gesture.pressed_at,time.perf_counter()-.21)
            began=time.perf_counter()
            if locked:
                key(first,True);key(second,True)
            else:key(first,False)
            stop_ms=(time.perf_counter()-began)*1000
            assert not engine.recording and session.capture_until
            key(second,False);key(first,False)
            wait(lambda:engine.active is None)
            result=next(e for e in reversed(events) if e['event']=='result')
            assert result['delivered'] and not result['error'],result
            assert normalize(result['text'])==normalize(expected),result['text']
            assert engine.guard.epoch==0 and not engine.guard.recording_chord.held
            log.add(result)
            results.append({'mode':'locked' if locked else 'hold','release_or_tap_to_stop_dispatch_ms':stop_ms,'gpu_decode_ms':session.decode_ms})
        log.close();log=History(directory/'log.sqlite3',True)
        assert len(log.rows)==count and len(initialization)==1
        return {'completed':count,'hold_cycles':count//2,'locked_cycles':count//2,
                'persistent_log_records':len(log.rows),'gpu_initializations':len(initialization),
                'personalization_enabled':bool(profile),
                'provider':'CUDA / CTranslate2','configured_max_seconds':engine.args.max_seconds,
                'sessions':results,'scope':'Production modifier event dispatcher with accelerated PCM replay. No OS input injection or physical keyboard/start-menu/microphone/30-minute-duration validation.'}
    finally:
        engine.quit.set()
        for thread in threads:thread.join(3)
        log.close()


if __name__=='__main__':
    report=run()
    (root/'results/ctrl-win-0.4.2.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
