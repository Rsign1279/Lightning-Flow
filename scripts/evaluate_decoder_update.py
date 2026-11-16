"""Compare released vs candidate dictation decoding on private local fixtures.

All CUDA calls and model destruction stay on this main thread. Reports contain
aggregate errors/timings, not private profile contents or full transcripts.
"""
import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import re
import statistics
import time
import numpy as np
from lightningflow.asr import CudaASR
from lightningflow.desktop.state import Preferences,apply_dictionary
from lightningflow.desktop.personalization import hint_text,correct_vocabulary,clean_hesitations,format_gpu_identifier
from lightningflow._vendor.faster_whisper.audio import decode_audio
from lightningflow.benchmark import error_rate

root=Path(__file__).resolve().parents[1]


def stats(values):
    values=sorted(values)
    return {'median':statistics.median(values),'p95':values[int(.95*(len(values)-1))],'max':max(values)}


def run(manifest,output,repeats=3,blocks=0,model=None,baseline_engine=None):
    settings=Preferences(Path(os.environ['LOCALAPPDATA'])/'LightningFlow/settings.json').load()
    if model:settings.model=model
    path=(Path(baseline_engine) if baseline_engine else root/'desktop-dist/LightningFlow/engine')/'lightningflow/desktop/personalization.py'
    spec=importlib.util.spec_from_file_location('released_personalization',path)
    released=importlib.util.module_from_spec(spec);spec.loader.exec_module(released)
    fixtures=json.loads(Path(manifest).read_text(encoding='utf-8-sig'))
    cases=[(decode_audio(f['audio']),Path(f['reference']).read_text(encoding='utf-8-sig')) for f in fixtures]
    engine=CudaASR(Path(settings.models_dir)/settings.model,settings.compute)
    hint=hint_text(settings.voice_profile,settings.dictionary)
    tokens=engine.model.hf_tokenizer.encode(' '+hint,add_special_tokens=False).ids[:192]
    private=[]
    def decode(audio,mode):
        started=time.perf_counter()
        segments,_=engine.model.transcribe(audio,language='en',beam_size=1,best_of=1,temperature=0,
            condition_on_previous_text=False,vad_filter=True,
            vad_parameters={'min_silence_duration_ms':300,'speech_pad_ms':120},word_timestamps=False,
            initial_prompt=None if mode.endswith('off') else tokens,without_timestamps=mode=='new_on')
        raw=' '.join(s.text.strip() for s in segments).strip()
        decode_ms=(time.perf_counter()-started)*1000
        start=time.perf_counter()
        if mode=='new_on':text=correct_vocabulary(raw,settings.voice_profile)
        elif mode=='old_on':text=released.correct_vocabulary(raw,settings.voice_profile)
        else:text=raw
        text=apply_dictionary(text,settings.dictionary)
        if settings.transcript_style=='Clean':text=clean_hesitations(text)
        return raw,text,decode_ms,(time.perf_counter()-start)*1000
    accuracy=[]
    for index,(audio,reference) in enumerate(cases):
        entry={'fixture':index+1};final_texts={}
        for mode in ('old_on','new_on','old_off','new_off'):
            times=[]
            for _ in range(repeats):
                raw,text,ms,post=decode(audio,mode);times.append(ms+post)
            entry[mode]={'final_WER':error_rate(reference,text),'RTX_5070_exact':'RTX 5070' in text,
                        'RTX_5090_exact':'RTX 5090' in text,'total_ms':stats(times)}
            private.append({'fixture':index+1,'condition':mode,'raw':raw,'final':text})
            final_texts[mode]=text
        entry['accuracy_not_worse']=entry['new_on']['final_WER']<=entry['old_on']['final_WER']+1e-9
        entry['raw_mode_accuracy_not_worse']=entry['new_off']['final_WER']<=entry['old_off']['final_WER']+1e-9
        normalize=lambda text:re.sub(r'[^a-z0-9 ]','',text.casefold()).split()
        entry['content_matches_released_except_identifier_formatting']=normalize(format_gpu_identifier(final_texts['old_on'],settings.voice_profile))==normalize(final_texts['new_on'])
        entry['raw_mode_content_matches_released']=normalize(final_texts['old_off'])==normalize(final_texts['new_off'])
        accuracy.append(entry)
    pairs=[]
    for index in range(blocks):
        fixture=index%min(2,len(cases));audio,reference=cases[fixture]
        order=['old_off','old_on','new_on','new_on','old_on','old_off']
        if index//2%2:order=['new_on','old_on','old_off','old_off','old_on','new_on']
        values={mode:[] for mode in ('old_off','old_on','new_on')}
        for mode in order:
            _raw,text,ms,post=decode(audio,mode)
            values[mode].append({'decode_ms':ms,'postprocessing_ms':post,'total_ms':ms+post,'WER':error_rate(reference,text)})
        pairs.append({'fixture':fixture+1,**values})
        if (index+1)%20==0:print(json.dumps({'timing_blocks_complete':index+1,'of':blocks}),flush=True)
    timing=[]
    for fixture in range(min(2,len(cases))):
        samples=[p for p in pairs if p['fixture']==fixture+1]
        if not samples:continue
        entry={'fixture':fixture+1,'blocks':len(samples)}
        for mode in ('old_off','old_on','new_on'):
            entry[mode]=stats([v['total_ms'] for p in samples for v in p[mode]])
        for baseline in ('old_off','old_on'):
            deltas=np.array([statistics.mean(v['total_ms'] for v in p['new_on'])-statistics.mean(v['total_ms'] for v in p[baseline]) for p in samples])
            rng=np.random.default_rng(6738+fixture)
            medians=np.median(rng.choice(deltas,size=(10000,len(deltas)),replace=True),axis=1)
            ci=np.quantile(medians,[.025,.975])
            entry['new_minus_'+baseline]={'paired_median_ms':float(np.median(deltas)),
                'median_95CI_ms':[float(x) for x in ci],
                'P95_delta_ms':entry['new_on']['p95']-entry[baseline]['p95']}
        timing.append(entry)
    _raw,silence,_,_=decode(np.zeros(16000,dtype=np.float32),'new_on')
    report={'model':settings.model,'compute':settings.compute,'provider':engine.provider,'model_initializations':1,
            'hint_tokens':len(tokens),'accuracy_cases':accuracy,'all_accuracy_cases_not_worse':all(x['accuracy_not_worse'] for x in accuracy),
            'all_raw_mode_accuracy_cases_not_worse':all(x['raw_mode_accuracy_not_worse'] for x in accuracy),
            'all_content_preserved_except_identifier_formatting':all(x['content_matches_released_except_identifier_formatting'] for x in accuracy),
            'hinted_silence_emitted_text':bool(silence),'timing':timing,'timing_samples':pairs,
            'scope':'Local synthetic speech, released timestamp decoder vs candidate text-only decoder, unchanged CUDA model and 192-token hint. No physical key injection, human-speech accuracy guarantee or user data upload.'}
    Path(output).write_text(json.dumps(report,indent=2))
    private_path=root/'.work/personalization-private/rtx-fix'/('evaluation-'+Path(output).stem+'.json')
    private_path.write_text(json.dumps(private,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='timing_samples'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--manifest',required=True);p.add_argument('--output',required=True)
    p.add_argument('--repeats',type=int,default=3);p.add_argument('--blocks',type=int,default=0)
    p.add_argument('--model',choices=['tiny.en','base.en','small.en'])
    p.add_argument('--baseline-engine')
    a=p.parse_args();run(a.manifest,a.output,a.repeats,a.blocks,a.model,a.baseline_engine)
