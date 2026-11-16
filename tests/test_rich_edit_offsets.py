import ctypes as C
import pytest
from lightningflow import win32 as w


@pytest.mark.parametrize('window_class,raw,start,wanted',[
    ('richeditd2dpt','A\r\nB',3,'A\rB'),
    ('richedit50w','A\r\nB\U0001f680',5,'A\rB\U0001f680'),
    ('edit','A\r\nB',4,'A\r\nB'),
])
def test_text_and_selection_share_utf16_coordinates(monkeypatch,window_class,raw,start,wanted):
    monkeypatch.setattr(w.u,'IsWindow',lambda _:True)
    monkeypatch.setattr(w.u,'IsWindowEnabled',lambda _:True)
    monkeypatch.setattr(w.u,'GetWindowLongW',lambda *_:4)
    monkeypatch.setattr(w,'class_name',lambda _:window_class)
    def message(_hwnd,code,wp=0,lp=0,**_):
        if code==0xE:return len(raw.encode('utf-16-le'))//2
        if code==0xD:
            value=C.create_unicode_buffer(raw);C.memmove(lp,value,C.sizeof(value));return len(raw)
        if code==0xB0:
            C.cast(wp,C.POINTER(w.W.DWORD))[0]=start
            C.cast(lp,C.POINTER(w.W.DWORD))[0]=start
        return 0
    monkeypatch.setattr(w,'message',message)
    state=w.read_edit(1)
    assert state==w.EditText(wanted,start,start)
    assert w.expected_text(state,' appended')==wanted+' appended'
