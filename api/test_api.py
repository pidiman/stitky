import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from main import create_app

ADMIN = "admin-" + "a" * 32
DEVICE = "device-" + "b" * 32
A = {"Authorization": "Bearer " + ADMIN}
D = {"Authorization": "Bearer " + DEVICE}


@pytest.fixture
def api(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "queue.sqlite"), "ADMIN_TOKEN": ADMIN,
                      "AGENT_TOKEN": DEVICE, "AGENT_ID": "esp32-01", "WEB_DIR": str(tmp_path / "web")})
    with TestClient(app) as client:
        yield client


def enqueue(client, **overrides):
    body = {"text": "USB-C -> USB-C", "font_size": 0, "agent_id": "esp32-01", "copies": 1,
            "idempotency_key": "test-request-0001"}
    body.update(overrides)
    return client.post("/api/jobs", headers=A, json=body)


def claim(client, headers=D):
    return client.post("/api/agent/claim", headers=headers)


def start(client, job, headers=D):
    return client.post(f"/api/agent/jobs/{job['id']}/start", headers=headers,
                       json={"lease_token": job["lease_token"]})


def finish(client, job, outcome="printed", headers=D):
    return client.post(f"/api/agent/jobs/{job['id']}/complete", headers=headers,
                       json={"lease_token": job["lease_token"], "outcome": outcome, "message": "test"})


def force_expired(client, job_id):
    with sqlite3.connect(client.app.state.db_path) as conn:
        conn.execute("UPDATE jobs SET lease_expires=0 WHERE id=?", (job_id,))


def test_auth_and_no_api_spa_fallback(api):
    assert api.get("/api/health").json() == {"ok": True}
    assert api.get("/api/jobs").status_code == 401
    assert api.get("/api/jobs", headers=D).status_code == 401
    assert claim(api, A).status_code == 401
    assert api.get("/api/nonexistent").status_code == 404
    assert api.post("/api/preview", json={"text": "x"}).status_code == 401


def test_preview_and_printer_use_exact_same_pixels(api):
    preview = api.post("/api/preview", headers=A, json={"text": "USB-C -> USB-C"})
    assert preview.status_code == 200
    image = Image.open(io.BytesIO(preview.content))
    assert image.size == (320, 96)
    assert enqueue(api).status_code == 201
    job = claim(api).json()
    raw = base64.b64decode(job["raster_base64"], validate=True)
    assert len(raw) == 3840
    assert hashlib.sha256(raw).hexdigest() == job["sha256"]
    assert (job["width"], job["height"]) == (96, 320)
    inverse = bytes(b ^ 255 for b in raw)
    assert image.transpose(Image.Transpose.ROTATE_270).tobytes() == inverse
    # Bounding box centered in the full 40x12mm logical label.
    ink = image.convert("L").point(lambda p: 255 - p)
    x0, y0, x1, y1 = ink.getbbox()
    assert abs((x0 + x1) - 320) <= 2
    assert abs((y0 + y1) - 96) <= 2


def test_job_request_idempotency_and_copies(api):
    one = enqueue(api, copies=3)
    assert one.status_code == 201
    ids = [j["id"] for j in one.json()]
    assert len(set(ids)) == 3
    assert [j["id"] for j in enqueue(api, copies=3).json()] == ids
    assert enqueue(api, copies=2).status_code == 409
    assert len(api.get("/api/jobs", headers=A).json()) == 3


def test_atomic_claim_and_start(api):
    enqueue(api, copies=2)
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: claim(api).json(), range(6)))
    assert len({j["id"] for j in claims}) == 1
    assert len({j["lease_token"] for j in claims}) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        starts = list(pool.map(lambda _: start(api, claims[0]).status_code, range(2)))
    assert sorted(starts) == [200, 409]
    assert claim(api).status_code == 204  # no concurrent work while printing
    assert finish(api, claims[0]).status_code == 200
    assert finish(api, claims[0]).status_code == 200
    assert finish(api, claims[0], "failed").status_code == 409
    assert claim(api).json()["id"] != claims[0]["id"]


def test_expired_unstarted_lease_requeues_with_new_token(api):
    enqueue(api)
    first = claim(api).json()
    force_expired(api, first["id"])
    second = claim(api).json()
    assert first["id"] == second["id"]
    assert first["lease_token"] != second["lease_token"]
    assert start(api, first).status_code == 409
    assert start(api, second).status_code == 200


