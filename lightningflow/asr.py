import json
import os
from pathlib import Path
import subprocess
import sys
import time

_DLL_HANDLES = []

def load_cuda_dlls():
    if os.name != "nt":
        raise RuntimeError("This slice requires Windows and CUDA; no CPU fallback is configured.")
    import site
    for root in site.getsitepackages():
        for folder in Path(root).glob("nvidia/*/bin"):
            _DLL_HANDLES.append(os.add_dll_directory(str(folder)))
            os.environ["PATH"] = str(folder) + os.pathsep + os.environ.get("PATH", "")

def gpu_snapshot():
    try:
        output = subprocess.check_output([
            "nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits"], text=True,
            creationflags=0x08000000, timeout=5)
        return [dict(zip(["name", "driver", "total_mib", "used_mib", "util_percent"],
                         [x.strip() for x in line.split(",")])) for line in output.strip().splitlines()]
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": str(exc)}

def prepare(model, root):
    """Explicit one-time network operation; inference itself is local-only."""
    from ._vendor.faster_whisper.utils import download_model
    from .model_integrity import publisher_manifest,verify_download
    import hashlib
    import tempfile
    manifest=publisher_manifest(model)
    base=Path(root).resolve();base.mkdir(parents=True,exist_ok=True)
    path=base/model
    if path.parent!=base:raise ValueError('Unsafe model directory')
    with tempfile.TemporaryDirectory(prefix='model-download-',dir=base) as temporary:
        staging=Path(temporary).resolve();backup=staging/'previous';download=staging/'download'
        if not staging.is_relative_to(base) or staging==base:raise ValueError('Unsafe staging directory')
        download_model(model,output_dir=str(download),revision=manifest['revision'],use_auth_token=False)
        verify_download(download,manifest)
        files={}
        for item in download.iterdir():
            if item.is_file():
                with item.open('rb') as stream:files[item.name]=hashlib.file_digest(stream,'sha256').hexdigest()
        (download/'publisher.json').write_text(json.dumps(manifest,indent=2))
        (download/'sha256.json').write_text(json.dumps(files,indent=2))
        if path.exists():path.rename(backup)
        try:download.rename(path)
        except Exception:
            if backup.exists():backup.rename(path)
            raise
    print(f"Model prepared: {path.resolve()}", flush=True)

class CudaASR:
    provider = "CUDA / CTranslate2"

    def __init__(self, model_dir, compute_type="float16"):
        load_cuda_dlls()
        import ctranslate2
        import numpy as np
        from ._vendor.faster_whisper import WhisperModel
        path = Path(model_dir).resolve()
        if not (path / "model.bin").is_file():
            raise RuntimeError(f"Model missing: {path}. Run the prepare command first.")
        if not ctranslate2.get_cuda_device_count():
            raise RuntimeError("CTranslate2 found no CUDA GPU. No CPU fallback was attempted.")
        supported = ctranslate2.get_supported_compute_types("cuda")
        if compute_type not in supported:
            raise RuntimeError(f"CUDA compute type {compute_type} unsupported; available: {supported}")
        start = time.perf_counter()
        self.model = WhisperModel(str(path), device="cuda", device_index=0,
                                 compute_type=compute_type, cpu_threads=4, num_workers=1,
                                 local_files_only=True)
        self._prompt_cache = {}
        # Actually execute encoder/decoder; loading alone does not prove CUDA compatibility.
        self.transcribe(np.zeros(RATE, dtype=np.float32), vad=False)
        self.transcribe(np.zeros(RATE, dtype=np.float32), vad=True)
        self.load_ms = (time.perf_counter() - start) * 1000
        self.compute_type = compute_type
        self.model_dir = str(path)
        self.runtime_version = ctranslate2.__version__
        if self.model.model.device != "cuda":
            raise RuntimeError("Unexpected execution provider; refusing CPU fallback.")

    def transcribe(self, audio, vad=True, initial_prompt=''):
        prompt=None
        if initial_prompt:
            if initial_prompt not in self._prompt_cache:
                # Keep head priority terms; faster-whisper otherwise truncates
                # old prompt tokens from the opposite end. Never use a prefix.
                tokens=self.model.hf_tokenizer.encode(' '+initial_prompt.strip(),add_special_tokens=False).ids[:192]
                if len(self._prompt_cache)>=4:self._prompt_cache.clear()
                self._prompt_cache[initial_prompt]=tokens
            prompt=self._prompt_cache[initial_prompt]
        segments, _ = self.model.transcribe(
            audio, language=None if getattr(self,'language','en')=='auto' else getattr(self,'language','en'), beam_size=1, best_of=1, temperature=0,
            condition_on_previous_text=False, vad_filter=vad,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 120},
            # Skip unused timestamp tokens on the personalized path. Keep the
            # released no-hint decoder unchanged to avoid unrelated accuracy
            # changes when personalization is disabled.
            word_timestamps=False,without_timestamps=bool(prompt),initial_prompt=prompt)
        return " ".join(s.text.strip() for s in segments).strip()

RATE = 16000
