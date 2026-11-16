import hashlib
import pytest
from lightningflow.model_integrity import verify_download


def test_lfs_and_git_hashes_are_both_checked(tmp_path):
    weights=b'fixture weights';config=b'{"model":"fixture"}'
    (tmp_path/'model.bin').write_bytes(weights);(tmp_path/'config.json').write_bytes(config)
    manifest={'files':{'model.bin':{'algorithm':'sha256','digest':hashlib.sha256(weights).hexdigest(),'size':len(weights)},
        'config.json':{'algorithm':'git-sha1','digest':hashlib.sha1(b'blob '+str(len(config)).encode()+b'\0'+config).hexdigest(),'size':len(config)}}}
    assert verify_download(tmp_path,manifest)
    (tmp_path/'model.bin').write_bytes(b'x'*len(weights))
    with pytest.raises(RuntimeError,match='checksum'):verify_download(tmp_path,manifest)


def test_model_manifest_cannot_read_outside_model_directory(tmp_path):
    with pytest.raises(ValueError,match='Unsafe'):
        verify_download(tmp_path,{'files':{'../private':{'algorithm':'sha256','digest':'0'*64}}})


def test_missing_or_truncated_model_is_rejected(tmp_path):
    manifest={'files':{'model.bin':{'algorithm':'sha256','digest':'0'*64,'size':10}}}
    with pytest.raises(RuntimeError,match='missing'):verify_download(tmp_path,manifest)
    (tmp_path/'model.bin').write_bytes(b'x')
    with pytest.raises(RuntimeError,match='size'):verify_download(tmp_path,manifest)
