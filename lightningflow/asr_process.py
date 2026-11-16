"""Resident CUDA in an owned child process; no native GPU code in capture.

Length-delimited local pipes carry bounded float32 audio without quantization.
The low-level decoder and its parameters are unchanged. Native crashes and
timeouts are terminal for this instance, never blind retries or CPU fallback.
"""
import atexit
from collections import deque
import json
import os
from pathlib import Path
import queue
import struct
import subprocess
import sys
import threading

MAX_AUDIO_SAMPLES=30*16000
MAX_MESSAGE=2*1024*1024


class GPUWorkerError(RuntimeError):pass


def read_exact(stream,count):
    parts=[];remaining=count
    while remaining:
        part=stream.read(remaining)
        if not part:raise EOFError('CUDA worker pipe closed')
        parts.append(part);remaining-=len(part)
    return b''.join(parts)


def read_message(stream):
    size=struct.unpack('<I',read_exact(stream,4))[0]
    if not 0<size<=MAX_MESSAGE:raise ValueError('Invalid CUDA worker message length')
    message=json.loads(read_exact(stream,size))
    if not isinstance(message,dict):raise ValueError('Invalid CUDA worker message')
    return message


def write_message(stream,message):
    data=json.dumps(message,ensure_ascii=True).encode('utf-8')
    if not 0<len(data)<=MAX_MESSAGE:raise ValueError('CUDA worker message exceeds its limit')
    write_all(stream,struct.pack('<I',len(data)));write_all(stream,data);stream.flush()


def write_all(stream,data):
    remaining=memoryview(data)
    while remaining:
        count=stream.write(remaining)
        if not count:raise OSError('CUDA worker pipe closed while writing')
        remaining=remaining[count:]


def own_process_tree(process_handle):
    """Bind the actual interpreter to a kill-on-close Windows job."""
    if os.name!='nt':return None
    import ctypes as C
    from ctypes import wintypes as W
    class BASIC(C.Structure):
        _fields_=[('process_time',C.c_int64),('job_time',C.c_int64),('flags',W.DWORD),
            ('min_working',C.c_size_t),('max_working',C.c_size_t),('active',W.DWORD),
            ('affinity',C.c_size_t),('priority',W.DWORD),('scheduling',W.DWORD)]
    class IO(C.Structure):_fields_=[(name,C.c_uint64) for name in ('ro','wo','oo','rt','wt','ot')]
    class LIMIT(C.Structure):
        _fields_=[('basic',BASIC),('io',IO),('process_memory',C.c_size_t),('job_memory',C.c_size_t),
            ('peak_process',C.c_size_t),('peak_job',C.c_size_t)]
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[C.c_void_p,W.LPCWSTR];kernel.CreateJobObjectW.restype=W.HANDLE
    kernel.SetInformationJobObject.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD]
    kernel.AssignProcessToJobObject.argtypes=[W.HANDLE,W.HANDLE];kernel.CloseHandle.argtypes=[W.HANDLE]
    handle=kernel.CreateJobObjectW(None,None);limits=LIMIT();limits.basic.flags=0x2000
    if handle and kernel.SetInformationJobObject(handle,9,C.byref(limits),C.sizeof(limits)) and kernel.AssignProcessToJobObject(handle,W.HANDLE(int(process_handle))):
        return kernel,handle
    if handle:kernel.CloseHandle(handle)
    raise GPUWorkerError('Windows could not isolate the CUDA process tree')



def own_interpreter(launcher,pid):
    if os.name!='nt':return None
    import ctypes as C
    from ctypes import wintypes as W
    import psutil
    if type(pid) is not int or (pid!=launcher.pid and launcher.pid not in [p.pid for p in psutil.Process(pid).parents()]):
        raise GPUWorkerError('CUDA worker did not identify an owned interpreter')
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    kernel.CloseHandle.argtypes=[W.HANDLE]
    handle=kernel.OpenProcess(0x100|0x1|0x1000,False,pid)
    if not handle:raise GPUWorkerError('Cannot own the CUDA interpreter')
    try:return own_process_tree(handle)
    finally:kernel.CloseHandle(handle)