def test_expired_printing_never_requeues_and_cannot_override_terminal(api):
    enqueue(api)
    job = claim(api).json()
    assert start(api, job).status_code == 200
    force_expired(api, job["id"])
    assert claim(api).status_code == 204
    assert api.get("/api/jobs", headers=A).json()[0]["status"] == "unknown"
    assert finish(api, job, "unknown").status_code == 200
    assert finish(api, job, "printed").status_code == 409


def test_device_isolation_and_token_hashing(api):
    response = api.post("/api/agents", headers=A, json={"name": "Second LAN"})
    assert response.status_code == 201
    other = response.json()
    other_headers = {"Authorization": "Bearer " + other["token"]}
    enqueue(api)
    job = claim(api).json()
    assert claim(api, other_headers).status_code == 204
    assert start(api, job, other_headers).status_code == 404
    assert finish(api, job, "unknown", other_headers).status_code == 404
    assert enqueue(api, agent_id=other["id"], idempotency_key="other-agent-request").status_code == 201
    assert claim(api, other_headers).status_code == 200
    with sqlite3.connect(api.app.state.db_path) as conn:
        stored = [r[0] for r in conn.execute("SELECT token_hash FROM agents")]
    assert DEVICE not in stored and other["token"] not in stored
    assert hashlib.sha256(other["token"].encode()).hexdigest() in stored
    agents = api.get("/api/agents", headers=A).json()
    assert len(agents) == 2 and all(a["status"] == "online" for a in agents)
    assert all("token" not in a and "token_hash" not in a for a in agents)


def test_prestart_failure_or_unknown_can_quarantine_but_not_print(api):
    enqueue(api)
    job = claim(api).json()
    assert finish(api, job).status_code == 409
    assert finish(api, job, "unknown").status_code == 200
    assert start(api, job).status_code == 409
    assert claim(api).status_code == 204


def test_cancellation_and_templates(api):
    job = enqueue(api).json()[0]
    assert api.post(f"/api/jobs/{job['id']}/cancel", headers=A).status_code == 200
    assert claim(api).status_code == 204
    job2 = enqueue(api, idempotency_key="request-2").json()[0]
    claim(api)
    assert api.post(f"/api/jobs/{job2['id']}/cancel", headers=A).status_code == 409
    template = api.post("/api/templates", headers=A, json={"name": "Cable", "text": "USB-C -> USB-C", "font_size": 20})
    assert template.status_code == 201
    assert api.get("/api/templates", headers=A).json() == [template.json()]
    assert api.delete("/api/templates/" + template.json()["id"], headers=A).status_code == 200
    assert api.get("/api/templates", headers=A).json() == []


@pytest.mark.parametrize("change", [{"text": " "}, {"text": "x" * 201}, {"font_size": 5}, {"font_size": 65}, {"copies": 0}, {"copies": 11}, {"text": "x\x00y"}, {"text": "line\n" * 5}, {"text": "W" * 200, "font_size": 64}])
def test_invalid_label_does_not_queue(api, change):
    assert enqueue(api, **change).status_code == 422
    assert api.get("/api/jobs", headers=A).json() == []


def test_jobs_survive_app_restart(tmp_path):
    config = {"DB_PATH": str(tmp_path / "persist.sqlite"), "ADMIN_TOKEN": ADMIN, "AGENT_TOKEN": DEVICE}
    with TestClient(create_app(config)) as first:
        enqueue(first)
        job = claim(first).json()
        assert start(first, job).status_code == 200
    with TestClient(create_app(config)) as second:
        assert claim(second).status_code == 204
        assert second.get("/api/jobs", headers=A).json()[0]["status"] == "printing"
        assert finish(second, job).status_code == 200


def test_original_pixel_print_is_bit_exact(api):
    # Digest of the actual JOB003 raster sent to the printer and accepted by user.
    assert enqueue(api, font='pixel', font_size=21).status_code == 201
    job = claim(api).json()
    assert job['sha256'] == '787b91633d53802049aeeb6f43255b03435d9fe242a84e8137589f41555e9196'


