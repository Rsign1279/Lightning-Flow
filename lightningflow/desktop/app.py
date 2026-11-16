"""Windows desktop shell. Inference and insertion live in a separate process."""
from dataclasses import asdict
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog,messagebox

import customtkinter as ctk
from . import paths
from .bridge import EngineProcess
from .state import Preferences,Settings,History,MODELS,MODES,key_label
from .widgets import *
from . import views
from .. import __version__
from .windows import Tray,SingleInstance,dark_titlebar,startup_enabled

PAGES=[('dictation','Home'),('history','Dictation log'),('writing','Writing style'),('dictionary','Dictionary'),
       ('models','Speech models'),('microphone','Microphone'),('shortcuts','Shortcuts'),
       ('performance','Performance'),('settings','Privacy & settings')]
BUSY={'starting','recording','paused','processing','enhancing'}

class DesktopApp(ctk.CTk):
    def __init__(self,auto_engine=True,hidden=False):
        self.preferences=Preferences(paths.data_dir()/'settings.json')
        self.settings=self.preferences.load()
        self.settings.startup=startup_enabled()
        ctk.set_appearance_mode(self.settings.theme)
        ctk.set_default_color_theme('green')
        super().__init__()
        if hidden: self.withdraw()
        self.title('LightningFlow')
        self.geometry('1160x840')
        self.minsize(1000,700)
        self.configure(fg_color=BG)
        self.events=queue.Queue()
        self.engine=None
        self.tasks=[]
        self.engine_state='offline'
        self.status_message='Hold your shortcut to dictate into the active app.'
        self.partial=''
        self.last_result=None
        self.session_words=0
        self.session_word_counts={}
        self.retained_audio_ids=set()
        self.hardware={}
        self.device_rows=[]
        self.local_models=[]
        self.diagnostics=[]
        self.level=0
        self.seconds=0
        self.page=''
        self.refs={}
        self._page_cache={}
        self._invalidate_pages=False
        self.restart_wait=False
        self.mic_testing=False
        self.repairing=False
        self.download_model=None
        self.closing=False
        self.history=History(paths.data_dir()/'history.sqlite3',self.settings.history_enabled)
        self.last_result=next((row for row in self.history.rows if row.get('text')),None)
        self.protocol('WM_DELETE_WINDOW',self.close_window)
        self.grid_columnconfigure(1,weight=1)
        self.grid_rowconfigure(0,weight=1)
        self.sidebar=ctk.CTkFrame(self,width=210,corner_radius=0,fg_color=SIDE)
        self.sidebar.grid(row=0,column=0,sticky='nsew')
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0,weight=1)
        self.sidebar.grid_rowconfigure(14,weight=1)
        brand=ctk.CTkFrame(self.sidebar,fg_color='transparent')
        brand.grid(row=0,column=0,padx=23,pady=(29,24),sticky='ew')
        self.logo=ctk.CTkLabel(brand,text='',image=icon('bolt',True,28),width=28,height=32)
        self.logo.pack(side='left',padx=(0,10))
        label(brand,'LightningFlow',17,True).pack(side='left')
        label(self.sidebar,'WORKSPACE',10,True,True).grid(row=1,column=0,padx=26,pady=(0,8),sticky='w')
        self.nav={}
        self.nav_font=font(14)
        self.nav_selected_font=font(14,True)
        sidebar_pages=[item for item in PAGES if item[0] in ('dictation','history','writing','dictionary','settings')]
        for index,(ident,name) in enumerate(sidebar_pages):
            row=15 if ident=='settings' else index+2
            b=ctk.CTkButton(self.sidebar,text=name,anchor='w',height=40,corner_radius=9,font=self.nav_font,
                image=icon(ident),compound='left',border_spacing=12,
                fg_color='transparent',text_color=MUTED,hover_color=BORDER,command=lambda p=ident:self.navigate(p))
            b.grid(row=row,column=0,padx=12,pady=2,sticky='ew')
            keyboard_control(b,b.invoke)
            self.nav[ident]=b
        bottom=ctk.CTkFrame(self.sidebar,fg_color='transparent')
        bottom.grid(row=17,column=0,padx=16,pady=(20,12),sticky='ew')
        self.side_status=label(bottom,'Microphone is off',12,True)
        self.side_status.pack(anchor='w',padx=13,pady=(13,3))
        label(bottom,'On-device transcription',11,muted=True).pack(anchor='w',padx=13,pady=(0,13))
        label(self.sidebar,'LightningFlow '+__version__,10,muted=True).grid(row=18,column=0,padx=26,pady=(0,17),sticky='w')
        self.body=ctk.CTkFrame(self,fg_color=BG,corner_radius=0)
        self.body.grid(row=0,column=1,sticky='nsew')
        self.body.grid_columnconfigure(0,weight=1)
        self.body.grid_rowconfigure(1,weight=1)
        header=ctk.CTkFrame(self.body,fg_color='transparent',height=50)
        header.grid(row=0,column=0,padx=32,pady=(23,0),sticky='ew')
        header.grid_columnconfigure(0,weight=1)
        self.breadcrumb=label(header,'Your workspace',12,False,True)
        self.breadcrumb.grid(row=0,column=0,sticky='w')
        self.status_badge=label(header,'Engine offline',11,True,fg_color=CARD,corner_radius=13,height=28,padx=12)
        self.status_badge.grid(row=0,column=1,sticky='e')
        self.theme_variable=tk.StringVar(value=self.settings.theme)
        option(header,['Light','Dark','System'],variable=self.theme_variable,
               command=self.change_theme,width=105,height=30).grid(row=0,column=2,padx=(12,0))
        self.content=ctk.CTkScrollableFrame(self.body,fg_color=BG,corner_radius=0)
        self.content.grid(row=1,column=0,padx=(24,20),pady=(12,4),sticky='nsew')
        self.content.grid_columnconfigure(0,weight=1)
        self.notice=label(self.body,'',12,muted=True,wraplength=800)
        self.notice.grid(row=2,column=0,padx=32,pady=(3,15),sticky='ew')
        self.overlay=RecordingOverlay(self)
        self.update_idletasks()
        dark_titlebar(self,ctk.get_appearance_mode()=='Dark')
        app_icon=paths.asset('lightningflow.ico')
        if app_icon.exists():
            self.iconbitmap(str(app_icon))
        try: self.tray=Tray(self,app_icon,self.show_window,self.quit_app) if app_icon.exists() else None
        except Exception: self.tray=None
        self.navigate('dictation' if self.settings.onboarding_done else 'onboarding')
        self.bind('<Control-Key-1>',lambda _:self.navigate('dictation'))
        self.bind('<Control-Key-2>',lambda _:self.navigate('history'))
        self.bind('<Escape>',lambda _:self.send('cancel') if self.engine_state in BUSY else None)
        self.after(8,self.poll_events)
        self.after(5000,self.performance_tick)
        if self.preferences.error: self.toast(self.preferences.error)
        if self.history.error: self.toast(self.history.error)
        if auto_engine: self.after(200,self.start_engine)
        if self.settings.check_updates:self.after(2000,self.check_for_updates)

    def shortcut(self,action='toggle'):
        if action=='toggle' and self.settings.recording_shortcut=='ctrl_win': return 'Ctrl + Win'
        return 'Ctrl + Alt + '+key_label(self.settings.shortcuts[action])

    def heading(self,title,subtitle):
        frame=ctk.CTkFrame(self.content,fg_color='transparent')
        frame.pack(fill='x',padx=8,pady=(0,24))
        label(frame,title,26,True).pack(anchor='w')
        label(frame,subtitle,14,muted=True,wraplength=760,justify='left').pack(anchor='w',pady=(7,0))

    def section(self,title,subtitle=None):
        frame=card(self.content)
        frame.pack(fill='x',padx=8,pady=(0,16))
        inner=ctk.CTkFrame(frame,fg_color='transparent')
        inner.pack(fill='both',expand=True,padx=22,pady=20)
        if title: label(inner,title,18,True).pack(anchor='w')
        if subtitle: label(inner,subtitle,13,muted=True,wraplength=730,justify='left').pack(anchor='w',pady=(6,14))
        return inner

    def navigate(self,page):
        if self._invalidate_pages:
            for child in self.content.winfo_children():child.destroy()
            self._page_cache={};self._invalidate_pages=False;self.refs={}
        elif self.page in ('dictation','history'):
            others={widget for name,(widgets,_) in self._page_cache.items() if name!=self.page for widget,_ in widgets}
            widgets=[(child,child.pack_info()) for child in self.content.winfo_children() if child not in others and child.winfo_manager()=='pack']
            self._page_cache[self.page]=(widgets,self.refs)
            for child,_ in widgets:child.pack_forget()
        else:
            retained={widget for widgets,_ in self._page_cache.values() for widget,_ in widgets}
            for child in self.content.winfo_children():
                if child not in retained:child.destroy()
        self.page=page; self.refs={}
        self.content._parent_canvas.yview_moveto(0)
        for ident,b in self.nav.items():
            selected=ident==page or (ident=='settings' and page in ('models','microphone','shortcuts','performance'))
            b.configure(fg_color=SELECTED if selected else 'transparent',text_color=TEXT if selected else MUTED,
                        font=self.nav_selected_font if selected else self.nav_font,image=icon(ident,selected))
        self.breadcrumb.configure(text='Getting started' if page=='onboarding' else 'Your workspace' if page=='dictation' else dict(PAGES).get(page,'Workspace'))
        if page in self._page_cache:
            widgets,self.refs=self._page_cache[page]
            for child,packing in widgets:child.pack(**packing)
            if page=='dictation':self.update_dashboard()
            elif 'log_refresh' in self.refs:self.refs['log_refresh']()
        else:getattr(self,'page_'+page)()
        self.refresh_status()

    def toast(self,message):
        self.notice.configure(text=message)

    def check_for_updates(self):
        if getattr(self,'checking_updates',False):return
        self.checking_updates=True
        def check():
            from .updates import release_update
            try:
                result=release_update(__version__)
                message='Version '+result['version']+' is available on GitHub Releases.' if result else 'No newer published release is available.'
            except Exception:message='Release check failed. You can open GitHub Releases manually.'
            finally:self.checking_updates=False
            self.events.put({'event':'notice','message':message})
        threading.Thread(target=check,daemon=True).start()

    def save_settings(self,restart=False,**changes):
        if restart and self.engine_state in BUSY:
            self.toast('Finish or cancel the current recording before changing the engine.'); return False
        if restart and not self.confirm_restart(): return False
        try:
            data=asdict(self.settings); data.update(changes)
            candidate=Settings(**data).validate()
            self.preferences.save(candidate)
            history_changed=candidate.history_enabled!=self.settings.history_enabled
            self.settings=candidate
            self._invalidate_pages=True
            if history_changed: self.history.configure(candidate.history_enabled)
            if restart: self.start_engine(confirmed=True)
            else: self.send('configure')
            self.refresh_status()
            self.toast('Changes saved on this PC.')
            return True
        except Exception as exc:
            self.toast(str(exc)); return False

    def send(self,action,**data):
        return self.engine.send(action,**data) if self.engine else False

    def confirm_restart(self):
        return not self.retained_audio_ids or messagebox.askyesno('Restart the local engine?',
            'Audio held only in memory will be forgotten. Completed encrypted recovery saves survive a restart when enabled. Export audio first to ensure you keep it.',parent=self)

    def start_engine(self,confirmed=False):
        if self.closing: return
        if self.engine_state in BUSY:
            self.toast('Finish or cancel dictation before restarting.'); return
        if not confirmed and not self.confirm_restart(): return
        if self.engine and self.engine.process.poll() is None:
            if self.restart_wait: return
            self.restart_wait=True
            self.retained_audio_ids.clear()
            for row in self.history.rows: row['audio_available']=False
            self.engine.stop()
            self.engine_state='loading'; self.status_message='Restarting the local engine…'; self.refresh_status()
            self.after(100,self.wait_restart)
            return
        self.launch_engine()

    def wait_restart(self):
        if self.closing: return
        if self.engine and self.engine.process.poll() is None:
            self.after(100,self.wait_restart); return
        self.restart_wait=False
        self.launch_engine()

    def launch_engine(self):
        try:
            python,engine,default_models=paths.runtime()
            models=Path(self.settings.models_dir) if self.settings.models_dir else default_models
            if not self.settings.models_dir:
                self.settings.models_dir=str(models); self.preferences.save(self.settings)
            self.engine_state='loading'; self.status_message='Loading your speech model onto the GPU…'
            self.engine=EngineProcess(python,engine,self.preferences.path,models,self.events)
        except Exception as exc:
            self.engine_state='error'; self.status_message=str(exc)
            self.toast(self.status_message)
        self.refresh_status()

    def poll_events(self,reschedule=True):
        if self.closing: return
        # Schedule first: a storage/widget exception must not permanently stop
        # status processing while the engine continues recording.
        if reschedule: self.after(8,self.poll_events)
        # Native WndProc callbacks cannot re-enter Tk safely. Tray callbacks
        # queue intentions and this normal Tk callback performs the UI action.
        if self.tray:
            while self.tray.actions:
                action=self.tray.actions.popleft()
                if action=='show': self.show_window()
                elif action=='quit': self.quit_app()
            if self.closing: return
        for _ in range(80):
            try: event=self.events.get_nowait()
            except queue.Empty: break
            kind=event.get('event')
            if event.get('process_pid') and self.engine and event['process_pid']!=self.engine.process.pid and not event.get('task_origin'):
                continue
            if kind=='status':
                if event.get('task_origin'):
                    if event.get('state')=='error':
                        self.download_model=None; self.toast(event.get('message','Model task failed.'))
                        if self.page=='models': self.navigate('models')
                    continue
                self.engine_state=event['state']; self.status_message=event.get('message','')
                if event.get('gesture'): self.overlay.set_gesture(event['gesture'])
                if self.engine_state=='starting':
                    self.seconds=0; self.level=0
                    if 'timer' in self.refs: self.refs['timer'].configure(text='00:00')
                if self.engine_state=='error': self.toast(self.status_message)
                if event.get('detail'): self.diagnostics=(self.diagnostics+[event['detail']])[-20:]
                self.refresh_status()
            elif kind=='gesture':
                self.overlay.set_gesture(event['state'])
                self.refresh_status()
            elif kind=='partial':
                self.partial=event.get('text','')
                if 'transcript' in self.refs:
                    self.set_text(self.refs['transcript'],self.partial or 'Listening…')
                    self.refs['transcript'].configure(text_color=TEXT)
                if 'recovery' in self.refs:
                    self.refs['recovery'].configure(text='Live preview · may change' if event.get('provisional') else 'Stable transcript · finishing')
            elif kind=='suggestion':
                row=next((row for row in self.history.rows if row['id']==event['id']),None)
                if row:
                    row=dict(row,cleanup_suggestion=event['text'])
                    self.history.add(row)
                    if self.last_result and self.last_result['id']==row['id']:self.last_result=row
                    self.toast('A local AI suggestion is available in the dictation log. Inserted text is unchanged.')
            elif kind=='recovered':
                for row in event['rows']:
                    existing=next((item for item in self.history.rows if item['id']==row['id']),None)
                    self.history.add(dict(existing or row,audio_available=True))
                    self.retained_audio_ids.add(row['id'])
                if self.page=='history' and 'log_refresh' in self.refs:self.refs['log_refresh']()
            elif kind=='recovery_removed':
                for row in self.history.rows:
                    if row['id'] in event['ids']:row['audio_available']=False
                self.retained_audio_ids.difference_update(event['ids'])
            elif kind=='result':
                self.last_result=event
                if not event.get('recording_in_progress'):self.partial=''
                count=len(event.get('text','').split())
                self.session_words+=count-self.session_word_counts.get(event['id'],0)
                self.session_word_counts[event['id']]=count
                while len(self.session_word_counts)>200: self.session_word_counts.pop(next(iter(self.session_word_counts)))
                self.history.add(event)
                if event.get('audio_available'): self.retained_audio_ids.add(event['id'])
                else: self.retained_audio_ids.discard(event['id'])
                if self.history.error: self.toast(self.history.error)
                if self.page=='dictation' and not event.get('recording_in_progress'): self.update_dashboard()
                elif self.page=='history' and 'log_refresh' in self.refs:self.refs['log_refresh']()
                elif self.page=='performance' and self.state()!='withdrawn':self.navigate(self.page)
                if event.get('error'): self.toast('Transcript kept: '+event['error'])
            elif kind=='level':
                self.level=event.get('level',0); self.seconds=event.get('seconds',0)
                recording=self.engine_state in ('starting','recording')
                if 'wave' in self.refs: self.refs['wave'].set(self.level,recording)
                if 'timer' in self.refs: self.refs['timer'].configure(text=f'{int(self.seconds)//60:02d}:{int(self.seconds)%60:02d}')
                self.overlay.wave.set(self.level,recording)
            elif kind=='devices':
                self.device_rows=event['devices']
                if self.page=='microphone': self.navigate('microphone')
            elif kind=='hardware':
                self.hardware=event
                if self.page=='performance': self.update_hardware_labels()
            elif kind=='notice': self.toast(event['message'])
            elif kind=='diagnostic': self.diagnostics=(self.diagnostics+[event['message']])[-20:]
            elif kind=='mic_level':
                if 'mic_wave' in self.refs: self.refs['mic_wave'].set(event['level'],self.mic_testing)
            elif kind=='mic_test':
                self.mic_testing=False
                self.toast(event.get('message','Microphone test finished.')+(f" First audio: {event['first_frame_ms']} ms." if event.get('first_frame_ms') else ''))
                if self.page=='microphone': self.navigate('microphone')
            elif kind=='cancelled':
                self.partial=''
                if self.page=='dictation': self.update_dashboard()
            elif kind=='local_models':
                self.local_models=event.get('models',[])
                self.toast(event.get('message','Local models connected.'))
                if self.page=='writing': self.navigate('writing')
            elif kind=='cleanup_test':
                if 'cleanup_output' in self.refs: self.set_text(self.refs['cleanup_output'],event.get('text',''))
                self.toast(event.get('message',''))
            elif kind=='task_done':
                self.download_model=None
                self.toast(event.get('message','Task finished.'))
                if self.page=='models': self.navigate('models')
                if event.get('task')=='download' and event.get('model')==self.settings.model:
                    self.start_engine()
            elif kind=='runtime_repaired':
                self.repairing=False
                self.engine_state='offline'
                if event.get('ok'): self.start_engine(confirmed=True)
                else:
                    self.engine_state='error'; self.status_message=event['message']
                    self.toast(self.status_message); self.refresh_status()
            elif kind=='process_exit':
                self.tasks=[task for task in self.tasks if task.process.pid!=event['pid']]
                if self.engine and event['pid']==self.engine.process.pid and not self.restart_wait and not self.repairing:
                    if event.get('code'):
                        from .state import interrupted_preview
                        row=interrupted_preview(self.partial,event['code'])
                        if row:
                            self.history.add(row);self.last_result=row;self.partial=''
                        self.engine_state='error'
                        self.status_message=f"Local engine exited unexpectedly (code {event['code']}). Check Performance diagnostics; restart the engine when ready."
                        self.toast('Engine stopped. Any available preview was retained in the log; it may be incomplete.')
                        if self.page=='dictation':self.update_dashboard()
                        elif self.page=='history' and 'log_refresh' in self.refs:self.refs['log_refresh']()
                    if self.engine_state!='error':
                        self.engine_state='offline'; self.status_message='The local engine is stopped.'
                    self.refresh_status()

    def refresh_status(self):
        active=self.engine_state in BUSY
        caption={'ready':'Ready to dictate','offline':'Engine stopped','loading':'Loading GPU model','error':'Needs attention',
                 'starting':'Opening microphone','recording':'Recording','paused':'Microphone paused','processing':'Transcribing','enhancing':'Local cleanup'}.get(self.engine_state,self.engine_state)
        if self.mic_testing: caption='Testing microphone'
        self.status_badge.configure(text=caption,text_color=SUCCESS if self.engine_state=='ready' else ERROR if self.engine_state=='error' else ACCENT)
        self.side_status.configure(text='Microphone is on' if self.mic_testing or self.engine_state in ('recording','starting') else 'Microphone is off')
        if self.tray: self.tray.update(caption)
        if self.settings.overlay and active: self.overlay.show_state(self.engine_state,self.shortcut())
        else: self.overlay.hide()
        if 'record' in self.refs:
            self.refs['record'].configure(text='Finish recording' if self.engine_state=='recording' else 'Working…' if active else 'Try in this window',
                state='normal' if not self.mic_testing and self.engine_state in ('ready','recording') else 'disabled')
        if 'record_cancel' in self.refs:
            if active:
                self.refs['record_cancel'].configure(state='normal')
                if not self.refs['record_cancel'].winfo_manager():self.refs['record_cancel'].pack(side='left',padx=(8,0))
            else:self.refs['record_cancel'].pack_forget()
        if 'state_text' in self.refs: self.refs['state_text'].configure(text=self.status_message)
        if not active and 'wave' in self.refs: self.refs['wave'].set(0,False)

    def practice(self):
        if self.engine_state=='recording': self.send('stop',requested_at=time.perf_counter())
        elif self.engine_state=='ready': self.send('sandbox')

    def page_dictation(self):
        views.home(self)

    def current_text(self):
        return self.partial if self.engine_state in BUSY else (self.last_result or {}).get('text','')

    def update_dashboard(self):
        views.update_home(self)

    def page_onboarding(self):
        self.heading('Set up LightningFlow','Three steps to start dictating on this PC.')
        intro=self.section('Welcome to LightningFlow','Speech is transcribed on your NVIDIA GPU. No account, no subscription, and no audio upload.')
        label(intro,'01   Choose a microphone\n\n02   Keep a speech model ready\n\n03   Try your first dictation',18,True,justify='left').pack(anchor='w',pady=(8,23))
        row=ctk.CTkFrame(intro,fg_color='transparent'); row.pack(fill='x')
        button(row,'Set up microphone',lambda:self.navigate('microphone'),True).pack(side='left')
        button(row,'Speech models',lambda:self.navigate('models')).pack(side='left',padx=10)
        privacy=self.section('Private by default','The microphone opens only while recording. Your history stays in memory. AI cleanup is off until you choose a local model.')
        button(privacy,'Open my workspace',self.finish_onboarding,True,width=210).pack(anchor='w')
        button(privacy,'Review privacy settings',lambda:self.navigate('settings'),width=210).pack(anchor='w',pady=(10,0))

    def finish_onboarding(self):
        if self.save_settings(onboarding_done=True): self.navigate('dictation')

    @staticmethod
    def set_text(widget,text):
        widget.configure(state='normal'); widget.delete('1.0','end'); widget.insert('1.0',text); widget.configure(state='disabled')

    def copy(self,text):
        if not text: self.toast('There is no transcript to copy yet.'); return
        self.clipboard_clear(); self.clipboard_append(text)
        self.toast('Copied to the Windows clipboard.')

    def export_text(self,text):
        if not text: self.toast('There is no transcript to export yet.'); return
        filename=filedialog.asksaveasfilename(parent=self,title='Export transcript',defaultextension='.txt',
            initialfile='LightningFlow-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.txt',filetypes=[('Text file','*.txt')])
        if filename:
            try: Path(filename).write_text(text,encoding='utf-8'); self.toast('Transcript exported.')
            except OSError as exc: self.toast(str(exc))

    def page_history(self):
        views.log(self)

    def open_transcript(self,row):
        dialog=ctk.CTkToplevel(self); dialog.title('Transcript · LightningFlow'); dialog.geometry('720x590'); dialog.minsize(600,450)
        if row.get('audio_available'):dialog.geometry('720x700')
        dialog.configure(fg_color=BG)
        dialog.transient(self)
        label(dialog,'Your transcript',25,True).pack(anchor='w',padx=26,pady=(24,7))
        label(dialog,row.get('cleanup','Raw transcription'),13,muted=True).pack(anchor='w',padx=26,pady=(0,15))
        textbox=ctk.CTkTextbox(dialog,font=font(16),text_color=TEXT,fg_color=CARD,wrap='word',height=180)
        textbox.pack(fill='both',expand=True,padx=26,pady=(0,12)); self.set_text(textbox,row.get('text',''))
        if row.get('error'): label(dialog,row['error'],12,muted=True,wraplength=650,justify='left').pack(anchor='w',padx=26,pady=(0,10))
        original=ctk.CTkTextbox(dialog,font=font(13),text_color=MUTED,fg_color=CARD,wrap='word',height=90)
        original.pack(fill='x',padx=26,pady=(0,12)); self.set_text(original,'RAW TRANSCRIPT\n'+row.get('raw',row.get('text','')))
        actions=ctk.CTkFrame(dialog,fg_color='transparent'); actions.pack(fill='x',padx=26,pady=(0,24))
        button(actions,'Copy text',lambda:self.copy(row.get('text','')),True,width=110).pack(side='left')
        button(actions,'Export',lambda:self.export_text(row.get('text','')),width=90).pack(side='left',padx=8)
        if row.get('cleanup_suggestion'):
            button(actions,'Copy AI suggestion',lambda:self.copy(row['cleanup_suggestion']),width=160).pack(side='left',padx=8)
            self.set_text(original,'AI SUGGESTION · not inserted\n'+row['cleanup_suggestion']+'\n\nRAW TRANSCRIPT\n'+row.get('raw',row.get('text','')))
        if row.get('audio_available'):
            recovery=ctk.CTkFrame(dialog,fg_color='transparent');recovery.pack(fill='x',padx=26,pady=(0,15))
            button(recovery,'Save retained audio',lambda:self.send('export_audio',id=row['id']),width=165).pack(side='left')
            button(recovery,'Retranscribe on GPU',lambda:self.send('retranscribe',id=row['id']),width=175).pack(side='left',padx=8)
            label(dialog,'Retranscription updates the log for review; it does not type into another app.',12,muted=True).pack(anchor='w',padx=26,pady=(0,12))
        dialog.after(50,lambda:dark_titlebar(dialog,ctk.get_appearance_mode()=='Dark'))

    def page_models(self):
        self.heading('Speech models','Choose the local speech model used for dictation.')
        root=Path(self.settings.models_dir or paths.runtime()[2])
        descriptions={'tiny.en':'Smallest download and lowest resource use. A good baseline for short English dictation.',
                      'base.en':'A larger English model for general dictation. Compare it with your own voice.',
                      'small.en':'More parameters for difficult speech. Accuracy and speed depend on your recordings.'}
        for model,(profile,mb) in MODELS.items():
            installed=(root/model/'model.bin').is_file()
            block=self.section(profile,descriptions.get(model,'Multilingual Whisper model. Select a language below; quality depends on your recordings. Download is explicit.'))
            row=ctk.CTkFrame(block,fg_color='transparent'); row.pack(fill='x')
            label(row,model+'  ·  '+('Installed' if installed else f'About {mb} MB download'),13,muted=True).pack(side='left')
            if self.download_model==model:
                label(row,'Downloading & verifying…',13,True).pack(side='right')
                progress=ctk.CTkProgressBar(block,mode='indeterminate',progress_color=ACCENT)
                progress.pack(fill='x',pady=(15,0)); progress.start()
            elif installed:
                use=button(row,'In use' if self.settings.model==model else 'Use '+profile,lambda m=model:self.use_model(m),
                           primary=self.settings.model!=model,width=120)
                use.pack(side='right')
                if self.settings.model==model: use.configure(state='disabled')
                button(row,'Verify',lambda m=model:self.model_task('verify',m),width=85).pack(side='right',padx=8)
                if model!=self.settings.model: button(row,'Delete',lambda m=model:self.delete_model(m),width=75).pack(side='right')
            else: button(row,f'Download · {mb} MB',lambda m=model:self.download(m),True,width=180).pack(side='right')
        advanced=self.section('GPU precision','FP16 is the default. INT8 is optional and is not assumed to be faster or more accurate.')
        var=tk.StringVar(value=self.settings.compute)
        option(advanced,['float16','int8_float16','int8'],variable=var).pack(anchor='w',pady=(0,13))
        button(advanced,'Apply precision',lambda:self.save_settings(restart=True,compute=var.get()),width=170).pack(anchor='w')
        label(advanced,'Models download from Hugging Face only after you choose Download. No audio or transcripts are uploaded.',12,muted=True,wraplength=700,justify='left').pack(anchor='w',pady=(17,0))
        label(advanced,'Recognition language',12,True).pack(anchor='w',pady=(18,5))
        from ..languages import LANGUAGE_CODES
        from ..languages import LANGUAGE_NAMES
        language_choices={'Automatic detection (auto)':'auto',**{f'{LANGUAGE_NAMES.get(code,code)} ({code})':code for code in LANGUAGE_CODES}}
        language=tk.StringVar(value=next(label for label,code in language_choices.items() if code==self.settings.language))
        option(advanced,list(language_choices),variable=language,width=240,
               command=lambda value:self.save_settings(restart=True,language=language_choices[value])).pack(anchor='w')
        label(advanced,'English-only models require en. Multilingual recognition uses the same local CUDA backend; English cleanup is disabled for other languages.',12,muted=True,wraplength=720).pack(anchor='w',pady=(8,0))
        label(advanced,'Model storage',12,True).pack(anchor='w',pady=(18,5))
        label(advanced,str(root),12,muted=True,wraplength=700).pack(anchor='w',pady=(0,10))
        def choose_folder():
            folder=filedialog.askdirectory(parent=self,title='Choose model storage',mustexist=True)
            if folder and self.save_settings(restart=True,models_dir=str(Path(folder).resolve())): self.navigate('models')
        button(advanced,'Choose model folder',choose_folder,width=210).pack(anchor='w')

    def use_model(self,model):
        if self.save_settings(restart=True,model=model,language='en' if model.endswith('.en') else self.settings.language): self.navigate('models')

    def model_task(self,task,model):
        if self.download_model:
            self.toast('Wait for the current model task to finish.'); return
        try:
            python,engine,models=paths.runtime()
            worker=EngineProcess(python,engine,self.preferences.path,self.settings.models_dir or models,self.events,task,model)
            self.tasks.append(worker)
            self.download_model=model
            self.toast('Downloading model files…' if task=='download' else 'Verifying local model hashes…')
            self.navigate('models')
        except Exception as exc: self.toast(str(exc))

    def download(self,model):
        profile,mb=MODELS[model]
        if messagebox.askyesno('Download speech model',f'Download {model} (about {mb} MB) from Hugging Face?\n\nOnly model files are downloaded. No audio or transcripts are sent.',parent=self):
            self.model_task('download',model)

    def delete_model(self,model):
        if model==self.settings.model: self.toast('Choose another model before deleting the active model.'); return
        if not messagebox.askyesno('Delete local model',f'Delete {model} from this PC? You can download it again later.',parent=self): return
        try:
            root=Path(self.settings.models_dir).resolve()
            target=(root/model).resolve()
            if model not in MODELS or target.parent!=root: raise ValueError('Invalid model directory.')
            shutil.rmtree(target)
            self.navigate('models'); self.toast('Model removed from this PC.')
        except Exception as exc: self.toast(str(exc))

    def page_microphone(self):
        self.heading('Microphone','Choose your input and check the signal before you start.')
        audio=self.section('Microphone','The microphone opens only for recording or this test. No test audio is saved.')
        names=['Windows default']+[f"{item['name']}  ·  {item['id']}" for item in self.device_rows]
        selected=next((names[index+1] for index,item in enumerate(self.device_rows) if item['id']==self.settings.device),names[0])
        var=tk.StringVar(value=selected)
        option(audio,names,variable=var,width=500).pack(anchor='w',pady=(0,16))
        def apply():
            value=var.get(); ident=None if value=='Windows default' else self.device_rows[names.index(value)-1]['id']
            self.save_settings(restart=True,device=ident)
        row=ctk.CTkFrame(audio,fg_color='transparent'); row.pack(fill='x')
        button(row,'Use microphone',apply,True,width=170).pack(side='left')
        button(row,'Refresh devices',lambda:self.send('devices'),width=155).pack(side='left',padx=10)
        test=self.section('Sound check','Speak a few words. The meter shows the actual microphone signal.')
        self.refs['mic_wave']=Waveform(test,width=650,height=75); self.refs['mic_wave'].pack(fill='x',pady=(0,18))
        button(test,'Stop test' if self.mic_testing else 'Test microphone · 5 sec',self.test_mic,True,width=230).pack(anchor='w')
        label(test,'If the signal stays flat, check the input volume and Windows microphone permissions. Shared WASAPI is preferred.',12,muted=True,wraplength=730,justify='left').pack(anchor='w',pady=(18,0))
        if not self.settings.onboarding_done: button(test,'Continue to workspace',self.finish_onboarding,width=230).pack(anchor='w',pady=(18,0))

    def test_mic(self):
        if self.mic_testing:
            self.send('cancel'); return
        if self.engine_state in BUSY: self.toast('Finish recording before testing the microphone.'); return
        if self.send('mic_test'):
            self.mic_testing=True; self.navigate('microphone')
        else: self.toast('Start the local engine first.')

    def page_writing(self):
        self.heading('Writing style','Optional local cleanup, with the original words always available.')
        transcript=self.section('Your transcript','Clean removes hesitation sounds and resolves clear date, time and number corrections locally. Ambiguous changes stay as spoken. Verbatim preserves restarts and bypasses AI rewriting. The original ASR text stays in the log.')
        transcript_style=tk.StringVar(value=self.settings.transcript_style)
        option(transcript,['Clean','Verbatim'],variable=transcript_style,width=230,
               command=lambda value:self.save_settings(transcript_style=value)).pack(anchor='w')
        style=self.section('Writing style','Raw transcription is the fastest path. Cleanup is best effort and falls back to raw text when slow or uncertain.')
        draft=getattr(self,'writing_draft',{})
        mode=tk.StringVar(value=draft.get('mode',self.settings.cleanup_mode))
        provider=tk.StringVar(value=draft.get('provider',self.settings.cleanup_provider))
        model=tk.StringVar(value=draft.get('model',self.settings.cleanup_model) or (self.local_models[0] if self.local_models else 'Connect to list models'))
        label(style,'Mode',12,True).pack(anchor='w',pady=(0,6))
        option(style,list(MODES),variable=mode,width=280).pack(anchor='w',pady=(0,17))
        label(style,'Local provider',12,True).pack(anchor='w',pady=(0,6))
        row=ctk.CTkFrame(style,fg_color='transparent'); row.pack(fill='x',pady=(0,17))
        option(row,['Ollama','llama.cpp'],variable=provider,width=180).pack(side='left')
        port=entry(row,'Local port',width=100); port.insert(0,str(draft.get('port',self.settings.cleanup_port))); port.pack(side='left',padx=10)
        def connect():
            try: number=int(port.get())
            except ValueError: self.toast('Enter a valid local port.'); return
            # Read Tk state before starting the background network call.
            selected_provider=provider.get()
            self.writing_draft={'mode':mode.get(),'provider':selected_provider,'model':model.get(),'port':number,
                'budget':budget.get(),'prompt':prompt.get('1.0','end').strip()}
            def run():
                from .cleanup import list_models
                try:
                    models=list_models(selected_provider,number)
                    self.events.put({'event':'local_models','models':models,'message':f'Found {len(models)} local models. Choose one and save.'})
                except Exception: self.events.put({'event':'notice','message':'Local server unavailable. Start it and check the port.'})
            threading.Thread(target=run,daemon=True).start()
            self.toast('Connecting to the loopback server on this PC…')
        button(row,'Connect',connect,width=110).pack(side='left')
        label(style,'Installed local model',12,True).pack(anchor='w',pady=(0,6))
        choices=list(dict.fromkeys(([self.settings.cleanup_model] if self.settings.cleanup_model else [])+self.local_models))
        option(style,choices or ['Connect to list models'],variable=model,width=400).pack(anchor='w',pady=(0,17))
        label(style,'Latency budget (milliseconds)',12,True).pack(anchor='w',pady=(0,6))
        budget=entry(style,width=150); budget.insert(0,str(draft.get('budget',self.settings.cleanup_budget_ms))); budget.pack(anchor='w',pady=(0,17))
        wait=tk.BooleanVar(value=self.settings.wait_for_cleanup)
        switch=ctk.CTkSwitch(style,text='Wait for AI before insertion (adds latency)',variable=wait,font=font(13),text_color=TEXT,progress_color=ACCENT)
        switch.pack(anchor='w',pady=(0,12));keyboard_control(switch,switch.toggle)
        label(style,'Off: dictate immediately; any later AI edit is a copyable suggestion in the log. On: wait up to the latency budget.',12,muted=True,wraplength=700).pack(anchor='w',pady=(0,17))
        label(style,'Custom instructions (used only in Custom mode)',12,True).pack(anchor='w',pady=(0,6))
        prompt=ctk.CTkTextbox(style,height=90,font=font(13),fg_color=BG,text_color=TEXT,wrap='word')
        prompt.pack(fill='x',pady=(0,16)); prompt.insert('1.0',draft.get('prompt',self.settings.custom_prompt))
        def save():
            try:
                chosen=model.get()
                if mode.get()!='Raw' and (not chosen or chosen=='Connect to list models'): raise ValueError('Connect and choose an installed local model first.')
                saved=self.save_settings(cleanup_mode=mode.get(),cleanup_provider=provider.get(),cleanup_model=chosen,
                    cleanup_port=int(port.get()),cleanup_budget_ms=int(budget.get()),wait_for_cleanup=wait.get(),custom_prompt=prompt.get('1.0','end').strip())
                if saved: self.writing_draft={}
            except ValueError as exc: self.toast(str(exc))
        button(style,'Save writing preferences',save,True,width=230).pack(anchor='w')
        label(style,'Only 127.0.0.1 is supported. Enabling cleanup sends transcripts to that local server; it may use GPU memory. No cloud endpoint is offered.',12,muted=True,wraplength=720,justify='left').pack(anchor='w',pady=(18,0))
        test=self.section('Try a cleanup','Save your preferences first. Numbers, technical identifiers and key qualifications are checked; these checks cannot prove semantic equivalence.')
        sample=ctk.CTkTextbox(test,height=80,font=font(14),fg_color=BG,text_color=TEXT,wrap='word')
        sample.pack(fill='x',pady=(0,12)); sample.insert('1.0','Um, please send the project report on Friday at 3.')
        def try_cleanup():
            raw=sample.get('1.0','end').strip(); settings=Settings(**asdict(self.settings))
            def run():
                from .cleanup import enhance
                from .personalization import prepare_transcript
                try: text,note=enhance(prepare_transcript(raw,settings),settings)
                except Exception: text,note=raw,'Local cleanup unavailable; original kept.'
                self.events.put({'event':'cleanup_test','text':text,'message':note})
            threading.Thread(target=run,daemon=True).start(); self.toast('Testing your saved local cleanup settings…')
        button(test,'Test saved settings',try_cleanup,width=200).pack(anchor='w',pady=(0,12))
        self.refs['cleanup_output']=ctk.CTkTextbox(test,height=85,font=font(14),fg_color=BG,text_color=TEXT,wrap='word')
        self.refs['cleanup_output'].pack(fill='x'); self.set_text(self.refs['cleanup_output'],'The result will appear here.')

    def page_dictionary(self):
        self.heading('Dictionary','Keep names, phrases and technical terms spelled the way you prefer.')
        self.personal_vocabulary_panel()
        add=self.section('Add a preferred spelling','Matches are exact, case-insensitive words or phrases. No fuzzy guessing or chained replacements.')
        row=ctk.CTkFrame(add,fg_color='transparent'); row.pack(fill='x',pady=(0,12))
        left=ctk.CTkFrame(row,fg_color='transparent'); left.pack(side='left',fill='x',expand=True,padx=(0,10))
        right=ctk.CTkFrame(row,fg_color='transparent'); right.pack(side='left',fill='x',expand=True)
        label(left,'When I say',12,True).pack(anchor='w',pady=(0,6)); spoken=entry(left,'e.g. esp thirty two'); spoken.pack(fill='x')
        label(right,'Write',12,True).pack(anchor='w',pady=(0,6)); written=entry(right,'e.g. ESP32-S3'); written.pack(fill='x')
        def add_entry():
            item={'spoken':spoken.get().strip(),'written':written.get().strip()}
            entries=[old for old in self.settings.dictionary if old['spoken'].casefold()!=item['spoken'].casefold()]+[item]
            if self.save_settings(dictionary=entries): self.navigate('dictionary')
        button(add,'Add replacement',add_entry,True,width=190).pack(anchor='w')
        entries=self.section('Your vocabulary',f'{len(self.settings.dictionary)} exact replacements')
        if not self.settings.dictionary: label(entries,'Add a name or technical phrase you use often.',14,muted=True).pack(anchor='w')
        for index,item in enumerate(self.settings.dictionary):
            row=ctk.CTkFrame(entries,fg_color='transparent'); row.pack(fill='x',pady=7)
            label(row,item['spoken']+'  →  '+item['written'],14,wraplength=550).pack(side='left')
            def remove(i=index):
                if self.save_settings(dictionary=[row for n,row in enumerate(self.settings.dictionary) if n!=i]): self.navigate('dictionary')
            button(row,'Remove',remove,width=90).pack(side='right')

    def personal_vocabulary_panel(self):
        from .personalization import import_bank,add_correction
        profile=self.settings.voice_profile
        count=len(profile.get('vocabulary',[]))
        personal=self.section('Personal vocabulary',
            f'{count} terms · {len(profile.get("rules",[]))} context rules · {len(profile.get("corrections",[]))} saved corrections' if profile else
            'Import your version 1.0 JSON knowledge bank. It stays in your local settings and is excluded from installers and source archives.')
        enabled=tk.BooleanVar(value=self.settings.personalization_enabled)
        switch=ctk.CTkSwitch(personal,text='Use personal vocabulary for new recordings',variable=enabled,
            progress_color=ACCENT,text_color=TEXT,font=font(13),
            command=lambda:self.save_settings(personalization_enabled=enabled.get()))
        switch.pack(anchor='w',pady=(0,15))
        keyboard_control(switch,switch.toggle)
        controls=ctk.CTkFrame(personal,fg_color='transparent');controls.pack(fill='x')
        def import_profile():
            selected=filedialog.askopenfilename(parent=self,title='Import personal vocabulary',filetypes=[('JSON knowledge bank','*.json')])
            if not selected:return
            try:
                compact=Path(selected).with_name('whisper_initial_prompt.txt')
                imported=import_bank(selected,compact if compact.is_file() else None)
                if self.save_settings(voice_profile=imported,personalization_enabled=True):self.navigate('dictionary')
            except Exception as exc:self.toast(f'Vocabulary could not be imported: {exc}')
        def export_profile():
            target=filedialog.asksaveasfilename(parent=self,title='Export personal vocabulary',defaultextension='.json',initialfile='personal-vocabulary.json',filetypes=[('JSON','*.json')])
            if target:
                try:Path(target).write_text(json.dumps(profile,indent=2,ensure_ascii=False),encoding='utf-8');self.toast('Vocabulary exported locally.')
                except OSError as exc:self.toast(str(exc))
        def remove_profile():
            if messagebox.askyesno('Remove personal vocabulary?',
                    'Remove imported terms and saved contextual corrections from LightningFlow? Your original files, manual dictionary and transcript log are kept.',parent=self):
                if self.save_settings(voice_profile={},personalization_enabled=False):self.navigate('dictionary')
        button(controls,'Import knowledge bank',import_profile,True,width=195).pack(side='left')
        if profile:
            button(controls,'Export',export_profile,width=88).pack(side='left',padx=8)
            button(controls,'Remove',remove_profile,width=88).pack(side='left')
            preview=ctk.CTkTextbox(personal,height=110,font=font(13),fg_color=BG,text_color=TEXT,wrap='word')
            preview.pack(fill='x',pady=(16,0));self.set_text(preview,', '.join(profile['vocabulary']))
            label(personal,'Whisper receives a vocabulary hint capped at 192 tokens. Background facts, remembered numbers and prose instructions are excluded. Recognition improves only if the model uses these hints correctly; this is not voice training.',12,muted=True,wraplength=720,justify='left').pack(anchor='w',pady=(12,0))
            learned=self.section('Teach a correction','Save only corrections you have checked. They match exact phrases when the context phrase is present. No automatic learning or audio retention.')
            fields=[]
            for title,hint in [('Heard phrase','e.g. low so'),('Correct spelling','e.g. LOSO'),('Required context phrase','e.g. validation')]:
                label(learned,title,12,True).pack(anchor='w',pady=(6,5))
                value=entry(learned,hint,width=430);value.pack(anchor='w',pady=(0,7));fields.append(value)
            def learn():
                try:
                    updated=add_correction(self.settings.voice_profile,*[v.get() for v in fields])
                    if self.save_settings(voice_profile=updated):self.navigate('dictionary')
                except ValueError as exc:self.toast(str(exc))
            button(learned,'Save checked correction',learn,True,width=225).pack(anchor='w',pady=(8,6))
            for index,rule in enumerate(profile.get('corrections',[])):
                row=ctk.CTkFrame(learned,fg_color='transparent');row.pack(fill='x',pady=5)
                label(row,f'{rule["spoken"]} → {rule["written"]} · {rule["context"]}',12,wraplength=540).pack(side='left')
                def remove(i=index):
                    updated=json.loads(json.dumps(self.settings.voice_profile))
                    updated['corrections'].pop(i)
                    if self.save_settings(voice_profile=updated):self.navigate('dictionary')
                button(row,'Remove',remove,width=82).pack(side='right')

    def page_shortcuts(self):
        self.heading('Keyboard shortcuts','Global shortcuts work while LightningFlow stays in the background.')
        controls=self.section('Keyboard shortcuts','Use either Ctrl + Win or Ctrl + Alt plus a key for recording. Other actions use Ctrl + Alt plus a key.')
        shortcut_names={'ctrl_win':'Ctrl + Win','ctrl_alt_key':'Ctrl + Alt + key'}
        recording_shortcut=tk.StringVar(value=shortcut_names[self.settings.recording_shortcut])
        label(controls,'Recording shortcut',12,True).pack(anchor='w',pady=(0,6))
        option(controls,list(shortcut_names.values()),variable=recording_shortcut,width=240).pack(anchor='w',pady=(0,16))
        interactions={'smart':'Hold + double press','hold':'Hold to talk','toggle':'Toggle recording'}
        activation=tk.StringVar(value=interactions[self.settings.activation])
        label(controls,'Recording interaction',12,True).pack(anchor='w',pady=(0,6))
        option(controls,['Hold to talk','Hold + double press','Toggle recording'],variable=activation,width=240).pack(anchor='w',pady=(0,16))
        codes=[*range(0x70,0x88),0x1B,0x20,*range(0x41,0x5B),*range(0x30,0x3A)]
        options={key_label(code):code for code in codes}
        variables={}
        recording_key_option=None
        names={'toggle':('Start / finish recording','Toggle dictation in the focused app.'),'cancel':('Cancel recording','Discard the current recording or pending delivery.'),
               'retry':('Retry last transcript','Place your cursor first. Check for partial delivery before retrying.'),
               'save':('Export retained audio','Save the last retained recording locally.'),'quit':('Quit LightningFlow','Release the microphone, GPU model and shortcuts.')}
        for action,(title,hint) in names.items():
            row=ctk.CTkFrame(controls,fg_color='transparent'); row.pack(fill='x',pady=10)
            words=ctk.CTkFrame(row,fg_color='transparent'); words.pack(side='left')
            label(words,title,14,True).pack(anchor='w'); label(words,hint,12,muted=True,wraplength=460,justify='left').pack(anchor='w',pady=(4,0))
            variable=tk.StringVar(value=key_label(self.settings.shortcuts[action])); variables[action]=variable
            key_option=option(row,list(options),variable=variable,width=110)
            key_option.pack(side='right')
            if action=='toggle': recording_key_option=key_option
            label(row,'Ctrl + Alt +',12,muted=True).pack(side='right',padx=10)
        def update_recording_key(*_):
            recording_key_option.configure(state='disabled' if recording_shortcut.get()=='Ctrl + Win' else 'normal')
        recording_shortcut.trace_add('write',update_recording_key)
        update_recording_key()
        def apply():
            keys={name:options[var.get()] for name,var in variables.items()}
            if self.save_settings(restart=True,shortcuts=keys,recording_shortcut=next(k for k,v in shortcut_names.items() if v==recording_shortcut.get()),activation=next(k for k,v in interactions.items() if v==activation.get())): self.navigate('shortcuts')
        button(controls,'Apply shortcuts',apply,True,width=190).pack(anchor='w',pady=(18,0))
        label(controls,'Hold + double press: hold to speak, then release to finish. Double-tap within 320 ms to keep recording hands-free; tap again to stop. Either Ctrl and Windows key works. Ctrl-first chords consume the Windows key; Win-first chords pass its matching release to avoid a stuck modifier. Windows cannot report modifier-only shortcut conflicts. The Start / finish key above applies only to Ctrl + Alt + key.',12,muted=True,wraplength=720,justify='left').pack(anchor='w',pady=(17,0))

    def page_performance(self):
        self.heading('Performance','Live hardware information and timings from your own dictations.')
        device=self.section('Local inference','ASR uses CUDA. There is no automatic CPU fallback.')
        gpu=self.hardware.get('gpu',[])
        first=gpu[0] if isinstance(gpu,list) and gpu else {}
        self.refs['gpu_name']=label(device,first.get('name','Detecting NVIDIA GPU…'),24,True)
        self.refs['gpu_name'].pack(anchor='w',pady=(0,14))
        for name,value in self.hardware_values():
            row=ctk.CTkFrame(device,fg_color='transparent'); row.pack(fill='x',pady=7)
            label(row,name,13,muted=True).pack(side='left')
            self.refs['hw_'+name]=label(row,value,13,True); self.refs['hw_'+name].pack(side='right')
        button(device,'Refresh hardware',lambda:self.send('hardware'),width=190).pack(anchor='w',pady=(16,0))
        label(device,'GPU memory and utilization include other applications. They are not attributed entirely to LightningFlow.',12,muted=True,wraplength=720,justify='left').pack(anchor='w',pady=(13,0))
        timing=self.section('Your recent timings','Measured values appear after a successful dictation. In-app scratchpad timings are separate from external delivery.')
        recent=[row for row in self.history.rows if row.get('metrics')][:8]
        if not recent: label(timing,'No timing samples yet. Try a short dictation.',14,muted=True).pack(anchor='w')
        for row in recent:
            metric=row['metrics']
            label(timing,f"{row.get('destination','external').title()}  ·  {metric.get('decode_ms',0):.0f} ms decode  ·  {metric.get('end_to_end_finish_ms',metric.get('stop_to_input_ms',0)):.0f} ms finish",14).pack(anchor='w',pady=7)
        if self.diagnostics:
            logs=self.section('Recent engine diagnostics','Held in memory. Transcripts are not written to a diagnostic file.')
            for line in self.diagnostics[-5:]: label(logs,line,12,muted=True,wraplength=710,justify='left').pack(anchor='w',pady=5)

    def hardware_values(self):
        gpu=self.hardware.get('gpu',[])
        first=gpu[0] if isinstance(gpu,list) and gpu else {}
        return [('Provider','CUDA / CTranslate2'),('Speech model',self.settings.model+' · '+self.settings.compute),
            ('Processor',self.hardware.get('cpu','—')),
            ('NVIDIA driver',first.get('driver','—')),('VRAM · entire device',f"{first.get('used_mib','—')} / {first.get('total_mib','—')} MiB"),
            ('GPU utilization · entire device',str(first.get('util_percent','—'))+'%'),('System RAM',str(self.hardware.get('ram_gib','—'))+' GiB'),
            ('Engine process memory',str(self.hardware.get('engine_ram_mib','—'))+' MiB')]

    def update_hardware_labels(self):
        gpu=self.hardware.get('gpu',[])
        first=gpu[0] if isinstance(gpu,list) and gpu else {}
        if 'gpu_name' in self.refs: self.refs['gpu_name'].configure(text=first.get('name','NVIDIA GPU unavailable'))
        for name,value in self.hardware_values():
            if 'hw_'+name in self.refs: self.refs['hw_'+name].configure(text=value)

    def page_settings(self):
        self.heading('Privacy & settings','Manage local data, appearance and application behavior.')
        setup=self.section('Dictation setup','Microphone, shortcuts, speech models and diagnostics.')
        # Keep setup controls out of the everyday sidebar, one click from here.
        links=ctk.CTkFrame(setup,fg_color='transparent');links.pack(fill='x',pady=(0,2))
        links.grid_columnconfigure((0,1),weight=1)
        for index,(page,title) in enumerate((('microphone','Microphone'),('shortcuts','Keyboard shortcuts'),
                                            ('models','Speech models'),('performance','Performance'))):
            button(links,title,lambda p=page:self.navigate(p),image=icon(page),compound='left',height=44,
                   anchor='w').grid(row=index//2,column=index%2,sticky='ew',padx=(0 if index%2==0 else 8,0),pady=(0,8))
        privacy=self.section('Your data','Core dictation works offline after installation. No telemetry, account, or automatic cloud processing.')
        for title,hint,name in [('Save transcript history on this PC','Off stops saving new transcripts. Existing history stays until Clear. Saved text is encrypted for your Windows account.','history_enabled'),
                                ('Recover failed recordings after restart','Opt in to encrypted audio for completed, undelivered recordings. Up to five recordings / 1 GiB. Turning off deletes these files. Live recordings are not journaled.','retain_failed_audio'),
                                ('Show the recording indicator','A compact, non-activating status capsule above the taskbar.','overlay'),
                                ('Close to the system tray','Keep the model ready when the main window closes. Use Quit to exit.','close_to_tray')]:
            row=ctk.CTkFrame(privacy,fg_color='transparent'); row.pack(fill='x',pady=12)
            words=ctk.CTkFrame(row,fg_color='transparent'); words.pack(side='left',fill='x',expand=True)
            label(words,title,14,True).pack(anchor='w'); label(words,hint,12,muted=True,wraplength=575,justify='left').pack(anchor='w',pady=(5,0))
            variable=tk.BooleanVar(value=getattr(self.settings,name))
            switch=ctk.CTkSwitch(row,text='',width=42,variable=variable,progress_color=ACCENT,button_color=TEXT,
                command=lambda n=name,v=variable:self.save_settings(**{n:v.get()}))
            switch.pack(side='right',padx=(15,0)); keyboard_control(switch,switch.toggle)
        appearance=self.section('Appearance & recording')
        row=ctk.CTkFrame(appearance,fg_color='transparent'); row.pack(fill='x',pady=(5,14))
        label(row,'Appearance',14,True).pack(side='left')
        option(row,['Dark','Light','System'],variable=tk.StringVar(value=self.settings.theme),command=self.change_theme,width=150).pack(side='right')
        label(appearance,'Maximum recording length (seconds, 1–3600)',12,True).pack(anchor='w',pady=(0,6))
        limit=entry(appearance,width=150); limit.insert(0,str(self.settings.max_seconds)); limit.pack(anchor='w',pady=(0,12))
        def apply_limit():
            try: self.save_settings(restart=True,max_seconds=int(limit.get()))
            except ValueError: self.toast('Enter a whole number between 1 and 3600.')
        button(appearance,'Apply recording limit',apply_limit,width=200).pack(anchor='w')
        storage=self.section('Local storage','Settings, saved history and opt-in recovery audio are encrypted for your Windows account. Explicit audio/text exports are plaintext.')
        label(storage,str(paths.data_dir()),12,muted=True,wraplength=700).pack(anchor='w',pady=(0,14))
        row=ctk.CTkFrame(storage,fg_color='transparent'); row.pack(fill='x')
        button(row,'Open data folder',self.open_data_folder,width=180).pack(side='left')
        button(row,'Clear transcript history',self.clear_history,width=210).pack(side='left',padx=10)
        label(storage,'Clearing history also forgets retained recovery audio in the engine. Export anything you want to keep first.',12,muted=True,wraplength=720,justify='left').pack(anchor='w',pady=(15,0))
        actions=self.section('Application')
        startup=tk.BooleanVar(value=self.settings.startup)
        def configure_startup():
            from .windows import set_startup
            try:
                set_startup(startup.get())
                self.save_settings(startup=startup.get())
            except Exception as exc:
                startup.set(self.settings.startup); self.toast('Startup setting could not be changed: '+str(exc))
        startup_switch=ctk.CTkSwitch(actions,text='Start in the tray when I sign in',variable=startup,font=font(14),text_color=TEXT,
            progress_color=ACCENT,command=configure_startup)
        startup_switch.pack(anchor='w',pady=(3,20)); keyboard_control(startup_switch,startup_switch.toggle)
        row=ctk.CTkFrame(actions,fg_color='transparent'); row.pack(fill='x')
        button(row,'Restart local engine',self.start_engine,width=190).pack(side='left')
        button(row,'Quit LightningFlow',self.quit_app,width=185).pack(side='left',padx=10)
        label(actions,'Updates are installed explicitly from GitHub Releases. No installer runs automatically.',12,muted=True,wraplength=720).pack(anchor='w',pady=(15,10))
        update_checks=tk.BooleanVar(value=self.settings.check_updates)
        update_switch=ctk.CTkSwitch(actions,text='Check GitHub for releases at launch (opt-in network request)',variable=update_checks,
            font=font(12),text_color=TEXT,progress_color=ACCENT,command=lambda:self.save_settings(check_updates=update_checks.get()))
        update_switch.pack(anchor='w',pady=(0,12));keyboard_control(update_switch,update_switch.toggle)
        buttons=ctk.CTkFrame(actions,fg_color='transparent');buttons.pack(fill='x')
        button(buttons,'Check for updates',self.check_for_updates,width=160).pack(side='left')
        def open_releases():
            import webbrowser
            from .updates import REPOSITORY
            webbrowser.open(REPOSITORY+'/releases')
        button(buttons,'Open GitHub Releases',open_releases,width=185).pack(side='left',padx=10)
        runtime=self.section('GPU runtime','Repair missing dependencies here. This may download about 1.4 GB of Python and NVIDIA packages. Audio and transcripts stay on this PC.')
        button(runtime,'Repair GPU runtime',self.repair_runtime,width=190).pack(anchor='w')

    def repair_runtime(self):
        if self.repairing: return
        if self.engine_state in BUSY:
            self.toast('Finish or cancel dictation before repairing the runtime.'); return
        if not self.confirm_restart(): return
        if not messagebox.askyesno('Repair GPU runtime','Download and install local runtime dependencies (about 1.4 GB if missing)? No audio or transcripts are sent.',parent=self): return
        self.repairing=True
        self.retained_audio_ids.clear()
        if self.engine: self.engine.stop()
        self.engine_state='repairing'; self.status_message='Repairing GPU runtime…'
        self.toast('Installing dependencies in the background. You can keep this window open.'); self.refresh_status()
        def repair():
            import subprocess
            try:
                result=subprocess.run(['powershell.exe','-NoProfile','-File',str(paths.home()/'Setup-Runtime.ps1'),
                    '-AppRoot',str(paths.home())],capture_output=True,text=True,creationflags=0x08000000,timeout=1200)
                if result.returncode: raise RuntimeError((result.stderr or result.stdout)[-800:])
                self.events.put({'event':'runtime_repaired','ok':True})
            except Exception as exc: self.events.put({'event':'runtime_repaired','ok':False,'message':str(exc)})
        threading.Thread(target=repair,daemon=True).start()

    def change_theme(self,theme):
        if self.save_settings(theme=theme):
            ctk.set_appearance_mode(theme)
            self.theme_variable.set(theme)
            dark_titlebar(self,ctk.get_appearance_mode()=='Dark')
            self.logo.configure(image=icon('bolt',True,28))
            for navigation in self.nav.values(): keyboard_control(navigation,navigation.invoke)
            self.navigate(self.page)

    def open_data_folder(self):
        paths.data_dir().mkdir(parents=True,exist_ok=True)
        os.startfile(paths.data_dir())

    def clear_history(self):
        if messagebox.askyesno('Clear local history','Delete all transcript history and forget retained recovery audio? Export anything you want to keep first.',parent=self):
            try:
                self.history.clear(); self.last_result=None; self.send('forget')
                self.retained_audio_ids.clear()
                self.toast('Transcript history cleared on this PC.')
            except Exception as exc: self.toast('History could not be cleared: '+str(exc))

    def performance_tick(self):
        if self.closing: return
        if self.page=='performance' and self.state()!='withdrawn': self.send('hardware')
        self.after(5000,self.performance_tick)

    def show_window(self):
        self.deiconify(); self.lift()
        if self.page in ('history','performance'): self.navigate(self.page)
        self.after(50,lambda:dark_titlebar(self,ctk.get_appearance_mode()=='Dark'))

    def close_window(self):
        if self.settings.close_to_tray and self.tray and self.tray.available: self.withdraw()
        else: self.quit_app()

    def quit_app(self):
        if self.closing: return
        if self.engine_state in BUSY and not messagebox.askyesno('Quit while recording?',
            'The current recording will be cancelled. Quit LightningFlow?',parent=self): return
        if self.retained_audio_ids and not messagebox.askyesno('Quit with retained audio?',
            'Recovery audio will be forgotten. Export it from History first if you want to keep it. Quit?',parent=self): return
        self.closing=True
        self.overlay.hide()
        if self.engine: self.engine.stop()
        for task in self.tasks: task.stop()
        if self.tray: self.tray.close()
        self.history.close()
        self.withdraw()
        deadline=time.perf_counter()+5.5
        def finish():
            processes=([self.engine] if self.engine else [])+self.tasks
            if any(process.process.poll() is None for process in processes) and time.perf_counter()<deadline:
                self.after(50,finish)
            else: self.destroy()
        finish()

    def report_callback_exception(self,exc_type,exc_value,traceback):
        self.diagnostics=(self.diagnostics+[exc_type.__name__+': '+str(exc_value)[:400]])[-20:]
        self.toast('That action could not finish. Open Performance for recent diagnostics.')

def main():
    if '--self-check' in sys.argv:
        from .self_check import run
        return run()
    import hashlib
    mutex=SingleInstance('LightningFlowDesktop-'+hashlib.sha256(str(paths.data_dir()).encode()).hexdigest()[:16])
    if mutex.already:
        mutex.close(); return 0
    try:
        app=DesktopApp(hidden='--background' in sys.argv)
        def wake():
            if app.closing: return
            if mutex.requested(): app.show_window()
            app.after(150,wake)
        app.after(150,wake)
        app.mainloop()
    finally: mutex.close()
    return 0

if __name__=='__main__': raise SystemExit(main())
