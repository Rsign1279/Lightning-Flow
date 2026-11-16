import math
import time
import tkinter as tk
import customtkinter as ctk
from functools import lru_cache
from PIL import Image,ImageDraw

BG=('#FBFAF7','#19181C')
SIDE=('#F2F0EA','#151418')
CARD=('#FFFFFF','#222126')
BORDER=('#E8E4DE','#39353F')
TEXT=('#2B2732','#F5F1F8')
MUTED=('#706A78','#ACA6B5')
ACCENT=('#6C4BC3','#C5B2FA')
ACCENT_TEXT=('#FFFFFF','#241B38')
HOVER=('#5938AF','#D6C7FF')
SUCCESS=('#28704C','#94D4B0')
ERROR=('#B5374C','#F5A0B0')
TINT=('#F0EBFA','#302939')
TINT_TEXT=('#5C438F','#D8C9F8')
SELECTED=('#E8E2F1','#35303F')


def _glyph(name,ink,size):
    """Original line icons, rendered locally at 4x for crisp Windows scaling."""
    scale=4
    image=Image.new('RGBA',(24*scale,24*scale))
    draw=ImageDraw.Draw(image)
    def line(points): draw.line([(int(x*scale),int(y*scale)) for x,y in points],fill=ink,width=6,joint='curve')
    def box(bounds,r=2):draw.rounded_rectangle(tuple(int(x*scale) for x in bounds),radius=r*scale,outline=ink,width=6)
    if name in ('dictation','home'):
        line([(3,10),(12,3),(21,10)]);line([(5,9),(5,21),(10,21),(10,15),(14,15),(14,21),(19,21),(19,9)])
    elif name=='history':
        draw.arc((4*scale,4*scale,21*scale,21*scale),205,530,fill=ink,width=6)
        line([(3,4),(3,10),(9,10)]);line([(12,8),(12,13),(16,15)])
    elif name=='dictionary':
        box((4,3,20,21));line([(8,3),(8,21)]);line([(11,8),(17,8)]);line([(11,12),(16,12)])
    elif name=='writing':
        line([(5,19),(6,14),(16,4),(20,8),(10,18),(5,19)]);line([(14,6),(18,10)]);line([(14,21),(21,21)])
    elif name=='microphone':
        box((9,3,15,15),3);draw.arc((6*scale,7*scale,18*scale,18*scale),0,180,fill=ink,width=6)
        line([(12,18),(12,22)]);line([(8,22),(16,22)])
    elif name=='shortcuts':
        box((2,5,22,19));line([(6,9),(7,9)]);line([(11,9),(12,9)]);line([(16,9),(17,9)])
        line([(6,14),(8,14)]);line([(11,14),(18,14)])
    elif name in ('models','performance'):
        box((6,6,18,18));box((9,9,15,15),1)
        for n in (8,12,16):
            line([(n,2),(n,6)]);line([(n,18),(n,22)]);line([(2,n),(6,n)]);line([(18,n),(22,n)])
    elif name=='settings':
        for y,x in ((6,8),(12,16),(18,10)):
            line([(3,y),(21,y)]);draw.ellipse(((x-2)*scale,(y-2)*scale,(x+2)*scale,(y+2)*scale),fill=ink)
    elif name=='copy':box((8,8,21,21));line([(4,16),(3,16),(3,3),(16,3),(16,4)])
    elif name=='arrow':line([(4,12),(20,12)]);line([(14,6),(20,12),(14,18)])
    elif name=='check':line([(5,12),(10,17),(20,6)])
    elif name=='bolt':draw.polygon([(14*scale,2*scale),(5*scale,13*scale),(11*scale,13*scale),(9*scale,22*scale),(20*scale,9*scale),(13*scale,9*scale)],fill=ink)
    elif name=='shield':
        line([(12,2),(21,6),(20,14),(17,19),(12,22),(7,19),(4,14),(3,6),(12,2)])
        line([(8,12),(11,15),(17,9)])
    elif name=='dot':draw.ellipse((8*scale,8*scale,16*scale,16*scale),fill=ink)
    return image.resize((size,size),Image.Resampling.LANCZOS)


@lru_cache(maxsize=80)
def icon(name,selected=False,size=18):
    colors=ACCENT if selected else MUTED
    return ctk.CTkImage(light_image=_glyph(name,colors[0],size*2),dark_image=_glyph(name,colors[1],size*2),size=(size,size))


def keycaps(parent,shortcut):
    frame=ctk.CTkFrame(parent,fg_color='transparent')
    for index,key in enumerate(shortcut.split(' + ')):
        cap=ctk.CTkFrame(frame,fg_color=CARD,corner_radius=8,border_width=1,border_color=BORDER)
        cap.pack(side='left',padx=(0,6 if index<2 else 0))
        ctk.CTkLabel(cap,text=key,font=font(14,True),text_color=TEXT,width=49 if len(key)<4 else 56,height=40).pack(padx=6)
    return frame

def color(pair):
    return pair[1 if ctk.get_appearance_mode()=='Dark' else 0] if isinstance(pair,tuple) else pair

