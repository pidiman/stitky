import base64
import io
import struct
import sqlite3

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from main import create_app
from brother import MEDIA

A={"Authorization":"Bearer "+"a"*32}
D={"Authorization":"Bearer "+"d"*32}

@pytest.fixture
def client(tmp_path):
    app=create_app({"DB_PATH":str(tmp_path/"multi.sqlite"),"ADMIN_TOKEN":"a"*32,"AGENT_TOKEN":"d"*32,"WEB_DIR":str(tmp_path/"web")})
    with TestClient(app,base_url="https://testserver") as c:yield c


def brother(client):
    r=client.post("/api/agents",headers=A,json={"name":"Brother test","printer_model":"brother_ql810w"})
    assert r.status_code==201,r.text
    data=r.json()
    return data["id"],{"Authorization":"Bearer "+data["token"]}


def decode_payload(payload):
    start=payload.index(b"\x1biz")
    info=payload[start+3:start+13]
    lines=struct.unpack("<I",info[4:8])[0]
    begin=payload.index(b"M\0",start+13)+2
    rows=[]
    for i in range(lines):
        off=begin+i*93
        assert payload[off:off+3]==b"g\0\x5a"
        rows.append(payload[off+3:off+93])
    assert payload[begin+lines*93:]==b"\x1a"
    return info,Image.frombytes("1",(720,lines),bytes(v^255 for v in b"".join(rows)))


@pytest.mark.parametrize("profile_id",list(MEDIA))
def test_native_geometry_preview_raster_pixel_equivalence_and_media(client,profile_id):
    target,headers=brother(client)
    label={"profile_id":profile_id,"length_mm":50,"text":"Brother QR","kind":"qr","qr_caption":"Popis"}
    preview=client.post("/api/preview",headers=A,json=label)
    assert preview.status_code==200,preview.text
    picture=Image.open(io.BytesIO(preview.content)).convert("1")
    media=MEDIA[profile_id];page,lines=media.geometry(50)
    assert picture.size==(page,media.width_dots)
    result=client.post("/api/jobs",headers=A,json={**label,"agent_id":target,"idempotency_key":"brother-native-"+profile_id})
    assert result.status_code==201,result.text
    claim=client.post("/api/agent/claim",headers=headers).json()
    assert claim["format"]=="brother-raster-v1" and "raster_base64" not in claim
    assert claim["width"]==720 and claim["height"]==lines
    payload=client.get(claim["payload_path"],headers={**headers,"X-Lease-Token":claim["lease_token"]})
    assert payload.status_code==200
    assert len(payload.content)==claim["size"]<250000
    info,head=decode_payload(payload.content)
    assert info[:4]==bytes([0xce,10 if media.continuous else 11,media.width_mm,media.media_length_mm])
    # Reverse printer pin ordering and feed rotation: exactly the same printable preview pixels.
    logical=head.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    offset=720-media.printable_dots-media.right_pins
    canvas=logical.crop((offset,0,offset+media.printable_dots,lines)).transpose(Image.Transpose.ROTATE_270)
    y=(media.width_dots-media.printable_dots)//2
    assert canvas.tobytes()==picture.crop((35,y,35+lines,y+media.printable_dots)).tobytes()
    assert logical.crop((0,0,offset,lines)).getextrema()==(255,255) if offset else True


def test_ipp_raster_starts_with_documented_invalidate_initialize_mode_sequence(client):
    target, headers = brother(client)
    assert client.post('/api/jobs', headers=A, json={
        'agent_id': target, 'profile_id': 'brother_29', 'text': 'Wire test',
        'idempotency_key': 'brother-ipp-initialization'
    }).status_code == 201
    claim = client.post('/api/agent/claim', headers=headers).json()
    payload = client.get(claim['payload_path'], headers={
        **headers, 'X-Lease-Token': claim['lease_token']
    }).content
    # Brother Raster Command Reference, print data overview (p. 5).
    assert payload[:406] == bytes(400) + bytes.fromhex('1b401b696101')
    decode_payload(payload)