@pytest.mark.parametrize('family', ['sans', 'sans-bold', 'serif', 'mono', 'pixel'])
def test_each_font_preview_matches_queued_raster(api, family):
    body = {'text': 'USB-C -> USB-C', 'font': family, 'font_size': 0}
    preview = api.post('/api/preview', headers=A, json=body)
    assert preview.status_code == 200
    assert enqueue(api, **body).status_code == 201
    job = claim(api).json()
    image = Image.open(io.BytesIO(preview.content))
    assert bytes(b ^ 255 for b in image.transpose(Image.Transpose.ROTATE_270).tobytes()) == base64.b64decode(job['raster_base64'])


def test_font_validation_and_template_persistence(api):
    assert api.post('/api/preview', headers=A, json={'text': 'x', 'font': '../../font'}).status_code == 422
    assert api.post('/api/preview', headers=A, json={'text': 'Štítok', 'font': 'pixel'}).status_code == 422
    saved = api.post('/api/templates', headers=A, json={'name': 'Pixel cable', 'text': 'USB-C', 'font': 'pixel', 'font_size': 21})
    assert saved.status_code == 201 and saved.json()['font'] == 'pixel'
    assert api.get('/api/templates', headers=A).json()[0]['font'] == 'pixel'
    assert enqueue(api, font='pixel', font_size=21).status_code == 201
    assert enqueue(api, font='mono', font_size=21).status_code == 409


def test_font_migration_preserves_existing_labels(tmp_path):
    config = {'DB_PATH': str(tmp_path / 'old.sqlite'), 'ADMIN_TOKEN': ADMIN, 'AGENT_TOKEN': DEVICE}
    with TestClient(create_app(config)) as client:
        original = enqueue(client).json()[0]['id']
        saved = client.post('/api/templates', headers=A, json={'name': 'Existing', 'text': 'USB-C'}).json()['id']
    # Reproduce the exact pre-font column layout, retaining rows and request keys.
    with sqlite3.connect(config['DB_PATH']) as conn:
        conn.execute('ALTER TABLE jobs DROP COLUMN font')
        conn.execute('ALTER TABLE templates DROP COLUMN font')
    with TestClient(create_app(config)) as client:
        jobs = client.get('/api/jobs', headers=A).json()
        assert jobs[0]['id'] == original and jobs[0]['font'] == 'sans'
        templates = client.get('/api/templates', headers=A).json()
        assert templates[0]['id'] == saved and templates[0]['font'] == 'sans'
        assert enqueue(client).json()[0]['id'] == original


@pytest.mark.parametrize('family',['sans','sans-bold','serif','mono','pixel'])
@pytest.mark.parametrize('style',[{'align':'left'}, {'align':'right'}, {'bold':True}, {'italic':True}, {'underline':True}, {'letter_spacing':2}, {'line_spacing':9}, {'border':True}, {'invert':True}])
def test_style_preview_and_job_raster_agree(api,family,style):
    body={'text':'USB\nCABLE','font':family,'font_size':14 if family=='pixel' else 20,**style}
    preview=api.post('/api/preview',headers=A,json=body)
    assert preview.status_code==200,preview.text if preview.status_code!=200 else ''
    image=Image.open(io.BytesIO(preview.content))
    response=enqueue(api,**body)
    assert response.status_code==201
    for key,value in style.items():assert response.json()[0][key]==value
    raw=base64.b64decode(claim(api).json()['raster_base64'])
    assert bytes(b^255 for b in image.transpose(Image.Transpose.ROTATE_270).tobytes())==raw


def test_alignment_and_decorations_change_actual_pixels(api):
    def image(**style):
        response=api.post('/api/preview',headers=A,json={'text':'USB','font_size':21,'font':'pixel',**style})
        assert response.status_code==200
        return Image.open(io.BytesIO(response.content)).convert('L')
    left=image(align='left');right=image(align='right');center=image()
    ink=lambda im:im.point(lambda p:255-p).getbbox()
    assert ink(left)[0]==12
    assert ink(right)[2]==308
    assert abs(sum(ink(center)[::2])-320)<=2
    assert image(bold=True).tobytes()!=center.tobytes()
    assert image(italic=True).tobytes()!=center.tobytes()
    assert image(underline=True).tobytes()!=center.tobytes()
    inverted=image(invert=True)
    assert bytes(255-v for v in center.tobytes())==inverted.tobytes()
    assert image(border=True).getpixel((10,3))==0


