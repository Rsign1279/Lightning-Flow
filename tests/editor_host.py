"""Disposable cross-process editor for delivery tests; never user documents."""
import ctypes as C
import json
import os
import queue
import sys
import threading
import time
import windows_integration as native
from lightningflow.win32 import u, k, pump

commands = queue.Queue()
def read_commands():
    for line in sys.stdin:
        commands.put(json.loads(line))

hwnd = u.CreateWindowExW(0,'EDIT','',0x10CF0000|0xC4|0x1000,100,100,640,180,None,None,k.GetModuleHandleW(None),None)
if not hwnd:
    raise C.WinError(C.get_last_error())
print(json.dumps({'hwnd':hwnd,'pid':os.getpid()}),flush=True)
threading.Thread(target=read_commands,daemon=True).start()
try:
    running=True
    while running:
        pump()
        try:
            command=commands.get_nowait()
        except queue.Empty:
            time.sleep(.002)
            continue
        if command['action']=='close':
            running=False
        elif command['action']=='activate':
            u.SetForegroundWindow(hwnd)
            u.SetFocus(hwnd)
        elif command['action']=='set':
            u.SetWindowTextW(hwnd,command['text'])
            u.SendMessageW(hwnd,0xB1,command.get('caret',0),command.get('caret',0))
        elif command['action']=='stall':
            print(json.dumps({'stalled':True}),flush=True)
            time.sleep(command['seconds'])
            continue
        print(json.dumps({'ok':True}),flush=True)
finally:
    u.DestroyWindow(hwnd)
