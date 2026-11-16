"""Test-only replay/gesture driver. Not shipped as a production backend."""
import ctypes as C
import queue
import time
import numpy as np
from .hold_integration import ReplayStream as BaseReplay
from lightningflow import app
from lightningflow.desktop import worker


class ReplayStream(BaseReplay):
    opens=0
    closes=0
    live=0
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        type(self).live+=1
    def close(self):
        type(self).closes+=1
        type(self).live-=1
    def read(self,n):
        time.sleep(n/16000*.10)
        data=self.samples[self.offset:self.offset+n]
        type(self).offset+=n
        return np.pad(data,(0,max(0,n-len(data))))[:,None],False


real_builder=worker.build_backend
real_asr=app.CudaASR
initializations=0


def resident_asr(*args,**kwargs):
    global initializations
    initializations+=1
    return real_asr(*args,**kwargs)


def build(*args):
    engine=real_builder(*args)
    controls=queue.Queue()
    original_put=engine.external.put
    def put(command,*a,**kw):
        if str(command.get('action','')).startswith('test_'):controls.put(command)
        else:original_put(command,*a,**kw)
    engine.external.put=put
    # Nothing in this worker may capture the microphone, inspect a user field,
    # reserve a shortcut or submit any Windows input.
    engine.guard.install=lambda:None
    engine.guard.identity=lambda:None
    engine.guard.insert=lambda *_:(_ for _ in ()).throw(AssertionError('External insertion forbidden in soak'))
    app.u.RegisterHotKey=lambda *_:True
    app.u.UnregisterHotKey=lambda *_:True
    app.u.GetAsyncKeyState=lambda *_:0
    new_session=engine.new_session
    def sandbox(target):
        session=new_session(None)
        session.destination='scratchpad'
        return session
    engine.new_session=sandbox
    normal_tick=engine.on_tick
    tap=None
    hold=None
    def tick():
        nonlocal tap,hold
        now=time.perf_counter()
        if tap and now>=tap['release_at']:
            engine.key_up(engine.args.toggle_vk)
            if tap['remaining']:
                engine.key_down(engine.args.toggle_vk,True)
                tap['remaining']-=1;tap['release_at']=now+.04
            else:
                worker.send('test_ack',action='taps',cycle=tap['cycle'],
                    ok=engine.active is None and engine.gesture.state=='idle' and ReplayStream.opens==tap['opens'],
                    stream_opens=ReplayStream.opens)
                tap=None
        normal_tick()
        if hold:
            if engine.active is not None and not hold.get('started'):
                hold['started']=True
                worker.send('test_ack',action='started',cycle=hold['cycle'],
                    press_to_start_ms=(engine.active.hotkey_at-hold['pressed_at'])*1000)
            if engine.recording and now>=hold['repeat_at']:
                engine.key_down(engine.args.toggle_vk,True)
                hold['repeat_at']=now+.025
                hold['repeats']+=1
            if engine.recording and ReplayStream.offset>=len(ReplayStream.samples)+1600:
                began=time.perf_counter()
                engine.key_up(hold['release_vk'])
                dispatch=(time.perf_counter()-began)*1000
                engine.key_up(engine.args.toggle_vk)
                worker.send('test_ack',action='released',cycle=hold['cycle'],
                    release_dispatch_ms=dispatch,repeat_messages=hold['repeats'],
                    recording_stopped=not engine.recording,capture_cutoff_set=bool(engine.active.capture_until))
                hold['released']=True
            if hold.get('released') and engine.active is None:
                worker.send('test_ack',action='idle',cycle=hold['cycle'],stream_opens=ReplayStream.opens,
                    stream_closes=ReplayStream.closes,live_streams=ReplayStream.live,
                    model_initializations=initializations,pending_jobs=engine.jobs.qsize())
                hold=None
        for _ in range(4):
            try: command=controls.get_nowait()
            except queue.Empty:break
            action=command['action']
            if engine.active is not None or tap or hold:
                worker.send('test_ack',action='rejected',cycle=command.get('cycle'),reason='Test engine busy')
                continue
            if action=='test_taps':
                tap={'cycle':command['cycle'],'remaining':1,'release_at':time.perf_counter()+.04,'opens':ReplayStream.opens}
                engine.key_down(engine.args.toggle_vk,True)
            elif action=='test_hold':
                ReplayStream.offset=0
                hold={'cycle':command['cycle'],'release_vk':command['release_vk'],
                      'pressed_at':time.perf_counter(),'repeat_at':time.perf_counter()+.03,'repeats':0}
                engine.key_down(engine.args.toggle_vk,True)
    engine.on_tick=tick
    return engine


if __name__=='__main__':
    app.CudaASR=resident_asr
    app.sd.InputStream=ReplayStream
    app.input_options=lambda _:{}
    worker.build_backend=build
    raise SystemExit(worker.main())
