"""Temporary, bounded clipboard transaction for verified paste.

All existing formats must be snapshot-able before anything is changed. A new
user copy always wins: restoration requires our exact sequence and owner.
"""
import ctypes as C
from ctypes import wintypes as W
import time

u=C.WinDLL('user32',use_last_error=True)
k=C.WinDLL('kernel32',use_last_error=True)
g=C.WinDLL('gdi32',use_last_error=True)
g.GetObjectW.argtypes=[W.HANDLE,C.c_int,C.c_void_p]; g.GetObjectW.restype=C.c_int
g.DeleteObject.argtypes=[W.HANDLE]; g.DeleteObject.restype=W.BOOL
u.CopyImage.argtypes=[W.HANDLE,W.UINT,C.c_int,C.c_int,W.UINT]; u.CopyImage.restype=W.HANDLE

class BITMAP(C.Structure):
    _fields_=[('type',W.LONG),('width',W.LONG),('height',W.LONG),('stride',W.LONG),
              ('planes',W.WORD),('bits_per_pixel',W.WORD),('bits',C.c_void_p)]
for name,args,result in (
    ('OpenClipboard',[W.HWND],W.BOOL),('CloseClipboard',[],W.BOOL),
    ('EmptyClipboard',[],W.BOOL),('EnumClipboardFormats',[W.UINT],W.UINT),
    ('GetClipboardData',[W.UINT],W.HANDLE),('SetClipboardData',[W.UINT,W.HANDLE],W.HANDLE),
    ('GetClipboardOwner',[],W.HWND),('GetClipboardSequenceNumber',[],W.DWORD),
    ('RegisterClipboardFormatW',[W.LPCWSTR],W.UINT),
    ('SendMessageTimeoutW',[W.HWND,W.UINT,W.WPARAM,W.LPARAM,W.UINT,W.UINT,C.POINTER(C.c_size_t)],C.c_ssize_t),
    ('CreateWindowExW',[W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,C.c_int,C.c_int,C.c_int,C.c_int,
                       W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p],W.HWND),
    ('DestroyWindow',[W.HWND],W.BOOL)):
    fn=getattr(u,name); fn.argtypes=args; fn.restype=result
for name,args,result in (
    ('GlobalAlloc',[W.UINT,C.c_size_t],W.HGLOBAL),('GlobalLock',[W.HGLOBAL],C.c_void_p),
    ('GlobalUnlock',[W.HGLOBAL],W.BOOL),('GlobalSize',[W.HGLOBAL],C.c_size_t),
    ('GlobalFree',[W.HGLOBAL],W.HGLOBAL)):
    fn=getattr(k,name); fn.argtypes=args; fn.restype=result


class ClipboardUnavailable(RuntimeError): pass


def allocate(data):
    handle=k.GlobalAlloc(0x42,len(data))  # GMEM_MOVEABLE | ZEROINIT
    if not handle: raise ClipboardUnavailable('Could not allocate clipboard memory')
    pointer=k.GlobalLock(handle)
    if not pointer:
        k.GlobalFree(handle)
        raise ClipboardUnavailable('Could not lock clipboard memory')
    C.memmove(pointer,data,len(data))
    k.GlobalUnlock(handle)
    return handle