class CudaASRProcess:
    provider='CUDA / CTranslate2'

    def __init__(self,model_dir,compute_type='float16',timeout=20.,startup_timeout=60.):
        self.timeout=timeout;self.language='en';self._prompt_cache={};self.closed=False;self.failed=False
        self.lock=threading.Lock();self.replies=queue.Queue(maxsize=2);self.diagnostics=deque(maxlen=8)
        self.outbox=queue.Queue(maxsize=1)
        self.model_dir=str(Path(model_dir).resolve());self.compute_type=compute_type
        environment=dict(os.environ,PYTHONUNBUFFERED='1',PYTHONUTF8='1',HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
        # Source engine root works both from a wheel and the packaged runtime.
        root=str(Path(__file__).resolve().parent.parent)
        environment['PYTHONPATH']=root+os.pathsep+environment.get('PYTHONPATH','')
        self.process=subprocess.Popen([sys.executable,'-u','-m','lightningflow.asr_process',self.model_dir,compute_type],
            cwd=root,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            bufsize=0,creationflags=0x08000000 if os.name=='nt' else 0)
        self.job=None
        threading.Thread(target=self._read,daemon=True,name='cuda-replies').start()
        threading.Thread(target=self._errors,daemon=True,name='cuda-diagnostics').start()
        try:
            spawned=self._receive(startup_timeout)
            if spawned.get('event')!='spawned':raise GPUWorkerError('CUDA interpreter handshake failed')
            self.job=own_interpreter(self.process,spawned.get('pid'))
            write_message(self.process.stdin,{'op':'initialize'})
            result=self._receive(startup_timeout)
            if result.get('event')!='ready' or result.get('provider')!=self.provider:raise GPUWorkerError('CUDA worker did not confirm GPU startup')
            self.load_ms=result['load_ms'];self.runtime_version=result['runtime_version']
        except BaseException:self.close();raise
        threading.Thread(target=self._write,daemon=True,name='cuda-requests').start()
        atexit.register(self.close)

    def _read(self):
        try:
            while True:self.replies.put(read_message(self.process.stdout))
        except (EOFError,OSError,ValueError) as exc:
            if not self.closed:self.failed=True
            try:self.replies.put_nowait({'event':'transport_error','error':str(exc)})
            except queue.Full:pass

    def _errors(self):
        try:
            for line in iter(lambda:self.process.stderr.readline(4096),b''):
                self.diagnostics.append(line.decode('utf-8',errors='replace').strip()[:500])
        except (OSError,ValueError):pass

    def _write(self):
        while not self.closed:
            try:message,audio=self.outbox.get(timeout=.1)
            except queue.Empty:continue
            try:
                write_message(self.process.stdin,message)
                write_all(self.process.stdin,audio);self.process.stdin.flush()
            except (OSError,ValueError) as exc:
                if not self.closed:
                    self.failed=True
                    try:self.replies.put_nowait({'event':'transport_error','error':str(exc)})
                    except queue.Full:pass
                return

    def _receive(self,timeout):
        try:result=self.replies.get(timeout=timeout)
        except queue.Empty:
            self.close();raise GPUWorkerError('CUDA inference timed out. Audio retained; restart the GPU engine. No CPU fallback attempted.')
        if result.get('event') in ('error','transport_error'):
            code=self.process.poll()
            detail=result.get('error','Unknown GPU error')
            raise GPUWorkerError(f'CUDA worker failed (exit {code}): {detail}. Audio retained; restart the GPU engine. No CPU fallback attempted.')
        return result

    def transcribe(self,audio,vad=True,initial_prompt=''):
        import numpy as np
        samples=np.asarray(audio,dtype='<f4')
        if samples.ndim!=1 or not 0<len(samples)<=MAX_AUDIO_SAMPLES or not np.isfinite(samples).all():
            raise ValueError('CUDA audio must be finite mono float32, at most 30 seconds')
        with self.lock:
            if self.closed or self.process.poll() is not None:raise GPUWorkerError('CUDA worker is stopped. Audio retained; restart the GPU engine.')
            try:self.outbox.put_nowait(({'op':'transcribe','samples':len(samples),'vad':bool(vad),
                'prompt':initial_prompt,'language':self.language},samples.tobytes()))
            except queue.Full as exc:raise GPUWorkerError('CUDA request queue is busy; audio retained') from exc
            result=self._receive(self.timeout)
            if result.get('event')!='transcript' or not isinstance(result.get('text'),str):raise GPUWorkerError('Invalid CUDA worker reply')
            self._prompt_cache.clear();self._prompt_cache.update(result.get('cached_prompts',{}))
            return result['text']

    def close(self):
        if self.closed:return
        self.closed=True
        if self.job:
            kernel,handle=self.job;kernel.CloseHandle(handle);self.job=None
        try:self.process.stdin.close()
        except (OSError,ValueError):pass
        if self.process.poll() is None:
            self.process.terminate()
        try:self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
            try:stream.close()
            except (OSError,ValueError):pass
        atexit.unregister(self.close)


def main():
    # Reserve a protocol handle before redirecting Python AND native stdout.
    # CTranslate2/driver diagnostics cannot corrupt framed responses.
    output=os.fdopen(os.dup(sys.stdout.fileno()),'wb',buffering=0)
    os.dup2(sys.stderr.fileno(),sys.stdout.fileno());sys.stdout=sys.stderr
    source=sys.stdin.buffer
    try:
        write_message(output,{'event':'spawned','pid':os.getpid()})
        if read_message(source).get('op')!='initialize':raise ValueError('CUDA startup handshake failed')
        from .asr import CudaASR
        import numpy as np
        engine=CudaASR(sys.argv[1],sys.argv[2])
        write_message(output,{'event':'ready','provider':engine.provider,'load_ms':engine.load_ms,'runtime_version':engine.runtime_version})
        while True:
            request=read_message(source)
            if request.get('op')!='transcribe':raise ValueError('Invalid CUDA worker operation')
            count=request.get('samples')
            if type(count) is not int or not 0<count<=MAX_AUDIO_SAMPLES:raise ValueError('Invalid CUDA audio length')
            audio=np.frombuffer(read_exact(source,count*4),dtype='<f4')
            engine.language=request.get('language','en')
            text=engine.transcribe(audio,vad=request.get('vad',True),initial_prompt=request.get('prompt',''))
            write_message(output,{'event':'transcript','text':text,'cached_prompts':engine._prompt_cache})
    except EOFError:return 0
    except Exception as exc:
        try:write_message(output,{'event':'error','error':str(exc)[:2000]})
        except (OSError,ValueError):pass
        return 1


if __name__=='__main__':raise SystemExit(main())
