import json
import os
from pathlib import Path
import sys

def home():
    if getattr(sys,'frozen',False): return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]

def data_dir():
    override=os.environ.get('LIGHTNINGFLOW_DATA_DIR')
    return Path(override) if override else Path(os.environ.get('LOCALAPPDATA',str(home()))) / 'LightningFlow'

def runtime():
    root=home()
    manifest=root/'runtime.json'
    data=json.loads(manifest.read_text(encoding='utf-8-sig')) if manifest.exists() else {}
    python=Path(data.get('python',str(root/'.venv/Scripts/python.exe')))
    if not getattr(sys,'frozen',False) and not python.is_file(): python=Path(sys.executable)
    engine=root/'engine' if (root/'engine/lightningflow').is_dir() else root
    models=Path(data.get('models',str(root/'models' if (root/'models').exists() else data_dir()/'models')))
    return python,engine,models

def asset(name):
    candidate=home()/'assets'/name
    return candidate if candidate.exists() else Path(__file__).parent/'assets'/name
