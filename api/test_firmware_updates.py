import hashlib
import sqlite3
import struct

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from main import create_app
from firmware_updates import MAX_IMAGE, validate_image

A={'Authorization':'Bearer '+'a'*32}
D={'Authorization':'Bearer '+'d'*32}


def image(version='2.0.0'):
    header=bytearray(24);header[0]=0xe9;header[1]=1;header[23]=1
    data=bytearray(1600);data[:4]=struct.pack('<I',0xabcd5432)
    tag=('FPS_OTA:esp32dev:dual1856-v1:'+version+':END').encode()
    data[300:300+len(tag)]=tag
    output=bytes(header)+struct.pack('<II',0x3f400020,len(data))+bytes(data)
    check=0xef
    for v in data:check^=v
    output+=bytes((-len(output)-1)%16)+bytes([check])
    return output+hashlib.sha256(output).digest()


@pytest.fixture
def client(tmp_path):
    app=create_app({'DB_PATH':str(tmp_path/'ota.sqlite'),'ADMIN_TOKEN':'a'*32,'AGENT_TOKEN':'d'*32,'WEB_DIR':str(tmp_path/'web')})
    with TestClient(app,base_url='https://testserver') as c:yield c


def release(c):
    r=c.post('/api/firmware/releases',headers={**A,'X-Firmware-Version':'2.0.0'},content=image())
    assert r.status_code==201,r.text
    return r.json()


def advertise(c):
    r=c.post('/api/agent/telemetry',headers=D,json={'firmware_version':'2.0.0','ota_supported':True,'ota_layout':'dual1856-v1','ota_slot':0})
    assert r.status_code==200,r.text


def begin(c):
    sha=release(c)['sha256'];advertise(c)
    r=c.post('/api/firmware/updates',headers=A,json={'agent_id':'esp32-01','sha256':sha})
    assert r.status_code==201,r.text
    return r.json()['id'],sha


def check(c,**fields):
    return c.post('/api/agent/firmware/check',headers=D,json={'version':'2.0.0','layout':'dual1856-v1',**fields})


def test_binary_validation_rejects_wrong_artifacts_truncation_version_and_corruption():
    assert validate_image(image(),'2.0.0')==hashlib.sha256(image()).hexdigest()
    for artifact,version in [(image()[:-1],'2.0.0'),(image(),'wrong'),(bytes(1200),'2.0.0'),(image()+b'x','2.0.0'),(b'x'*(MAX_IMAGE+1),'2.0.0'),(image(),'../../bad')]:
        with pytest.raises(HTTPException):validate_image(artifact,version)
    bad=bytearray(image());bad[100]^=1
    with pytest.raises(HTTPException):validate_image(bytes(bad),'2.0.0')


def test_upload_bounded_authenticated_and_deduplicated(client):
    for headers in [{},{**D,'X-Firmware-Version':'2.0.0'}]:
        assert client.post('/api/firmware/releases',headers=headers,content=image()).status_code==401
    assert client.post('/api/firmware/releases',headers={**A,'X-Firmware-Version':'2.0.0'},content=b'x'*(MAX_IMAGE+1)).status_code==413
    assert release(client)==release(client)
    data=client.get('/api/firmware',headers=A).json()
    assert len(data['releases'])==1 and 'image' not in data['releases'][0]
    assert data['maintenance'] is False


def test_requires_online_ota_device_and_empty_queue(client):
    sha=release(client)['sha256'];body={'agent_id':'esp32-01','sha256':sha}
    assert client.post('/api/firmware/updates',headers=A,json=body).status_code==409
    client.post('/api/agent/telemetry',headers=D,json={'firmware_version':'1.3.2'})
    assert client.post('/api/firmware/updates',headers=A,json=body).status_code==409
    advertise(client)
    assert client.post('/api/jobs',headers=A,json={'agent_id':'esp32-01','text':'Pending','idempotency_key':'ota-busy-test'}).status_code==201
    assert client.post('/api/firmware/updates',headers=A,json=body).status_code==409


