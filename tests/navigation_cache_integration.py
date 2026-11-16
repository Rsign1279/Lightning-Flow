"""Hidden real-widget navigation test. No microphone, hooks or external app input."""
import json
import os
from pathlib import Path
import statistics
import tempfile
import time


def run():
    from lightningflow.desktop.app import DesktopApp
    previous=os.environ.get('LIGHTNINGFLOW_DATA_DIR')
    with tempfile.TemporaryDirectory() as directory:
        os.environ['LIGHTNINGFLOW_DATA_DIR']=directory
        app=DesktopApp(auto_engine=False,hidden=True);errors=[]
        app.report_callback_exception=lambda *args:errors.append(str(args))
        try:
            app.navigate('dictation');home=app.refs['transcript']
            app.navigate('history');log_refresh=app.refs['log_refresh']
            samples=[]
            for _ in range(100):
                for page in ('dictation','history'):
                    start=time.perf_counter();app.navigate(page);app.update_idletasks()
                    samples.append((time.perf_counter()-start)*1000)
                    if page=='dictation':assert app.refs['transcript'] is home
                    else:assert app.refs['log_refresh'] is log_refresh
            assert len(app._page_cache)==2 and not errors
            return {'switches':len(samples),'median_ms':statistics.median(samples),
                'p95_ms':sorted(samples)[int(.95*(len(samples)-1))],'max_ms':max(samples),
                'widgets_reused':True,'cached_pages':2,'callback_errors':errors,
                'scope':'Hidden Home/Log navigation and idle layout, not visible compositor FPS or all settings screens.'}
        finally:
            app.quit_app()
            if previous is None:os.environ.pop('LIGHTNINGFLOW_DATA_DIR',None)
            else:os.environ['LIGHTNINGFLOW_DATA_DIR']=previous


if __name__=='__main__':
    result=run();root=Path(__file__).resolve().parents[1]
    (root/'results').mkdir(exist_ok=True)
    (root/'results/navigation-cache-0.5.0.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
