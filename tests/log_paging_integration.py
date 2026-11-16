"""Regression for large-log stalls: bounded cards, reuse, and complete search."""
import json
import os
from pathlib import Path
import time
root=Path(__file__).resolve().parents[1]
os.environ['LIGHTNINGFLOW_DATA_DIR']=str(root/'.work/log-paging-test')
from lightningflow.desktop.app import DesktopApp
from lightningflow.desktop.state import Preferences,Settings


def run():
    Preferences(Path(os.environ['LIGHTNINGFLOW_DATA_DIR'])/'settings.json').save(Settings(onboarding_done=True))
    app=DesktopApp(auto_engine=False,hidden=True)
    for index in range(100):
        app.history.add({'id':str(index),'text':f'Synthetic transcript {index:03d}','delivered':True})
    outcome={};errors=[]
    app.report_callback_exception=lambda _t,e,_tb:errors.append(str(e))
    def verify():
        try:
            start=time.perf_counter();app.navigate('history')
            initial_ms=(time.perf_counter()-start)*1000
            pool=app.refs['log_widgets'];identities=[id(row['wrapper']) for row in pool]
            assert len(pool)==10
            visited=[];times=[]
            for page in range(10):
                visited.extend(row['id'] for row in app.refs['log_state']['items'])
                start=time.perf_counter();app.refs['log_next']();times.append((time.perf_counter()-start)*1000)
                assert [id(row['wrapper']) for row in app.refs['log_widgets']]==identities
            assert len(visited)==100 and len(set(visited))==100
            search=app.refs['log_search'];search.insert(0,'074');app.refs['log_refresh'](reset=True)
            assert [row['id'] for row in app.refs['log_state']['items']]==['74']
            search.delete(0,'end');app.refs['log_refresh'](reset=True)
            app.history.add({'id':'new','text':'New completion','delivered':True})
            app.refs['log_refresh']()
            assert app.refs['log_state']['items'][0]['id']=='new'
            assert [id(row['wrapper']) for row in app.refs['log_widgets']]==identities
            outcome.update(initial_navigation_ms=initial_ms,max_page_update_ms=max(times),
                rendered_cards=10,all_100_records_reachable=True,searches_all_records=True,
                widgets_reused_on_pagination_and_new_completion=True,callback_errors=errors)
        except Exception as exc:outcome['error']=str(exc)
        finally:app.quit_app()
    app.after(100,verify);app.mainloop()
    assert not errors and 'error' not in outcome,outcome
    return outcome


if __name__=='__main__':
    result=run()
    (root/'results/log-paging-0.4.1.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
