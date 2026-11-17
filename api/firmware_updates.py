"""Authenticated, bounded OTA maintenance for the ESP32 dual-slot layout."""
import hashlib
import json
import re
import struct
import time
import uuid

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

LAYOUT = 'dual1856-v1'
MAX_IMAGE = 0x1D0000
ACTIVE = ('queued', 'installing', 'rebooting')


def initialize(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS firmware_releases (
      sha256 TEXT PRIMARY KEY, version TEXT NOT NULL, size INTEGER NOT NULL,
      image BLOB NOT NULL, created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS firmware_updates (
      id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
      sha256 TEXT NOT NULL REFERENCES firmware_releases(sha256), state TEXT NOT NULL,
      message TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
      deadline REAL NOT NULL);
    ''')


def active(c):
    now = time.time()
    c.execute("UPDATE firmware_updates SET state='unknown', message='Aktualizácia sa nepotvrdila včas. Skontroluj zariadenie.', updated_at=? WHERE state IN ('queued','installing','rebooting') AND deadline<?", (now, now))
    return c.execute("SELECT * FROM firmware_updates WHERE state IN ('queued','installing','rebooting') LIMIT 1").fetchone()


def validate_image(image, version):
    if not re.fullmatch(r'[0-9A-Za-z][0-9A-Za-z.+_-]{0,31}', version):
        raise HTTPException(422, 'Neplatné označenie verzie firmvéru.')
    tag = ('FPS_OTA:esp32dev:' + LAYOUT + ':' + version + ':END').encode()
    if len(image) < 1024 or len(image) > MAX_IMAGE:
        raise HTTPException(422, 'Firmvér má neplatnú veľkosť pre túto ESP32 dosku.')
    if image[0] != 0xE9 or image[1] not in range(1, 17) or image[12:14] != b'\0\0' or tag not in image:
        raise HTTPException(422, 'Vyber aplikačný .bin firmvér Fajny Print pre ESP32 s podporou OTA.')
    if image[32:36] != struct.pack('<I', 0xABCD5432) or image[23] != 1:
        raise HTTPException(422, 'Firmvér nemá podporovanú ESP32 hlavičku a kontrolný súčet.')
    # Parse segment boundaries rather than trusting the file name or magic byte.
    pos = 24
    for _ in range(image[1]):
        if pos + 8 > len(image):
            raise HTTPException(422, 'Firmvér je skrátený.')
        length = struct.unpack_from('<I', image, pos + 4)[0]
        pos += 8 + length
        if pos > len(image):
            raise HTTPException(422, 'Firmvér je skrátený.')
    signed_length = (pos + 16) & ~15
    if signed_length + 32 != len(image) or hashlib.sha256(image[:signed_length]).digest() != image[signed_length:]:
        raise HTTPException(422, 'Kontrolný súčet firmvéru nesúhlasí.')
    checksum = 0xEF
    pos = 24
    for _ in range(image[1]):
        length = struct.unpack_from('<I', image, pos + 4)[0]
        for value in image[pos + 8:pos + 8 + length]:
            checksum ^= value
        pos += 8 + length
    if image[signed_length - 1] != checksum:
        raise HTTPException(422, 'Kontrolný súčet segmentov nesúhlasí.')
    return hashlib.sha256(image).hexdigest()


class Install(BaseModel):
    agent_id: str = Field(min_length=1, max_length=80)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class Check(BaseModel):
    version: str = Field(min_length=1, max_length=64)
    layout: str = Field(max_length=32)
    result_id: str = Field(default='', max_length=40)
    boot_sha256: str = Field(default='', max_length=64)
    error: str = Field(default='', max_length=160)


def install(app, transaction, admin, administrator, device):
    @app.get('/api/firmware', dependencies=[Depends(admin)])
    def status():
        with transaction() as c:
            maintenance = active(c)
            return {'maintenance': bool(maintenance),
                    'releases': [dict(r) for r in c.execute('SELECT sha256,version,size,created_at FROM firmware_releases ORDER BY created_at DESC LIMIT 20')],
                    'updates': [dict(r) for r in c.execute('SELECT u.*,r.version FROM firmware_updates u JOIN firmware_releases r USING(sha256) ORDER BY u.created_at DESC LIMIT 20')]}

    @app.post('/api/firmware/releases', dependencies=[Depends(administrator)], status_code=201)
    async def upload(request: Request):
        version = request.headers.get('x-firmware-version', '')
        image = bytearray()
        async for chunk in request.stream():
            image.extend(chunk)
            if len(image) > MAX_IMAGE:
                raise HTTPException(413, 'Firmvér je príliš veľký pre túto ESP32 dosku.')
        image = bytes(image)
        sha = validate_image(image, version)
        with transaction() as c:
            c.execute('INSERT OR IGNORE INTO firmware_releases VALUES(?,?,?,?,?)', (sha, version, len(image), image, time.time()))
        return {'sha256': sha, 'version': version, 'size': len(image)}

    @app.post('/api/firmware/updates', dependencies=[Depends(administrator)], status_code=201)
    def start(body: Install):
        with transaction() as c:
            if active(c):
                raise HTTPException(409, 'Už prebieha aktualizácia ESP32.')
            if c.execute("SELECT 1 FROM jobs WHERE status IN ('queued','leased','printing') LIMIT 1").fetchone():
                raise HTTPException(409, 'Najprv dokonči alebo zruš všetky čakajúce tlačové úlohy.')
            target = c.execute('SELECT * FROM agents WHERE id=?', (body.agent_id,)).fetchone()
            if not target:
                raise HTTPException(404, 'Zariadenie sa nenašlo.')
            telemetry = json.loads(target['telemetry_json'])
            if not target['last_seen'] or time.time() - target['last_seen'] > 45:
                raise HTTPException(409, 'ESP32 musí byť online.')
            if not telemetry.get('ota_supported') or telemetry.get('ota_layout') != LAYOUT:
                raise HTTPException(409, 'Toto ESP32 najprv potrebuje jednorazovú USB inštaláciu podpory OTA.')
            if not c.execute('SELECT 1 FROM firmware_releases WHERE sha256=?', (body.sha256,)).fetchone():
                raise HTTPException(404, 'Firmvér sa nenašiel.')
            identifier = str(uuid.uuid4()); now = time.time()
            c.execute('INSERT INTO firmware_updates VALUES(?,?,?,?,?,?,?,?)',
                      (identifier, body.agent_id, body.sha256, 'queued', 'Čaká na prevzatie ESP32.', now, now, now + 600))
        return {'id': identifier}

    @app.post('/api/firmware/updates/{identifier}/cancel', dependencies=[Depends(administrator)])
    def cancel(identifier: str):
        with transaction() as c:
            row = c.execute('SELECT * FROM firmware_updates WHERE id=?', (identifier,)).fetchone()
            if not row:
                raise HTTPException(404, 'Aktualizácia sa nenašla.')
            if row['state'] != 'queued':
                raise HTTPException(409, 'Prevzatú aktualizáciu už nemožno prerušiť z aplikácie.')
            c.execute("UPDATE firmware_updates SET state='cancelled',message='Zrušené pred prevzatím.',updated_at=? WHERE id=?", (time.time(), identifier))
        return {'ok': True}

    @app.post('/api/agent/firmware/check')
    def check(body: Check, agent: str = Depends(device)):
        with transaction() as c:
            active(c)
            if body.result_id:
                row = c.execute('SELECT * FROM firmware_updates WHERE id=? AND agent_id=?', (body.result_id, agent)).fetchone()
                if row and row['state'] in ACTIVE + ('unknown',):
                    if body.error:
                        c.execute("UPDATE firmware_updates SET state='failed',message=?,updated_at=? WHERE id=?", ('ESP32: ' + body.error, time.time(), row['id']))
                    elif body.boot_sha256 == row['sha256']:
                        c.execute("UPDATE firmware_updates SET state='succeeded',message='Nový firmvér sa spustil a overil kontrolný súčet.',updated_at=? WHERE id=?", (time.time(), row['id']))
                # Acknowledgement is explicit; the device may clear its result journal.
                acknowledged = bool(row and (body.error or body.boot_sha256 == row['sha256']))
            else:
                acknowledged = False
            row = c.execute("SELECT u.*,r.version,r.size FROM firmware_updates u JOIN firmware_releases r USING(sha256) WHERE u.agent_id=? AND u.state='queued' ORDER BY u.created_at LIMIT 1", (agent,)).fetchone()
            if not row or body.layout != LAYOUT:
                return {'update': None, 'acknowledged': acknowledged}
            if c.execute("SELECT 1 FROM jobs WHERE status IN ('queued','leased','printing') LIMIT 1").fetchone():
                return {'update': None, 'acknowledged': acknowledged}
            c.execute("UPDATE firmware_updates SET state='installing',message='ESP32 sťahuje a overuje firmvér.',updated_at=? WHERE id=?", (time.time(), row['id']))
            return {'acknowledged': acknowledged, 'update': {'id': row['id'], 'version': row['version'], 'sha256': row['sha256'], 'size': row['size'], 'path': '/api/agent/firmware/' + row['id'] + '/image'}}

    @app.get('/api/agent/firmware/{identifier}/image')
    def download(identifier: str, agent: str = Depends(device)):
        with transaction() as c:
            active(c)
            row = c.execute("SELECT r.image FROM firmware_updates u JOIN firmware_releases r USING(sha256) WHERE u.id=? AND u.agent_id=? AND u.state='installing'", (identifier, agent)).fetchone()
            if not row:
                raise HTTPException(404, 'Aktualizácia nie je dostupná pre toto zariadenie.')
            return Response(bytes(row['image']), media_type='application/octet-stream', headers={'Cache-Control': 'no-store'})
