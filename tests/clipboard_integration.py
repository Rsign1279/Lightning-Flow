"""Verify real clipboard preservation without pasting into any app."""
import ctypes as C
import hashlib
import json
from pathlib import Path
from lightningflow import clipboard as cb


def signature():
    if not cb.u.OpenClipboard(None): raise RuntimeError('Clipboard is busy')
    try:
        result={}; fmt=0
        while True:
            fmt=cb.u.EnumClipboardFormats(fmt)
            if not fmt: break
            handle=cb.u.GetClipboardData(fmt)
            if fmt in (2,0x82):
                info=cb.BITMAP()
                assert cb.g.GetObjectW(handle,C.sizeof(info),C.byref(info))
                result[fmt]=(info.width,info.height,info.planes,info.bits_per_pixel)
            else:
                size=cb.k.GlobalSize(handle)
                pointer=cb.k.GlobalLock(handle)
                if not pointer: raise RuntimeError('Non-memory clipboard format')
                try: result[fmt]=hashlib.sha256(C.string_at(pointer,size)).digest()
                finally: cb.k.GlobalUnlock(handle)
        return result
    finally: cb.u.CloseClipboard()


def run():
    original=signature()
    with cb.PasteClipboard('LightningFlow temporary transport fixture') as transaction:
        assert cb.u.GetClipboardSequenceNumber()==transaction.sequence
    assert not transaction.restore_note,transaction.restore_note
    assert original==signature(),'Clipboard changed (a concurrent user copy must be preserved)'
    return {'real_clipboard_roundtrip_verified':True,'formats_preserved':len(original),
            'bitmap_present':2 in original,'all_memory_formats_byte_identical':True,
            'scope':'Current clipboard, including bitmap dimensions; no content or fingerprints logged'}


if __name__=='__main__':
    result=run()
    Path('results/clipboard-preservation-0.3.0.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