def font(size=14,bold=False): return ctk.CTkFont(family='Segoe UI Variable',size=size,weight='bold' if bold else 'normal')

def label(parent,text,size=14,bold=False,muted=False,**kwargs):
    result=ctk.CTkLabel(parent,text=text,font=font(size,bold),text_color=MUTED if muted else TEXT,anchor='w',**kwargs)
    if 'wraplength' in kwargs:
        maximum=kwargs['wraplength']
        def wrap(event):
            if result.winfo_exists() and event.width>100: result.configure(wraplength=min(maximum,event.width))
        parent.bind('<Configure>',wrap,add='+')
    return result

def button(parent,text,command,primary=False,**kwargs):
    options=dict(height=38,corner_radius=9,font=font(13,True),fg_color=ACCENT if primary else 'transparent',
                 text_color=ACCENT_TEXT if primary else TEXT,hover_color=HOVER if primary else BORDER,
                 border_width=0 if primary else 1,border_color=BORDER)
    options.update(kwargs)
    result=ctk.CTkButton(parent,text=text,command=command,**options)
    result._canvas.configure(takefocus=True)
    result._canvas.bind('<Return>',lambda _:result.invoke())
    result._canvas.bind('<space>',lambda _:result.invoke())
    result._canvas.bind('<FocusIn>',lambda _:result.configure(border_width=2,border_color=ACCENT))
    result._canvas.bind('<FocusOut>',lambda _:result.configure(border_width=0 if primary else 1,border_color=BORDER))
    return result

def card(parent,**kwargs):
    options=dict(fg_color=CARD,corner_radius=16,border_width=1,border_color=BORDER);options.update(kwargs)
    return ctk.CTkFrame(parent,**options)

def entry(parent,placeholder='',**kwargs):
    options=dict(height=40,corner_radius=9,font=font(),fg_color=CARD,border_color=BORDER,text_color=TEXT)
    options.update(kwargs)
    result=ctk.CTkEntry(parent,placeholder_text=placeholder,**options)
    result._entry.bind('<FocusIn>',lambda _:result.configure(border_color=ACCENT),add='+')
    result._entry.bind('<FocusOut>',lambda _:result.configure(border_color=BORDER),add='+')
    return result

def keyboard_control(widget,invoke=None):
    widget._canvas.configure(takefocus=True,highlightthickness=0,highlightbackground=color(ACCENT),highlightcolor=color(ACCENT))
    widget._canvas.bind('<FocusIn>',lambda _:widget._canvas.configure(highlightthickness=1),add='+')
    widget._canvas.bind('<FocusOut>',lambda _:widget._canvas.configure(highlightthickness=0),add='+')
    if invoke:
        widget._canvas.bind('<Return>',lambda _:invoke())
        widget._canvas.bind('<space>',lambda _:invoke())

def option(parent,values,variable=None,command=None,**kwargs):
    options=dict(height=38,font=font(13),dropdown_font=font(13),fg_color=CARD,button_color=BORDER,
                 button_hover_color=SIDE,text_color=TEXT,dropdown_fg_color=CARD,dropdown_text_color=TEXT)
    options.update(kwargs)
    result=ctk.CTkOptionMenu(parent,values=values,variable=variable,command=command,**options)
    result._canvas.configure(takefocus=True)
    keyboard_control(result)
    def change(direction):
        index=values.index(result.get()) if result.get() in values else 0
        value=values[(index+direction)%len(values)]
        result.set(value)
        if command: command(value)
    result._canvas.bind('<Down>',lambda _:change(1))
    result._canvas.bind('<Up>',lambda _:change(-1))
    return result

