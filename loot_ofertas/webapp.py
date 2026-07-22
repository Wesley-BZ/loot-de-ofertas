from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request


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


@app.get("/")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "loot-de-ofertas"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


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
