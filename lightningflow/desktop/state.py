"""Validated preferences and opt-in local transcript storage; no GUI imports."""
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sqlite3
import uuid
from . import storage

MODELS = {'tiny.en':('Fast · English',75), 'base.en':('Balanced · English',145), 'small.en':('Accurate · English',465),
          'tiny':('Fast · Multilingual',75),'base':('Balanced · Multilingual',145),'small':('Accurate · Multilingual',465)}
MODES = ('Raw', 'Smart cleanup', 'Professional', 'Casual', 'Technical', 'Custom')
DEFAULT_KEYS = {'toggle':0x77,'cancel':0x1B,'retry':0x78,'quit':ord('Q'),'save':ord('S')}

@dataclass
class Settings:
    theme: str = 'Light'
    model: str = 'tiny.en'
    compute: str = 'float16'
    language: str = 'en'
    device: int | None = None
    models_dir: str = ''
    history_enabled: bool = False
    overlay: bool = True
    close_to_tray: bool = True
    onboarding_done: bool = False
    max_seconds: int = 120
    activation: str = 'hold'
    recording_shortcut: str = 'ctrl_alt_key'
    controls_revision: int = 2
    startup: bool = False
    shortcuts: dict = field(default_factory=lambda:dict(DEFAULT_KEYS))
    dictionary: list = field(default_factory=list)
    voice_profile: dict = field(default_factory=dict)
    personalization_enabled: bool = False
    transcript_style: str = 'Clean'
    cleanup_mode: str = 'Raw'
    cleanup_provider: str = 'Ollama'
    cleanup_model: str = ''
    cleanup_port: int = 11434
    cleanup_budget_ms: int = 500
    wait_for_cleanup: bool = False
    live_preview: bool = True
    check_updates: bool = False
    custom_prompt: str = ''

    def validate(self):
        if self.theme not in ('Dark','Light','System'): raise ValueError('Choose Dark, Light or System theme.')
        if self.model not in MODELS: raise ValueError('Choose an available Whisper model.')
        from ..languages import LANGUAGE_CODES
        if self.language not in ('auto',*LANGUAGE_CODES):raise ValueError('Choose a supported language code or auto.')
        if self.model.endswith('.en') and self.language!='en':raise ValueError('Choose a multilingual model before changing language.')
        if self.compute not in ('float16','int8_float16','int8'): raise ValueError('Invalid GPU precision.')
        if self.device is not None and (not isinstance(self.device,int) or self.device<0): raise ValueError('Invalid microphone device.')
        if not 1<=int(self.max_seconds)<=3600: raise ValueError('Recording limit must be 1–3600 seconds.')
        if self.activation not in ('smart','toggle','hold'): raise ValueError('Choose hold + double press, toggle, or hold-to-talk.')
        if self.recording_shortcut not in ('ctrl_alt_key','ctrl_win'): raise ValueError('Choose Ctrl + Win or Ctrl + Alt + key.')
        if set(self.shortcuts)!=set(DEFAULT_KEYS): raise ValueError('Every shortcut action must be configured.')
        values=list(self.shortcuts.values())
        if len(set(values))!=len(values) or any(not isinstance(v,int) or not 1<=v<=255 for v in values):
            raise ValueError('Shortcuts must use distinct valid keys.')
        if self.cleanup_mode not in MODES: raise ValueError('Invalid cleanup mode.')
        if self.transcript_style not in ('Verbatim','Clean'): raise ValueError('Choose Verbatim or Clean transcript.')
        from .personalization import validate_profile
        validate_profile(self.voice_profile)
        if self.cleanup_provider not in ('Ollama','llama.cpp'): raise ValueError('Choose a local AI provider.')
        if self.cleanup_mode!='Raw' and (not self.cleanup_model.strip() or self.cleanup_model=='Connect to list models'):
            raise ValueError('Choose an installed local model before enabling cleanup.')
        if not 1024<=int(self.cleanup_port)<=65535: raise ValueError('Local port must be between 1024 and 65535.')
        if not 100<=int(self.cleanup_budget_ms)<=2000: raise ValueError('Cleanup budget must be 100–2000 ms.')
        if len(self.dictionary)>500: raise ValueError('Dictionary supports up to 500 exact replacements.')
        for entry in self.dictionary:
            if set(entry)!={'spoken','written'} or not all(isinstance(v,str) and 0<len(v.strip())<=120 for v in entry.values()):
                raise ValueError('Each dictionary entry needs a spoken and written phrase (1–120 characters).')
        for name in ('history_enabled','overlay','close_to_tray','onboarding_done','startup','personalization_enabled','wait_for_cleanup','live_preview','check_updates'):
            if not isinstance(getattr(self,name),bool): raise ValueError(f'{name} must be a boolean.')
        return self

