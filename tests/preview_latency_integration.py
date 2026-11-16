"""Real-time replay, one resident CUDA model, no microphone or OS input."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import queue
import threading
import time
import numpy as np


def run(model='tiny.en',compute='float16',settings_path=None):
    from lightningflow import app
    from lightningflow.desktop import worker
    from lightningflow.desktop.state import Settings,Preferences
    from lightningflow._vendor.faster_whisper.audio import decode_audio
    root=Path(__file__).resolve().parents[1]
    directory=root/'.work/preview-latency';directory.mkdir(parents=True,exist_ok=True)
    settings=Preferences(settings_path).load() if settings_path else Settings(model=model,compute=compute,models_dir=str(root/'models'))
    settings.recording_shortcut='ctrl_win';settings.activation='smart';settings.cleanup_mode='Raw';settings.history_enabled=False
    Preferences(directory/'settings.json').save(settings)
    samples=decode_audio(str(root/'benchmarks/synthetic.wav'))
    messages=[];engine=None;threads=[];output=[]
    class Replay:
        offset=0
        def __init__(self,**_):pass
        def start(self):pass
        def close(self):pass
        def read(self,n):
            time.sleep(n/16000)
            value=samples[Replay.offset:Replay.offset+n];Replay.offset+=n
            return np.pad(value,(0,max(0,n-len(value))))[:,None],False
    original_stream=app.sd.InputStream;original_options=app.input_options;original_send=worker.send
    app.sd.InputStream=Replay;app.input_options=lambda _:{}
    worker.send=lambda kind,**data:messages.append({'event':kind,**data})
    def tick():
        engine.on_tick()
        while True:
            try:kind,value=engine.events.get_nowait()
            except queue.Empty:break
            if kind=='ready':engine.ready=True
            elif kind=='fatal':raise RuntimeError(value)
            elif kind=='done':engine.schedule_delivery(value)
        engine.tick_delivery();time.sleep(.001)
    def wait(test,timeout=45):
        end=time.perf_counter()+timeout
        while not test():
            assert time.perf_counter()<end,'Preview benchmark timed out'
            tick()
    try:
        engine=worker.build_backend(directory/'settings.json',settings.models_dir)
        def no_target():raise RuntimeError('Isolated replay: no external field')
        engine.guard.identity=no_target
        new=engine.new_session
        def session(target):
            value=new(target);value.destination='scratchpad';return value
        engine.new_session=session
        threads=[threading.Thread(target=method) for method in (engine.infer,engine.capture)]
        for thread in threads:thread.start()
        wait(lambda:engine.ready)
        final=[]
        for enabled in (False,True):
            engine.settings.live_preview=enabled;Replay.offset=0
            engine.recording_edge('press');current=engine.active
            assert current and engine.recording
            wait(lambda:Replay.offset>=len(samples))
            current.requested_stop=time.perf_counter()
            engine.recording_edge('release')
            wait(lambda:engine.active is None)
            assert current.delivered and not current.error
            final.append(current.text)
            output.append({'preview_enabled':enabled,'first_partial_ms':(current.first_partial-current.began)*1000,
                'stop_to_result_ms':(time.perf_counter()-current.requested_stop)*1000,
                'authoritative_decode_ms':current.decode_ms,'delivered_to_isolated_scratchpad':current.delivered})
        assert final[0]==final[1],'Preview changed the authoritative transcript'
        assert output[1]['first_partial_ms']<output[0]['first_partial_ms']
        return {'model':settings.model,'compute':settings.compute,'provider':'CUDA / CTranslate2',
            'audio_seconds':len(samples)/16000,'cases':output,'final_transcripts_identical':True,
            'scope':'Real-time synthetic PCM replay, production capture/inference/gesture code, isolated scratchpad. Two sessions, no acoustic or physical-key latency and no external insertion.'}
    finally:
        if engine:engine.quit.set()
        for thread in threads:thread.join(5)
        app.sd.InputStream=original_stream;app.input_options=original_options;worker.send=original_send
        assert not any(thread.is_alive() for thread in threads)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--model',default='tiny.en');parser.add_argument('--compute',default='float16')
    parser.add_argument('--settings');parser.add_argument('--output',default='results/preview-latency-0.5.0.json')
    args=parser.parse_args();result=run(args.model,args.compute,args.settings)
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
