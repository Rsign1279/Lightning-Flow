"""Current-Windows-user DPAPI storage. Exports remain explicit plaintext."""
import base64
import ctypes as C
from ctypes import wintypes as W
import hashlib
import hmac
import json

FORMAT='lightningflow.dpapi.v1'
MAGIC=b'LightningFlow\x00v1\x00'
LIMIT=4*1024*1024

class Blob(C.Structure):
    _fields_=[('size',W.DWORD),('data',C.POINTER(C.c_ubyte))]


def _dpapi(data,decrypt=False):
    if len(data)>LIMIT:raise ValueError('Protected data exceeds the local storage limit')
    crypt=C.WinDLL('crypt32',use_last_error=True)
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[C.c_void_p];kernel.LocalFree.restype=C.c_void_p
    operation=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes=[C.POINTER(Blob),C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,W.DWORD,C.POINTER(Blob)]
    operation.restype=W.BOOL
    buffer=C.create_string_buffer(data)
    source=Blob(len(data),C.cast(buffer,C.POINTER(C.c_ubyte)));output=Blob()
    try:
        if not operation(C.byref(source),None,None,None,None,1,C.byref(output)):
            raise OSError('Windows could not '+('decrypt' if decrypt else 'protect')+' local data for this user')
        return C.string_at(output.data,output.size)
    finally:
        C.memset(C.addressof(buffer),0,C.sizeof(buffer))
        if output.data:
            C.memset(output.data,0,output.size)
            kernel.LocalFree(output.data)


def dumps(value):
    payload=json.dumps(value,ensure_ascii=False).encode('utf-8')
    data=MAGIC+hashlib.sha256(payload).digest()+payload
    return json.dumps({'format':FORMAT,'data':base64.b64encode(_dpapi(data)).decode('ascii')})


def loads(text):
    envelope=json.loads(text)
    if not isinstance(envelope,dict) or envelope.get('format')!=FORMAT:
        return envelope  # Read legacy plaintext; next save migrates it.
    data=_dpapi(base64.b64decode(envelope['data'],validate=True),decrypt=True)
    start=len(MAGIC)
    if not data.startswith(MAGIC) or not hmac.compare_digest(data[start:start+32],hashlib.sha256(data[start+32:]).digest()):
        raise ValueError('Protected local data failed its integrity check')
    return json.loads(data[start+32:].decode('utf-8'))


def protected(text):
    try:return json.loads(text).get('format')==FORMAT
    except (ValueError,AttributeError):return False


def clear_recovery(root):
    """Delete only owned recording directories, including with the engine down."""
    from pathlib import Path
    import re
    import shutil
    root=Path(root)
    if not root.exists():return
    resolved=root.resolve()
    for folder in root.iterdir():
        if not re.fullmatch('[0-9a-f]{32}',folder.name):continue
        if folder.resolve().parent!=resolved or folder.is_symlink():raise ValueError('Recovery path leaves its storage directory')
        shutil.rmtree(folder)