class Preferences:
    def __init__(self, path):
        self.path=Path(path)
        self.error=''

    def load(self):
        if not self.path.exists(): return Settings()
        try:
            data=storage.loads(self.path.read_text(encoding='utf-8'))
            if data.get('controls_revision',0)<2:
                data['activation']='hold'
                data['controls_revision']=2
            return Settings(**{k:v for k,v in data.items() if k in Settings.__dataclass_fields__}).validate()
        except Exception as exc:
            self.error=f'Preferences could not be read. Defaults are in use: {exc}'
            return Settings()

    def save(self, settings):
        settings.validate()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.error and self.path.exists():
            import shutil
            backup=self.path.with_name(self.path.stem+'-unreadable-'+datetime.now().strftime('%Y%m%d%H%M%S')+'.json')
            shutil.copy2(self.path,backup)
            self.error=''
        temporary=self.path.with_suffix('.tmp')
        with temporary.open('w',encoding='utf-8') as stream:
            stream.write(storage.dumps(asdict(settings)))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,self.path)

class History:
    def __init__(self,path,enabled=False):
        self.path=Path(path)
        self.rows=[]
        self.connection=None
        self.error=''
        try: self.configure(enabled)
        except (sqlite3.Error,ValueError,KeyError,OSError) as exc:
            if self.connection: self.connection.close()
            self.connection=None
            self.error='Local history storage is unavailable. This session is not saved.'

    def configure(self,enabled):
        if not enabled:
            if self.connection: self.connection.close()
            self.connection=None
            return
        if self.connection: return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.connection=sqlite3.connect(self.path)
        self.connection.execute('PRAGMA secure_delete=ON')
        self.connection.execute('CREATE TABLE IF NOT EXISTS transcripts (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        stored=[];migrations=[]
        for item in self.connection.execute('SELECT id,payload FROM transcripts ORDER BY rowid DESC LIMIT 200'):
            try:
                value=storage.loads(item[1])
                if isinstance(value,dict) and 'id' in value and 'created' in value:
                    value['audio_available']=False  # Audio is never persisted in history.
                    stored.append(value)
                    if not storage.protected(item[1]):migrations.append((storage.dumps(value),item[0]))
            except ValueError:
                self.error='Some history entries could not be read. Their stored records were left unchanged.'
                continue
        if migrations:self.connection.executemany('UPDATE transcripts SET payload=? WHERE id=?',migrations)
        existing={row['id'] for row in self.rows}
        self.rows.extend(row for row in stored if row['id'] not in existing)
        self.rows.sort(key=lambda row:row['created'],reverse=True)
        # Enabling the log also saves the current session, not only future
        # results. The user should not lose the visible log on the next restart.
        for row in self.rows[:200]:
            self.connection.execute('INSERT OR IGNORE INTO transcripts VALUES (?,?)',(row['id'],storage.dumps(row)))
        self.connection.commit()
        if migrations:self.connection.execute('VACUUM')

    def add(self,row):
        row=dict(row)
        row.setdefault('id',uuid.uuid4().hex)
        row.setdefault('created',datetime.now().astimezone().isoformat(timespec='seconds'))
        self.rows=[item for item in self.rows if item['id']!=row['id']]
        self.rows.insert(0,row)
        self.rows=self.rows[:200]
        if self.connection:
            try:
                self.connection.execute('INSERT OR REPLACE INTO transcripts VALUES (?,?)',(row['id'],storage.dumps(row)))
                self.connection.execute('DELETE FROM transcripts WHERE rowid NOT IN (SELECT rowid FROM transcripts ORDER BY rowid DESC LIMIT 200)')
                self.connection.commit()
            except (sqlite3.Error,OSError,ValueError):
                self.connection.close(); self.connection=None
                self.error='History could not be saved. The transcript is kept in this session.'
        return row

    def delete(self,ident):
        self.rows=[row for row in self.rows if row['id']!=ident]
        if self.connection:
            self.connection.execute('DELETE FROM transcripts WHERE id=?',(ident,))
            self.connection.commit()

    def clear(self):
        self.rows.clear()
        connection=self.connection or (sqlite3.connect(self.path) if self.path.exists() else None)
        if connection:
            try:
                connection.execute('PRAGMA secure_delete=ON')
                connection.execute('DELETE FROM transcripts')
                connection.commit()
                connection.execute('VACUUM')
            finally:
                if connection is not self.connection: connection.close()

    def close(self):
        if self.connection: self.connection.close()
        self.connection=None

def apply_dictionary(text, entries):
    # One longest-first, exact word/phrase pass. Replacements cannot cascade.
    mapping={entry['spoken'].strip().casefold():entry['written'].strip() for entry in entries}
    if not mapping: return text
    pattern=r'(?<!\w)('+'|'.join(re.escape(key) for key in sorted(mapping,key=len,reverse=True))+r')(?!\w)'
    return re.sub(pattern,lambda match:mapping[match.group().casefold()],text,flags=re.IGNORECASE)

def key_label(vk):
    if 0x70<=vk<=0x87: return f'F{vk-0x6F}'
    return {0x1B:'Esc',0x20:'Space'}.get(vk,chr(vk) if 0x30<=vk<=0x5A else f'VK {vk:#x}')
