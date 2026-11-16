import numpy as np
import pytest
from lightningflow.audio import Segmenter, merge, RATE
from lightningflow.benchmark import error_rate

def test_silence_does_not_emit_hallucinations_or_grow_forever():
    s = Segmenter(max_seconds=.1)
    for _ in range(100):
        assert s.feed(np.zeros(320, dtype=np.float32)) is None
        assert s.samples < RATE*.1

def test_endpoint_keeps_audio_and_repeated_phrase():
    s = Segmenter(silence_seconds=.04)
    assert s.feed(np.ones(320, dtype=np.float32)*.1) is None
    assert s.feed(np.zeros(320, dtype=np.float32)) is None
    c = s.feed(np.zeros(320, dtype=np.float32))
    assert c is not None and len(c.audio) == 960 and not c.overlapped
    assert merge("yes", "yes", False) == "yes yes"

def test_forced_overlap_only_deduplicates_boundary():
    assert merge("Meet on Friday", "Friday at three.", True) == "Meet on Friday at three."
    s = Segmenter(max_seconds=.1)
    chunk = None
    for _ in range(5):
        chunk = s.feed(np.ones(320, dtype=np.float32)*.1)
    assert chunk is not None
    assert s.flush() is None  # Tail alone cannot become a duplicate final chunk.

def test_error_metrics_known_edits():
    assert error_rate("One two three", "one four three") == pytest.approx(1/3)
    assert error_rate("CUDA 5070.", "CUDA 5070") == 0
    assert error_rate("cat", "cut", True) == pytest.approx(1/3)

def test_x64_input_layout():
    import ctypes
    from lightningflow.win32 import INPUT
    assert ctypes.sizeof(INPUT) == 40
