"""100 additional hidden desktop/IPC/CUDA/log cycles; no user input or audio."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import re
import statistics
import threading
import time
import psutil

root=Path(__file__).resolve().parents[1]
run_id=datetime.now().strftime('%Y%m%d-%H%M%S')
directory=root/'.work'/('soak-100-'+run_id)
os.environ['LIGHTNINGFLOW_DATA_DIR']=str(directory)
from lightningflow.desktop.state import Settings,Preferences,History
from lightningflow.desktop.app import DesktopApp,PAGES
from lightningflow.desktop.bridge import EngineProcess


def normalized(text):
    return re.sub(r'[^a-z0-9 ]','',text.casefold().replace('3','three')).split()


def distribution(values):
    data=sorted(values)
    return {'min':min(data),'median':statistics.median(data),'p95':data[int((len(data)-1)*.95)],'max':max(data)} if data else {}


def run(count=100):
    preferences=Preferences(directory/'settings.json')
    preferences.save(Settings(history_enabled=True,overlay=False,onboarding_done=True,models_dir=str(root/'models')))
    desktop=DesktopApp(auto_engine=False,hidden=True)
    observed=queue.Queue()
    class Events(queue.Queue):
        def put(self,event,*a,**kw):
            if event.get('event') in ('test_ack','result','status','process_exit'):
                observed.put((time.perf_counter(),dict(event)))
            return super().put(event,*a,**kw)
    desktop.events=Events()
    errors=[];heartbeats=[];cycles=[];result_ids=set();results={};acks={};ready_signals=[]
    desktop.report_callback_exception=lambda _t,error,_tb:errors.append(str(error))
    desktop.engine=EngineProcess(root/'.venv/Scripts/python.exe',root,preferences.path,root/'models',desktop.events,
                                  worker_module='tests.soak_worker')
    process=psutil.Process(desktop.engine.process.pid)
    started=time.perf_counter();deadline=started+40
    phase='startup';index=0;release_keys=(0x77,0x11,0x12,0xA2,0xA3,0xA4,0xA5)
    memory=[];failure=None;theme=None
    expected=normalized((root/'benchmarks/reference.txt').read_text(encoding='utf-8'))
    def rss():
        children=process.children(recursive=True)
        return round(sum(p.memory_info().rss for p in [process,*children] if p.is_running())/1024**2,2)
    def beat():
        if desktop.closing:return
        heartbeats.append(time.perf_counter())
        desktop.after(16,beat)
    def next_cycle():
        nonlocal index,phase,deadline,theme
        index+=1
        next_theme='Light' if ((index-1)//len(PAGES))%2==0 else 'Dark'
        if next_theme!=theme:
            desktop.change_theme(next_theme);theme=next_theme
        desktop.navigate(PAGES[(index-1)%len(PAGES)][0])
        deadline=time.perf_counter()+20
        desktop.engine.send('test_taps',cycle=index)
        phase='taps'
    def drive():
        nonlocal phase,deadline,failure
        try:
            while True:
                try:received,event=observed.get_nowait()
                except queue.Empty:break
                kind=event.get('event')
                if kind=='test_ack':acks[(event.get('cycle'),event.get('action'))]=event
                if kind=='result':results[index]=event
                if kind=='status' and event.get('provider'):ready_signals.append(event)
                if kind=='process_exit':raise AssertionError('GPU worker exited unexpectedly')
            assert not errors,errors
            if time.perf_counter()>deadline:raise AssertionError(f'Cycle {index} timed out in {phase}: {desktop.status_message}')
            if desktop.engine_state=='error':raise AssertionError(desktop.status_message)
            if phase=='startup' and desktop.engine_state=='ready':next_cycle()
            elif phase=='taps' and (index,'taps') in acks:
                ack=acks[(index,'taps')]
                assert ack['ok'],f'Tap opened a recording: {ack}'
                assert index not in results,'Tap emitted a transcript'
                desktop.engine.send('test_hold',cycle=index,release_vk=release_keys[(index-1)%len(release_keys)])
                phase='dictation'
            elif phase=='dictation' and index in results and (index,'idle') in acks and desktop.engine_state=='ready':
                result=results[index]
                assert result['delivered'] and not result.get('error'),result.get('error')
                assert result['destination']=='scratchpad'
                assert normalized(result['text'])==expected,'Fixture transcript changed'
                assert result['id'] not in result_ids,'Duplicate transcript identifier'
                result_ids.add(result['id'])
                assert desktop.last_result['id']==result['id']
                assert desktop.history.connection.execute('SELECT COUNT(*) FROM transcripts').fetchone()[0]==index
                assert len(desktop.history.rows)==index and not desktop.history.error
                idle=acks[(index,'idle')];released=acks[(index,'released')]
                assert idle['stream_opens']==index and idle['stream_closes']==index
                assert idle['live_streams']==0 and idle['pending_jobs']==0
                assert idle['model_initializations']==1
                assert released['recording_stopped'] and released['capture_cutoff_set']
                assert released['repeat_messages']>0
                sample={'cycle':index,'page':desktop.page,'theme':theme,'passed':True,
                    'release_vk':release_keys[(index-1)%len(release_keys)],
                    'press_to_start_ms':acks[(index,'started')]['press_to_start_ms'],
                    'release_to_stop_command_ms':released['release_dispatch_ms'],
                    'release_to_completed_ms':result['metrics']['end_to_end_finish_ms'],
                    'gpu_decode_ms':result['metrics']['decode_ms'],
                    'worker_tree_rss_mib':rss(),
                    'gui_rss_mib':round(psutil.Process().memory_info().rss/1024**2,2)}
                cycles.append(sample)
                if index%10==0:
                    print(json.dumps({'completed':index,'passed':len(cycles),'last_gpu_decode_ms':round(sample['gpu_decode_ms'],1),
                        'worker_tree_rss_mib':sample['worker_tree_rss_mib']}),flush=True)
                if index==count:
                    phase='complete';desktop.quit_app();return
                next_cycle()
            desktop.after(5,drive)
        except Exception as exc:
            failure={'cycle':index,'phase':phase,'error':str(exc)}
            desktop.engine_state='error';desktop.retained_audio_ids.clear();desktop.quit_app()
    desktop.after(16,beat);desktop.after(25,drive)
    desktop.mainloop()
    stored=History(directory/'history.sqlite3',True)
    try:
        persisted=len(stored.rows)
        reopened_ids={row['id'] for row in stored.rows}
    finally:stored.close()
    report={'requested_cycles':count,'completed_cycles':len(cycles),'passed_cycles':len(cycles),
        'failed_cycles':1 if failure else 0,'unattempted_cycles':count-len(cycles)-(1 if failure else 0),
        'failure':failure,'quick_tap_checks':len([key for key in acks if key[1]=='taps'])*2,
        'unique_transcripts':len(result_ids),'persisted_after_reopen':persisted,
        'log_ids_match':reopened_ids==result_ids,'gpu_initializations':len(ready_signals),
        'elapsed_seconds':round(time.perf_counter()-started,2),'callback_errors':errors,
        'scope':'Hidden source desktop + real JSON IPC + production hold callbacks + accelerated PCM replay + actual CUDA + isolated SQLite log. No microphone, external apps, clipboard or physical keyboard injection.',
        'memory_scope':'Worker process tree RSS; frontend theme/page construction is included. Not a VRAM or long-term leak proof.',
        'cycles':cycles}
    for key in ('press_to_start_ms','release_to_stop_command_ms','release_to_completed_ms','gpu_decode_ms','worker_tree_rss_mib','gui_rss_mib'):
        report[key]=distribution([cycle[key] for cycle in cycles])
    report['gui_heartbeat_ms']=distribution([(b-a)*1000 for a,b in zip(heartbeats,heartbeats[1:])])
    if len(cycles)>=20:
        report['worker_rss_change_after_warmup_mib']=round(statistics.mean(c['worker_tree_rss_mib'] for c in cycles[-10:])-statistics.mean(c['worker_tree_rss_mib'] for c in cycles[10:20]),2)
    destination=root/'results'/('soak-100-'+run_id+'.json')
    destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='cycles'},indent=2),flush=True)
    print('REPORT: '+str(destination),flush=True)
    assert not failure and len(cycles)==count and persisted==count and report['log_ids_match'],failure
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cycles',type=int,default=100)
    run(parser.parse_args().cycles)
