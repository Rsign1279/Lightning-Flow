"""Test-only PCM replay replacing capture, while retaining real CUDA inference."""
import time
from pathlib import Path
import numpy as np
import sounddevice as sd
from lightningflow._vendor.faster_whisper.audio import decode_audio
from lightningflow.desktop import worker

class ReplayStream:
    audio=decode_audio(str(Path(__file__).resolve().parents[1]/'benchmarks/synthetic.wav'))
    def __init__(self,**kwargs): self.offset=0
    def start(self): pass
    def read(self,frames):
        time.sleep(frames/16000*.1)
        audio=self.audio[self.offset:self.offset+frames]
        self.offset+=frames
        return np.pad(audio,(0,max(0,frames-len(audio))))[:,None],False
    def close(self): pass

if __name__=='__main__':
    sd.InputStream=ReplayStream
    raise SystemExit(worker.main())
