import io
import struct
import os
import subprocess
import sys
import time
import pytest
from lightningflow.asr_process import read_exact,read_message,write_message,write_all,CudaASRProcess,GPUWorkerError,MAX_MESSAGE,own_interpreter


def test_exact_float_transport_handles_short_pipe_reads_and_writes():
    class Short(io.BytesIO):
        def read(self,count=-1):return super().read(min(count,3))
        def write(self,data):return super().write(data[:3])
    stream=Short();write_message(stream,{'event':'transcript','text':'CUDA 5070 — exact text'})
    data=bytes(range(256))*128;write_all(stream,data);stream.seek(0)
    assert read_message(stream)['text']=='CUDA 5070 — exact text'
    assert read_exact(stream,len(data))==data


@pytest.mark.parametrize('size',[0,MAX_MESSAGE+1,2**32-1])
def test_worker_messages_reject_invalid_allocation_bounds(size):
    with pytest.raises(ValueError):read_message(io.BytesIO(struct.pack('<I',size)))


def test_truncated_child_response_is_a_detectable_eof():
    with pytest.raises(EOFError):read_message(io.BytesIO(struct.pack('<I',20)+b'{}'))


def test_startup_failure_is_reported_without_cpu_fallback(tmp_path):
    with pytest.raises(GPUWorkerError,match='No CPU fallback'):
        CudaASRProcess(tmp_path,startup_timeout=15)


@pytest.mark.skipif(os.name!='nt',reason='Windows process-tree ownership')
def test_job_owns_actual_interpreter_before_gpu_initialization():
    import psutil
    program="import os,sys,time; print(os.getpid(),flush=True); sys.stdin.readline(); time.sleep(60)"
    process=subprocess.Popen([sys.executable,'-u','-c',program],stdin=subprocess.PIPE,stdout=subprocess.PIPE,creationflags=0x08000000)
    child=None;job=None
    try:
        child=psutil.Process(int(process.stdout.readline()))
        job=own_interpreter(process,child.pid)
        process.stdin.write(b'initialize\n');process.stdin.flush()
        kernel,handle=job;kernel.CloseHandle(handle);job=None
        process.wait(timeout=5);deadline=time.perf_counter()+5
        while child.is_running() and time.perf_counter()<deadline:time.sleep(.01)
        assert not child.is_running(),'CUDA interpreter descendant escaped its owning job'
    finally:
        if job:job[0].CloseHandle(job[1])
        if process.poll() is None:process.terminate();process.wait(timeout=5)
        if child and child.is_running():child.kill()
        process.stdout.close();process.stdin.close()
