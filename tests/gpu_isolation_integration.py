"""Own-child termination, retained capture and unchanged CUDA decoder output.

Never resets the display driver or other applications' CUDA contexts.
"""
import json
import os
from pathlib import Path
import queue
import statistics
import threading
import time
import numpy as np
import psutil
from lightningflow import app,__version__
from lightningflow.desktop import worker
from lightningflow.desktop.state import Preferences,Settings
from lightningflow._vendor.faster_whisper.audio import decode_audio
from lightningflow.asr_process import CudaASRProcess,GPUWorkerError
from lightningflow.asr import CudaASR
from lightningflow.benchmark import error_rate


def parity(root):
    samples=decode_audio(str(root/'benchmarks/synthetic.wav'));reference=(root/'benchmarks/reference.txt').read_text(encoding='utf-8')
    direct=CudaASR(root/'models/small.en','int8_float16');isolated=CudaASRProcess(root/'models/small.en','int8_float16')
    cases=[]
    try:
        for prompt in ('','CUDA, RTX 5070, PATHOS, WESAD, LOSO.'):
            times={'direct':[],'isolated':[]};baseline=[];remote=[]
            for index in range(8):
                for name,engine,values in (('direct',direct,baseline),('isolated',isolated,remote)) if index%2==0 else (('isolated',isolated,remote),('direct',direct,baseline)):
                    start=time.perf_counter();text=engine.transcribe(samples,initial_prompt=prompt)
                    times[name].append((time.perf_counter()-start)*1000);values.append(text)
            assert len(set(baseline+remote))==1,'Isolation changed the decoded text'
            cases.append({'personalization_hint':bool(prompt),'paired_decodes':8,'identical_transcripts':True,
                'synthetic_WER':error_rate(reference,baseline[0]),
                'direct_median_ms':statistics.median(times['direct']),'isolated_median_ms':statistics.median(times['isolated'])})
    finally:isolated.close()
    return cases


def fault(root,mode):
    folder=root/'.work/gpu-fault'/mode;folder.mkdir(parents=True,exist_ok=True)
    Preferences(folder/'settings.json').save(Settings(model='small.en',compute='int8_float16',recording_shortcut='ctrl_win',activation='smart'))
    samples=decode_audio(str(root/'benchmarks/synthetic.wav'));models=[];results=[]
    original=(app.CudaASR,app.sd.InputStream,app.input_options,app.u.GetAsyncKeyState,worker.send)
    class Replay:
        live=0;offset=0
        def __init__(self,**_):pass
        def start(self):Replay.live+=1
        def close(self):Replay.live-=1
        def read(self,n):
            time.sleep(.002)
            data=samples[np.arange(Replay.offset,Replay.offset+n)%len(samples)];Replay.offset+=n
            return data[:,None],False
    def model(*args,**kwargs):
        item=original[0](*args,**kwargs);models.append(item);return item
    def send(kind,**data):
        if kind=='result':results.append(data)
    app.CudaASR=model;app.sd.InputStream=Replay;app.input_options=lambda _:{};app.u.GetAsyncKeyState=lambda _:0;worker.send=send
    engine=worker.build_backend(folder/'settings.json',root/'models');engine.guard.identity=lambda:None
    engine.guard.insert=lambda *_:(_ for _ in ()).throw(AssertionError('Fault test cannot type externally'))
    threads=[threading.Thread(target=f) for f in (engine.infer,engine.capture)]
    def tick():
        engine.on_tick()
        while True:
            try:kind,value=engine.events.get_nowait()
            except queue.Empty:break
            if kind=='ready':engine.ready=not engine.gpu_error
            elif kind=='fatal':raise AssertionError(value)
            elif kind=='done':engine.schedule_delivery(value)
        engine.tick_delivery();time.sleep(.001)
    def wait(predicate,seconds=30):
        deadline=time.perf_counter()+seconds
        while not predicate():assert time.perf_counter()<deadline,'Fault integration timed out';tick()
    key=engine.guard.key_event
    try:
        for thread in threads:thread.start()
        wait(lambda:engine.ready)
        key(0xA2,True);key(0x5B,True);session=engine.active
        if mode=='locked':
            end=time.perf_counter()+.025;wait(lambda:time.perf_counter()>=end)
            key(0x5B,False);key(0xA2,False);wait(lambda:not Replay.live)
            key(0xA2,True);key(0x5B,True);key(0x5B,False);key(0xA2,False)
            assert engine.gesture.state=='locked'
        wait(lambda:bool(session.text));before=session.text
        proxy=models[0];children=psutil.Process(proxy.process.pid).children(recursive=True)
        actual=children[-1] if children else psutil.Process(proxy.process.pid)
        assert actual.pid!=os.getpid() and 'lightningflow.asr_process' in ' '.join(actual.cmdline())
        start=time.perf_counter();actual.kill()
        wait(lambda:engine.active is None)
        elapsed=(time.perf_counter()-start)*1000
        key(0x5B,False);key(0xA2,False)
        assert session.error and session.raw and session.text.startswith(before)
        assert not session.delivered and not engine.recording and not engine.ready and engine.gpu_error
        assert len(results)==1 and not results[0]['delivered'] and results[0]['audio_available']
        assert not Replay.live and all(thread.is_alive() for thread in threads)
        assert not engine.can_start_recording()
        return {'mode':mode,'parent_capture_and_inference_threads_survived':True,'microphone_closed':True,
            'audio_frames_retained':len(session.raw),'partial_text_retained':True,'automatic_insertions':0,
            'failed_runtime_reused':False,'fault_to_retained_result_ms':elapsed}
    finally:
        engine.quit.set()
        for thread in threads:thread.join(8)
        app.CudaASR,app.sd.InputStream,app.input_options,app.u.GetAsyncKeyState,worker.send=original
        assert not any(thread.is_alive() for thread in threads)


def timeout(root):
    engine=CudaASRProcess(root/'models/small.en','int8_float16',timeout=.3)
    try:
        children=psutil.Process(engine.process.pid).children(recursive=True)
        actual=children[-1] if children else psutil.Process(engine.process.pid)
        assert 'lightningflow.asr_process' in ' '.join(actual.cmdline())
        actual.suspend()  # Only this idle test interpreter, never the driver.
        start=time.perf_counter()
        try:engine.transcribe(np.ones(8*16000,dtype=np.float32)*.05)
        except GPUWorkerError as exc:assert 'timed out' in str(exc)
        else:raise AssertionError('A suspended CUDA worker did not time out')
        elapsed=(time.perf_counter()-start)*1000
        assert elapsed<2000 and engine.closed and not actual.is_running()
        return {'suspended_owned_child':True,'timeout_including_pipe_write_ms':elapsed,'child_terminated':True,'parent_survived':True}
    finally:engine.close()


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    value={'version':__version__,'provider':'CUDA / CTranslate2','model':'small.en','compute':'int8_float16',
        'parity':parity(root),'fault_cases':[fault(root,mode) for mode in ('hold','locked')],'timeout_case':timeout(root),
        'scope':'Actual GPU decodes and deliberate termination of this test-owned CUDA child. Synthetic speech and production modifier callbacks; not a forced driver TDR or physical keyboard test.'}
    Path('results/gpu-isolation-0.6.1.json').write_text(json.dumps(value,indent=2),encoding='utf-8');print(json.dumps(value,indent=2))
