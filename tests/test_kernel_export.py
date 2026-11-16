import hashlib
import json
from pathlib import Path
import subprocess
import uuid


ROOT=Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
        '-File',str(ROOT/'scripts/Export-TdrDump.ps1'),*args],cwd=ROOT,capture_output=True,text=True,timeout=15,
        creationflags=0x08000000)


def test_private_kernel_export_copies_exact_fixture_without_changing_source():
    folder=ROOT/'.work/kernel-export-tests';folder.mkdir(parents=True,exist_ok=True)
    source=folder/(uuid.uuid4().hex+'.bin');data=bytes(range(256))*1024;source.write_bytes(data)
    try:
        result=run('-FixturePath',str(source))
        assert result.returncode==0,result.stderr
        status=json.loads((ROOT/'.work/kernel-diagnostics/status-test.json').read_text(encoding='utf-8'))
        copied=Path(status['copied_dump'])
        assert status['state']=='complete' and status['test_mode'] is True
        assert copied.read_bytes()==data==source.read_bytes()
        assert status['sha256']==hashlib.sha256(data).hexdigest()
        assert subprocess.run(['git','check-ignore','--quiet',str(copied)],cwd=ROOT).returncode==0
        copied.unlink()
    finally:source.unlink()


def test_export_rejects_path_traversal_and_sources_outside_private_workspace(tmp_path):
    assert run('-DumpName','../other.dmp','-FixturePath',str(ROOT/'.work/unused')).returncode!=0
    source=tmp_path/'private.bin';source.write_bytes(b'keep')
    assert run('-FixturePath',str(source)).returncode!=0
    assert source.read_bytes()==b'keep'
