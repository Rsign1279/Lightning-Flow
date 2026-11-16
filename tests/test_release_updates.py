import io
import json
import pytest
from lightningflow.desktop.updates import release_update,REPOSITORY
from lightningflow.desktop.state import Settings


def test_release_checks_are_off_by_default():
    assert Settings().check_updates is False


def test_check_only_returns_newer_release_in_the_correct_repository(monkeypatch):
    def response(_request,timeout):
        assert timeout==5
        return io.BytesIO(json.dumps({'tag_name':'v0.6.0','html_url':REPOSITORY+'/releases/tag/v0.6.0'}).encode())
    monkeypatch.setattr('urllib.request.urlopen',response)
    assert release_update('0.5.0')['version']=='0.6.0'
    assert release_update('0.6.0') is None


def test_release_metadata_cannot_redirect_to_another_site(monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen',lambda *_a,**_k:io.BytesIO(json.dumps({'tag_name':'v9.0.0','html_url':'https://example.invalid/malware.exe'}).encode()))
    with pytest.raises(ValueError,match='repository'):release_update('0.5.0')
