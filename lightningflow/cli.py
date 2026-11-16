import argparse
import json
import os
from pathlib import Path
import sys
import time

def parser():
    p = argparse.ArgumentParser(description="LightningFlow CUDA dictation vertical slice")
    p.add_argument("--models", default=str(Path(__file__).resolve().parents[1] / "models"))
    sub = p.add_subparsers(dest="command", required=True)
    for command in ("prepare", "run", "benchmark"):
        s = sub.add_parser(command)
        s.add_argument("--model", default="tiny.en")
        s.add_argument("--compute", choices=["float16", "int8_float16", "int8"], default="float16")
        if command == "run":
            s.add_argument('--language',default='en')
            s.add_argument("--device", type=int)
            s.add_argument("--max-seconds", type=int, default=120, choices=range(1,3601), metavar="1..3600")
            s.add_argument("--toggle-vk", type=lambda v: int(v,0), default=0x77)
            s.add_argument("--retry-vk", type=lambda v: int(v,0), default=0x78)
            s.add_argument("--cancel-vk", type=lambda v: int(v,0), default=0x1B)
            s.add_argument("--quit-vk", type=lambda v: int(v,0), default=ord('Q'))
            s.add_argument("--save-vk", type=lambda v: int(v,0), default=ord('S'))
            s.add_argument("--recovery", default=str(Path(__file__).resolve().parents[1] / "recovery"))
        if command == "benchmark":
            s.add_argument("--audio", required=True)
            s.add_argument("--reference")
            s.add_argument("--runs", type=int, default=5, choices=range(1,101), metavar="1..100")
            s.add_argument("--output", default="results/benchmark.json")
    sub.add_parser("doctor")
    sub.add_parser("desktop")
    mic = sub.add_parser("mic-test")
    mic.add_argument("--device", type=int)
    mic.add_argument("--seconds", type=float, default=1)
    mic.add_argument("--output", default="results/microphone.json")
    check = sub.add_parser("verify-model")
    check.add_argument("--model", default="tiny.en")
    return p

def main():
    args = parser().parse_args()
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    if args.command != 'prepare':
        os.environ['HF_HUB_OFFLINE'] = '1'
    try:
        if args.command == "prepare":
            from .asr import prepare
            prepare(args.model, args.models)
        elif args.command == 'desktop':
            from .desktop.app import main as desktop_main
            return desktop_main()
        elif args.command == "run":
            from .app import Dictation
            return Dictation(args).run()
        elif args.command == "benchmark":
            from .benchmark import run
            return run(args)
        elif args.command == "verify-model":
            import hashlib
            root = Path(args.models) / args.model
            for name, expected in json.loads((root/"sha256.json").read_text()).items():
                with (root/name).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                        raise RuntimeError(f"Corrupt model file: {name}")
            print("Local model hashes match installation manifest.")
        elif args.command == "doctor":
            import platform
            import psutil
            import sounddevice as sd
            from .asr import gpu_snapshot, load_cuda_dlls
            load_cuda_dlls()
            import ctranslate2
            print(json.dumps({"os": platform.platform(), "cpu": platform.processor(),
                "ram_gib": psutil.virtual_memory().total/1024**3, "gpu": gpu_snapshot(),
                "ctranslate2": ctranslate2.__version__, "cuda_devices": ctranslate2.get_cuda_device_count(),
                "compute_types": sorted(ctranslate2.get_supported_compute_types("cuda"))}, indent=2))
            print(sd.query_devices())
        elif args.command == "mic-test":
            import numpy as np
            import sounddevice as sd
            from .audio import RATE, BLOCK, input_options
            options = input_options(args.device)
            start = time.perf_counter()
            first = None
            peak = 0.
            overflows = 0
            with sd.InputStream(**options, samplerate=RATE, channels=1,
                                dtype="float32", blocksize=BLOCK, latency="low") as stream:
                for _ in range(max(1, int(args.seconds*RATE/BLOCK))):
                    data, overflow = stream.read(BLOCK)
                    first = first or time.perf_counter()
                    peak = max(peak, float(np.max(np.abs(data))))
                    overflows += bool(overflow)
            result = {"first_frame_ms": (first-start)*1000, "peak": peak,
                      "overflows": overflows, "seconds": args.seconds,
                      "audio_saved": False, "device": str(sd.query_devices(options["device"], "input"))}
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
            return 0 if overflows == 0 else 1
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}\nNo CPU fallback was attempted.", file=sys.stderr, flush=True)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
