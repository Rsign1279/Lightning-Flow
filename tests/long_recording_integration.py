"""Long-duration synthetic PCM through production Ctrl+Win and resident CUDA.

No hooks/OS key injection, microphone or external editor. --speed 1 is wall
clock replay; smaller values accelerate the same duration of captured audio.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import queue
import threading
import time
import numpy as np
import psutil


def run(seconds=1800,speed=.08,model='small.en',compute='int8_float16'):
    from lightningflow import app,__version__
    from lightningflow.desktop import worker
    from lightningflow.desktop.state import Preferences,Settings
    from lightningflow._vendor.faster_whisper.audio import decode_audio
    from lightningflow.benchmark import error_rate
    root=Path(__file__).resolve().parents[1]
    folder=root/'.work/long-recording';folder.mkdir(parents=True,exist_ok=True)
    settings=Settings(model=model,compute=compute,models_dir=str(root/'models'),recording_shortcut='ctrl_win',activation='smart',
        max_seconds=3600,personalization_enabled=True,voice_profile=json.loads((root/'examples/vocabulary.json').read_text()))
    Preferences(folder/'settings.json').save(settings)
    samples=decode_audio(str(root/'benchmarks/synthetic.wav'))
    reference=(root/'benchmarks/reference.txt').read_text(encoding='utf-8').strip()
    tail=decode_audio(str(folder/'final-marker.wav'))
    tail_reference=(folder/'final-marker.txt').read_text(encoding='utf-8').strip()
    total=int(seconds*16000);repeats=int((total-len(tail)-16000)//len(samples));body=repeats*len(samples)
    assert repeats>0 and body+len(tail)<=total
    results=[];messages=[];models=[];faults=[]
    class Replay:
        offset=0;live=0;opens=0;closes=0
        def __init__(self,**_):Replay.opens+=1
        def start(self):Replay.live+=1
        def close(self):Replay.live-=1;Replay.closes+=1
        def read(self,n):
            time.sleep(n/16000*speed)
            start=Replay.offset;end=start+n;value=np.zeros(n,dtype=np.float32)
            if start<body:
                stop=min(end,body);value[:stop-start]=samples[np.arange(start,stop)%len(samples)]
            a=max(start,body);b=min(end,body+len(tail))
            if b>a:value[a-start:b-start]=tail[a-body:b-body]
            Replay.offset=end
            return value[:,None],False
    original_stream=app.sd.InputStream;original_options=app.input_options;original_asr=app.CudaASR;original_send=worker.send
    original_keys=app.u.GetAsyncKeyState
    def cuda(*args,**kwargs):
        engine=original_asr(*args,**kwargs);models.append(engine.provider);return engine
    def send(kind,**data):
        if kind=='result':results.append(data)
        elif kind=='status' and data['state']=='error':faults.append(data.get('message'))
    app.sd.InputStream=Replay;app.input_options=lambda _:{};app.CudaASR=cuda;app.u.GetAsyncKeyState=lambda _:0;worker.send=send
    engine=worker.build_backend(folder/'settings.json',root/'models')
    engine.guard.identity=lambda:None
    engine.guard.insert=lambda *_:(_ for _ in ()).throw(AssertionError('External input is forbidden in this test'))
    original_session=engine.new_session
    def session(_target):
        item=original_session(None);item.destination='scratchpad'
        frames=type(item.raw)
        class Tracked(frames):
            appended=0
            def append(self,frame):self.appended+=1;super().append(frame)
        item.raw=Tracked();return item
    engine.new_session=session
    threads=[threading.Thread(target=f) for f in (engine.infer,engine.capture)]
    process=psutil.Process();rss=[];report=[];started=time.perf_counter();last_sample=0;last_progress=0
    def tick():
        nonlocal last_sample,last_progress
        engine.on_tick()
        while True:
            try:kind,value=engine.events.get_nowait()
            except queue.Empty:break
            if kind=='ready':engine.ready=True
            elif kind=='fatal':raise AssertionError(value)
            elif kind=='done':engine.schedule_delivery(value)
        engine.tick_delivery()
        now=time.perf_counter()
        if now-last_sample>.5:rss.append(process.memory_info().rss/1024**2);last_sample=now
        if now-last_progress>20:
            print(json.dumps({'captured_audio_seconds':round(Replay.offset/16000,1),'model_loads':len(models),'pending_real_jobs':engine.jobs.qsize()}),flush=True)
            last_progress=now
        time.sleep(.001)
    def wait(predicate,timeout):
        end=time.perf_counter()+timeout
        while not predicate():
            assert time.perf_counter()<end,'Long recording timed out'
            assert not faults,faults
            tick()
    def delay(value):
        until=time.perf_counter()+value;wait(lambda:time.perf_counter()>=until,value+5)
    key=engine.guard.key_event
    try:
        for thread in threads:thread.start()
        wait(lambda:engine.ready,45)
        for index,mode in enumerate(('hold','locked')):
            Replay.offset=0;begin=time.perf_counter();key(0xA2,True);key(0x5B,True)
            current=engine.active;assert current and engine.recording
            if mode=='locked':
                delay(.025);key(0x5B,False);key(0xA2,False);wait(lambda:not Replay.live,5)
                delay(.04);key(0xA2,True);key(0x5B,True);key(0x5B,False);key(0xA2,False)
                assert engine.gesture.state=='locked' and engine.recording
            wait(lambda:Replay.offset>=total+320,max(90,seconds*speed*3))
            captured=len(current.raw);stop=time.perf_counter()
            if mode=='hold':key(0x5B,False);key(0xA2,False)
            else:key(0xA2,True);key(0x5B,True);key(0x5B,False);key(0xA2,False)
            assert not engine.recording and current.capture_until
            wait(lambda:engine.active is None,90)
            completed=time.perf_counter()
            assert len(results)==index+1 and current.delivered and not current.error,results[-1]
            assert not Replay.live and engine.jobs.empty() and not engine.pending and not engine.sessions
            assert not current.raw and len(models)==1
            assert current.raw.appended==captured,'Audio appended after the stop edge'
            assert 'silver mountain' in current.text.casefold(),'Final spoken marker was lost'
            expected=(' '+reference)*repeats+' '+tail_reference
            wer=error_rate(expected,current.text)
            assert wer<.15,('Unexpected long-form synthetic WER',wer)
            report.append({'mode':mode,'captured_audio_seconds':captured*.02,'wall_seconds':completed-begin,
                'stop_to_result_ms':(completed-stop)*1000,'synthetic_WER':wer,'final_marker_present':True,
                'transcript_characters':len(current.text),'transcript_sha256':hashlib.sha256(current.text.encode()).hexdigest(),
                'single_result':True,'audio_released':True,'post_stop_audio_appends':0})
        return {'version':__version__,'model':model,'compute':compute,'provider':models[0],'model_initializations':len(models),
            'requested_audio_seconds_per_mode':seconds,'replay_wall_scale':speed,'cases':report,
            'stream_opens':Replay.opens,'stream_closes':Replay.closes,'peak_sampled_process_RSS_MiB':max(rss),
            'elapsed_seconds':time.perf_counter()-started,
            'scope':'Synthetic PCM of the reported duration, accelerated when scale <1, actual CUDA and production modifier callbacks. Isolated scratchpad; not a live microphone, physical Windows-key interception or external editor certification.'}
    finally:
        engine.quit.set()
        for thread in threads:thread.join(8)
        app.sd.InputStream=original_stream;app.input_options=original_options;app.CudaASR=original_asr
        app.u.GetAsyncKeyState=original_keys;worker.send=original_send
        assert not any(thread.is_alive() for thread in threads)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=int,default=1800);parser.add_argument('--speed',type=float,default=.08)
    parser.add_argument('--model',default='small.en');parser.add_argument('--compute',default='int8_float16')
    parser.add_argument('--output',default='results/long-recordings-0.6.0.json')
    args=parser.parse_args();value=run(args.seconds,args.speed,args.model,args.compute)
    Path(args.output).write_text(json.dumps(value,indent=2));print(json.dumps(value,indent=2))
