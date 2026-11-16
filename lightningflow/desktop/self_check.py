"""Explicit packaged-app diagnostics using isolated settings and no recording."""
import json
import os
from pathlib import Path
import tempfile
import time


def run():
    from . import paths
    from .state import Preferences,Settings
    from .app import DesktopApp,PAGES
    from .. import __version__
    report=Path(os.environ.get('LIGHTNINGFLOW_SELF_CHECK_REPORT',str(paths.home()/'.work/frozen-self-check.json')))
    old=os.environ.get('LIGHTNINGFLOW_DATA_DIR')
    result={'version':__version__,'passed':False,'scope':'Packaged GUI, isolated settings, real CUDA startup/warm-up, no microphone or text insertion.'}
    started=time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix='lightningflow-self-check-') as directory:
            os.environ['LIGHTNINGFLOW_DATA_DIR']=directory
            _,_,models=paths.runtime()
            Preferences(Path(directory)/'settings.json').save(Settings(models_dir=str(models),onboarding_done=True,
                close_to_tray=False,shortcuts={'toggle':0x83,'cancel':0x84,'retry':0x85,'quit':0x86,'save':0x87}))
            app=DesktopApp(hidden=True)
            errors=[]
            app.report_callback_exception=lambda *error:errors.append(str(error[1]))
            def poll():
                if app.engine_state=='error' or errors or time.perf_counter()-started>45:
                    result['error']=errors or app.status_message
                    app.engine_state='error';app.quit_app();return
                if app.engine_state=='ready':
                    pages=[]
                    try:
                        for theme in ('Dark','Light'):
                            app.change_theme(theme)
                            for page,_ in PAGES:
                                app.navigate(page);app.update_idletasks();pages.append(theme+'/'+page)
                        result.update(passed=not errors,pages=pages,callback_errors=errors,
                            provider='CUDA / CTranslate2',model=app.settings.model,
                            elapsed_seconds=time.perf_counter()-started)
                    except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
                    app.quit_app();return
                app.after(50,poll)
            app.after(100,poll);app.mainloop()
    except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
    finally:
        if old is None:os.environ.pop('LIGHTNINGFLOW_DATA_DIR',None)
        else:os.environ['LIGHTNINGFLOW_DATA_DIR']=old
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return 0 if result['passed'] else 1