class PasteClipboard:
    def __init__(self,text,service=lambda:None):
        self.text=text
        self.service=service
        self.window=None
        self.saved=[]
        self.new=[]
        self.sequence=None
        self.restore_note=''

    def open(self):
        deadline=time.perf_counter()+.12
        while not u.OpenClipboard(self.window):
            if time.perf_counter()>=deadline: raise ClipboardUnavailable('Clipboard is busy')
            self.service()
            time.sleep(.003)

    def __enter__(self):
        self.window=u.CreateWindowExW(0,'STATIC','LightningFlow clipboard',0,0,0,0,0,None,None,None,None)
        if not self.window: raise ClipboardUnavailable('Clipboard owner could not be created')
        try:
            owner=u.GetClipboardOwner()
            if owner:
                result=C.c_size_t()
                if not u.SendMessageTimeoutW(owner,0,0,0,0x22,100,C.byref(result)):
                    raise ClipboardUnavailable('Clipboard owner is not responding; using direct typing')
            self.open()
            try:
                fmt=0; total=0
                while True:
                    C.set_last_error(0)
                    fmt=u.EnumClipboardFormats(fmt)
                    if not fmt:
                        if C.get_last_error(): raise ClipboardUnavailable('Clipboard formats are unavailable')
                        break
                    if len(self.saved)>=64 or fmt in (3,9,14) or (0x80<=fmt<=0x8E and fmt!=0x82):
                        raise ClipboardUnavailable('Clipboard contains a non-memory format; using direct typing')
                    handle=u.GetClipboardData(fmt)
                    if fmt in (2,0x82):
                        info=BITMAP()
                        if not handle or not g.GetObjectW(handle,C.sizeof(info),C.byref(info)):
                            raise ClipboardUnavailable('Clipboard image could not be preserved')
                        total+=abs(info.stride*info.height)
                        if total>16*1024*1024:
                            raise ClipboardUnavailable('Clipboard image exceeds the preservation limit')
                        duplicate=u.CopyImage(handle,0,0,0,0x2000)
                        if not duplicate: raise ClipboardUnavailable('Clipboard image could not be copied')
                        self.saved.append((fmt,duplicate))
                        continue
                    size=k.GlobalSize(handle) if handle else 0
                    total+=size
                    if not size or total>16*1024*1024:
                        raise ClipboardUnavailable('Clipboard cannot be preserved within the memory limit')
                    pointer=k.GlobalLock(handle)
                    if not pointer: raise ClipboardUnavailable('Clipboard format could not be read')
                    try: data=C.string_at(pointer,size)
                    finally: k.GlobalUnlock(handle)
                    self.saved.append((fmt,allocate(data)))
                # Allocate every original and replacement before clearing.
                self.new=[(13,allocate(self.text.encode('utf-16-le')+b'\0\0'))]
                for name,value in (('ExcludeClipboardContentFromMonitorProcessing',1),
                                   ('CanIncludeInClipboardHistory',0),('CanUploadToCloudClipboard',0)):
                    fmt=u.RegisterClipboardFormatW(name)
                    if not fmt: raise ClipboardUnavailable('Clipboard privacy format unavailable')
                    self.new.append((fmt,allocate(value.to_bytes(4,'little'))))
                if not u.EmptyClipboard(): raise ClipboardUnavailable('Clipboard could not be opened for writing')
                try:
                    self.publish(self.new)
                except Exception as exc:
                    if not u.EmptyClipboard():
                        raise RuntimeError('Clipboard write failed and original content could not be restored') from exc
                    try: self.publish(self.saved)
                    except Exception as restore:
                        raise RuntimeError('Clipboard restoration failed before paste; no input sent') from restore
                    raise
            finally: u.CloseClipboard()
            # Windows may synthesize ANSI/OEM/locale formats on CloseClipboard,
            # advancing the sequence. Arm restoration only AFTER that step.
            self.sequence=u.GetClipboardSequenceNumber()
            if u.GetClipboardOwner()!=self.window:
                raise ClipboardUnavailable('Clipboard changed before paste; current user content kept')
            return self
        except Exception:
            self.dispose()
            raise

    @staticmethod
    def publish(items):
        for index,(fmt,handle) in enumerate(items):
            if not u.SetClipboardData(fmt,handle):
                raise ClipboardUnavailable('A clipboard format could not be published')
            items[index]=(fmt,None)  # Windows owns this allocation now.

    def __exit__(self,*_):
        try:
            self.open()
            try:
                if u.GetClipboardSequenceNumber()==self.sequence and u.GetClipboardOwner()==self.window:
                    if not u.EmptyClipboard(): raise ClipboardUnavailable('Clipboard restoration was blocked')
                    self.publish(self.saved)
                # Another copy changed it. Preserve that new user content.
            finally: u.CloseClipboard()
        except ClipboardUnavailable:
            self.restore_note='Clipboard restoration was blocked; the clipboard may contain this transcript.'
        finally: self.dispose()

    def dispose(self):
        for fmt,handle in self.saved+self.new:
            if handle:
                if fmt in (2,0x82): g.DeleteObject(handle)
                else: k.GlobalFree(handle)
        self.saved=[]; self.new=[]
        if self.window: u.DestroyWindow(self.window); self.window=None