@pytest.mark.parametrize('family',['sans','sans-bold','serif','mono','pixel'])
def test_curated_icons_render_for_each_font_without_tofu(api,family):
    from rendering import SYMBOLS
    # Every symbol is rendered from an authored monochrome glyph, independent of
    # installed Unicode font coverage; they must produce distinct ink patterns.
    hashes=set()
    for icon in SYMBOLS:
        result=api.post('/api/preview',headers=A,json={'text':icon,'font':family,'font_size':21})
        assert result.status_code==200
        image=Image.open(io.BytesIO(result.content)).convert('L')
        assert image.point(lambda p:255-p).getbbox()
        hashes.add(hashlib.sha256(image.tobytes()).hexdigest())
    assert len(hashes)==len(SYMBOLS)
    assert api.post('/api/preview',headers=A,json={'text':'🦄','font':family}).status_code==422


def test_styles_survive_templates_and_change_idempotency(api):
    style={'align':'right','bold':True,'italic':True,'underline':True,'line_spacing':6,'letter_spacing':1,'border':True,'invert':True}
    body={'text':'Cable','font_size':14,**style}
    saved=api.post('/api/templates',headers=A,json={'name':'Styled',**body})
    assert saved.status_code==201
    listed=api.get('/api/templates',headers=A).json()[0]
    assert saved.json()==listed
    for key,value in style.items():assert listed[key]==value
    assert enqueue(api,**body).status_code==201
    assert enqueue(api,**body).status_code==201
    assert enqueue(api,**{**body,'italic':False}).status_code==409


@pytest.mark.parametrize('style',[{'align':'bottom'},{'line_spacing':-1},{'line_spacing':17},{'letter_spacing':7}])
def test_invalid_style_rejected(api,style):
    assert enqueue(api,**style).status_code==422