class Waveform(tk.Canvas):
    def __init__(self,parent,width=420,height=58,**kwargs):
        super().__init__(parent,width=width,height=height,bg=color(CARD),highlightthickness=0,**kwargs)
        self.level=0.
        self.target=0.
        self.phase=0.
        self.active=False
        self.processing=False
        self.barcolor=None
        self.items=[]
        self.job=None
        self.last=time.perf_counter()
        self.sample_at=0.
        self.motion=animations_enabled()
        self.bind('<Destroy>',self._destroy,add='+')
        self.bind('<Configure>',lambda _:self.draw())
        self.draw()

    def set(self,level,active=False):
        self.target=max(0,min(1,float(level)))
        self.sample_at=time.perf_counter()
        self.active=active
        if not active: self.target=0
        if not active: self.level=0
        if not self.motion: self.level=self.target
        self.draw()
        self._schedule()

    def set_processing(self,value):
        self.processing=value
        self._schedule()

    def _destroy(self,event):
        if event.widget is self and self.job:
            self.after_cancel(self.job)
            self.job=None

    def _schedule(self):
        if self.job is None and self.motion and (self.active or self.processing or self.level>.002):
            self.job=self.after(16,self._frame)

    def _frame(self):
        self.job=None
        now=time.perf_counter()
        dt=min(.05,max(.001,now-self.last)); self.last=now
        target=self.target if now-self.sample_at<.18 else 0.
        tau=.012 if target>self.level else .070
        self.level+=(target-self.level)*(1-math.exp(-dt/tau))
        self.phase+=dt*9
        if self.winfo_viewable():
            self.draw()
            self._schedule()

    def draw(self):
        width=max(50,self.winfo_width() if self.winfo_width()>1 else int(self['width']))
        height=max(10,self.winfo_height() if self.winfo_height()>1 else int(self['height']))
        bars=max(10,min(48,width//8))
        while len(self.items)>bars: self.delete(self.items.pop())
        while len(self.items)<bars:
            self.items.append(self.create_line(0,0,0,0,width=3,capstyle='round'))
        gap=width/bars
        for index,item in enumerate(self.items):
            amplitude=.22+.78*abs(math.sin(index*.67+self.phase))
            span=max(3,self.level*(height-5)*amplitude)
            if self.processing:
                span=3+(height*.48)*max(0,math.sin(index*.26-self.phase*1.8))**3 if self.motion else 5
            x=index*gap+gap/2
            self.coords(item,x,height/2-span/2,x,height/2+span/2)
            self.itemconfigure(item,fill=self.barcolor or color(ACCENT if self.active or self.processing else BORDER))


def animations_enabled():
    try:
        import ctypes as C
        enabled=C.c_int(1)
        C.windll.user32.SystemParametersInfoW(0x1042,0,C.byref(enabled),0)
        return bool(enabled.value)
    except Exception: return True

class RecordingOverlay(ctk.CTkToplevel):
    def __init__(self,root):
        super().__init__(root)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes('-topmost',True)
        self.configure(fg_color='#010101')
        self.attributes('-transparentcolor','#010101')
        self.geometry('294x64')
        self.title('LightningFlow recording')
        self.pill=ctk.CTkFrame(self,fg_color='#242128',corner_radius=24,border_width=1,border_color='#4B4356')
        self.pill.pack(fill='both',expand=True,padx=3,pady=3)
        words=ctk.CTkFrame(self.pill,fg_color='transparent')
        words.pack(side='left',padx=(17,7),pady=8)
        self.heading=ctk.CTkLabel(words,text='Listening',text_color='#FAF7FF',font=font(13,True),anchor='w',height=20)
        self.heading.pack(anchor='w')
        self.hint=ctk.CTkLabel(words,text='Release to finish',text_color='#BFB5CD',font=font(11),anchor='w',height=17)
        self.hint.pack(anchor='w')
        self.wave=Waveform(self.pill,width=83,height=27)
        self.wave.configure(bg='#242128')
        self.wave.barcolor='#D2BFFA'
        self.wave.pack(side='right',padx=(2,16))
        self.visible=False
        self.kind=''
        self.gesture='held'
        self.fade_job=None
        self.motion=animations_enabled()
        self.period=False
        self.update_idletasks()
        from .windows import nonactivating
        nonactivating(self)

    def show_state(self,state,shortcut):
        from .windows import nonactivating
        self.kind=state
        self.heading.configure(text={'starting':'Getting ready','recording':'Recording locked' if self.gesture=='locked' else 'Listening',
                                     'paused':'Keep recording?', 'processing':'Transcribing',
                                     'enhancing':'Cleaning up locally'}.get(state,state.title()))
        self.hint.configure(text='Press shortcut to finish' if self.gesture=='locked' and state=='recording' else
                            'Tap again to lock' if state=='paused' else 'Release to finish' if state in ('starting','recording') else 'Processing on your GPU')
        self.wave.set_processing(state in ('processing','enhancing','starting'))
        if state not in ('recording','starting'): self.wave.set(0,False)
        if not self.visible:
            self.visible=True
            if self.motion and not self.period:
                try:
                    import ctypes as C
                    self.period=C.windll.winmm.timeBeginPeriod(1)==0
                except Exception: pass
            self.x=(self.winfo_screenwidth()-294)//2
            self.y=self.winfo_screenheight()-142
            self.geometry(f'294x64+{self.x}+{self.y}')
            # Recording feedback is visible on its first paint, not after a
            # fade from zero. The remaining small transition is two frames.
            self.attributes('-alpha',.85 if self.motion else 1.)
            nonactivating(self)
            self.deiconify()
            self._fade(1.)
        nonactivating(self)

    def set_gesture(self,state):
        self.gesture=state

    def _fade(self,target):
        if self.fade_job: self.after_cancel(self.fade_job); self.fade_job=None
        if not self.motion:
            self.attributes('-alpha',target)
            if not target: self._hidden()
            return
        current=float(self.attributes('-alpha'))
        value=current+(target-current)*.70
        if abs(value-target)<.025:
            self.attributes('-alpha',target)
            if not target: self._hidden()
            return
        self.attributes('-alpha',value)
        self.fade_job=self.after(16,lambda:self._fade(target))

    def hide(self):
        if not self.visible: return
        self.visible=False
        self.wave.set_processing(False)
        self.wave.set(0,False)
        self._fade(0.)

    def _hidden(self):
        self.withdraw()
        if self.period:
            import ctypes as C
            C.windll.winmm.timeEndPeriod(1)
            self.period=False
