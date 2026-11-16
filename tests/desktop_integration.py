from lightningflow import __version__
"""Actual GUI -> JSON IPC -> resident CUDA -> GUI/history, without live mic speech."""
import ctypes as C
import json
import os
from pathlib import Path
import time

root=Path(__file__).resolve().parents[1]
test_data=root/'.work/desktop-integration-data'
os.environ['LIGHTNINGFLOW_DATA_DIR']=str(test_data)
from lightningflow.desktop.state import Preferences,Settings
from lightningflow.desktop.app import DesktopApp,PAGES
from lightningflow.desktop.bridge import EngineProcess
from lightningflow.desktop.windows import user,hwnd

def run():
    Preferences(test_data/'settings.json').save(Settings(onboarding_done=True,models_dir=str(root/'models'),
        shortcuts={'toggle':0x81,'retry':0x82,'cancel':0x83,'quit':0x84,'save':0x85},
        dictionary=[{'spoken':'cuda','written':'CUDA'}]))
    app=DesktopApp(auto_engine=False,hidden=True)
    callback_errors=[]
    app.report_callback_exception=lambda *error:callback_errors.append(str(error[1]))
    built=[]
    for theme in ('Dark','Light'):
        app.change_theme(theme)
        for ident,_ in PAGES:
            app.navigate(ident); app.update_idletasks(); built.append(theme+'/'+ident)
    app.change_theme('Dark'); app.navigate('dictation')
    user.GetForegroundWindow.restype=C.c_void_p
    foreground_before=user.GetForegroundWindow()
    app.engine=EngineProcess(root/'.venv/Scripts/python.exe',root,app.preferences.path,root/'models',app.events,
                             worker_module='tests.desktop_replay_worker')
    deadline=time.perf_counter()+45
    phase='wait'
    outcome={}
    overlay_checked=False
    ticks=[]
    def heartbeat():
        if not app.closing:
            ticks.append(time.perf_counter())
            app.after(16,heartbeat)
    def drive():
        nonlocal phase,overlay_checked
        try:
            if callback_errors: raise AssertionError(callback_errors)
            if time.perf_counter()>deadline: raise RuntimeError('Desktop GPU replay timed out: '+app.status_message)
            if app.engine_state=='error': raise RuntimeError(app.status_message)
            if phase=='wait' and app.engine_state=='ready':
                app.practice(); phase='record'
            elif phase=='record' and app.engine_state=='recording' and not overlay_checked:
                handle=hwnd(app.overlay)
                assert user.GetWindowLongPtrW(handle,-20)&0x08000000
                assert user.GetForegroundWindow()!=handle
                overlay_checked=True
            elif phase=='record' and app.seconds>=9.0:
                app.practice(); phase='finish'
            elif phase=='finish' and app.last_result and app.engine_state=='ready':
                result=app.last_result
                assert result['delivered'] and result['destination']=='scratchpad'
                assert 'project report' in result['text'] and 'CUDA' in result['text']
                assert app.history.rows and app.history.rows[0]['text']==result['text']
                assert not (test_data/'history.sqlite3').exists()
                assert app.refs['transcript'].get('1.0','end').strip()==result['text']
                outcome.update({'actual_gui_ipc_cuda_scratchpad':True,'session_history_verified':True,
                    'persistent_history_default_off':True,'all_screens_both_themes_constructed':built,
                    'callback_errors':callback_errors,'metrics':result['metrics'],
                    'transcript':result['text'],'source':'Accelerated PCM replay in test-only worker; real CUDA ASR',
                    'gui_heartbeat_max_gap_ms':max((b-a)*1000 for a,b in zip(ticks,ticks[1:])) if len(ticks)>1 else None,
                    'overlay_style_noactivate':overlay_checked})
                assert overlay_checked
                app.quit_app(); return
            app.after(25,drive)
        except Exception as exc:
            outcome['error']=str(exc)
            app.engine_state='error'
            app.quit_app()
    app.after(16,heartbeat); app.after(50,drive)
    app.mainloop()
    assert 'error' not in outcome,outcome
    assert outcome.get('actual_gui_ipc_cuda_scratchpad'),outcome
    return outcome

if __name__=='__main__':
    result=run()
    (root/f'results/desktop-integration-{__version__}.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