def test_owner_only_download_success_confirmed_only_after_boot_hash(client):
    identifier,sha=begin(client)
    assert client.post('/api/agent/claim',headers=D).status_code==204
    assert client.post('/api/jobs',headers=A,json={'agent_id':'esp32-01','text':'Blocked','idempotency_key':'ota-maintenance'}).status_code==409
    assert client.get('/api/agent/firmware/'+identifier+'/image',headers=D).status_code==404
    manifest=check(client).json()['update'];assert manifest['sha256']==sha
    assert check(client).json()['update'] is None  # No duplicate delivery after uncertain download.
    other=client.post('/api/agents',headers=A,json={'name':'Other ESP'}).json()
    other_headers={'Authorization':'Bearer '+other['token']}
    assert client.get(manifest['path'],headers=other_headers).status_code==404
    assert client.get(manifest['path']).status_code==401
    assert client.get(manifest['path'],headers=D).content==image()
    assert check(client,result_id=identifier,boot_sha256='0'*64).json()['acknowledged'] is False
    assert client.get('/api/firmware',headers=A).json()['maintenance'] is True
    assert check(client,result_id=identifier,boot_sha256=sha).json()['acknowledged'] is True
    data=client.get('/api/firmware',headers=A).json()
    assert not data['maintenance'] and data['updates'][0]['state']=='succeeded'
    assert client.get(manifest['path'],headers=D).status_code==404
    check(client,result_id=identifier,error='Late report')
    assert client.get('/api/firmware',headers=A).json()['updates'][0]['state']=='succeeded'


def test_failure_cancel_timeout_and_no_automatic_retry(client):
    identifier,_=begin(client)
    assert client.post('/api/firmware/updates/'+identifier+'/cancel',headers=A).status_code==200
    assert not client.get('/api/firmware',headers=A).json()['maintenance']
    identifier,_=begin(client);check(client)
    assert client.post('/api/firmware/updates/'+identifier+'/cancel',headers=A).status_code==409
    assert check(client,result_id=identifier,error='SHA mismatch').json()['acknowledged']
    assert client.get('/api/firmware',headers=A).json()['updates'][0]['state']=='failed'
    identifier,_=begin(client);check(client)
    with sqlite3.connect(client.app.state.db_path) as db:db.execute('UPDATE firmware_updates SET deadline=0 WHERE id=?',(identifier,))
    data=client.get('/api/firmware',headers=A).json()
    assert not data['maintenance'] and data['updates'][0]['state']=='unknown'
    assert check(client).json()['update'] is None


def test_browser_admin_csrf_and_user_permissions(client):
    login=client.post('/api/auth/login',json={'login':'admin','password':'admin'}).json()
    setup=client.post('/api/auth/setup',headers={'X-CSRF-Token':login['csrf_token']},json={'email':'owner@example.com','nickname':'Owner','password':'very secure password'})
    assert setup.status_code==200,setup.text
    nonce=setup.json()['csrf_token']
    assert client.post('/api/firmware/releases',headers={'X-Firmware-Version':'2.0.0'},content=image()).status_code==403
    assert client.post('/api/firmware/releases',headers={'X-CSRF-Token':nonce,'X-Firmware-Version':'2.0.0','Origin':'https://evil.example'},content=image()).status_code==403
    assert client.post('/api/firmware/releases',headers={'X-CSRF-Token':nonce,'X-Firmware-Version':'2.0.0'},content=image()).status_code==201
    with sqlite3.connect(client.app.state.db_path) as db:db.execute("UPDATE users SET role='user'")
    assert client.post('/api/firmware/releases',headers={'X-CSRF-Token':nonce,'X-Firmware-Version':'2.0.0'},content=image()).status_code==403


def test_release_and_install_state_survive_application_restart(client):
    identifier,sha=begin(client);check(client)
    other=create_app({'DB_PATH':client.app.state.db_path,'ADMIN_TOKEN':'a'*32,'AGENT_TOKEN':'d'*32,'WEB_DIR':'/nonexistent'})
    with TestClient(other,base_url='https://testserver') as c:
        data=c.get('/api/firmware',headers=A).json()
        assert data['maintenance'] and data['updates'][0]['id']==identifier
        assert data['releases'][0]['sha256']==sha


def test_dual_slot_layout_preserves_nvs_and_fits_maximum_brother_spool():
    import csv
    from pathlib import Path
    from brother import MEDIA, render_brother
    from main import Label, font_path
    table=Path(__file__).resolve().parent.parent/'firmware'/'partitions_ota.csv'
    rows=[]
    for row in csv.reader(line for line in table.read_text().splitlines() if not line.lstrip().startswith('#')):
        if row:rows.append((row[0].strip(),int(row[3].strip(),0),int(row[4].strip(),0)))
    parts={name:(offset,size) for name,offset,size in rows}
    assert parts['nvs']==(0x9000,0x5000)
    assert parts['otadata']==(0xe000,0x2000)
    assert parts['app0'][1]==parts['app1'][1]==MAX_IMAGE
    previous=0x9000
    for name,offset,size in rows:
        assert offset>=previous and offset+size<=4*1024*1024
        if name.startswith('app'):assert offset%0x10000==0
        previous=offset+size
    for profile in MEDIA:
        _,payload=render_brother(Label(profile_id=profile,length_mm=200,text='Maximum spool'),font_path)
        assert len(payload)+32768<parts['spiffs'][1]  # Filesystem metadata and allocation reserve.
