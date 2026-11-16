import base64
import io
import sqlite3
import time

import pytest
import qrcode
from fastapi.testclient import TestClient
from PIL import Image
from main import create_app
from accounts import COOKIE, sha

ADMIN='a'*32
DEVICE='d'*32
A={'Authorization':'Bearer '+ADMIN}
D={'Authorization':'Bearer '+DEVICE}
PROFILE={'email':' Owner@Example.com ','nickname':' Fajny admin ','password':'very secure password'}

def make(tmp_path, **config):
    return create_app({'DB_PATH':str(tmp_path/'q.sqlite'),'ADMIN_TOKEN':ADMIN,'AGENT_TOKEN':DEVICE,'WEB_DIR':str(tmp_path/'web'),**config})

@pytest.fixture
def client(tmp_path):
    with TestClient(make(tmp_path),base_url='https://testserver') as c:yield c

def bootstrap(c):
    r=c.post('/api/auth/login',json={'login':'admin','password':'admin'})
    assert r.status_code==200
    return r.json()['csrf_token']

def setup(c):
    csrf=bootstrap(c)
    r=c.post('/api/auth/setup',json=PROFILE,headers={'X-CSRF-Token':csrf})
    assert r.status_code==200,r.text
    return r.json()['csrf_token']

def test_bootstrap_requires_atomic_setup_and_rotates_sessions(client):
    assert client.get('/api/auth/config').json()=={'registration_enabled':False}
    nonce=bootstrap(client)
    cookie=client.cookies.get(COOKIE)
    assert client.get('/api/auth/me').json()['user']['must_setup'] is True
    for method,url,data in [('get','/api/jobs',None),('post','/api/preview',{'text':'x'}),('put','/api/auth/settings',{'registration_enabled':True})]:
        assert getattr(client,method)(url,**({'json':data} if data else {}),headers={'X-CSRF-Token':nonce}).status_code==403
    assert client.post('/api/auth/setup',json=PROFILE).status_code==403
    result=client.post('/api/auth/setup',json=PROFILE,headers={'X-CSRF-Token':nonce})
    assert result.status_code==200
    assert result.json()['user']=={'id':result.json()['user']['id'],'email':'owner@example.com','nickname':'Fajny admin','role':'admin','must_setup':False}
    assert client.cookies.get(COOKIE)!=cookie
    assert all(flag in result.headers['set-cookie'].lower() for flag in ('secure','httponly','samesite=lax'))
    assert client.get('/api/auth/me',headers={'Cookie':f'{COOKIE}={cookie}'}).status_code==401
    assert client.post('/api/auth/login',json={'login':'admin','password':'admin'}).status_code==401
    assert client.post('/api/auth/setup',json=PROFILE,headers={'X-CSRF-Token':result.json()['csrf_token']}).status_code==409
    with sqlite3.connect(client.app.state.db_path) as db:
        hashed=db.execute('select password_hash from users').fetchone()[0]
        assert hashed.startswith('$argon2id$')
        stored=db.execute('select token_hash from account_sessions').fetchone()[0]
        assert stored==sha(client.cookies.get(COOKIE))


def test_cookie_csrf_origin_logout_expiry(client):
    nonce=setup(client)
    assert client.post('/api/preview',json={'text':'ok'}).status_code==403
    assert client.post('/api/preview',json={'text':'ok'},headers={'X-CSRF-Token':nonce,'Origin':'https://evil.test'}).status_code==403
    assert client.post('/api/preview',json={'text':'ok'},headers={'X-CSRF-Token':nonce,'Origin':'https://testserver'}).status_code==200
    old=client.cookies.get(COOKIE)
    assert client.post('/api/auth/logout',headers={'X-CSRF-Token':nonce}).status_code==200
    assert client.get('/api/auth/me',headers={'Cookie':f'{COOKIE}={old}'}).status_code==401
    r=client.post('/api/auth/login',json={'login':'OWNER@example.com','password':PROFILE['password']})
    assert r.status_code==200
    with sqlite3.connect(client.app.state.db_path) as db:db.execute('update account_sessions set expires=?',(time.time()-1,))
    assert client.get('/api/auth/me').status_code==401


def test_registration_roles_and_shared_workspace(client):
    body={'email':'user@example.com','nickname':'user','password':'another secure password','role':'admin'}
    assert client.post('/api/auth/register',json=body).status_code==403
    admin_csrf=setup(client)
    admin_cookie=client.cookies.get(COOKIE)
    assert client.put('/api/auth/settings',json={'registration_enabled':True},headers={'X-CSRF-Token':admin_csrf}).status_code==200
    r=client.post('/api/auth/register',json=body)
    assert r.status_code==201
    nonce=r.json()['csrf_token'];headers={'X-CSRF-Token':nonce}
    assert r.json()['user']['role']=='user'
    assert client.get('/api/auth/me').status_code==200
    assert client.post('/api/preview',json={'text':'shared'},headers=headers).status_code==200
    assert client.post('/api/templates',json={'name':'ours','text':'shared'},headers=headers).status_code==201
    assert client.post('/api/jobs',json={'text':'shared','agent_id':'esp32-01','idempotency_key':'cookie-user-12345'},headers=headers).status_code==201
    assert client.get('/api/jobs').status_code==200
    assert client.get('/api/agents').status_code==200
    assert client.get('/api/auth/settings').status_code==403
    assert client.put('/api/auth/settings',json={'registration_enabled':False},headers=headers).status_code==403
    assert client.post('/api/agents',json={'name':'bad'},headers=headers).status_code==403
    assert client.post('/api/agents/esp32-01/pause',json={'paused':True},headers=headers).status_code==403
    assert client.post('/api/auth/register',json=body).status_code==409
    assert client.put('/api/auth/settings',json={'registration_enabled':False},headers={'Cookie':f'{COOKIE}={admin_cookie}','X-CSRF-Token':admin_csrf}).status_code==200
    assert client.post('/api/auth/register',json={**body,'email':'new@example.com'}).status_code==403


