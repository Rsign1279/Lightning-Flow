"""Real CUDA queue/fault/recovery integration; synthetic audio, no desktop input."""
import json
from pathlib import Path
import queue
import threading
import time
import numpy as np
from lightningflow import app,__version__
from lightningflow.desktop import worker
from lightningflow.desktop.state import Settings,Preferences
from lightningflow._vendor.faster_whisper.audio import decode_audio


def run():
    root=Path(__file__).resolve().parents[1];folder=root/'.work/queue-recovery';folder.mkdir(parents=True,exist_ok=True)
    settings=Settings(model='small.en',compute='int8_float16',recording_shortcut='ctrl_win',activation='smart',retain_failed_audio=True)
    Preferences(folder/'settings.json').save(settings)
    samples=decode_audio(str(root/'benchmarks/synthetic.wav'))
    block_decode=threading.Event();release=threading.Event();entered=threading.Event();models=[];results=[];events=[]
    class Replay:
        offset=0;live=0;fault=False
        def __init__(self,**_):pass
        def start(self):Replay.live+=1
        def close(self):Replay.live-=1
        def read(self,n):
            time.sleep(n/16000*.06)
            if Replay.fault and Replay.offset>=len(samples):raise OSError('Synthetic microphone disconnection')
            data=samples[Replay.offset:Replay.offset+n];Replay.offset+=n
            return np.pad(data,(0,max(0,n-len(data))))[:,None],False
    original=(app.sd.InputStream,app.input_options,app.CudaASR,worker.send,app.u.GetAsyncKeyState)
    class CUDA:
        def __init__(self,*args,**kwargs):
            self.engine=original[2](*args,**kwargs);models.append(self.engine.provider)
        def __getattr__(self,name):return getattr(self.engine,name)
        def transcribe(self,*args,**kwargs):
            if block_decode.is_set():entered.set();assert release.wait(30)
            return self.engine.transcribe(*args,**kwargs)
    def send(kind,**data):
        if kind=='result':results.append(data)
        events.append((kind,data))
    app.sd.InputStream=Replay;app.input_options=lambda _:{};app.CudaASR=CUDA;worker.send=send;app.u.GetAsyncKeyState=lambda _:0
    engine=worker.build_backend(folder/'settings.json',root/'models');engine.guard.identity=lambda:None
    engine.guard.insert=lambda *_:(_ for _ in ()).throw(AssertionError('No external insertion permitted'))
    engine.recovery.store.clear()
    original_session=engine.new_session
    def session(target):
        item=original_session(None);item.destination='scratchpad';return item
    engine.new_session=session
    threads=[threading.Thread(target=f) for f in (engine.infer,engine.capture)]
    def tick():
        engine.on_tick()
        while True:
            try:kind,value=engine.events.get_nowait()
            except queue.Empty:break
            if kind=='ready':engine.ready=True
            elif kind=='fatal':raise AssertionError(value)
            elif kind=='done':engine.schedule_delivery(value)
        engine.tick_delivery();time.sleep(.001)
    def wait(predicate,timeout=30):
        end=time.perf_counter()+timeout
        while not predicate():assert time.perf_counter()<end,'GPU queue/recovery timeout';tick()
    key=engine.guard.key_event
    def start():
        Replay.offset=0;key(0xA2,True);key(0x5B,True);assert engine.recording;return engine.active
    def stop():key(0x5B,False);key(0xA2,False)
    try:
        for thread in threads:thread.start()
        wait(lambda:engine.ready)
        block_decode.set();first=start();wait(entered.is_set)
        wait(lambda:Replay.offset>=len(samples)+1600);stop()
        second=start();assert first is not second and len(engine.sessions)==2
        wait(lambda:Replay.offset>=len(samples)+1600);stop();block_decode.clear();release.set()
        wait(lambda:engine.active is None)
        assert [r['id'] for r in results]==[first.ident,second.ident] and all(r['delivered'] for r in results)
        assert first.text==second.text and not first.raw and not second.raw
        Replay.fault=True;failed=start();wait(lambda:engine.active is None);stop()
        assert failed.capture_warning and failed.raw and failed.text and not failed.delivered
        captured=np.array(failed.raw)
        wait(lambda:(engine.recovery.store.folder(failed.ident)/'manifest.json').exists())
        # Drop the RAM copy, then load the committed recording through the
        # actual worker command path and retranscribe on the original model.
        engine.failed.clear();engine.external.put({'action':'retranscribe','id':failed.ident})
        wait(lambda:len(results)==4)
        assert results[-1]['id']==failed.ident and results[-1]['delivered'] and results[-1]['text']==failed.text
        assert len(models)==1 and models[0]=='CUDA / CTranslate2' and not Replay.live
        wait(lambda:not engine.recovery.store.folder(failed.ident).exists())
        assert not engine.sessions and engine.jobs.empty()
        return {'version':__version__,'provider':models[0],'model':'small.en','compute':'int8_float16',
            'model_initializations':len(models),'queued_order_preserved':True,'queued_transcripts_identical':True,
            'microphone_fault_preserved_audio_and_text':True,'encrypted_disk_reload_retranscribed':True,
            'retranscribed_text_identical':True,'failed_audio_seconds':len(captured)*.02,
            'external_insertions':0,'scope':'Synthetic replay and an injected device error through production capture, queue, DPAPI persistence and resident CUDA. No microphone, physical keyboard or external editor.'}
    finally:
        release.set();engine.quit.set()
        for thread in threads:thread.join(8)
        app.sd.InputStream,app.input_options,app.CudaASR,worker.send,app.u.GetAsyncKeyState=original
        assert not any(thread.is_alive() for thread in threads)


if __name__=='__main__':
    result=run();Path('results/queue-recovery-0.6.0.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
