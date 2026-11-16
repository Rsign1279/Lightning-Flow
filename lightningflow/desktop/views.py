"""Desktop presentation only. Capture, shortcuts and GPU inference stay separate."""
from datetime import datetime
import customtkinter as ctk
from .state import MODELS
from .widgets import *


def totals(app):
    today=datetime.now().date()
    rows=[]
    for row in app.history.rows:
        try:
            if datetime.fromisoformat(row['created']).astimezone().date()==today and row.get('text'):rows.append(row)
        except (ValueError,KeyError):pass
    return sum(len(row['text'].split()) for row in rows),len(rows)


def home(app):
    hint={'hold':'Hold to speak. Release to finish. Quick taps do nothing.',
          'smart':'Hold to speak. Double-tap for hands-free dictation. Tap again to finish.',
          'toggle':'Tap your shortcut to start. Tap again to finish.'}[app.settings.activation]
    app.heading('Welcome back',hint)
    summary=ctk.CTkFrame(app.content,fg_color='transparent')
    summary.pack(fill='x',padx=10,pady=(0,22))
    words,count=totals(app)
    app.refs['stat_words']=label(summary,f'{words:,} words today',13,True)
    app.refs['stat_words'].pack(side='left')
    label(summary,' / ',13,muted=True).pack(side='left',padx=9)
    app.refs['stat_count']=label(summary,f'{count} dictation'+('' if count==1 else 's'),13,muted=True)
    app.refs['stat_count'].pack(side='left')
    label(summary,'Local workspace',12,muted=True,image=icon('shield'),compound='left',padx=6).pack(side='right')

    hero=card(app.content,fg_color=TINT,border_width=0,corner_radius=18)
    hero.pack(fill='x',padx=8,pady=(0,22))
    hero.grid_columnconfigure(0,weight=1)
    left=ctk.CTkFrame(hero,fg_color='transparent')
    left.grid(row=0,column=0,sticky='nsew',padx=(25,12),pady=23)
    label(left,'VOICE DICTATION',10,True,True).pack(anchor='w')
    app.refs['state_text']=label(left,app.status_message,21,True,wraplength=380,justify='left')
    app.refs['state_text'].pack(anchor='w',pady=(6,5))
    label(left,'Place your cursor, hold your shortcut, and speak.',13,muted=True,wraplength=360,justify='left').pack(anchor='w')
    actions=ctk.CTkFrame(left,fg_color='transparent');actions.pack(fill='x',pady=(18,0))
    app.refs['record']=button(actions,'Try in this window',app.practice,True,width=164,image=icon('microphone',True),compound='left')
    # The primary button uses an original white microphone mark for contrast.
    app.refs['record'].configure(image=ctk.CTkImage(light_image=_white_microphone(),dark_image=_dark_microphone(),size=(16,16)))
    app.refs['record'].pack(side='left')
    app.refs['record_cancel']=button(actions,'Cancel',lambda:app.send('cancel'),width=75,border_width=0)
    app.refs['record_cancel'].pack(side='left',padx=(8,0))
    right=ctk.CTkFrame(hero,fg_color='transparent')
    right.grid(row=0,column=1,sticky='e',padx=(8,26),pady=20)
    label(right,'HOLD YOUR SHORTCUT',10,True,True).pack(anchor='center',pady=(0,9))
    keycaps(right,app.shortcut()).pack()
    meter=ctk.CTkFrame(right,fg_color='transparent');meter.pack(fill='x',pady=(14,0))
    app.refs['wave']=Waveform(meter,width=151,height=24)
    app.refs['wave'].configure(bg=color(TINT))
    app.refs['wave'].pack(side='left',padx=(0,8))
    app.refs['timer']=label(meter,'00:00',12,muted=True)
    app.refs['timer'].pack(side='right')

    latest=card(app.content,corner_radius=16)
    latest.pack(fill='x',padx=8,pady=(0,22))
    top=ctk.CTkFrame(latest,fg_color='transparent');top.pack(fill='x',padx=23,pady=(18,9))
    label(top,'Latest transcript',16,True).pack(side='left')
    button(top,'Copy',lambda:app.copy(app.current_text()),width=72,height=30,border_width=0,
           image=icon('copy'),compound='left').pack(side='right')
    button(top,'Export',lambda:app.export_text(app.current_text()),width=65,height=30,border_width=0).pack(side='right',padx=3)
    app.refs['transcript']=ctk.CTkTextbox(latest,height=126,fg_color='transparent',corner_radius=0,
        border_width=0,text_color=TEXT,font=font(17),wrap='word',spacing3=5)
    app.refs['transcript'].pack(fill='x',padx=19,pady=(0,14))
    text=app.partial or (app.last_result or {}).get('text','')
    app.set_text(app.refs['transcript'],text or 'Your next dictation will appear here.')
    if not text:app.refs['transcript'].configure(text_color=MUTED)
    ctk.CTkFrame(latest,height=1,fg_color=BORDER).pack(fill='x',padx=23)
    footer=ctk.CTkFrame(latest,fg_color='transparent');footer.pack(fill='x',padx=23,pady=13)
    app.refs['recovery']=label(footer,'',11,muted=True)
    app.refs['recovery'].pack(side='left')
    app.refs['stat_decode']=label(footer,'',11,muted=True)
    app.refs['stat_decode'].pack(side='right')

    recent=ctk.CTkFrame(app.content,fg_color='transparent')
    recent.pack(fill='x',padx=10,pady=(0,12))
    label(recent,'Recent dictations',15,True).pack(side='left')
    button(recent,'View log',lambda:app.navigate('history'),width=95,height=30,border_width=0,
           image=icon('arrow'),compound='right').pack(side='right')
    app.refs['home_recent']=ctk.CTkFrame(app.content,fg_color='transparent')
    app.refs['home_recent'].pack(fill='x',padx=10)
    app._home_row_widgets=[]
    for index in range(2):
        row=ctk.CTkFrame(app.refs['home_recent'],fg_color='transparent')
        row.grid_columnconfigure(1,weight=1)
        stamp=label(row,'',11,muted=True,width=72);stamp.grid(row=0,column=0,sticky='w',padx=(0,14))
        text_label=label(row,'',13,wraplength=500);text_label.grid(row=0,column=1,sticky='w')
        action=button(row,'Open',lambda i=index:app.open_transcript(app._home_items[i]),width=62,height=30,border_width=0)
        action.grid(row=0,column=2,padx=(8,0))
        app._home_row_widgets.append((row,stamp,text_label))
    update_home(app)


