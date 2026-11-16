import json
from pathlib import Path
import statistics
import threading
import time
import re
import hashlib
from datetime import datetime, timezone
import psutil
from .asr import CudaASR, gpu_snapshot

def error_rate(reference, hypothesis, chars=False):
    clean = lambda s: " ".join(re.findall(r"\w+", s.casefold()))
    a, b = clean(reference), clean(hypothesis)
    a, b = (list(a.replace(" ", "")), list(b.replace(" ", ""))) if chars else (a.split(), b.split())
    previous = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        row = [i]
        for j, y in enumerate(b, 1):
            row.append(min(previous[j] + 1, row[-1] + 1, previous[j-1] + (x != y)))
        previous = row
    return previous[-1] / max(1, len(a))

def run(args):
    from ._vendor.faster_whisper.audio import decode_audio
    audio = decode_audio(args.audio, sampling_rate=16000)
    reference = Path(args.reference).read_text(encoding="utf-8").strip() if args.reference else None
    process = psutil.Process()
    before = gpu_snapshot()
    engine = CudaASR(Path(args.models) / args.model, args.compute)
    # Warm-up included in load time, not in resident inference samples.
    rss = []
    gpu = []
    stop = threading.Event()
    def sample():
        while not stop.is_set():
            rss.append(process.memory_info().rss)
            gpu.append(gpu_snapshot())
            stop.wait(.2)
    watcher = threading.Thread(target=sample, daemon=True)
    watcher.start()
    times, outputs, cpu = [], [], []
    try:
        for _ in range(args.runs):
            c0 = process.cpu_times()
            start = time.perf_counter()
            output = engine.transcribe(audio)
            elapsed = time.perf_counter()-start
            c1 = process.cpu_times()
            times.append(elapsed*1000)
            outputs.append(output)
            cpu.append(((c1.user-c0.user)+(c1.system-c0.system))/elapsed*100)
    finally:
        stop.set()
        watcher.join(timeout=6)
    result = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "audio_sha256": hashlib.sha256(Path(args.audio).read_bytes()).hexdigest(),
        "model": args.model, "compute_type": args.compute, "provider": engine.provider,
        "runtime_version": engine.runtime_version, "model_load_and_warm_ms": engine.load_ms,
        "audio_seconds": len(audio)/16000, "runs": args.runs,
        "finalization_ms": times, "median_finalization_ms": statistics.median(times),
        "real_time_factor": [t/1000/(len(audio)/16000) for t in times],
        "process_cpu_percent_one_core_100": cpu,
        "process_peak_sampled_rss_mib": max(rss, default=process.memory_info().rss)/1024**2,
        "gpu_before_load": before, "gpu_samples": gpu,
        "gpu_scope": "Device-wide sampled values; includes other apps; not process VRAM attribution",
        "transcripts": outputs,
        "wer": [error_rate(reference, text) for text in outputs] if reference else None,
        "cer": [error_rate(reference, text, True) for text in outputs] if reference else None,
        "first_partial_ms": None,
        "limitations": ["File decode benchmark, not microphone-to-input latency", "No token streaming timing", "Synthetic speech is not representative human accuracy", "No AI cleanup in this slice"]}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "gpu_samples"}, indent=2))
    return 0
