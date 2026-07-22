from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from .config import load_env
from .database import OfferRepository
from .scheduling import PublicationPolicy
from .wppconnect import WppConnectClient, WppConnectError


app = FastAPI(title="Loot de Ofertas", docs_url=None, redoc_url=None)


def _database_path() -> Path:
    path = Path(os.getenv("WEBHOOK_DATABASE", "data/webhooks.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _initialize() -> None:
    with sqlite3.connect(_database_path(), timeout=2) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mercado_livre_webhooks (
                event_key TEXT PRIMARY KEY,
                topic TEXT,
                resource TEXT,
                user_id TEXT,
                application_id TEXT,
                payload TEXT NOT NULL,
                received_at TEXT NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0
            )
            """
        )


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    path = Path(__file__).with_name("dashboard.html")
    return HTMLResponse(path.read_text(encoding="utf-8"))


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


def _loot_database_path() -> Path:
    return Path(os.getenv("LOOT_DATABASE", "loot_ofertas.db"))


def _rows(connection: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def _has_table(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _wpp_status() -> dict[str, Any]:
    base = os.getenv("WPP_BASE_URL", "").strip()
    session = os.getenv("WPP_SESSION", "").strip()
    token = os.getenv("WPP_TOKEN", "").strip()
    if not all((base, session, token)):
        return {"connected": False, "detail": "não configurado"}
    try:
        response = WppConnectClient(base, session, token, timeout=3).status()
        serialized = json.dumps(response, ensure_ascii=False).casefold()
        connected = "connected" in serialized and "disconnected" not in serialized
        return {"connected": connected, "detail": "conectado" if connected else "sessão inativa"}
    except WppConnectError:
        return {"connected": False, "detail": "servidor indisponível"}


def _scheduled_task_status(name: str = "LootDeOfertas-Monitor") -> dict[str, Any]:
    if os.name != "nt":
        return {"configured": False, "state": "indisponível neste sistema"}
    script = (
        f"$t=Get-ScheduledTask -TaskName '{name}' -ErrorAction Stop;"
        f"$i=Get-ScheduledTaskInfo -TaskName '{name}' -ErrorAction Stop;"
        "[pscustomobject]@{configured=$true;state=[string]$t.State;"
        "last_run=$i.LastRunTime.ToString('o');next_run=$i.NextRunTime.ToString('o');"
        "last_result=$i.LastTaskResult}|ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=4, check=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return {"configured": False, "state": "não encontrada"}


def _integration_status(wpp: dict[str, Any], scheduler: dict[str, Any]) -> list[dict[str, Any]]:
    token_file = Path(".meli-token.json")
    return [
        {"name": "Monitor agendado", "ok": bool(scheduler.get("configured")), "detail": scheduler.get("state")},
        {"name": "WhatsApp / WPPConnect", "ok": bool(wpp.get("connected")), "detail": wpp.get("detail")},
        {"name": "Grupo do WhatsApp", "ok": bool(os.getenv("WPP_GROUP_ID", "").strip()), "detail": "configurado" if os.getenv("WPP_GROUP_ID", "").strip() else "ausente"},
        {"name": "Mercado Livre API", "ok": token_file.exists() and bool(os.getenv("MELI_CLIENT_ID", "").strip()), "detail": "autorizada" if token_file.exists() else "token ausente"},
        {"name": "Magazine Você", "ok": bool(os.getenv("MAGALU_STORE_URL", "").strip() and os.getenv("MAGALU_PROMOTER_ID", "").strip()), "detail": "loja e divulgador configurados"},
        {"name": "Google Shopping", "ok": bool(os.getenv("SERPAPI_API_KEY", "").strip()), "detail": "SerpApi configurada" if os.getenv("SERPAPI_API_KEY", "").strip() else "opcional · chave ausente"},
    ]


@app.get("/api/dashboard")
def dashboard_data() -> dict[str, Any]:
    load_env()
    database = _loot_database_path()
    repo = OfferRepository(database)
    repo.initialize()
    policy = PublicationPolicy.from_env()
    decision = repo.publication_decision("wppconnect", policy)
    now = policy.local_now()
    with repo.connection() as connection:
        stats = dict(connection.execute(
            """SELECT COUNT(*) total,
                      SUM(CASE WHEN status='ready' AND available=1 THEN 1 ELSE 0 END) ready,
                      SUM(CASE WHEN status='published' THEN 1 ELSE 0 END) published,
                      COUNT(DISTINCT store) stores
               FROM offers"""
        ).fetchone())
        offers = _rows(connection, """
            SELECT o.id, o.title, o.price, o.original_price, o.store, o.coupon, o.category,
                   o.score, o.status, o.available, o.affiliate_url, o.image_url, o.last_seen_at,
                   a.label assessment, a.score assessment_score, a.confidence, a.competitor_count, a.market_median,
                   a.market_savings_percent, a.reasons
            FROM offers o
            LEFT JOIN deal_assessments a ON a.id=(
                SELECT da.id FROM deal_assessments da WHERE da.offer_id=o.id ORDER BY da.id DESC LIMIT 1
            )
            ORDER BY o.last_seen_at DESC, o.score DESC LIMIT 100
        """) if _has_table(connection, "deal_assessments") else _rows(connection, """
            SELECT id, title, price, original_price, store, coupon, category, score, status,
                   available, affiliate_url, image_url, last_seen_at
            FROM offers ORDER BY last_seen_at DESC, score DESC LIMIT 100
        """)
        publications = _rows(connection, """
            SELECT p.id, p.offer_id, o.title, p.channel, p.category, p.price, p.headline,
                   p.published_at
            FROM publication_history p LEFT JOIN offers o ON o.id=p.offer_id
            ORDER BY p.id DESC LIMIT 50
        """)
        prices = int(connection.execute("SELECT COUNT(*) FROM price_history").fetchone()[0])
        categories = _rows(connection, """
            SELECT COALESCE(category, 'sem categoria') category, COUNT(*) total
            FROM offers GROUP BY category ORDER BY total DESC LIMIT 12
        """)
    webhook_count = 0
    webhook_db = _database_path()
    if webhook_db.exists():
        with sqlite3.connect(webhook_db) as connection:
            if _has_table(connection, "mercado_livre_webhooks"):
                webhook_count = int(connection.execute(
                    "SELECT COUNT(*) FROM mercado_livre_webhooks"
                ).fetchone()[0])
    log_path = Path("logs/monitor.log")
    log_lines = []
    log_updated = None
    if log_path.exists():
        log_updated = datetime.fromtimestamp(log_path.stat().st_mtime, policy.timezone).isoformat()
        log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-180:]
    for offer in offers:
        try:
            offer["reasons"] = json.loads(offer.get("reasons") or "[]")
        except (TypeError, json.JSONDecodeError):
            offer["reasons"] = []
        original = offer.get("original_price")
        offer["discount_percent"] = round((1 - offer["price"] / original) * 100, 1) if original and original > offer["price"] else 0
        offer["publication_score"] = round(
            float(offer.get("score") or 0) + max(0.0, float(offer.get("assessment_score") or 0)), 2
        )
    wpp = _wpp_status()
    scheduler = _scheduled_task_status()
    recent_errors = sum(
        1 for line in log_lines if any(term in line.casefold() for term in ("erro", "falhou", "recusada", "indisponível"))
    )
    return {
        "generated_at": now.isoformat(),
        "bot": {
            "active": bool(scheduler.get("configured")) and str(scheduler.get("state", "")).casefold() in {"ready", "running", "pronto", "executando"},
            "send_allowed": decision.allowed,
            "send_reason": decision.reason,
            "wait_seconds": decision.wait_seconds,
            "schedule": f"{policy.start_hour:02d}:00–{policy.end_hour:02d}:00",
            "interval_minutes": policy.min_interval_minutes,
            "daily_limit": policy.daily_limit,
            "category_limit": policy.category_daily_limit,
            "monitor_interval_minutes": 15,
            "log_updated": log_updated,
            "scheduler": scheduler,
        },
        "whatsapp": {**wpp, "group_configured": bool(os.getenv("WPP_GROUP_ID", "").strip())},
        "stats": {**stats, "price_observations": prices, "webhooks": webhook_count},
        "offers": offers,
        "publications": publications,
        "categories": categories,
        "logs": log_lines,
        "recent_errors": recent_errors,
        "integrations": _integration_status(wpp, scheduler),
    }


@app.post("/webhooks/mercadolivre")
async def mercado_livre_webhook(request: Request) -> dict[str, str]:
    try:
        payload = await request.json()
    except Exception as error:
        raise HTTPException(status_code=400, detail="JSON inválido") from error

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload inválido")

    expected_app_id = os.getenv("MELI_CLIENT_ID", "").strip()
    received_app_id = str(payload.get("application_id", "")).strip()
    if expected_app_id and received_app_id and received_app_id != expected_app_id:
        raise HTTPException(status_code=403, detail="Aplicação inválida")

    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    event_key = str(payload.get("_id") or payload.get("id") or "").strip()
    if not event_key:
        event_key = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    _initialize()
    with sqlite3.connect(_database_path(), timeout=2) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO mercado_livre_webhooks
                (event_key, topic, resource, user_id, application_id, payload, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_key,
                str(payload.get("topic", "")),
                str(payload.get("resource", "")),
                str(payload.get("user_id", "")),
                received_app_id,
                serialized,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    return {"status": "ok"}
