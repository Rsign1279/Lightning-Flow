"""Small per-user installer for the actual desktop executable and GPU runtime."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import zipfile
import tkinter.messagebox as messagebox
import customtkinter as ctk

ctk.set_appearance_mode('Light')
root=ctk.CTk()
root.title('Install LightningFlow')
root.geometry('560x440')
root.resizable(False,False)
root.configure(fg_color='#FBFAF7')
from lightningflow.desktop.windows import dark_titlebar
root.after(100,lambda:dark_titlebar(root,False))
target=Path(os.environ['LOCALAPPDATA'])/'Programs/LightningFlow'
events=queue.Queue()
ctk.CTkLabel(root,text='Install LightningFlow',font=('Segoe UI Variable',26,'bold'),text_color='#2B2732').pack(anchor='w',padx=36,pady=(34,12))
ctk.CTkLabel(root,text='Local GPU dictation',font=('Segoe UI Variable',16),text_color='#706A78').pack(anchor='w',padx=36,pady=(0,22))
ctk.CTkLabel(root,text='Installs for your Windows user account. No administrator access.\n\n'
    'Setup installs the desktop app and a local GPU runtime.\n'
    'GPU libraries may require about 1.4 GB of downloads.\n'
    'Python 3.11/3.12 x64 (or uv) is required for the runtime.\n\n'
    'Speech models are chosen in the app. No audio is uploaded.',
    justify='left',font=('Segoe UI Variable',13),text_color='#706A78').pack(anchor='w',padx=36)
status=ctk.CTkLabel(root,text=str(target),wraplength=480,justify='left',text_color='#706A78',font=('Segoe UI Variable',11))
status.pack(anchor='w',padx=36,pady=(22,10))
progress=ctk.CTkProgressBar(root,mode='indeterminate',progress_color='#6C4BC3')
progress.pack(fill='x',padx=36,pady=(0,12)); progress.set(0)

def install():
    action.configure(state='disabled',text='Installing…')
    progress.start()
    def run():
        try:
            bundle=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'desktop-payload.zip'
            target.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(bundle) as archive:
                for member in archive.infolist():
                    final=(target/member.filename).resolve()
                    if not final.is_relative_to(target.resolve()): raise RuntimeError('Invalid installer path.')
                archive.extractall(target)
            events.put(('message','Preparing your local GPU runtime. This can take a few minutes…'))
            result=subprocess.run(['powershell.exe','-NoProfile','-File',str(target/'Install-LightningFlow.ps1'),
                                   '-Destination',str(target),'-PrepareRuntime'],capture_output=True,text=True,
                                  creationflags=0x08000000)
            if result.returncode: raise RuntimeError((result.stderr or result.stdout)[-1500:])
            events.put(('done','Installed. Open LightningFlow to choose your microphone and speech model.'))
        except Exception as exc: events.put(('error',str(exc)))
    threading.Thread(target=run,daemon=True).start()

action=ctk.CTkButton(root,text='Install LightningFlow',height=42,fg_color='#6C4BC3',hover_color='#5938AF',
                   text_color='#FFFFFF',font=('Segoe UI Variable',14,'bold'),command=install)
action.pack(anchor='w',padx=36)

def poll():
    while not events.empty():
        kind,message=events.get()
        status.configure(text=message)
        if kind in ('done','error'):
            progress.stop(); progress.set(1 if kind=='done' else 0)
            action.configure(state='normal',text='Open LightningFlow' if kind=='done' else 'Try installation again',
                             command=(lambda:os.startfile(target/'LightningFlow.exe')) if kind=='done' else install)
        if kind=='error': messagebox.showerror('Installation did not finish',message,parent=root)
    root.after(100,poll)
root.after(100,poll)
root.mainloop()
