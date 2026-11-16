"""Opt-in failed-recording recovery. Disk work never runs on the input hook.

Float32 samples are preserved exactly in independently DPAPI-protected chunks.
Only a completed manifest makes a recording visible; unfinished saves are not
treated as recoverable recordings. This does not journal a live microphone.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import threading
import time

import numpy as np
from . import storage

FRAMES_PER_CHUNK=250
MAX_FRAMES=180000
MAX_BYTES=1024**3
ID=re.compile(r'^[0-9a-f]{32}$')


class RecoveryStore:
    def __init__(self,root):self.root=Path(root)

    def folder(self,ident):
        if not isinstance(ident,str) or not ID.fullmatch(ident):raise ValueError('Invalid recovery recording identifier')
        folder=self.root/ident
        if folder.resolve().parent!=self.root.resolve():raise ValueError('Recovery path leaves its storage directory')
        return folder

    def remove(self,ident):
        folder=self.folder(ident)
        if folder.exists():
            if folder.is_symlink():raise ValueError('Recovery directories cannot be links')
            shutil.rmtree(folder)

    def clear(self):
        storage.clear_recovery(self.root)

    def metadata(self,ident):
        path=self.folder(ident)/'manifest.json'
        if path.stat().st_size>storage.LIMIT:raise ValueError('Recovery manifest exceeds its limit')
        text=path.read_text(encoding='utf-8')
        if not storage.protected(text):raise ValueError('Recovery manifest is not protected')
        value=storage.loads(text)
        frames=value.get('frames',0)
        if (value.get('id')!=ident or type(frames) is not int or not 0<frames<=MAX_FRAMES
                or len(value.get('chunks',[]))!=(frames+FRAMES_PER_CHUNK-1)//FRAMES_PER_CHUNK):
            raise ValueError('Invalid recovery manifest')
        return value

    def inventory(self):
        rows=[];errors=[]
        if self.root.exists():
            for folder in self.root.iterdir():
                if not ID.fullmatch(folder.name) or not (folder/'manifest.json').exists():continue
                try:rows.append(self.metadata(folder.name))
                except Exception:errors.append(folder.name)
        return sorted(rows,key=lambda row:row['saved_at']),errors

    def save(self,ident,frames,row,valid=lambda:True):
        if not 0<len(frames)<=MAX_FRAMES:raise ValueError('Recovery audio exceeds the one-hour limit')
        folder=self.folder(ident);self.root.mkdir(parents=True,exist_ok=True)
        # Do not destroy an older committed recording on a failed repeat save.
        if (folder/'manifest.json').exists():return []
        folder.mkdir(exist_ok=True);chunks=[]
        try:
            for offset in range(0,len(frames),FRAMES_PER_CHUNK):
                if not valid():raise InterruptedError('Recovery save was cleared')
                part=np.asarray(frames[offset:offset+FRAMES_PER_CHUNK],dtype='<f4')
                if part.shape!=(min(FRAMES_PER_CHUNK,len(frames)-offset),320):raise ValueError('Invalid recovery audio shape')
                data=part.tobytes();digest=hashlib.sha256(data).hexdigest();chunks.append(digest)
                payload=storage.dumps({'pcm':base64.b64encode(data).decode('ascii'),'sha256':digest})
                (folder/f'{len(chunks)-1:04d}.json').write_text(payload,encoding='utf-8')
            manifest={'id':ident,'frames':len(frames),'chunks':chunks,'row':row,'saved_at':time.time()}
            temporary=folder/'manifest.tmp'
            with temporary.open('w',encoding='utf-8') as stream:
                stream.write(storage.dumps(manifest));stream.flush();os.fsync(stream.fileno())
            if not valid():raise InterruptedError('Recovery save was cleared')
            os.replace(temporary,folder/'manifest.json')
        except Exception:
            self.remove(ident);raise
        rows,_=self.inventory();evicted=[]
        def size():return sum(p.stat().st_size for r in rows for p in self.folder(r['id']).iterdir() if p.is_file())
        while len(rows)>5 or size()>MAX_BYTES:
            old=rows.pop(0);self.remove(old['id']);evicted.append(old['id'])
        return evicted

    def load(self,ident):
        value=self.metadata(ident);frames=[]
        for index,digest in enumerate(value['chunks']):
            path=self.folder(ident)/f'{index:04d}.json'
            if path.stat().st_size>800000:raise ValueError('Recovery chunk exceeds its limit')
            text=path.read_text(encoding='utf-8')
            if not storage.protected(text):raise ValueError('Recovery audio is not protected')
            data=base64.b64decode(storage.loads(text)['pcm'],validate=True)
            count=min(FRAMES_PER_CHUNK,value['frames']-len(frames))
            if len(data)!=count*320*4 or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Recovery audio failed its integrity check')
            frames.extend(np.frombuffer(data,dtype='<f4').reshape(count,320).copy())
        return frames,value['row']


class RecoveryWorker:
    """Lazy single writer; bounded saves, cancellation generations for Clear."""
    def __init__(self,root):
        self.store=RecoveryStore(root);self.jobs=queue.Queue(maxsize=8);self.results=queue.Queue()
        self.generation=0;self.clear_pending=threading.Event();self.thread=None;self.lock=threading.Lock()

    def submit(self,action,*args):
        try:self.jobs.put_nowait((self.generation,action,args))
        except queue.Full:return False
        self.start();return True

    def start(self):
        with self.lock:
            if self.thread is None or not self.thread.is_alive():
                self.thread=threading.Thread(target=self.run,daemon=True,name='encrypted-recovery');self.thread.start()

    def clear(self):
        self.generation+=1;self.clear_pending.set();self.start()

    def run(self):
        while True:
            if self.clear_pending.is_set():
                self.clear_pending.clear()
                try:self.store.clear()
                except Exception as exc:self.results.put((self.generation,'error',str(exc)))
            try:generation,action,args=self.jobs.get(timeout=.1)
            except queue.Empty:
                with self.lock:
                    if self.jobs.empty() and not self.clear_pending.is_set():self.thread=None;return
                continue
            if generation!=self.generation:continue
            try:
                if action=='save':
                    evicted=self.store.save(*args,valid=lambda:generation==self.generation)
                    result=('saved',{'id':args[0],'evicted':evicted})
                elif action=='load':result=('loaded',(args[0],*self.store.load(*args)))
                elif action=='inventory':result=('inventory',self.store.inventory())
                elif action=='remove':self.store.remove(*args);result=('removed',args[0])
                else:raise ValueError('Unknown recovery action')
                if generation==self.generation:self.results.put((generation,*result))
            except InterruptedError:pass
            except Exception as exc:
                if generation==self.generation:self.results.put((generation,'error',str(exc)))
