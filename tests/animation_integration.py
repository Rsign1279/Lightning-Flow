"""Real Tk frame pacing and no-activation check; no microphone is opened."""
import ctypes as C
import json
import math
import os
from pathlib import Path
import statistics
import time

root=Path(__file__).resolve().parents[1]
os.environ['LIGHTNINGFLOW_DATA_DIR']=str(root/'.work/animation-test')
from lightningflow.desktop.app import DesktopApp
from lightningflow.desktop.windows import user,hwnd


def run():
    app=DesktopApp(auto_engine=False,hidden=True)
    errors=[]
    app.report_callback_exception=lambda *error:errors.append(str(error[1]))
    frames=[]; states=[]
    original=app.overlay.wave._frame
    def frame():
        frames.append(time.perf_counter())
        original()
    app.overlay.wave._frame=frame
    before=user.GetForegroundWindow()
    started=time.perf_counter()
    app.overlay.show_state('recording','Ctrl + Alt + F8')
    first_opacity=float(app.overlay.attributes('-alpha'))
    assert first_opacity>=.85
    hidden_at=[]; hide_started=[]
    original_hidden=app.overlay._hidden
    def hidden():
        hidden_at.append(time.perf_counter()); original_hidden()
    app.overlay._hidden=hidden
    assert user.GetWindowLongPtrW(hwnd(app.overlay),-20)&0x08000000
    assert user.GetForegroundWindow()==before,'Overlay stole focus'
    def feed():
        elapsed=time.perf_counter()-started
        if elapsed<1.3:
            app.overlay.wave.set((1+math.sin(elapsed*12))*.35,True)
        elif elapsed<2.5:
            if not states:
                states.append('processing')
                app.overlay.show_state('processing','Ctrl + Alt + F8')
        elif elapsed<2.8:
            if len(states)==1:
                states.append('hidden'); hide_started.append(time.perf_counter()); app.overlay.hide()
        else:
            assert not app.overlay.visible and not app.overlay.period
            app.quit_app(); return
        app.after(25,feed)
    app.after(25,feed)
    app.mainloop()
    assert not errors,errors
    assert len(frames)>90 if app.overlay.motion else not frames
    gaps=sorted((b-a)*1000 for a,b in zip(frames,frames[1:]))
    return {'frames':len(frames),'median_frame_ms':statistics.median(gaps) if gaps else None,
            'p95_frame_ms':gaps[int(len(gaps)*.95)] if gaps else None,
            'max_frame_ms':max(gaps) if gaps else None,'callback_errors':errors,
            'first_paint_opacity':first_opacity,
            'hide_transition_ms':(hidden_at[0]-hide_started[0])*1000 if hidden_at and hide_started else None,
            'overlay_did_not_activate':True,'timer_resolution_released_after_hide':True,
            'motion_enabled':app.overlay.motion,'source':'Synthetic levels to the real recording widget; no microphone recording'}


if __name__=='__main__':
    result=run()
    (root/'results/animation-0.5.0.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
