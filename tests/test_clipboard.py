from dataclasses import replace
import pytest
from lightningflow import clipboard as cb
from lightningflow.win32 import InputGuard,Target
from lightningflow.accessibility import AccessibleText


def test_restoration_never_overwrites_a_new_user_copy(monkeypatch):
    transaction=cb.PasteClipboard('test')
    transaction.window=100; transaction.sequence=42
    disposed=[]
    monkeypatch.setattr(transaction,'open',lambda:None)
    monkeypatch.setattr(transaction,'dispose',lambda:disposed.append(True))
    monkeypatch.setattr(cb.u,'GetClipboardSequenceNumber',lambda:43)
    monkeypatch.setattr(cb.u,'GetClipboardOwner',lambda:100)
    monkeypatch.setattr(cb.u,'CloseClipboard',lambda:True)
    monkeypatch.setattr(cb.u,'EmptyClipboard',lambda:pytest.fail('new user copy was overwritten'))
    transaction.__exit__()
    assert disposed


def test_failed_paste_is_not_followed_by_unicode_retransmission(monkeypatch):
    guard=InputGuard([])
    target=Target(10,20,(),0,state=AccessibleText((1,),2,'',0,0))
    class Transaction:
        restore_note=''
        def __init__(self,*_): pass
        def __enter__(self): return self
        def __exit__(self,*_): restored.append(True)
    restored=[]; pasted=[]
    monkeypatch.setattr(cb,'PasteClipboard',Transaction)
    monkeypatch.setattr(guard,'valid',lambda _:True)
    monkeypatch.setattr('lightningflow.win32.u.GetAsyncKeyState',lambda _:0)
    monkeypatch.setattr('lightningflow.win32.send_virtual_keys',lambda _:pasted.append(True))
    monkeypatch.setattr(guard,'verify_accessible',lambda *_:(_ for _ in ()).throw(RuntimeError('partial paste')))
    monkeypatch.setattr('lightningflow.win32.u.SendInput',lambda *_:pytest.fail('duplicate Unicode fallback'))
    with pytest.raises(RuntimeError,match='partial paste'): guard.insert('private test',target)
    assert restored==[True] and pasted==[True]


def test_successful_paste_still_reports_clipboard_restoration_issue(monkeypatch):
    guard=InputGuard([])
    target=Target(10,20,(),0,state=AccessibleText((1,),2,'',0,0))
    class Transaction:
        restore_note='Clipboard restoration was blocked'
        def __init__(self,*_): pass
        def __enter__(self): return self
        def __exit__(self,*_): pass
    monkeypatch.setattr(cb,'PasteClipboard',Transaction)
    monkeypatch.setattr(guard,'valid',lambda _:True)
    monkeypatch.setattr('lightningflow.win32.u.GetAsyncKeyState',lambda _:0)
    monkeypatch.setattr('lightningflow.win32.send_virtual_keys',lambda _:None)
    monkeypatch.setattr(guard,'verify_accessible',lambda *_:None)
    receipt=guard.insert('hello',target)
    assert receipt.confirmed and 'restoration was blocked' in receipt.method


def test_unsupported_clipboard_format_refused_before_clearing(monkeypatch):
    transaction=cb.PasteClipboard('test')
    monkeypatch.setattr(cb.u,'CreateWindowExW',lambda *_:100)
    monkeypatch.setattr(cb.u,'GetClipboardOwner',lambda:None)
    monkeypatch.setattr(cb.u,'DestroyWindow',lambda *_:True)
    monkeypatch.setattr(transaction,'open',lambda:None)
    monkeypatch.setattr(cb.u,'CloseClipboard',lambda:True)
    monkeypatch.setattr(cb.u,'EnumClipboardFormats',lambda _:3) # CF_METAFILEPICT needs special ownership
    monkeypatch.setattr(cb.u,'EmptyClipboard',lambda:pytest.fail('original bitmap clipboard was cleared'))
    with pytest.raises(cb.ClipboardUnavailable,match='non-memory'): transaction.__enter__()


def test_sequence_is_captured_after_windows_synthesizes_formats_on_close(monkeypatch):
    import ctypes as C
    state={'sequence':10,'restored':False}
    formats=iter([13,0])
    memory=C.create_string_buffer(b'abcd')
    monkeypatch.setattr(cb.u,'CreateWindowExW',lambda *_:100)
    monkeypatch.setattr(cb.u,'DestroyWindow',lambda *_:True)
    monkeypatch.setattr(cb.u,'GetClipboardOwner',lambda:100)
    monkeypatch.setattr(cb.u,'SendMessageTimeoutW',lambda *_:1)
    monkeypatch.setattr(cb.u,'OpenClipboard',lambda *_:True)
    monkeypatch.setattr(cb.u,'EmptyClipboard',lambda:True)
    monkeypatch.setattr(cb.u,'EnumClipboardFormats',lambda _:next(formats))
    monkeypatch.setattr(cb.u,'GetClipboardData',lambda _:123)
    monkeypatch.setattr(cb.k,'GlobalSize',lambda _:4)
    monkeypatch.setattr(cb.k,'GlobalLock',lambda _:C.addressof(memory))
    monkeypatch.setattr(cb.k,'GlobalUnlock',lambda _:True)
    monkeypatch.setattr(cb.k,'GlobalFree',lambda _:None)
    monkeypatch.setattr(cb,'allocate',lambda _:500)
    monkeypatch.setattr(cb.u,'RegisterClipboardFormatW',lambda _:1000)
    monkeypatch.setattr(cb.u,'SetClipboardData',lambda _f,h:h)
    monkeypatch.setattr(cb.u,'GetClipboardSequenceNumber',lambda:state['sequence'])
    def close(): state['sequence']+=1
    monkeypatch.setattr(cb.u,'CloseClipboard',close)
    transaction=cb.PasteClipboard('fixture')
    with transaction:
        assert transaction.sequence==11
        assert transaction.saved[0][1]==500
    # Original allocation was handed to Windows, not freed as an abandoned copy.
    assert transaction.restore_note=='' and state['sequence']==12