def _white_microphone():
    from .widgets import _glyph
    return _glyph('microphone','#FFFFFF',32)


def _dark_microphone():
    from .widgets import _glyph
    return _glyph('microphone','#241B38',32)


def update_home(app):
    result=app.last_result or {}
    if 'transcript' in app.refs:
        text=result.get('text','')
        app.set_text(app.refs['transcript'],text or 'Your next dictation will appear here.')
        app.refs['transcript'].configure(text_color=TEXT if text else MUTED)
    words,count=totals(app)
    if 'stat_words' in app.refs:app.refs['stat_words'].configure(text=f'{words:,} words today')
    if 'stat_count' in app.refs:app.refs['stat_count'].configure(text=f'{count} dictation'+('' if count==1 else 's'))
    metrics=result.get('metrics',{})
    if 'stat_decode' in app.refs:app.refs['stat_decode'].configure(text=f"{metrics['decode_ms']:.0f} ms decode" if 'decode_ms' in metrics else '')
    if 'recovery' in app.refs:
        message='Retained · check the target before retrying' if result.get('text') and not result.get('delivered') else 'Saved to your local log' if app.history.connection else 'This session only'
        app.refs['recovery'].configure(text=message)
    app._home_items=[row for row in app.history.rows if row.get('text') and row.get('id')!=result.get('id')][:2]
    for index,(row,stamp,text_label) in enumerate(getattr(app,'_home_row_widgets',[])):
        if index>=len(app._home_items):row.pack_forget();continue
        item=app._home_items[index]
        try:date=datetime.fromisoformat(item['created']).strftime('%I:%M %p').lstrip('0')
        except (ValueError,KeyError):date=''
        stamp.configure(text=date)
        preview=' '.join(item.get('text','').split())
        text_label.configure(text=preview[:82]+('…' if len(preview)>82 else ''))
        row.pack(fill='x',pady=(0,6))


