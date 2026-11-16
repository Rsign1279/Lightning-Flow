"""Hold controller -> replay capture -> resident CUDA -> persistent local log.

Calls the production key callbacks directly, without sending global input,
reading user documents or touching another application's focus/clipboard.
"""
import json
from pathlib import Path
import queue
import threading
import time
import numpy as np
from lightningflow import app
from lightningflow._vendor.faster_whisper.audio import decode_audio
from lightningflow.desktop import worker
from lightningflow.desktop.state import Preferences,Settings,History

root=Path(__file__).resolve().parents[1]


class ReplayStream:
    samples=decode_audio(str(root/'benchmarks/synthetic.wav'))
    offset=0
    opens=0
    def __init__(self,**_): type(self).opens+=1
    def start(self): pass
    def close(self): pass
    def read(self,n):
        time.sleep(n/16000*.15)
        data=self.samples[self.offset:self.offset+n]
        type(self).offset+=n
        return np.pad(data,(0,max(0,n-len(data))))[:,None],False


def run():
    directory=root/'.work/hold-integration'
    Preferences(directory/'settings.json').save(Settings(activation='hold',history_enabled=True))
    engine=worker.build_backend(directory/'settings.json',root/'models')
    engine.guard.identity=lambda:None  # This test has no external target.
    events=[]; old_send=worker.send
    worker.send=lambda kind,**data:events.append({'event':kind,'at':time.perf_counter(),**data})
    old_stream=app.sd.InputStream; old_options=app.input_options
    app.sd.InputStream=ReplayStream; app.input_options=lambda _:{}
    log=History(directory/'log.sqlite3',True); log.clear()
    threads=[threading.Thread(target=f,daemon=True) for f in (engine.infer,engine.capture)]
    def tick():
        engine.on_tick()
        while True:
            try: kind,value=engine.events.get_nowait()
            except queue.Empty: break
            if kind=='ready': engine.ready=True
            if kind=='fatal': raise RuntimeError(value)
            if kind=='done': engine.deliver(value)
        time.sleep(.001)
    def wait(predicate,limit=30):
        deadline=time.perf_counter()+limit
        while not predicate():
            if time.perf_counter()>deadline: raise RuntimeError('Hold test timed out')
            tick()
    try:
        for thread in threads: thread.start()
        wait(lambda:engine.ready)
        # Two ordinary taps, including a former double-tap gesture.
        for _ in range(2):
            engine.key_down(engine.args.toggle_vk,True)
            until=time.perf_counter()+.05
            wait(lambda:time.perf_counter()>=until)
            engine.key_up(engine.args.toggle_vk)
        assert not engine.active and ReplayStream.opens==0
        results=[]
        for index in range(2):
            ReplayStream.offset=0
            pressed=time.perf_counter()
            engine.key_down(engine.args.toggle_vk,True)
            wait(lambda:engine.active is not None)
            session=engine.active; session.destination='scratchpad'
            wait(lambda:ReplayStream.offset>=len(ReplayStream.samples))
            stopped=time.perf_counter()
            engine.key_up(engine.args.toggle_vk)
            stop_dispatch_ms=(time.perf_counter()-stopped)*1000
            assert not engine.recording and session.capture_until
            wait(lambda:engine.active is None)
            result=next(e for e in reversed(events) if e['event']=='result')
            assert result['delivered'] and 'project report' in result['text'] and 'CUDA' in result['text']
            log.add(result)
            starts=[e for e in events if e['event']=='status' and e.get('state')=='starting']
            results.append({'press_to_start_signal_ms':(starts[-1]['at']-pressed)*1000,
                            'release_to_stop_command_ms':stop_dispatch_ms,
                            'release_to_completed_transcript_ms':(time.perf_counter()-stopped)*1000,
                            'gpu_decode_ms':session.decode_ms})
        log.close(); log=History(directory/'log.sqlite3',True)
        assert len(log.rows)==2
        ready=[e for e in events if e['event']=='status' and e.get('state')=='ready' and e.get('provider')]
        assert len(ready)==1
        return {'tap_and_double_tap_opened_no_microphone':True,'hold_threshold_ms':120,
                'two_completed_transcripts_persisted':True,'gpu_initializations':len(ready),
                'sessions':results,'provider':'CUDA / CTranslate2',
                'scope':'Direct production key callbacks and accelerated PCM replay; not physical-keyboard or acoustic latency'}
    finally:
        engine.quit.set()
        for thread in threads:thread.join(2)
        log.close(); worker.send=old_send
        app.sd.InputStream=old_stream; app.input_options=old_options


if __name__=='__main__':
    result=run()
    (root/'results/hold-integration-0.3.1.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
