"""Repeat both production modifier gestures against real resident CUDA.

Runs only replay audio and an isolated log. No hooks, OS key injection,
microphone, clipboard, external target inspection or text submission.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import re
import statistics
import sys
import threading
import time
from types import SimpleNamespace
import numpy as np
import psutil

root=Path(__file__).resolve().parents[1]
# An explicit engine path can validate a staged release; default to this checkout.
sys.path.insert(0,os.environ.get('LIGHTNINGFLOW_TEST_ENGINE',str(root)))
from lightningflow import app
from lightningflow import __version__
import lightningflow.desktop.personalization as personalization
from lightningflow.desktop import worker
from lightningflow.desktop.state import Preferences,Settings,History
from lightningflow.desktop.personalization import correct_vocabulary,prepare_transcript
from lightningflow._vendor.faster_whisper.audio import decode_audio
from lightningflow.benchmark import error_rate


def distribution(values):
    values=sorted(values)
    return {'median':statistics.median(values),'p95':values[int(.95*(len(values)-1))],'max':max(values),'min':min(values)} if values else {}


def run(per_mode,manifest_path,output,pair_count=100,technical_every=10,settings_path=None,model=None,compute=None):
    settings=Preferences(settings_path).load() if settings_path else Settings(
        model=model or 'tiny.en',compute=compute or 'float16',models_dir=str(root/'models'),
        recording_shortcut='ctrl_win',activation='smart',personalization_enabled=True,
        voice_profile=json.loads((root/'examples/vocabulary.json').read_text()))
    if model:settings.model=model
    if compute:settings.compute=compute
    assert settings.recording_shortcut=='ctrl_win' and settings.activation=='smart'
    assert settings.personalization_enabled and settings.voice_profile
    fixtures=json.loads(Path(manifest_path).read_text(encoding='utf-8-sig'))
    base=Path(manifest_path).resolve().parent
    resolve=lambda value:Path(value) if Path(value).is_absolute() else base/value
    audio=[decode_audio(str(resolve(row['audio']))) for row in fixtures]
    references=[resolve(row['reference']).read_text(encoding='utf-8-sig') for row in fixtures]
    directory=root/'.work'/('ctrl-win-soak-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    directory.mkdir(parents=True)
    Preferences(directory/'settings.json').save(Settings(**{**asdict(settings),'history_enabled':True,'overlay':False,'cleanup_mode':'Raw'}))
    engine=worker.build_backend(directory/'settings.json',Path(settings.models_dir))
    engine.guard.identity=lambda:None
    engine.guard.insert=lambda *_:(_ for _ in ()).throw(AssertionError('External insertion forbidden'))
    results=[];states=[];faults=[]
    def emit(kind,**data):
        if kind=='result':results.append((time.perf_counter(),data))
        elif kind=='status':states.append((time.perf_counter(),data))
    worker.send=emit
    app.u.GetAsyncKeyState=lambda _:0

    class Replay:
        samples=audio[0];offset=0;opens=0;closes=0;live=0
        def __init__(self,**_):type(self).opens+=1
        def start(self):type(self).live+=1
        def close(self):type(self).live-=1;type(self).closes+=1
        def read(self,n):
            time.sleep(n/16000*.06)
            data=type(self).samples[type(self).offset:type(self).offset+n]
            type(self).offset+=n
            return np.pad(data,(0,max(0,n-len(data))))[:,None],False
    app.sd.InputStream=Replay;app.input_options=lambda _:{}
    real_asr=app.CudaASR;models=[]
    def asr(*args,**kwargs):
        model=real_asr(*args,**kwargs)
        # Keep measurements, not a cross-thread ownership reference to CUDA.
        models.append({'provider':model.provider,'prompt_cache':model._prompt_cache})
        return model
    app.CudaASR=asr
    new_session=engine.new_session
    def session(target):
        value=new_session(None);value.destination='scratchpad'
        frames=type(value.raw)
        class Tracked(frames):
            appended=0
            def append(self,frame):self.appended+=1;super().append(frame)
        value.raw=Tracked()
        return value
    engine.new_session=session
    log=History(directory/'log.sqlite3',True)
    threads=[threading.Thread(target=f,daemon=True) for f in (engine.infer,engine.capture)]
    def tick():
        engine.on_tick()
        while True:
            try:kind,value=engine.events.get_nowait()
            except queue.Empty:break
            if kind=='ready':engine.ready=True
            elif kind=='fatal':raise AssertionError(value)
            elif kind=='done':engine.schedule_delivery(value)
        engine.tick_delivery()
        time.sleep(.001)
    def wait(predicate,limit=30):
        deadline=time.perf_counter()+limit
        while not predicate():
            assert time.perf_counter()<deadline,'Replay state timed out'
            tick()
    def delay(seconds):
        deadline=time.perf_counter()+seconds;wait(lambda:time.perf_counter()>=deadline)
    def key(vk,down):return engine.guard.key_event(vk,down)
    records=[];seen=set();rss=[]
    normalize=lambda s:re.sub(r'[^a-z0-9 ]','',s.casefold().replace('3','three')).split()
    started=time.perf_counter()
    try:
        for thread in threads:thread.start()
        wait(lambda:engine.ready)
        assert len(models)==1 and models[0]['provider']=='CUDA / CTranslate2'
        for index in range(per_mode*2):
            mode='hold' if index%2==0 else 'locked';n=index//2
            fixture=1 if n%technical_every==technical_every-1 and len(audio)>1 else 0
            Replay.samples=audio[fixture];Replay.offset=0
            ctrl=(0xA2,0xA3)[n//2%2];win=(0x5B,0x5C)[n%2]
            first,second=(ctrl,win) if n//4%2==0 else (win,ctrl)
            begin=time.perf_counter();key(first,True);key(second,True)
            dispatch_ms=(time.perf_counter()-begin)*1000
            current=engine.active;assert current and engine.recording
            if mode=='locked':
                # Actual short-press/pause/resume timing, not a synthetic clock
                # jump. Exercise both retained-modifier and full-release taps.
                delay(.025)
                key(second,False)
                if n%2:key(first,False)
                wait(lambda:Replay.live==0)
                assert engine.gesture.state=='waiting'
                delay(.035+(n%3)*.02)
                if n%2:key(first,True)
                key(second,True)
                assert engine.gesture.state=='locked'
                delay(.020)
                key(second,False);key(first,False)
                assert engine.recording and not current.capture_until
            # Repeat messages never make a second recording or unlock it.
            if mode=='hold':
                key(first,True);key(second,True)
            wait(lambda:Replay.offset>=len(Replay.samples)+1600)
            wait(lambda:time.perf_counter()-begin>.22)
            raw_count=current.raw.appended
            begin_stop=time.perf_counter()
            if mode=='hold':key((first,second)[n//8%2],False)
            else:key(first,True);key(second,True)
            stop_dispatch_ms=(time.perf_counter()-begin_stop)*1000
            assert not engine.recording and current.capture_until>=begin_stop
            key(second,False);key(first,False)
            wait(lambda:engine.active is None)
            completed,result=results[-1]
            assert len(results)==index+1 and result['delivered'] and not result.get('error')
            assert result['id'] not in seen;seen.add(result['id'])
            assert current.raw.appended==raw_count,'Audio appended after stop edge'
            assert not engine.guard.recording_chord.held and not engine.guard.recording_chord.consumed_windows
            assert not Replay.live and engine.jobs.empty() and not engine.pending
            assert not current.raw,'Delivered audio not released'
            if fixture==0:assert normalize(result['text'])==normalize(references[0]),'Baseline fixture changed'
            if fixture==1 and hasattr(personalization,'format_gpu_identifier'):
                if 'RTX 5070' not in result['text']:
                    (directory/'identifier-failure.json').write_text(json.dumps({'raw':result.get('raw'),'final':result['text']},indent=2))
                assert 'RTX 5070' in result['text'],'RTX identifier regression in streamed dictation'
            log.add(result)
            assert len(log.rows)==index+1
            memory=psutil.Process().memory_info().rss/1024**2;rss.append(memory)
            records.append({'cycle':index+1,'mode':mode,'fixture':fixture+1,
                'press_dispatch_ms':dispatch_ms,'stop_dispatch_ms':stop_dispatch_ms,
                'stop_to_result_ms':(completed-begin_stop)*1000,'gpu_decode_ms':current.decode_ms,
                'WER':error_rate(references[fixture],result['text']),'process_RSS_MiB':memory})
            if (index+1)%20==0:
                print(json.dumps({'progress':index+1,'of':per_mode*2,'model_initializations':len(models)}),flush=True)
        log.close();log=History(directory/'log.sqlite3',True)
        assert len(log.rows)==per_mode*2 and {r['id'] for r in log.rows}==seen
        assert Replay.opens==Replay.closes and not Replay.live and len(models)==1

        # Paired AB/BA comparisons share this exact resident model. Balance
        # ordering to reduce warm-up, GPU clock and background-load bias.
        gpu=models[0];hint=engine.asr_hint
        def decode(samples,context=''):
            # Route benchmark work through the production inference queue too.
            # Calling CTranslate2 from a second thread can leave CUDA thread-
            # local resources alive at interpreter teardown on this runtime.
            request=app.Session(None);request.asr_prompt=context
            engine.enqueue('chunk',request,SimpleNamespace(audio=samples,overlapped=False))
            engine.enqueue('finish',request)
            deadline=time.perf_counter()+30
            while True:
                assert time.perf_counter()<deadline,'Benchmark decode timed out'
                try:kind,value=engine.events.get(timeout=.1)
                except queue.Empty:continue
                if kind=='fatal':raise AssertionError(value)
                if kind=='done' and value is request:
                    assert not request.error,request.error
                    return request.text,request.decode_ms
        for fixture in range(len(audio)):
            decode(audio[fixture]);decode(audio[fixture],hint)
        comparisons=[]
        for pair in range(pair_count):
            fixture=pair%len(audio)
            order=[False,True,True,False] if pair//len(audio)%2==0 else [True,False,False,True]
            sample={};replicates={'on':[],'off':[]}
            for enabled in order:
                raw,decode_ms=decode(audio[fixture],hint if enabled else '')
                processing_settings=Settings(**{**asdict(settings),'personalization_enabled':enabled,'cleanup_mode':'Raw'})
                began=time.perf_counter();final=prepare_transcript(raw,processing_settings)
                process_ms=(time.perf_counter()-began)*1000
                normalized=personalization.format_gpu_identifier(raw,settings.voice_profile) if enabled and hasattr(personalization,'format_gpu_identifier') else raw
                assert re.findall(r'\d+(?:[.,:]\d+)*',normalized)==re.findall(r'\d+(?:[.,:]\d+)*',final)
                replicates['on' if enabled else 'off'].append({'decode_ms':decode_ms,'postprocessing_ms':process_ms,
                    'total_ms':decode_ms+process_ms,'raw_WER':error_rate(references[fixture],raw),'final_WER':error_rate(references[fixture],final)})
                if fixture>0 and enabled:
                    name=next((w for w in settings.voice_profile['vocabulary'] if len(w.split())==3),None)
                    terms={'name':name,'project':'PATHOS','dataset':'WESAD','evaluation':'LOSO','runtime':'CUDA','GPU_identifier':'RTX 5070'}
                    sample['key_term_matches']={label:bool(term and term in final) for label,term in terms.items()}
            for mode,values in replicates.items():
                sample[mode]={metric:statistics.mean(v[metric] for v in values) for metric in values[0]}
                sample[mode]['replicates']=values
            comparisons.append({'fixture':fixture+1,**sample})
            if (pair+1)%20==0:print(json.dumps({'paired_benchmark_progress':pair+1,'of':pair_count}),flush=True)

        # Verify imported canonical spellings and every vocabulary term without
        # recording or modifying the user's saved personal profile.
        canonical_ok=sum(correct_vocabulary(w.lower(),settings.voice_profile)==w for w in settings.voice_profile['canonical'])
        unchanged_ok=sum(correct_vocabulary(w,settings.voice_profile)==w for w in settings.voice_profile['vocabulary'])
        assert canonical_ok==len(settings.voice_profile['canonical'])
        assert unchanged_ok==len(settings.voice_profile['vocabulary'])
        silence,_=decode(np.zeros(16000,dtype=np.float32),hint)
        assert not silence
        by_fixture=[]
        for fixture in range(len(audio)):
            pairs=[p for p in comparisons if p['fixture']==fixture+1]
            by_fixture.append({'fixture':fixture+1,'pairs':len(pairs),
                **{mode:{metric:distribution([p[mode][metric] for p in pairs]) for metric in ('decode_ms','postprocessing_ms','total_ms','raw_WER','final_WER')} for mode in ('off','on')},
                'paired_total_delta_ms':distribution([p['on']['total_ms']-p['off']['total_ms'] for p in pairs]),
                'key_term_passes':dict(Counter(k for p in pairs for k,v in p.get('key_term_matches',{}).items() if v))})
        report={'version':__version__,'model':settings.model,'compute':settings.compute,'provider':gpu['provider'],
            'completed':len(records),'per_mode':{mode:sum(r['mode']==mode for r in records) for mode in ('hold','locked')},
            'unique_persistent_log_records':len(log.rows),'GPU_model_initializations':len(models),
            'stream_opens':Replay.opens,'stream_closes':Replay.closes,'post_stop_audio_appends':0,
            'prompt_cache_entries':len(gpu['prompt_cache']),'hint_tokens':len(gpu['prompt_cache'][hint]),
            'vocabulary_terms_preserved':unchanged_ok,'canonical_spellings_checked':canonical_ok,
            'personalization_on_all_recording_cycles':True,'hinted_silence_emitted_text':bool(silence),
            'paired_benchmark_order':'ABBA/BAAB blocks, two measurements per condition per block, alternated for each fixture',
            'timings':{mode:{metric:distribution([r[metric] for r in records if r['mode']==mode]) for metric in ('press_dispatch_ms','stop_dispatch_ms','stop_to_result_ms','gpu_decode_ms')} for mode in ('hold','locked')},
            'RSS_MiB':distribution(rss),'RSS_warm_mean_change_MiB':statistics.mean(rss[-20:])-statistics.mean(rss[20:40] or rss),
            'paired_benchmark':by_fixture,'cycles':records,'paired_samples':comparisons,
            'elapsed_seconds':time.perf_counter()-started,
            'scope':'Production modifier dispatcher, realistic tap gaps, accelerated synthetic PCM, real CUDA, isolated log. Engine from LIGHTNINGFLOW_TEST_ENGINE or this source checkout. Not physical keyboard/hook/Start-menu, microphone, external insertion, human-speech accuracy, GUI animation FPS or a 30-minute-session certification. GPU load is not exclusive.'}
        Path(output).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('cycles','paired_samples')},indent=2),flush=True)
    finally:
        engine.quit.set()
        for thread in threads:thread.join(5)
        log.close()
        assert not any(thread.is_alive() for thread in threads),'Test worker did not stop normally'
        models.clear()
        if 'gpu' in locals():del gpu
        import gc
        gc.collect()
        print('TEST_WORKER_CLEANUP_COMPLETE',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--per-mode',type=int,default=100)
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--pairs',type=int,default=100)
    parser.add_argument('--technical-every',type=int,default=10)
    parser.add_argument('--settings',help='Optional private settings file; the default uses only the example profile')
    parser.add_argument('--model');parser.add_argument('--compute')
    args=parser.parse_args();run(args.per_mode,args.manifest,args.output,args.pairs,args.technical_every,args.settings,args.model,args.compute)
