from dataclasses import dataclass
from collections import deque
import numpy as np

RATE = 16000
BLOCK = 320

def input_options(device=None):
    """Prefer shared WASAPI over MME; do not silently switch microphones."""
    import sounddevice as sd
    if device is None:
        default = sd.query_devices(kind="input")
        default_name = default["name"].rstrip()
        # MME truncates names. Match only this physical input, not an arbitrary mic.
        candidates = [(i, d) for i, d in enumerate(sd.query_devices())
                      if d["max_input_channels"] > 0
                      and sd.query_hostapis(d["hostapi"])["name"] == "Windows WASAPI"
                      and (d["name"].startswith(default_name) or default_name.startswith(d["name"]))]
        if len(candidates) == 1:
            device = candidates[0][0]
    info = sd.query_devices(device, "input")
    api = sd.query_hostapis(info["hostapi"])["name"]
    settings = sd.WasapiSettings(auto_convert=True) if api == "Windows WASAPI" else None
    return {"device": device, "extra_settings": settings}

@dataclass
class Chunk:
    audio: np.ndarray
    overlapped: bool = False

class PreviewBuffer:
    """Bounded provisional windows; authoritative Segmenter stays unchanged."""
    def __init__(self,first_seconds=.8,interval_seconds=1.2,max_seconds=4.):
        self.first=int(first_seconds*RATE)
        self.interval=int(interval_seconds*RATE)
        self.limit=int(max_seconds*RATE)
        self.reset()

    def reset(self):
        self.frames=deque()
        self.samples=self.elapsed=0
        self.next=self.first
        self.voiced=False

    def feed(self,frame):
        frame=np.asarray(frame,dtype=np.float32).reshape(-1)
        self.frames.append(frame.copy());self.samples+=len(frame);self.elapsed+=len(frame)
        self.voiced|=float(np.sqrt(np.mean(frame*frame)))>=.008
        while self.frames and self.samples-len(self.frames[0])>=self.limit:
            self.samples-=len(self.frames.popleft())
        if self.elapsed>=self.next:
            self.next=self.elapsed+self.interval
            if self.voiced:return np.concatenate(self.frames)[-self.limit:]
        return None

class Segmenter:
    """Bounded energy endpointing; neural VAD also runs before ASR.

    Keep silence for Silero to trim. Only forced splits overlap; silence
    endpoints do not deduplicate legitimately repeated phrases.
    """
    def __init__(self, max_seconds=8.0, silence_seconds=0.5, threshold=0.008):
        self.limit = int(max_seconds * RATE)
        self.silence_limit = int(silence_seconds * RATE)
        self.threshold = threshold
        self.frames = []
        self.samples = self.silence = 0
        self.speech = False
        self.overlapped = False

    def feed(self, frame):
        frame = np.asarray(frame, dtype=np.float32).reshape(-1).copy()
        self.frames.append(frame)
        self.samples += len(frame)
        voiced = float(np.sqrt(np.mean(frame * frame))) >= self.threshold
        self.speech |= voiced
        self.silence = 0 if voiced else self.silence + len(frame)
        if self.samples >= self.limit or (self.speech and self.silence >= self.silence_limit):
            return self.flush(forced=self.samples >= self.limit and voiced)
        return None

    def flush(self, forced=False):
        if not self.frames:
            return None
        data = np.concatenate(self.frames)
        result = Chunk(data, self.overlapped) if self.speech else None
        tail = data[-int(RATE * .25):].copy() if forced else None
        self.frames = [tail] if tail is not None else []
        self.samples = len(tail) if tail is not None else 0
        self.silence = 0
        # A carried tail alone must not cause duplicate decoding on immediate stop.
        self.speech = False
        self.overlapped = forced
        return result

def merge(left, right, overlapped=False):
    import re
    if not left:
        return right.strip()
    a, b = left.split(), right.split()
    normalize = lambda w: re.sub(r"[^\w]", "", w).casefold()
    if overlapped:
        for count in range(min(12, len(a), len(b)), 0, -1):
            if list(map(normalize, a[-count:])) == list(map(normalize, b[:count])):
                b = b[count:]
                break
    return (left.rstrip() + " " + " ".join(b)).strip()