def test_throttle_persists_and_init_does_not_reset_accounts(tmp_path):
    with TestClient(make(tmp_path),base_url='https://testserver') as c:
        nonce=setup(c)
        c.put('/api/auth/settings',json={'registration_enabled':True},headers={'X-CSRF-Token':nonce})
        for _ in range(5):assert c.post('/api/auth/login',json={'login':'owner@example.com','password':'wrong'}).status_code==401
    with TestClient(make(tmp_path),base_url='https://testserver') as c:
        assert c.post('/api/auth/login',json={'login':'owner@example.com','password':PROFILE['password']}).status_code==429
        assert c.get('/api/auth/config').json()['registration_enabled'] is True
        with sqlite3.connect(c.app.state.db_path) as db:assert db.execute('select count(*) from users').fetchone()[0]==1
        assert c.post('/api/auth/login',json={'login':'admin','password':'admin'}).status_code==401


def test_maintenance_cidrs_and_public_origin(tmp_path):
    app=make(tmp_path,MAINTENANCE_CIDRS='127.0.0.0/8,100.64.0.0/10',PUBLIC_ORIGIN='https://labels.example.com')
    with TestClient(app,base_url='https://testserver',client=('172.18.0.3',1234)) as c:
        assert c.get('/api/jobs',headers={**A,'X-Forwarded-For':'127.0.0.1'}).status_code==403
        assert c.post('/api/agent/claim',headers=D).status_code==204
        assert c.post('/api/auth/login',json={'login':'admin','password':'admin'},headers={'Origin':'https://testserver'}).status_code==403
        assert c.post('/api/auth/login',json={'login':'admin','password':'admin'},headers={'Origin':'https://labels.example.com'}).status_code==200
    with TestClient(app,base_url='https://testserver',client=('127.0.0.1',1234)) as c:assert c.get('/api/jobs',headers=A).status_code==200


def test_qr_matrix_quiet_zone_raster_and_persistence(client):
    payload='https://example.com'
    r=client.post('/api/preview',json={'kind':'qr','text':payload},headers=A)
    assert r.status_code==200,r.text
    image=Image.open(io.BytesIO(r.content)).convert('1')
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,border=4,box_size=1)
    qr.add_data(payload);qr.make(fit=True);matrix=qr.get_matrix()
    side=len(matrix);scale=96//side;left=(320-side*scale)//2;top=(96-side*scale)//2
    assert scale>=2
    expected=Image.new('1',(320,96),1)
    for y,row in enumerate(matrix):
        for x,value in enumerate(row):
            for dy in range(scale):
                for dx in range(scale):expected.putpixel((left+x*scale+dx,top+y*scale+dy),0 if value else 1)
    assert image.tobytes()==expected.tobytes()
    assert all(image.getpixel((x,y)) for x in range(320) for y in range(top+4*scale))
    body={'kind':'qr','text':payload,'agent_id':'esp32-01','idempotency_key':'qr-request-123456'}
    result=client.post('/api/jobs',json=body,headers=A)
    assert result.status_code==201 and result.json()[0]['kind']=='qr'
    assert client.post('/api/jobs',json=body,headers=A).json()[0]['id']==result.json()[0]['id']
    job=client.post('/api/agent/claim',headers=D).json()
    assert base64.b64decode(job['raster_base64'])==bytes(v^255 for v in image.transpose(Image.Transpose.ROTATE_270).tobytes())
    assert client.post('/api/templates',json={'kind':'qr','text':payload,'name':'QR'},headers=A).status_code==201
    assert client.get('/api/templates',headers=A).json()[0]['kind']=='qr'
    assert client.post('/api/preview',json={'kind':'qr','text':'abc','invert':True},headers=A).status_code==422
    dense=''.join(chr(33+i%90) for i in range(200))
    r=client.post('/api/preview',json={'kind':'qr','text':dense},headers=A)
    assert r.status_code==422 and 'hustý' in r.json()['detail']

@pytest.mark.parametrize('field,value',[('email','no email'),('nickname',' '),('nickname','x'*61),('nickname','bad\x00name'),('password','short'),('password','x'*129)])
def test_setup_validates_profile_without_consuming_bootstrap(client,field,value):
    nonce=bootstrap(client)
    assert client.post('/api/auth/setup',json={**PROFILE,field:value},headers={'X-CSRF-Token':nonce}).status_code==422
    assert client.get('/api/auth/me').json()['user']['must_setup'] is True


def test_existing_rows_default_text_and_account_migration_idempotent(tmp_path):
    with TestClient(make(tmp_path),base_url='https://testserver') as c:
        assert c.post('/api/templates',json={'text':'legacy','name':'legacy'},headers=A).status_code==201
        db_path=c.app.state.db_path
    with sqlite3.connect(db_path) as db:
        db.execute("update templates set style_json='{}'")
        original=db.execute('select id,password_hash from users').fetchone()
    with TestClient(make(tmp_path),base_url='https://testserver') as c:
        assert c.get('/api/templates',headers=A).json()[0]['kind']=='text'
        with sqlite3.connect(db_path) as db:assert db.execute('select id,password_hash from users').fetchone()==original
