"""QR captions must share preview/print pixels and preserve scanner quiet zones."""
import base64
import hashlib
import io
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from main import create_app

ADMIN = {"Authorization": "Bearer " + "a" * 32}
DEVICE = {"Authorization": "Bearer " + "d" * 32}
PAYLOAD = "https://example.com"


def make_app(tmp_path):
    return create_app({
        "DB_PATH": str(tmp_path / "caption.sqlite"),
        "ADMIN_TOKEN": "a" * 32, "AGENT_TOKEN": "d" * 32,
        "WEB_DIR": str(tmp_path / "web"),
    })


@pytest.fixture
def client(tmp_path):
    with TestClient(make_app(tmp_path), base_url="https://testserver") as c:
        yield c


def preview(client, **fields):
    response = client.post("/api/preview", headers=ADMIN, json={
        "kind": "qr", "text": PAYLOAD, **fields,
    })
    assert response.status_code == 200, response.text
    return Image.open(io.BytesIO(response.content)).convert("1")


def test_caption_keeps_full_qr_and_gap_and_exact_print_raster(client):
    plain = preview(client)
    captioned = preview(client, qr_caption="Wi-Fi pre hostí\nNaskenuj ma")
    assert captioned.size == (320, 96)
    # Moving the entire 96-dot QR region keeps every module and its quiet zone.
    assert captioned.crop((0, 0, 96, 96)).tobytes() == plain.crop((112, 0, 208, 96)).tobytes()
    assert captioned.crop((96, 0, 120, 96)).getextrema() == (255, 255)
    assert ImageChops.invert(captioned.crop((120, 12, 308, 84))).getbbox()
    assert captioned.crop((108, 0, 320, 12)).getextrema() == (255, 255)
    assert captioned.crop((308, 0, 320, 96)).getextrema() == (255, 255)
    job = client.post("/api/jobs", headers=ADMIN, json={
        "kind": "qr", "text": PAYLOAD, "qr_caption": "Wi-Fi pre hostí\nNaskenuj ma",
        "agent_id": "esp32-01", "idempotency_key": "caption-raster-123",
    })
    assert job.status_code == 201
    claim = client.post("/api/agent/claim", headers=DEVICE).json()
    assert base64.b64decode(claim["raster_base64"]) == bytes(
        value ^ 255 for value in captioned.transpose(Image.Transpose.ROTATE_270).tobytes()
    )


@pytest.mark.parametrize("style", [
    {"font": "sans"}, {"font": "sans-bold"}, {"font": "serif"},
    {"font": "mono"}, {"font": "pixel", "qr_caption": "QR LABEL"},
    {"align": "left", "bold": True, "italic": True, "underline": True,
     "letter_spacing": 1, "line_spacing": 3},
])
def test_caption_fonts_styles_and_bounds(client, style):
    image = preview(client, **({"qr_caption": "Popis QR", **style}))
    assert ImageChops.invert(image.crop((108, 0, 320, 96))).getbbox()
    assert image.crop((96, 0, 120, 96)).getextrema() == (255, 255)


def test_caption_template_job_restart_and_request_conflict(tmp_path):
    body = {"kind": "qr", "text": PAYLOAD, "qr_caption": "  Popis\nQR  ",
            "font": "serif", "bold": True}
    request = {**body, "agent_id": "esp32-01", "idempotency_key": "caption-save-123"}
    with TestClient(make_app(tmp_path), base_url="https://testserver") as client:
        job = client.post("/api/jobs", headers=ADMIN, json=request).json()[0]
        assert job["qr_caption"] == "Popis\nQR"
        assert client.post("/api/templates", headers=ADMIN, json={**body, "name": "QR s popisom"}).status_code == 201
    with TestClient(make_app(tmp_path), base_url="https://testserver") as client:
        template = client.get("/api/templates", headers=ADMIN).json()[0]
        assert template["qr_caption"] == "Popis\nQR"
        assert template["font"] == "serif" and template["bold"] is True
        restored = client.post("/api/preview", headers=ADMIN, json=template)
        assert restored.status_code == 200
        assert client.post("/api/jobs", headers=ADMIN, json=request).json()[0]["id"] == job["id"]
        changed = client.post("/api/jobs", headers=ADMIN, json={**request, "qr_caption": "Iný popis"})
        assert changed.status_code == 409


@pytest.mark.parametrize("fields", [
    {"qr_caption": "x" * 121},
    {"qr_caption": "1\n2\n3\n4\n5"},
    {"qr_caption": "bad\x00text"},
    {"qr_caption": "Text", "kind": "text"},
    {"qr_caption": "W" * 30, "font_size": 64},
    {"qr_caption": "Diakritika š", "font": "pixel"},
    {"qr_caption": "Popis", "border": True},
    {"qr_caption": "Popis", "invert": True},
])
def test_caption_rejects_invalid_or_overflowing_content(client, fields):
    response = client.post("/api/preview", headers=ADMIN, json={
        "kind": "qr", "text": PAYLOAD, **fields,
    })
    assert response.status_code == 422, response.text


def test_blank_caption_keeps_original_layout_and_legacy_idempotency(client):
    assert preview(client, qr_caption=" \n ").tobytes() == preview(client).tobytes()
    request = {"kind": "qr", "text": PAYLOAD, "agent_id": "esp32-01",
               "idempotency_key": "legacy-qr-123"}
    created = client.post("/api/jobs", headers=ADMIN, json=request).json()[0]
    # Persist the exact pre-caption request shape, as an existing deployment would.
    legacy = {"text": PAYLOAD, "kind": "qr", "font_size": 0,
              "agent_id": "esp32-01", "copies": 1}
    fingerprint = hashlib.sha256(json.dumps(legacy, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with sqlite3.connect(client.app.state.db_path) as db:
        db.execute("UPDATE requests SET fingerprint=?", (fingerprint,))
        db.execute("UPDATE jobs SET style_json='{}'")
    response = client.post("/api/jobs", headers=ADMIN, json={**request, "qr_caption": ""})
    assert response.status_code == 201
    assert response.json()[0]["id"] == created["id"]
    assert response.json()[0]["qr_caption"] == ""
