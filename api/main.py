"""Authenticated, durable queue for a deliberately at-most-once P15 bridge."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
import uuid
import qrcode
from contextlib import contextmanager, asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field, field_validator

try:
    from .brother import render_brother, profile_catalog, model_for_profile, job_geometry, MEDIA
    from .accounts import install as install_accounts
    from . import firmware_updates
    from .rendering import render_canvas, STYLE_DEFAULTS, style_dict
except ImportError:
    from brother import render_brother, profile_catalog, model_for_profile, job_geometry, MEDIA
    from accounts import install as install_accounts
    import firmware_updates
    from rendering import render_canvas, STYLE_DEFAULTS, style_dict

LEASE_SECONDS = 90
TERMINAL = {"printed", "failed", "unknown", "cancelled"}


def utc(ts: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc).isoformat()


def digest(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


class Label(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    kind: Literal["text", "qr"] = "text"
    qr_caption: str = Field(default="", max_length=120)
    profile_id: Literal["p15_40x12", "brother_29", "brother_62", "brother_29x90", "brother_62x100"] = "p15_40x12"
    length_mm: int = Field(default=50, ge=20, le=200, strict=True)
    auto_cut: bool = Field(default=True, strict=True)
    font_size: int = Field(default=0, ge=0, le=64)
    font: Literal["sans", "sans-bold", "serif", "mono", "pixel"] = "sans"
    align: Literal["left", "center", "right"] = "center"
    bold: bool = False
    italic: bool = False
    underline: bool = False
    line_spacing: int = Field(default=4, ge=0, le=16)
    letter_spacing: int = Field(default=0, ge=0, le=6)
    border: bool = False
    invert: bool = False

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 and c != "\n" for c in value):
            raise ValueError("Text must contain printable characters")
        if len(value.splitlines()) > 4:
            raise ValueError("At most four lines are supported")
        return value

    @field_validator("qr_caption")
    @classmethod
    def validate_caption(cls, value: str) -> str:
        if any(ord(c) < 32 and c != "\n" for c in value):
            raise ValueError("Popis QR musí obsahovať iba tlačiteľné znaky.")
        value = value.strip()
        if len(value.splitlines()) > 4:
            raise ValueError("Popis QR môže mať najviac štyri riadky.")
        return value

    @field_validator("font_size")
    @classmethod
    def validate_size(cls, value: int) -> int:
        if value and value < 6:
            raise ValueError("Font size must be 0 (auto) or 6–64")
        return value


class JobInput(Label):
    agent_id: str = Field(min_length=1, max_length=80)
    copies: int = Field(default=1, ge=1, le=10)
    idempotency_key: str = Field(min_length=8, max_length=128)


class LeaseInput(BaseModel):
    lease_token: str = Field(min_length=16, max_length=128)


class Completion(LeaseInput):
    outcome: Literal["printed", "failed", "unknown"]
    message: str = Field(default="", max_length=500)


class TemplateInput(Label):
    name: str = Field(min_length=1, max_length=80)


class AgentInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    printer_model: Literal["p15", "brother_ql810w"] = "p15"


class PauseInput(BaseModel):
    paused: bool = Field(strict=True)


class Telemetry(BaseModel):
    model_config = {"extra": "forbid"}
    ota_supported: bool | None = Field(default=None, strict=True)
    ota_layout: Literal["dual1856-v1"] | None = None
    ota_slot: int | None = Field(default=None, ge=0, le=1, strict=True)
    firmware_version: str | None = Field(default=None, max_length=64)
    wifi_rssi: int | None = Field(default=None, ge=-127, le=0, strict=True)
    uptime_s: int | None = Field(default=None, ge=0, le=2**53, strict=True)
    free_heap: int | None = Field(default=None, ge=0, le=16*1024*1024, strict=True)
    printer_connected: bool | None = Field(default=None, strict=True)
    printer_checked: bool | None = Field(default=None, strict=True)
    model: str | None = Field(default=None, max_length=96)
    firmware: str | None = Field(default=None, max_length=96)
    serial: str | None = Field(default=None, max_length=96)
    battery_percent: int | None = Field(default=None, ge=0, le=100, strict=True)
    printer_status: Literal["ready", "out_of_paper", "cover_open", "overheating", "low_battery", "cover_closed", "unknown"] | None = None
    last_error: str | None = Field(default=None, max_length=250)
    media_ready: str | None = Field(default=None, max_length=96)

    @field_validator("firmware_version", "model", "firmware", "serial", "last_error", "media_ready")
    @classmethod
    def clean_strings(cls, value):
        if value is not None and any(ord(c)<32 or ord(c)==127 for c in value):
            raise ValueError("Telemetry strings must not contain control characters")
        return value


FONT_FILES = {
    "sans": ("DejaVuSans", "Arial"),
    "sans-bold": ("DejaVuSans", "Arial"),
    "serif": ("DejaVuSerif", "Times New Roman"),
    "mono": ("DejaVuSansMono", "Courier New"),
}


def font_path(family: str = "sans", bold: bool = False, italic: bool = False) -> str:
    bold = bold or family == "sans-bold"
    stem, mac = FONT_FILES[family]
    slant = "Italic" if family == "serif" else "Oblique"
    suffix = ("-Bold" + (slant if italic else "")) if bold else ("-" + slant if italic else "")
    mac_suffix = (" Bold" if bold else "") + (" Italic" if italic else "")
    configured = os.getenv("FONT_PATH") if family == "sans" and not bold and not italic else None
    candidates = ([configured] if configured else []) + [
        f"/usr/share/fonts/truetype/dejavu/{stem}{suffix}.ttf",
        f"/System/Library/Fonts/Supplemental/{mac}{mac_suffix}.ttf"]
    for item in candidates:
        if item and Path(item).is_file():
            return item
    raise RuntimeError("Install fonts-dejavu-core to provide the selected font")


def render_label(label: Label) -> tuple[bytes, bytes]:
    try:
        if label.kind != "qr" and label.qr_caption:
            raise ValueError("Popis QR je dostupný iba pri QR štítku.")
        if label.profile_id != "p15_40x12":
            return render_brother(label, font_path)
        if label.kind == "qr":
            if label.invert or label.border:
                raise ValueError('QR kód nepodporuje inverziu ani rámik; zachovaj jeho biely okraj.')
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=4, box_size=1)
            qr.add_data(label.text); qr.make(fit=True)
            matrix=qr.get_matrix(); side=len(matrix); scale=96//side
            if scale<2:raise ValueError('QR kód je na 12 mm štítok príliš hustý. Použi kratší text alebo odkaz.')
            image=Image.new('1',(320,96),1); draw=ImageDraw.Draw(image)
            left=((96 if label.qr_caption else 320)-side*scale)//2; top=(96-side*scale)//2
            for y,row in enumerate(matrix):
                for x,black in enumerate(row):
                    if black:draw.rectangle((left+x*scale,top+y*scale,left+(x+1)*scale-1,top+(y+1)*scale-1),fill=0)
            if label.qr_caption:
                caption = label.model_copy(update={"text": label.qr_caption, "kind": "text", "qr_caption": ""})
                try:
                    caption_image = render_canvas(caption, font_path, width=212, height=96)
                except ValueError as exc:
                    raise ValueError("Popis vedľa QR: " + str(exc)) from exc
                image.paste(caption_image, (108, 0))
        else:
            image = render_canvas(label, font_path)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    preview = io.BytesIO()
    image.save(preview, format="PNG")
    raster = bytes(byte ^ 0xFF for byte in image.transpose(Image.Transpose.ROTATE_270).tobytes())
    assert len(raster) == 3840
    return preview.getvalue(), raster


def create_app(config: dict | None = None) -> FastAPI:
    config = dict(config or {})
    db_path = str(config.get("DB_PATH", os.getenv("DB_PATH", "/data/p15.sqlite3")))
    admin_token = str(config.get("ADMIN_TOKEN", os.getenv("ADMIN_TOKEN", "")))
    agent_id = str(config.get("AGENT_ID", os.getenv("AGENT_ID", "esp32-01")))
    agent_name = str(config.get("AGENT_NAME", os.getenv("AGENT_NAME", "P15 · ESP32")))
    agent_token = str(config.get("AGENT_TOKEN", os.getenv("AGENT_TOKEN", "")))
    web_dir = Path(config.get("WEB_DIR", os.getenv("WEB_DIR", str(Path(__file__).parent.parent / "web" / "dist")))).resolve()

    @contextmanager
    def transaction():
        conn = sqlite3.connect(db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize():
        if len(admin_token) < 24 or len(agent_token) < 24:
            raise RuntimeError("ADMIN_TOKEN and AGENT_TOKEN must each contain at least 24 characters")
        if hmac.compare_digest(admin_token, agent_token):
            raise RuntimeError("Use distinct admin and agent tokens")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
                last_seen REAL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
                text TEXT NOT NULL, font_size INTEGER NOT NULL, raster BLOB NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                message TEXT NOT NULL DEFAULT '', lease_token TEXT, lease_expires REAL);
            CREATE INDEX IF NOT EXISTS queue ON jobs(agent_id,status,created_at);
            CREATE TABLE IF NOT EXISTS requests (
                key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, job_ids TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS templates (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, text TEXT NOT NULL, font_size INTEGER NOT NULL);
            """)
            for table in ("jobs", "templates"):
                columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                if "font" not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN font TEXT NOT NULL DEFAULT 'sans'")
                if "style_json" not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN style_json TEXT NOT NULL DEFAULT '{{}}'")
            job_columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            for column, definition in {"payload_format": "TEXT NOT NULL DEFAULT 'p15-raster'",
                                       "raster_width": "INTEGER NOT NULL DEFAULT 96",
                                       "raster_height": "INTEGER NOT NULL DEFAULT 320"}.items():
                if column not in job_columns:
                    conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
            firmware_updates.initialize(conn)
            agent_columns = {row[1] for row in conn.execute("PRAGMA table_info(agents)")}
            for column, definition in {
                "printer_model": "TEXT NOT NULL DEFAULT 'p15'",
                "telemetry_json": "TEXT NOT NULL DEFAULT '{}'",
                "telemetry_received_at": "TEXT",
                "printer_checked_at": "TEXT",
                "refresh_requested": "INTEGER NOT NULL DEFAULT 0",
                "paused": "INTEGER NOT NULL DEFAULT 0",
            }.items():
                if column not in agent_columns:
                    conn.execute(f"ALTER TABLE agents ADD COLUMN {column} {definition}")
            conn.execute("INSERT INTO agents(id,name,token_hash,created_at) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET token_hash=excluded.token_hash",
                         (agent_id, agent_name, digest(agent_token), utc()))

    @asynccontextmanager
    async def lifespan(app):
        initialize()
        initialize_accounts()
        yield

    app = FastAPI(title="Fajny Print Studio", version="0.4.1", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db_path = db_path

    def expire(conn):
        now = time.time()
        conn.execute("UPDATE jobs SET status='queued',lease_token=NULL,lease_expires=NULL,updated_at=?,message='Lease expired before print start' WHERE status='leased' AND lease_expires<?", (utc(now), now))
        conn.execute("UPDATE jobs SET status='unknown',updated_at=?,message='Agent disappeared after print start; inspect label before creating a new job' WHERE status='printing' AND lease_expires<?", (utc(now), now))

    def bearer(request: Request) -> str:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer ") or len(header) > 256:
            raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
        return header[7:]

    initialize_accounts, admin, administrator = install_accounts(app, transaction, admin_token, config)

    def device(request: Request) -> str:
        token = bearer(request)
        with transaction() as conn:
            row = conn.execute("SELECT id FROM agents WHERE token_hash=?", (digest(token),)).fetchone()
            if row is None:
                raise HTTPException(401, "Invalid agent token")
            conn.execute("UPDATE agents SET last_seen=? WHERE id=?", (time.time(), row["id"]))
            return row["id"]

    firmware_updates.install(app, transaction, admin, administrator, device)

    def stored_style(row):
        return {"kind":"text", "qr_caption":"", "profile_id":"p15_40x12", "length_mm":50, "auto_cut":True, **STYLE_DEFAULTS, **json.loads(row["style_json"] or "{}")}

    def public_job(row):
        return {**{k: row[k] for k in ("id", "agent_id", "text", "font_size", "font", "status", "created_at", "updated_at", "message")}, **stored_style(row)}

    def public_template(row):
        return {**{k: row[k] for k in ("id", "name", "text", "font_size", "font")}, **stored_style(row)}

    @app.get("/api/health")
    def health():
        with transaction() as conn:
            conn.execute("SELECT 1")
        return {"ok": True}

    @app.get("/api/profiles", dependencies=[Depends(admin)])
    def profiles():
        return profile_catalog()

    @app.get("/api/agents", dependencies=[Depends(admin)])
    def agents():
        now = time.time()
        with transaction() as conn:
            expire(conn)
            updating = bool(firmware_updates.active(conn))
            return [{"updating": updating, "id": r["id"], "name": r["name"], "printer_model": r["printer_model"], "last_seen": utc(r["last_seen"]) if r["last_seen"] else None,
                     "status": "online" if r["last_seen"] and now - r["last_seen"] < 45 else "offline",
                     "telemetry": json.loads(r["telemetry_json"] or "{}"),
                     "telemetry_received_at": r["telemetry_received_at"],
                     "printer_checked_at": r["printer_checked_at"], "paused": bool(r["paused"])}
                    for r in conn.execute("SELECT * FROM agents ORDER BY created_at")]

    @app.post("/api/agents", dependencies=[Depends(administrator)], status_code=201)
    def add_agent(body: AgentInput):
        token = secrets.token_urlsafe(32)
        identifier = "esp32-" + uuid.uuid4().hex[:12]
        with transaction() as conn:
            conn.execute("INSERT INTO agents(id,name,token_hash,last_seen,created_at,printer_model) VALUES(?,?,?,?,?,?)", (identifier, body.name, digest(token), None, utc(), body.printer_model))
        return {"id": identifier, "name": body.name, "token": token, "printer_model":body.printer_model}

    @app.post("/api/agents/{target_id}/pause", dependencies=[Depends(administrator)])
    def pause_agent(target_id: str, body: PauseInput):
        with transaction() as conn:
            if conn.execute("UPDATE agents SET paused=? WHERE id=?", (body.paused, target_id)).rowcount == 0:
                raise HTTPException(404, "Agent not found")
        return {"ok": True}

    @app.post("/api/agents/{target_id}/refresh", dependencies=[Depends(admin)])
    def refresh_printer(target_id: str):
        with transaction() as conn:
            if conn.execute("UPDATE agents SET refresh_requested=1 WHERE id=?", (target_id,)).rowcount == 0:
                raise HTTPException(404, "Agent not found")
        return {"ok": True}

    @app.post("/api/agent/telemetry")
    def telemetry(body: Telemetry, agent: str = Depends(device)):
        incoming = body.model_dump(exclude_unset=True)
        with transaction() as conn:
            row = conn.execute("SELECT telemetry_json FROM agents WHERE id=?", (agent,)).fetchone()
            merged = json.loads(row["telemetry_json"] or "{}")
            if body.printer_checked is True:
                # An unanswered new probe invalidates old battery/status numbers.
                for key in ("battery_percent", "printer_status"):
                    merged[key] = None
                if "media_ready" in merged:
                    merged["media_ready"] = None
            for key, value in incoming.items():
                if key in {"model", "firmware", "serial"} and not value:
                    continue  # Keep the last observed identity; timestamps expose age.
                merged[key] = value
            now = utc()
            checked_at = now if body.printer_checked is True else None
            conn.execute("""UPDATE agents SET telemetry_json=?,telemetry_received_at=?,
                printer_checked_at=COALESCE(?,printer_checked_at),
                refresh_requested=CASE WHEN ? THEN 0 ELSE refresh_requested END WHERE id=?""",
                (json.dumps(merged, ensure_ascii=False), now, checked_at, body.printer_checked is True, agent))
        return {"ok": True}

    @app.post("/api/preview", dependencies=[Depends(admin)])
    def preview(body: Label):
        png, _ = render_label(body)
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.post("/api/jobs", dependencies=[Depends(admin)], status_code=201)
    def enqueue(body: JobInput):
        fingerprint_body = body.model_dump(exclude={"idempotency_key", *STYLE_DEFAULTS})
        fingerprint_body.update({key: value for key, value in style_dict(body).items() if value != STYLE_DEFAULTS[key]})
        if body.profile_id == "p15_40x12":
            for key in ("profile_id", "length_mm", "auto_cut"):
                fingerprint_body.pop(key)
        if not body.qr_caption:
            fingerprint_body.pop("qr_caption")  # Preserve existing text and QR request fingerprints.
        if body.kind == "text":
            fingerprint_body.pop("kind")
        if body.font == "sans":
            fingerprint_body.pop("font")  # Preserve pre-font submission keys.
        fingerprint = digest(json.dumps(fingerprint_body, sort_keys=True, ensure_ascii=False))
        _, raster = render_label(body)
        with transaction() as conn:
            previous = conn.execute("SELECT * FROM requests WHERE key=?", (body.idempotency_key,)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise HTTPException(409, "Idempotency key already used with different content")
                return [public_job(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()) for job_id in json.loads(previous["job_ids"])]
            if firmware_updates.active(conn):
                raise HTTPException(409, "Prebieha aktualizácia ESP32. Po jej dokončení môžeš tlačiť.")
            target = conn.execute("SELECT printer_model FROM agents WHERE id=?", (body.agent_id,)).fetchone()
            if target is None:
                raise HTTPException(404, "Agent not found")
            if target["printer_model"] != model_for_profile(body.profile_id):
                raise HTTPException(422, "Zvolený formát nepatrí k cieľovej tlačiarni.")
            ids = []
            now = utc()
            for _ in range(body.copies):
                job_id = str(uuid.uuid4())
                conn.execute("INSERT INTO jobs(id,agent_id,text,font_size,font,raster,style_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,'queued',?,?)", (job_id, body.agent_id, body.text, body.font_size, body.font, raster, json.dumps({**style_dict(body), "kind":body.kind, "qr_caption":body.qr_caption, "profile_id":body.profile_id, "length_mm":body.length_mm, "auto_cut":body.auto_cut}), now, now))
                fmt, width, height = job_geometry(body)
                conn.execute("UPDATE jobs SET payload_format=?,raster_width=?,raster_height=? WHERE id=?", (fmt,width,height,job_id))
                ids.append(job_id)
            conn.execute("INSERT INTO requests VALUES(?,?,?)", (body.idempotency_key, fingerprint, json.dumps(ids)))
            return [public_job(conn.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()) for identifier in ids]

    @app.get("/api/jobs", dependencies=[Depends(admin)])
    def jobs():
        with transaction() as conn:
            expire(conn)
            return [public_job(r) for r in conn.execute("SELECT * FROM jobs ORDER BY created_at DESC,rowid DESC LIMIT 200")]

    @app.post("/api/jobs/{job_id}/cancel", dependencies=[Depends(admin)])
    def cancel(job_id: str):
        with transaction() as conn:
            expire(conn)
            row = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Job not found")
            if row["status"] != "queued":
                raise HTTPException(409, "Only queued jobs can be cancelled")
            conn.execute("UPDATE jobs SET status='cancelled',updated_at=? WHERE id=?", (utc(), job_id))
        return {"ok": True}

    @app.get("/api/templates", dependencies=[Depends(admin)])
    def templates():
        with transaction() as conn:
            return [public_template(r) for r in conn.execute("SELECT * FROM templates ORDER BY name")]

    @app.post("/api/templates", dependencies=[Depends(admin)], status_code=201)
    def add_template(body: TemplateInput):
        render_label(body)
        template_id = str(uuid.uuid4())
        with transaction() as conn:
            conn.execute("INSERT INTO templates(id,name,text,font_size,font,style_json) VALUES(?,?,?,?,?,?)", (template_id, body.name, body.text, body.font_size, body.font, json.dumps({**style_dict(body), "kind":body.kind, "qr_caption":body.qr_caption, "profile_id":body.profile_id, "length_mm":body.length_mm, "auto_cut":body.auto_cut})))
        return {"id": template_id, **body.model_dump()}

    @app.delete("/api/templates/{template_id}", dependencies=[Depends(admin)])
    def delete_template(template_id: str):
        with transaction() as conn:
            if conn.execute("DELETE FROM templates WHERE id=?", (template_id,)).rowcount == 0:
                raise HTTPException(404, "Template not found")
        return {"ok": True}

    @app.post("/api/agent/claim")
    def claim(agent: str = Depends(device)):
        with transaction() as conn:
            expire(conn)
            if firmware_updates.active(conn):
                return Response(status_code=204)
            if conn.execute("SELECT paused FROM agents WHERE id=?", (agent,)).fetchone()[0]:
                return Response(status_code=204)
            # A lost poll response cannot cause this device to receive another job.
            row = conn.execute("SELECT * FROM jobs WHERE agent_id=? AND status IN ('leased','printing') ORDER BY created_at,rowid LIMIT 1", (agent,)).fetchone()
            if row and row["status"] == "printing":
                return Response(status_code=204)
            if row is None:
                row = conn.execute("SELECT * FROM jobs WHERE agent_id=? AND status='queued' ORDER BY created_at,rowid LIMIT 1", (agent,)).fetchone()
                if row is None:
                    refresh = conn.execute("SELECT refresh_requested FROM agents WHERE id=?", (agent,)).fetchone()[0]
                    return Response(status_code=204, headers={"X-Printer-Refresh": "1"} if refresh else {})
                conn.execute("UPDATE jobs SET status='leased',lease_token=?,lease_expires=?,updated_at=?,message='' WHERE id=?", (secrets.token_urlsafe(24), time.time() + LEASE_SECONDS, utc(), row["id"]))
                row = conn.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
            raw = bytes(row["raster"])
            result = {"id": row["id"], "lease_token": row["lease_token"], "width": row["raster_width"],
                      "height": row["raster_height"], "sha256": digest(raw)}
            if row["payload_format"] == "p15-raster":
                result["raster_base64"] = base64.b64encode(raw).decode()
            else:
                media = MEDIA[stored_style(row)["profile_id"]]
                result.update({"format":row["payload_format"], "size":len(raw),
                               "payload_path":"/api/agent/jobs/"+row["id"]+"/payload",
                               "media_width_mm":media.width_mm, "media_length_mm":media.media_length_mm})
            return result

    def leased_job(conn, job_id, agent, token):
        expire(conn)
        row = conn.execute("SELECT * FROM jobs WHERE id=? AND agent_id=?", (job_id, agent)).fetchone()
        if row is None:
            raise HTTPException(404, "Job not found")
        if not row["lease_token"] or not hmac.compare_digest(row["lease_token"], token):
            raise HTTPException(409, "Lease no longer valid")
        return row

    @app.get("/api/agent/jobs/{job_id}/payload")
    def payload(job_id: str, request: Request, agent: str = Depends(device)):
        token = request.headers.get("x-lease-token", "")
        with transaction() as conn:
            row = leased_job(conn, job_id, agent, token)
            if row["status"] != "leased" or row["payload_format"] != "brother-raster-v1":
                raise HTTPException(409, "Payload is not available for this lease")
            raw = bytes(row["raster"])
        return Response(raw, media_type="application/octet-stream", headers={"Cache-Control":"no-store", "X-SHA256":digest(raw)})

    @app.post("/api/agent/jobs/{job_id}/start")
    def start(job_id: str, body: LeaseInput, agent: str = Depends(device)):
        with transaction() as conn:
            row = leased_job(conn, job_id, agent, body.lease_token)
            if row["status"] != "leased":
                # Deliberately NOT idempotent: replaying a lost start is ambiguous.
                raise HTTPException(409, "Print start already consumed or job expired; do not print again")
            conn.execute("UPDATE jobs SET status='printing',lease_expires=?,updated_at=? WHERE id=?", (time.time() + LEASE_SECONDS, utc(), job_id))
        return {"ok": True}

    @app.post("/api/agent/jobs/{job_id}/complete")
    def complete(job_id: str, body: Completion, agent: str = Depends(device)):
        with transaction() as conn:
            row = leased_job(conn, job_id, agent, body.lease_token)
            if row["status"] == body.outcome:
                return {"ok": True}
            if row["status"] in TERMINAL:
                raise HTTPException(409, "Job already has a different terminal result")
            if row["status"] not in {"leased", "printing"} or (row["status"] == "leased" and body.outcome == "printed"):
                raise HTTPException(409, "Job is not awaiting this print result")
            conn.execute("UPDATE jobs SET status=?,message=?,updated_at=? WHERE id=?", (body.outcome, body.message, utc(), job_id))
        return {"ok": True}

    @app.get("/{path:path}")
    def static(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "API route not found")
        candidate = (web_dir / path).resolve()
        if candidate.is_relative_to(web_dir) and candidate.is_file():
            return FileResponse(candidate)
        index = web_dir / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        raise HTTPException(404, "Web build not installed")

    return app


app = create_app()
