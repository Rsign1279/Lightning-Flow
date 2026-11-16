"""Own-process JSON bridge. No sockets, browser runtime or cloud transport."""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import queue
import subprocess
import sys
import os
import threading
import time

class EngineProcess:
    def __init__(self,python,engine,settings,models,events,task='engine',model='tiny.en',worker_module='lightningflow.desktop.worker'):
        self.events=events
        self.write_lock=threading.Lock()
        self.job=None
        self.closed=False
        self.task=task; self.model=model
        python,engine=Path(python),Path(engine)
        if not python.is_file(): raise RuntimeError('GPU runtime is not installed. Open Privacy & settings and choose Repair GPU runtime.')
        environment=dict(os.environ)
        for key in list(environment):
            if key.startswith('_PYI_') or key in ('PYTHONHOME','TCL_LIBRARY','TK_LIBRARY'):
                environment.pop(key,None)
        environment.update(PYTHONPATH=str(engine),PYTHONUTF8='1',PYTHONUNBUFFERED='1',HF_HUB_DISABLE_TELEMETRY='1')
        command=[str(python),'-u','-m',worker_module,'--settings',str(settings),
                 '--models',str(models),'--task',task,'--model',model]
        kernel=C.WinDLL('kernel32',use_last_error=True)
        kernel.SetDllDirectoryW.argtypes=[W.LPCWSTR]
        if getattr(sys,'frozen',False): kernel.SetDllDirectoryW(None)
        try:
            self.process=subprocess.Popen(command,cwd=str(engine),env=environment,stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',
                creationflags=0x08000000)
        finally:
            if getattr(sys,'frozen',False): kernel.SetDllDirectoryW(sys._MEIPASS)
        self._job(kernel)
        threading.Thread(target=self._read,daemon=True).start()
        threading.Thread(target=self._errors,daemon=True).start()

    def _job(self,kernel):
        # Own the entire Windows Python launcher/worker tree. If the desktop
        # exits unexpectedly, its backend cannot keep the microphone/hotkeys.
        class BASIC(C.Structure):
            _fields_=[('process_time',C.c_int64),('job_time',C.c_int64),('flags',W.DWORD),
                      ('min_working',C.c_size_t),('max_working',C.c_size_t),('active',W.DWORD),
                      ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
        class IO(C.Structure): _fields_=[(name,C.c_uint64) for name in ('ro','wo','oo','rt','wt','ot')]
        class LIMIT(C.Structure):
            _fields_=[('basic',BASIC),('io',IO),('process_memory',C.c_size_t),('job_memory',C.c_size_t),
                      ('peak_process',C.c_size_t),('peak_job',C.c_size_t)]
        kernel.CreateJobObjectW.argtypes=[C.c_void_p,W.LPCWSTR]; kernel.CreateJobObjectW.restype=W.HANDLE
        kernel.SetInformationJobObject.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD]
        kernel.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE]
        kernel.CloseHandle.argtypes=[W.HANDLE]
        handle=kernel.CreateJobObjectW(None,None)
        limits=LIMIT(); limits.basic.flags=0x2000
        if handle and kernel.SetInformationJobObject(handle,9,C.byref(limits),C.sizeof(limits)) and kernel.AssignProcessToJobObject(handle,W.HANDLE(int(self.process._handle))):
            self.job=(kernel,handle)
        elif handle: kernel.CloseHandle(handle)

    def _read(self):
        for line in self.process.stdout:
            try:
                event=json.loads(line)
                event['process_pid']=self.process.pid
                if self.task!='engine': event.update(task_origin=self.task,task_model=self.model)
                self.events.put(event)
            except ValueError: self.events.put({'event':'notice','message':'An invalid engine response was ignored.'})
        self.process.wait()
        self._release_job()
        self.events.put({'event':'process_exit','pid':self.process.pid,'code':self.process.returncode,
                         'task_origin':self.task,'task_model':self.model})

    def _release_job(self):
        with self.write_lock:
            if self.job:
                kernel,handle=self.job
                kernel.CloseHandle(handle)
                self.job=None

    def _errors(self):
        # Keep recent diagnostics in memory only. No transcript logs are written.
        for line in self.process.stderr:
            if line.strip(): self.events.put({'event':'diagnostic','message':line.strip()[:500]})

    def send(self,action,**data):
        if self.process.poll() is not None: return False
        try:
            with self.write_lock:
                self.process.stdin.write(json.dumps({'action':action,**data})+'\n')
                self.process.stdin.flush()
            return True
        except (OSError,ValueError): return False

    def stop(self):
        if self.closed: return
        self.closed=True
        self.send('shutdown')
        def finish():
            try: self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if not self.job:
                    import psutil
                    try:
                        parent=psutil.Process(self.process.pid)
                        for child in parent.children(recursive=True): child.terminate()
                        parent.terminate()
                    except psutil.Error: pass
            finally:
                self._release_job()
        threading.Thread(target=finish,daemon=True).start()