def test_payload_auth_lease_isolation_and_target_validation(client):
    target,headers=brother(client)
    request={"text":"test","profile_id":"brother_29","agent_id":target,"idempotency_key":"brother-isolation"}
    assert client.post("/api/jobs",headers=A,json={**request,"agent_id":"esp32-01"}).status_code==422
    assert client.post("/api/jobs",headers=A,json={**request,"profile_id":"p15_40x12"}).status_code==422
    assert client.post("/api/jobs",headers=A,json=request).status_code==201
    assert client.post("/api/agent/claim",headers=D).status_code==204
    claim=client.post("/api/agent/claim",headers=headers).json();path=claim["payload_path"]
    assert client.get(path).status_code==401
    assert client.get(path,headers={**D,"X-Lease-Token":claim["lease_token"]}).status_code==404
    assert client.get(path,headers={**headers,"X-Lease-Token":"wrong"}).status_code==409
    lease={"lease_token":claim["lease_token"]}
    assert client.post("/api/agent/jobs/"+claim["id"]+"/start",headers=headers,json=lease).status_code==200
    assert client.get(path,headers={**headers,"X-Lease-Token":claim["lease_token"]}).status_code==409
    assert client.post("/api/agent/jobs/"+claim["id"]+"/complete",headers=headers,json={**lease,"outcome":"unknown"}).status_code==200
    assert client.post("/api/agent/claim",headers=headers).status_code==204


@pytest.mark.parametrize("cut",[True,False])
def test_cut_flags_and_profile_metadata_persist(client,cut):
    target,headers=brother(client)
    body={"profile_id":"brother_29","length_mm":75,"auto_cut":cut,"kind":"qr","text":"TEST","qr_caption":"QR"}
    assert client.post("/api/templates",headers=A,json={**body,"name":"Brother"}).status_code==201
    template=client.get("/api/templates",headers=A).json()[0]
    assert {k:template[k] for k in body}==body
    job_body={**body,"agent_id":target,"idempotency_key":"cut-test-key"}
    response=client.post("/api/jobs",headers=A,json=job_body);assert response.status_code==201
    assert client.post("/api/jobs",headers=A,json=job_body).json()==response.json()
    assert client.post("/api/jobs",headers=A,json={**job_body,"auto_cut":not cut}).status_code==409
    claim=client.post("/api/agent/claim",headers=headers).json()
    payload=client.get(claim["payload_path"],headers={**headers,"X-Lease-Token":claim["lease_token"]}).content
    assert b"\x1biM"+bytes([64 if cut else 0]) in payload[:460]
    assert b"\x1biK"+bytes([8 if cut else 0]) in payload[:460]
    assert b"\x1bid\x23\0" in payload[:460]


def test_p15_claim_and_migration_defaults_remain_unchanged(client):
    with sqlite3.connect(client.app.state.db_path) as db:
        assert db.execute("select printer_model from agents where id='esp32-01'").fetchone()[0]=="p15"
    response=client.post("/api/jobs",headers=A,json={"text":"P15","agent_id":"esp32-01","idempotency_key":"p15-legacy-safe"})
    assert response.status_code==201
    claim=client.post("/api/agent/claim",headers=D).json()
    assert (claim["width"],claim["height"])==(96,320)
    assert len(base64.b64decode(claim["raster_base64"]))==3840
    assert "format" not in claim and "payload_path" not in claim


@pytest.mark.parametrize("fields",[
    {"profile_id":"other"},{"profile_id":"brother_29","length_mm":19},
    {"profile_id":"brother_29","length_mm":201},{"profile_id":"brother_29","length_mm":50.5},
    {"profile_id":"brother_29","auto_cut":"yes"},
])
def test_profile_validation(client,fields):
    assert client.post("/api/preview",headers=A,json={"text":"ok",**fields}).status_code==422


def test_catalog_and_telemetry(client):
    profiles=client.get("/api/profiles",headers=A).json()
    assert len(profiles)==5 and {p["dpi"] for p in profiles}=={203,300}
    target,headers=brother(client)
    r=client.post("/api/agent/telemetry",headers=headers,json={"printer_checked":True,"printer_connected":True,"model":"Brother QL-810W","media_ready":"roll_current_29x0mm","printer_status":"ready"})
    assert r.status_code==200,r.text
    row=next(a for a in client.get("/api/agents",headers=A).json() if a["id"]==target)
    assert row["printer_model"]=="brother_ql810w"
    assert row["telemetry"]["media_ready"]=="roll_current_29x0mm"

    assert client.post("/api/agent/telemetry",headers=headers,json={"printer_checked":True,"printer_connected":False}).status_code==200
    row=next(a for a in client.get("/api/agents",headers=A).json() if a["id"]==target)
    assert row["telemetry"]["media_ready"] is None
