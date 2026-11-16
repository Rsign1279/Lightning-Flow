from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import threading
import urllib.error
import pytest
from lightningflow.desktop.cleanup import enhance,local_request
from lightningflow.desktop.state import Settings,Preferences

@contextmanager
def local_server():
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append((self.path,data))
            if self.path=='/redirect':
                self.send_response(302); self.send_header('Location','https://example.invalid/never-contact'); self.end_headers(); return
            response={} if self.path=='/api/show' else {'message':{'content':'Please meet Friday at 3.'}}
            self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        def log_message(self,*args): pass
    server=HTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try: yield server.server_address[1],calls
    finally: server.shutdown(); server.server_close(); thread.join(timeout=1)

def test_local_ai_roundtrip_ignores_system_proxy(monkeypatch):
    monkeypatch.setenv('HTTP_PROXY','http://127.0.0.1:1')
    with local_server() as (port,calls):
        result,note=enhance('Um, please meet Friday at 3.',Settings(cleanup_mode='Smart cleanup',cleanup_model='local-test',cleanup_port=port))
        assert result=='Please meet Friday at 3.' and note=='Local cleanup applied'
        assert [path for path,data in calls]==['/api/show','/api/chat']
        assert calls[-1][1]['stream'] is False

def test_local_server_cannot_redirect_transcript_to_an_external_host():
    with local_server() as (port,calls):
        with pytest.raises(urllib.error.HTTPError) as error:
            local_request('Ollama',port,'/redirect',{'text':'must remain local'})
        assert error.value.code==302
        assert len(calls)==1

def test_slow_cleanup_releases_raw_and_never_revises_it_later(tmp_path,monkeypatch):
    from lightningflow.desktop import worker
    from lightningflow.desktop.worker import build_backend
    finished=threading.Event()
    release=threading.Event()
    def delayed(raw,settings):
        release.wait(1)
        finished.set()
        return 'late edited text','applied'
    monkeypatch.setattr('lightningflow.desktop.cleanup.enhance',delayed)
    monkeypatch.setattr(worker,'send',lambda *a,**k:None)
    path=tmp_path/'settings.json'
    Preferences(path).save(Settings(cleanup_mode='Smart cleanup',cleanup_model='local-test',wait_for_cleanup=True))
    backend=build_backend(path,tmp_path/'models')
    session=backend.new_session(None); session.text='original dictation'; backend.active=session
    backend.schedule_delivery(session)
    assert backend.cleanup_pending
    backend.cleanup_pending=(session,0)
    backend.on_tick()
    assert backend.pending and backend.pending[0] is session and session.text=='original dictation'
    release.set(); assert finished.wait(1)
    backend.on_tick()
    assert session.text=='original dictation'
