import json
import sqlite3
import pytest
from lightningflow.desktop import storage
from lightningflow.desktop.state import Settings,Preferences,History


def test_dpapi_roundtrip_does_not_expose_plaintext():
    value={'text':'Private local sentence 🔒','count':15}
    sealed=storage.dumps(value)
    assert 'Private local sentence' not in sealed and storage.protected(sealed)
    assert storage.loads(sealed)==value


def test_dpapi_corruption_is_not_accepted():
    value=json.loads(storage.dumps({'text':'private'}))
    value['data']=value['data'][:-8]+'AAAAAA=='
    with pytest.raises((OSError,ValueError)):storage.loads(json.dumps(value))


def test_legacy_preferences_migrate_without_losing_shortcuts(tmp_path):
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'controls_revision':2,'recording_shortcut':'ctrl_win','activation':'smart'}))
    store=Preferences(path);settings=store.load();store.save(settings)
    assert storage.protected(path.read_text())
    loaded=store.load()
    assert loaded.recording_shortcut=='ctrl_win' and loaded.activation=='smart'


def test_history_ciphertext_roundtrip_and_legacy_migration(tmp_path):
    path=tmp_path/'history.sqlite3'
    db=sqlite3.connect(path)
    db.execute('CREATE TABLE transcripts (id TEXT PRIMARY KEY,payload TEXT NOT NULL)')
    row={'id':'one','created':'2026-11-15T00:00:00','text':'Sensitive test transcript','raw':'Sensitive test transcript'}
    db.execute('INSERT INTO transcripts VALUES (?,?)',('one',json.dumps(row)));db.commit();db.close()
    log=History(path,True)
    assert log.rows[0]['text']==row['text']
    log.add(dict(row,id='two'));log.close()
    db=sqlite3.connect(path)
    assert all(storage.protected(payload) for (payload,) in db.execute('SELECT payload FROM transcripts'))
    db.close()
    assert b'Sensitive test transcript' not in path.read_bytes()
    restored=History(path,True)
    assert len(restored.rows)==2 and not restored.error
    restored.close()