def log(app):
    app.heading('Your dictations','Search, copy or revisit your transcripts.')
    top=ctk.CTkFrame(app.content,fg_color='transparent');top.pack(fill='x',padx=8,pady=(0,12))
    search=entry(top,'Search your transcripts…',height=42)
    search.pack(side='left',fill='x',expand=True)
    label(top,'Saved locally' if app.history.connection else 'Session only',12,muted=True,
          image=icon('shield'),compound='left',padx=8).pack(side='right',padx=(18,0))
    pager=ctk.CTkFrame(app.content,fg_color='transparent');pager.pack(fill='x',padx=8,pady=(0,12))
    count_label=label(pager,'',12,muted=True);count_label.pack(side='left')
    rows=ctk.CTkFrame(app.content,fg_color='transparent');rows.pack(fill='x',padx=8)
    state={'offset':0,'items':[]}
    page_size=10
    pool=[]
    # Reuse a bounded set of cards. Rebuilding a hundred rounded cards and
    # destroying them on navigation can stall Tk for several seconds.
    for _ in range(page_size):
        wrapper=ctk.CTkFrame(rows,fg_color='transparent')
        wrapper.grid_columnconfigure(0,weight=1)
        group_label=label(wrapper,'',12,True,True)
        group_label.grid(row=0,column=0,sticky='w',pady=(8,12))
        block=card(wrapper,corner_radius=13);block.grid(row=1,column=0,sticky='ew')
        block.grid_columnconfigure(1,weight=1)
        clock=label(block,'',11,muted=True,width=72)
        clock.grid(row=0,column=0,sticky='nw',padx=(20,10),pady=20)
        body=ctk.CTkFrame(block,fg_color='transparent');body.grid(row=0,column=1,sticky='ew',pady=17,padx=(0,14))
        text=label(body,'',15,wraplength=580,justify='left');text.pack(anchor='w')
        status=label(body,'',10,muted=True);status.pack(anchor='w',pady=(9,0))
        actions=ctk.CTkFrame(block,fg_color='transparent');actions.grid(row=0,column=2,sticky='ne',padx=(0,13),pady=14)
        copy=button(actions,'Copy',lambda:None,width=64,height=30,border_width=0);copy.pack()
        open_button=button(actions,'Open',lambda:None,width=64,height=30,border_width=0);open_button.pack(pady=(3,0))
        pool.append(dict(wrapper=wrapper,group=group_label,clock=clock,text=text,status=status,copy=copy,open=open_button))
    empty=card(rows,fg_color=TINT,border_width=0)
    empty_title=label(empty,'',19,True);empty_title.pack(anchor='w',padx=25,pady=(28,7))
    empty_hint=label(empty,'',13,muted=True);empty_hint.pack(anchor='w',padx=25,pady=(0,28))
    def render(reset=False):
        if reset:state['offset']=0
        query=search.get().strip().casefold()
        matches=[row for row in app.history.rows if query in row.get('text','').casefold()]
        state['offset']=min(state['offset'],max(0,((len(matches)-1)//page_size)*page_size))
        offset=state['offset'];items=matches[offset:offset+page_size];state['items']=items
        if not items:
            empty_title.configure(text='No matching dictations' if query else 'Your log starts with your next dictation')
            empty_hint.configure(text='Try another search.' if query else 'Hold '+app.shortcut()+', speak, then release.')
            empty.pack(fill='x',pady=(0,16))
        else:empty.pack_forget()
        current=None
        for index,widgets in enumerate(pool):
            if index>=len(items):widgets['wrapper'].pack_forget();continue
            item=items[index]
            try:
                stamp=datetime.fromisoformat(item['created']).astimezone()
                days=(datetime.now().date()-stamp.date()).days
                group='Today' if days==0 else 'Yesterday' if days==1 else stamp.strftime('%B %d, %Y')
                clock=stamp.strftime('%I:%M %p').lstrip('0')
            except (ValueError,KeyError):group='Earlier';clock=''
            widgets['group'].configure(text=group)
            if group!=current:widgets['group'].grid()
            else:widgets['group'].grid_remove()
            current=group
            widgets['clock'].configure(text=clock)
            widgets['text'].configure(text=item.get('text','')[:420] or 'No speech detected.')
            widgets['status'].configure(text='Inserted' if item.get('delivered') else 'Retained for recovery')
            widgets['copy'].configure(command=lambda row=item:app.copy(row.get('text','')))
            widgets['open'].configure(command=lambda row=item:app.open_transcript(row))
            widgets['wrapper'].pack(fill='x',pady=(0,9))
        count_label.configure(text=f'{offset+1}–{offset+len(items)} of {len(matches)} dictations' if items else '0 dictations')
        previous.configure(state='normal' if offset else 'disabled')
        following.configure(state='normal' if offset+page_size<len(matches) else 'disabled')
    def move(direction):
        state['offset']=max(0,state['offset']+direction*page_size)
        render()
        app.content._parent_canvas.yview_moveto(0)
    following=button(pager,'Next',lambda:move(1),width=68,height=30,border_width=0)
    following.pack(side='right')
    previous=button(pager,'Previous',lambda:move(-1),width=85,height=30,border_width=0)
    previous.pack(side='right',padx=(0,6))
    search.bind('<KeyRelease>',lambda _:render(reset=True))
    app.refs.update(log_refresh=render,log_next=lambda:move(1),log_previous=lambda:move(-1),
                    log_search=search,log_state=state,log_widgets=pool)
    render()
