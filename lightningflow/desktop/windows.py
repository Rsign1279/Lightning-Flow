"""Small native desktop integrations; no third-party tray or clipboard code."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
from collections import deque

user=C.WinDLL('user32',use_last_error=True)
shell=C.WinDLL('shell32',use_last_error=True)
kernel=C.WinDLL('kernel32',use_last_error=True)
PTR=C.c_ssize_t
WNDPROC=C.WINFUNCTYPE(PTR,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
user.GetParent.argtypes=[W.HWND]; user.GetParent.restype=W.HWND
user.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int]; user.GetWindowLongPtrW.restype=PTR
user.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,PTR]; user.SetWindowLongPtrW.restype=PTR
user.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
user.LoadImageW.argtypes=[W.HINSTANCE,W.LPCWSTR,W.UINT,C.c_int,C.c_int,W.UINT]; user.LoadImageW.restype=W.HANDLE
user.CallWindowProcW.argtypes=[C.c_void_p,W.HWND,W.UINT,W.WPARAM,W.LPARAM]; user.CallWindowProcW.restype=PTR
user.CreatePopupMenu.restype=W.HMENU
user.AppendMenuW.argtypes=[W.HMENU,W.UINT,C.c_size_t,W.LPCWSTR]
user.TrackPopupMenu.argtypes=[W.HMENU,W.UINT,C.c_int,C.c_int,C.c_int,W.HWND,C.c_void_p]
user.TrackPopupMenu.restype=W.UINT
user.DestroyMenu.argtypes=[W.HMENU]
user.SetForegroundWindow.argtypes=[W.HWND]
user.DestroyIcon.argtypes=[W.HANDLE]
kernel.CreateMutexW.argtypes=[C.c_void_p,W.BOOL,W.LPCWSTR]; kernel.CreateMutexW.restype=W.HANDLE
kernel.CloseHandle.argtypes=[W.HANDLE]
kernel.CreateEventW.argtypes=[C.c_void_p,W.BOOL,W.BOOL,W.LPCWSTR]; kernel.CreateEventW.restype=W.HANDLE
kernel.SetEvent.argtypes=[W.HANDLE]
kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD]; kernel.WaitForSingleObject.restype=W.DWORD

def startup_command():
    import subprocess
    import sys
    from .paths import home
    command=[sys.executable,'--background'] if getattr(sys,'frozen',False) else [str(home()/'.venv/Scripts/pythonw.exe'),str(home()/'desktop_main.py'),'--background']
    return subprocess.list2cmdline(command)

def startup_enabled():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            return winreg.QueryValueEx(key,'LightningFlowDesktop')[0]==startup_command()
    except OSError: return False

def set_startup(enabled):
    import winreg
    key=winreg.CreateKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Run')
    try:
        if enabled:
            winreg.SetValueEx(key,'LightningFlowDesktop',0,winreg.REG_SZ,startup_command())
        else:
            try: winreg.DeleteValue(key,'LightningFlowDesktop')
            except FileNotFoundError: pass
    finally: winreg.CloseKey(key)

def hwnd(window):
    child=window.winfo_id()
    return user.GetParent(child) or child

def dark_titlebar(window,dark=True):
    try:
        dwm=C.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes=[W.HWND,W.DWORD,C.c_void_p,W.DWORD]
        value=W.BOOL(dark)
        dwm.DwmSetWindowAttribute(hwnd(window),20,C.byref(value),C.sizeof(value))
    except OSError: pass

def nonactivating(window):
    handle=hwnd(window)
    style=user.GetWindowLongPtrW(handle,-20)
    user.SetWindowLongPtrW(handle,-20,style|0x08000000|0x80)
    user.SetWindowPos(handle,W.HWND(-1),0,0,0,0,0x1|0x2|0x10|0x20)

class SingleInstance:
    def __init__(self,name):
        self.handle=kernel.CreateMutexW(None,False,'Local\\'+name)
        self.already=C.get_last_error()==183
        self.signal=kernel.CreateEventW(None,False,False,'Local\\'+name+'-show')
        if self.already and self.signal: kernel.SetEvent(self.signal)
    def requested(self):
        return bool(self.signal and kernel.WaitForSingleObject(self.signal,0)==0)
    def close(self):
        if self.signal: kernel.CloseHandle(self.signal); self.signal=None
        if self.handle: kernel.CloseHandle(self.handle); self.handle=None

class GUID(C.Structure): _fields_=[('a',W.DWORD),('b',W.WORD),('c',W.WORD),('d',C.c_byte*8)]
class NOTIFY(C.Structure):
    _fields_=[('size',W.DWORD),('window',W.HWND),('ident',W.UINT),('flags',W.UINT),
              ('message',W.UINT),('icon',W.HANDLE),('tip',W.WCHAR*128),('state',W.DWORD),
              ('mask',W.DWORD),('info',W.WCHAR*256),('timeout',W.UINT),('title',W.WCHAR*64),
              ('infoflags',W.DWORD),('guid',GUID),('balloon',W.HANDLE)]
shell.Shell_NotifyIconW.argtypes=[W.DWORD,C.POINTER(NOTIFY)]

class Tray:
    def __init__(self,root,icon_path,show,quit_app):
        self.root=root; self.window=hwnd(root); self.show=show; self.quit_app=quit_app
        self.actions=deque()
        self.icon=user.LoadImageW(None,str(icon_path),1,32,32,0x10)
        self.data=NOTIFY(size=C.sizeof(NOTIFY),window=self.window,ident=1,flags=1|2|4,
                         message=0x8042,icon=self.icon,tip='LightningFlow · Local GPU dictation')
        self.previous=None
        self.callback=WNDPROC(self._window_proc)
        self.previous=user.SetWindowLongPtrW(self.window,-4,C.cast(self.callback,C.c_void_p).value)
        self.available=bool(shell.Shell_NotifyIconW(0,C.byref(self.data)))

    def _window_proc(self,window,message,wp,lp):
        if message==0x8042:
            if lp==0x203: self.actions.append('show')
            elif lp==0x205:
                menu=user.CreatePopupMenu()
                user.AppendMenuW(menu,0,1,'Open LightningFlow')
                user.AppendMenuW(menu,0,2,'Quit LightningFlow')
                point=W.POINT(); user.GetCursorPos(C.byref(point))
                user.SetForegroundWindow(self.window)
                chosen=user.TrackPopupMenu(menu,0x100|0x80,point.x,point.y,0,self.window,None)
                user.DestroyMenu(menu)
                if chosen==1: self.actions.append('show')
                elif chosen==2: self.actions.append('quit')
            return 0
        return user.CallWindowProcW(self.previous,window,message,wp,lp) if self.previous else 0

    def update(self,text):
        self.data.tip=('LightningFlow · '+text)[:127]
        shell.Shell_NotifyIconW(1,C.byref(self.data))

    def close(self):
        if self.available: shell.Shell_NotifyIconW(2,C.byref(self.data))
        if self.previous: user.SetWindowLongPtrW(self.window,-4,self.previous)
        if self.icon: user.DestroyIcon(self.icon)
        self.available=False
