import hashlib
import json
import sqlite3
import urllib.request

import pytest
from fastapi.testclient import TestClient
import github_firmware as github
from main import create_app
from test_firmware_updates import image, advertise, A, D


class GitHub:
    def __init__(self, version='2.1.0'):
        self.version=version;self.calls=[];self.error=False;self.corrupt=False;self.on_image=None
        self.manifest=self.metadata(version)
        self.releases=[self.release(version)]

    def metadata(self, version):
        data=image(version)
        return {'schema':1,'product':'fajny-print-studio','board':'esp32dev','layout':'dual1856-v1','version':version,'file':f'esp32-firmware-{version}.bin','size':len(data),'sha256':hashlib.sha256(data).hexdigest()}

    def release(self, version):
        m=self.metadata(version)
        return {'tag_name':'firmware-v'+version,'draft':False,'prerelease':False,'published_at':'2026-01-01T00:00:00Z',
                'assets':[{'name':m['file'],'state':'uploaded','size':m['size'],'digest':'sha256:'+m['sha256'],'browser_download_url':'http://127.0.0.1/private'},
                          {'name':f'esp32-firmware-{version}.json','state':'uploaded','size':500}]}

    def fetch(self,url,limit):
        self.calls.append(url)
        if self.error:raise github.SourceError('GitHub test unavailable')
        if url==github.API_URL:return json.dumps(self.releases).encode()
        if url==github.asset_url(self.version,'json'):return json.dumps(self.manifest).encode()
        if url==github.asset_url(self.version,'bin'):
            if self.on_image:self.on_image()
            return b'corrupt' if self.corrupt else image(self.version)
        raise AssertionError('Unexpected download destination: '+url)


@pytest.fixture
def context(tmp_path,monkeypatch):
    source=GitHub();monkeypatch.setattr(github,'download',source.fetch)
    app=create_app({'DB_PATH':str(tmp_path/'github.sqlite'),'ADMIN_TOKEN':'a'*32,'AGENT_TOKEN':'d'*32,'WEB_DIR':str(tmp_path/'web')})
    with TestClient(app,base_url='https://testserver') as client:
        advertise(client);yield client,source


def body(source):return {'agent_id':'esp32-01','version':source.version,'sha256':source.manifest['sha256']}


def expire_cache(client):
    with sqlite3.connect(client.app.state.db_path) as c:c.execute('UPDATE firmware_source_cache SET last_attempt=0')


def test_check_is_read_only_cached_and_uses_only_fixed_repo(context):
    c,source=context
    assert c.get('/api/firmware/github').status_code==401
    first=c.get('/api/firmware/github',headers=A).json()
    assert first['release']['version']=='2.1.0' and first['error'] is None
    assert source.calls==[github.API_URL,github.asset_url('2.1.0','json')]
    assert c.post('/api/firmware/github/check',headers=A).json()==first
    assert len(source.calls)==2
    state=c.get('/api/firmware',headers=A).json()
    assert not state['releases'] and not state['updates'] and not state['maintenance']


def test_selects_highest_stable_firmware_version_numerically():
    source=GitHub('2.10.0')
    source.releases=[source.release('2.9.9'),source.release('2.10.0'),{**source.release('3.0.0'),'prerelease':True},{**source.release('4.0.0'),'draft':True},{'tag_name':'server-v9.0.0'}]
    assert github.read_latest(source.fetch)['version']=='2.10.0'
    for v in ['2.01.0','v2.0.0','2.0','2.0.0-rc1','1.2.3/../../x',None]:
        with pytest.raises(github.SourceError):github.version_tuple(v)


@pytest.mark.parametrize('field,value',[('board','other'),('layout','old'),('version','2.0.0'),('size',True),('size',9999999),('sha256','invalid'),('schema',True),('product','other'),('file','other.bin')])
def test_rejects_incompatible_or_malformed_manifest(context,field,value):
    c,source=context;source.manifest[field]=value
    result=c.get('/api/firmware/github',headers=A).json()
    assert result['error'] and result['release'] is None
    assert c.post('/api/firmware/github/install',headers=A,json=body(source)).status_code in [422,502]
    assert not any(url.endswith('.bin') for url in source.calls)