def test_old_style_schema_migration_and_idempotency(tmp_path):
    import json
    config={'DB_PATH':str(tmp_path/'old-style.sqlite'),'ADMIN_TOKEN':ADMIN,'AGENT_TOKEN':DEVICE}
    body={'text':'USB-C -> USB-C','font_size':0,'agent_id':'esp32-01','copies':1,'idempotency_key':'legacy-style-request'}
    with TestClient(create_app(config)) as client:
        identifier=client.post('/api/jobs',headers=A,json=body).json()[0]['id']
        client.post('/api/templates',headers=A,json={'name':'Old','text':'USB'})
    with sqlite3.connect(config['DB_PATH']) as conn:
        conn.execute('ALTER TABLE jobs DROP COLUMN style_json')
        conn.execute('ALTER TABLE templates DROP COLUMN style_json')
        for col in ('telemetry_json','telemetry_received_at','printer_checked_at','refresh_requested','paused'):
            conn.execute(f'ALTER TABLE agents DROP COLUMN {col}')
        # Pre-style, pre-telemetry request fingerprint must remain valid.
        old={k:v for k,v in body.items() if k!='idempotency_key'}
        conn.execute('UPDATE requests SET fingerprint=?',(hashlib.sha256(json.dumps(old,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),))
    with TestClient(create_app(config)) as client:
        result=client.post('/api/jobs',headers=A,json=body)
        assert result.status_code==201 and result.json()[0]['id']==identifier
        assert result.json()[0]['align']=='center' and not result.json()[0]['bold']
        assert client.get('/api/templates',headers=A).json()[0]['line_spacing']==4
        agent=client.get('/api/agents',headers=A).json()[0]
        assert agent['telemetry']=={} and agent['telemetry_received_at'] is None and not agent['paused']


def test_telemetry_auth_device_isolation_and_refresh(api):
    assert api.post('/api/agent/telemetry',json={}).status_code==401
    assert api.post('/api/agent/telemetry',headers=A,json={}).status_code==401
    other=api.post('/api/agents',headers=A,json={'name':'Elsewhere'}).json()
    other_headers={'Authorization':'Bearer '+other['token']}
    report={'firmware_version':'1.2.0','wifi_rssi':-58,'uptime_s':42,'free_heap':120000,'printer_checked':True,'printer_connected':True,'model':'P15','firmware':'1.0.18','serial':'12345','battery_percent':77,'printer_status':'ready'}
    assert api.post('/api/agent/telemetry',headers=D,json=report).status_code==200
    entries={a['id']:a for a in api.get('/api/agents',headers=A).json()}
    assert entries['esp32-01']['telemetry']==report
    assert entries[other['id']]['telemetry']=={}
    checked=entries['esp32-01']['printer_checked_at']
    assert checked and entries['esp32-01']['telemetry_received_at']
    assert api.post('/api/agents/esp32-01/refresh',headers=other_headers).status_code==401
    assert api.post('/api/agents/missing/refresh',headers=A).status_code==404
    assert api.post('/api/agents/esp32-01/refresh',headers=A).status_code==200
    assert claim(api).headers['X-Printer-Refresh']=='1'
    assert claim(api).headers['X-Printer-Refresh']=='1'  # Not consumed by poll.
    assert api.post('/api/agent/telemetry',headers=D,json={'wifi_rssi':-60,'printer_checked':False}).status_code==200
    entry=next(a for a in api.get('/api/agents',headers=A).json() if a['id']=='esp32-01')
    assert entry['printer_checked_at']==checked and entry['telemetry']['battery_percent']==77
    assert claim(api).headers['X-Printer-Refresh']=='1'
    assert api.post('/api/agent/telemetry',headers=D,json={'printer_checked':True,'printer_connected':False,'last_error':'BLE unavailable'}).status_code==200
    entry=next(a for a in api.get('/api/agents',headers=A).json() if a['id']=='esp32-01')
    assert entry['telemetry']['battery_percent'] is None and entry['telemetry']['printer_status'] is None
    assert entry['telemetry']['model']=='P15'
    assert 'X-Printer-Refresh' not in claim(api).headers


@pytest.mark.parametrize('report',[{'battery_percent':101},{'battery_percent':-1},{'battery_percent':True},{'wifi_rssi':20},{'uptime_s':-1},{'free_heap':-1},{'model':'x'*97},{'serial':'x\nSECRET'},{'agent_id':'another'},{'printer_status':'out_of_ink'},{'printer_connected':'yes'}])
def test_invalid_telemetry_does_not_store(api,report):
    assert api.post('/api/agent/telemetry',headers=D,json=report).status_code==422
    assert api.get('/api/agents',headers=A).json()[0]['telemetry']=={}


def test_refresh_waits_until_queue_empty(api):
    api.post('/api/agents/esp32-01/refresh',headers=A)
    enqueue(api)
    job=claim(api).json()
    assert start(api,job).status_code==200
    assert 'X-Printer-Refresh' not in claim(api).headers
    finish(api,job)
    assert claim(api).headers['X-Printer-Refresh']=='1'


def test_pause_prevents_claim_but_allows_existing_lease_to_finish(api):
    enqueue(api,copies=2)
    job=claim(api).json()
    assert api.post('/api/agents/esp32-01/pause',headers=D,json={'paused':True}).status_code==401
    assert api.post('/api/agents/missing/pause',headers=A,json={'paused':True}).status_code==404
    assert api.post('/api/agents/esp32-01/pause',headers=A,json={'paused':'yes'}).status_code==422
    assert api.post('/api/agents/esp32-01/pause',headers=A,json={'paused':True}).status_code==200
    assert api.get('/api/agents',headers=A).json()[0]['paused']
    assert claim(api).status_code==204
    assert start(api,job).status_code==200
    assert finish(api,job).status_code==200
    assert claim(api).status_code==204
    assert api.post('/api/agents/esp32-01/pause',headers=A,json={'paused':False}).status_code==200
    assert claim(api).status_code==200


@pytest.mark.parametrize('source,target',[('🙂','☺'),('😊','☺'),('😀','☺'),('🙁','☹'),('❤','♥'),('⭐','★'),('✅','✓'),('❌','✕'),('⚠️','⚠'),('♥︎','♥')])
def test_common_emoji_aliases_preserve_text_and_render_symbols(api,source,target):
    def preview(text):return api.post('/api/preview',headers=A,json={'text':text,'font':'pixel','font_size':21})
    actual=preview(source);expected=preview(target)
    assert actual.status_code==200 and actual.content==expected.content
    saved=api.post('/api/templates',headers=A,json={'name':'Emoji','text':source,'font':'pixel','font_size':21})
    assert saved.status_code==201 and saved.json()['text']==source


@pytest.mark.parametrize('text',['x️','🙂\u200d🙂','⚠️️'])
def test_unsupported_emoji_composition_rejected(api,text):
    assert api.post('/api/preview',headers=A,json={'text':text}).status_code==422
