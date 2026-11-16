"""Opt-in release metadata only. Never downloads or executes an installer."""
import json
import re
import urllib.error
import urllib.request

REPOSITORY='https://github.com/Rsign1279/Lightning-Flow'
API='https://api.github.com/repos/Rsign1279/Lightning-Flow/releases/latest'


def release_update(current):
    request=urllib.request.Request(API,headers={'Accept':'application/vnd.github+json','User-Agent':'LightningFlow-release-check'})
    try:
        with urllib.request.urlopen(request,timeout=5) as response:data=json.loads(response.read(1024*1024))
    except urllib.error.HTTPError as exc:
        if exc.code==404:return None
        raise
    tag=data.get('tag_name','');url=data.get('html_url','')
    if not re.fullmatch(r'v?\d+\.\d+\.\d+',tag) or not url.startswith(REPOSITORY+'/releases/tag/'):
        raise ValueError('Release metadata did not match this repository')
    version=lambda value:tuple(map(int,value.removeprefix('v').split('.')))
    return {'version':tag.removeprefix('v'),'url':url} if version(tag)>version(current) else None