def test_incomplete_release_empty_source_and_digest_disagreement(context):
    c,source=context;source.releases=[]
    result=c.get('/api/firmware/github',headers=A).json();assert result['release'] is None and result['error'] is None
    assert c.post('/api/firmware/github/install',headers=A,json=body(source)).status_code==404
    source.releases=[source.release(source.version)];source.releases[0]['assets'].pop();expire_cache(c)
    assert c.post('/api/firmware/github/check',headers=A).json()['error']
    source.releases=[source.release(source.version)];source.releases[0]['assets'][0]['digest']='sha256:'+'0'*64;expire_cache(c)
    assert c.post('/api/firmware/github/check',headers=A).json()['error']


def test_explicit_install_downloads_checks_and_schedules_existing_ota_flow(context):
    c,source=context
    release=c.get('/api/firmware/github',headers=A).json()['release']
    assert c.post('/api/firmware/github/install',headers=D,json=body(source)).status_code==401
    result=c.post('/api/firmware/github/install',headers=A,json=body(source))
    assert result.status_code==201,result.text
    state=c.get('/api/firmware',headers=A).json()
    assert state['maintenance'] and state['updates'][0]['state']=='queued'
    assert state['releases'][0]['sha256']==release['sha256']
    manifest=c.post('/api/agent/firmware/check',headers=D,json={'version':'2.0.0','layout':'dual1856-v1'}).json()['update']
    assert c.get(manifest['path'],headers=D).content==image('2.1.0')
    assert c.post('/api/firmware/github/install',headers=A,json=body(source)).status_code==409


def test_rejects_stale_selection_and_current_or_older_versions(context):
    c,source=context
    assert c.post('/api/firmware/github/install',headers=A,json={**body(source),'sha256':'0'*64}).status_code==409
    c.post('/api/agent/telemetry',headers=D,json={'firmware_version':'2.1.0'})
    assert c.post('/api/firmware/github/install',headers=A,json=body(source)).status_code==409
    c.post('/api/agent/telemetry',headers=D,json={'firmware_version':'3.0.0'})
    assert c.post('/api/firmware/github/install',headers=A,json=body(source)).status_code==409
    assert not any(url.endswith('.bin') for url in source.calls)


def test_corrupt_binary_and_busy_race_never_start_install(context):
    c,source=context;source.corrupt=True
    assert c.post('/api/firmware/github/install',headers=A,json=body(source)).status_code==502
    assert not c.get('/api/firmware',headers=A).json()['updates']
    source.corrupt=False
    def queued_job():
        with sqlite3.connect(c.app.state.db_path) as db:db.execute("INSERT INTO jobs(id,agent_id,text,font_size,raster,status,created_at,updated_at) VALUES('race','esp32-01','Test',0,X'00','queued','now','now')")
    source.on_image=queued_job
    assert c.post('/api/firmware/github/install',headers=A,json=body(source)).status_code==409
    assert not c.get('/api/firmware',headers=A).json()['updates']


def test_network_failure_keeps_last_result_but_blocks_install_and_recovers(context):
    c,source=context
    first=c.get('/api/firmware/github',headers=A).json();source.error=True;expire_cache(c)
    failure=c.post('/api/firmware/github/check',headers=A).json()
    assert failure['release']==first['release'] and failure['checked_at']==first['checked_at'] and failure['error']
    assert c.post('/api/firmware/github/install',headers=A,json=body(source)).status_code==502
    source.error=False;expire_cache(c)
    assert c.post('/api/firmware/github/check',headers=A).json()['error'] is None


def test_rejects_non_github_https_redirects_and_limits_download(monkeypatch):
    request=urllib.request.Request(github.API_URL);handler=github.GitHubRedirects()
    for url in ['http://github.com/x','https://127.0.0.1/x','https://github.com.evil.example/x','https://user:pass@github.com/x','https://github.com:80/x','https://github.com:bad/x']:
        with pytest.raises(github.SourceError):handler.redirect_request(request,None,302,'',{},url)
    class Response:
        headers={}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def geturl(self):return github.API_URL
        def read(self,size):return b'x'*size
    class Opener:
        def open(self,*args,**kwargs):return Response()
    monkeypatch.setattr(urllib.request,'build_opener',lambda *args:Opener())
    with pytest.raises(github.SourceError):github.download(github.API_URL,100)
