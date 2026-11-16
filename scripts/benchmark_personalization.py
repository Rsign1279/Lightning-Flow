"""Private local personalization benchmark; reports no names or transcripts."""
import argparse
import json
from pathlib import Path
import re
import statistics
import time
import numpy as np
from lightningflow.asr import CudaASR
from lightningflow._vendor.faster_whisper.audio import decode_audio
from lightningflow.benchmark import error_rate
from lightningflow.desktop.personalization import import_bank,hint_text,correct_vocabulary


def run(bank,prompt,manifest,models):
    profile=import_bank(bank,prompt)
    hint=hint_text(profile)
    fixtures=json.loads(Path(manifest).read_text(encoding='utf-8-sig'))
    cases=[(decode_audio(row['audio']),Path(row['reference']).read_text(encoding='utf-8-sig')) for row in fixtures]
    engine=CudaASR(Path(models)/'tiny.en','float16')
    results=[]
    for index,(audio,reference) in enumerate(cases):
        modes={}
        for name,context in [('baseline',''),('personalized',hint)]:
            times=[];raw=None
            for _ in range(3):
                began=time.perf_counter();raw=engine.transcribe(audio,initial_prompt=context)
                times.append((time.perf_counter()-began)*1000)
            final=correct_vocabulary(raw,profile) if context else raw
            # Token-number equality is strict for digits; spelled number variants
            # still require an appropriately normalized reference for WER.
            numbers=lambda text:re.findall(r'\d+(?:[.,:]\d+)*',text)
            modes[name]={'median_decode_ms':statistics.median(times),'decode_ms':times,
                'raw_wer':error_rate(reference,raw),'final_wer':error_rate(reference,final),
                'digit_values_match_reference':numbers(raw)==numbers(reference),
                'postprocessing_preserved_digits':numbers(raw)==numbers(final)}
        results.append({'fixture':index+1,**modes})
    silence=engine.transcribe(np.zeros(16000,dtype=np.float32),initial_prompt=hint)
    return {'provider':engine.provider,'model':'tiny.en','compute':'float16','model_initializations':1,
        'vocabulary_terms':len(profile['vocabulary']),'contextual_rules':len(profile['rules']),
        'hint_token_count':len(engine._prompt_cache[hint]),'hint_token_limit':192,
        'silence_emitted_text':bool(silence),'cases':results,
        'scope':'Synthetic speech only, three decodes per mode, one resident CUDA model. This is not accuracy on the user\'s voice; no acoustic training. No audio or profile uploads.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for flag in ('bank','prompt','manifest','models','output'):parser.add_argument('--'+flag,required=True)
    args=parser.parse_args()
    result=run(args.bank,args.prompt,args.manifest,args.models)
    Path(args.output).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
