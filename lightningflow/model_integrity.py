"""Pinned Hub revision + publisher-hosted LFS/Git hashes, never model code."""
import hashlib
import re
from pathlib import Path


def publisher_manifest(model):
    from huggingface_hub import HfApi
    from ._vendor.faster_whisper.utils import _MODELS
    if model not in _MODELS:raise ValueError('Choose a supported Whisper model name')
    info=HfApi(token=False).model_info(_MODELS[model],files_metadata=True,timeout=15)
    if not re.fullmatch(r'[0-9a-f]{40}',info.sha or ''):raise RuntimeError('Publisher revision was not available; no unverified download')
    files={}
    for item in info.siblings:
        if item.rfilename not in ('config.json','preprocessor_config.json','model.bin','tokenizer.json') and not item.rfilename.startswith('vocabulary.'):continue
        if '/' in item.rfilename or '\\' in item.rfilename:continue
        if item.lfs:
            files[item.rfilename]={'algorithm':'sha256','digest':item.lfs.sha256,'size':item.lfs.size}
        elif item.blob_id:
            files[item.rfilename]={'algorithm':'git-sha1','digest':item.blob_id,'size':item.size}
    if files.get('model.bin',{}).get('algorithm')!='sha256':raise RuntimeError('Publisher model SHA-256 was unavailable')
    return {'repository':_MODELS[model],'revision':info.sha,'files':files,
            'trust':'HTTPS publisher-hosted Hub metadata at a pinned revision; not an independent signature or security certification.'}


def verify_download(directory,manifest):
    directory=Path(directory).resolve()
    for name,expected in manifest['files'].items():
        path=(directory/name).resolve()
        if not path.is_relative_to(directory) or path.parent!=directory:raise ValueError('Unsafe model manifest path')
        if not path.is_file():raise RuntimeError('Downloaded model file is missing: '+name)
        size=path.stat().st_size
        if expected.get('size') is not None and size!=expected['size']:raise RuntimeError('Publisher size mismatch: '+name)
        algorithm=expected['algorithm']
        if algorithm not in ('sha256','git-sha1'):raise ValueError('Unknown publisher hash algorithm')
        digest=hashlib.sha256() if algorithm=='sha256' else hashlib.sha1()
        if algorithm=='git-sha1':digest.update(b'blob '+str(size).encode()+b'\0')
        with path.open('rb') as stream:
            while chunk:=stream.read(1024*1024):digest.update(chunk)
        if digest.hexdigest()!=expected['digest']:raise RuntimeError('Publisher checksum mismatch: '+name)
    return True
