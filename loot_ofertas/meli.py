from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
API_URL = "https://api.mercadolibre.com"
AUTH_STATE_PATH = Path(".meli-auth.json")
TOKEN_PATH = Path(".meli-token.json")


class MeliError(RuntimeError):
    pass


def authorization_url() -> str:
    client_id, _, redirect_uri = _credentials()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    state = secrets.token_urlsafe(32)
    _write_private_json(AUTH_STATE_PATH, {
        "state": state,
        "code_verifier": verifier,
        "created_at": int(time.time()),
    })
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })


def exchange_callback(callback: str) -> dict[str, Any]:
    if not AUTH_STATE_PATH.exists():
        raise MeliError("Gere primeiro a URL de autorização.")
    saved = json.loads(AUTH_STATE_PATH.read_text(encoding="utf-8"))
    parsed = urllib.parse.urlsplit(callback.strip())
    params = urllib.parse.parse_qs(parsed.query) if parsed.query else {}
    code = (params.get("code") or [callback.strip()])[0]
    returned_state = (params.get("state") or [""])[0]
    if params and returned_state != saved.get("state"):
        raise MeliError("O state retornado não corresponde à autorização iniciada.")
    client_id, client_secret, redirect_uri = _credentials()
    token = _post_form(TOKEN_URL, {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": saved["code_verifier"],
    })
    _save_token(token)
    AUTH_STATE_PATH.unlink(missing_ok=True)
    return token


def access_token() -> str:
    if not TOKEN_PATH.exists():
        raise MeliError("Autorize a aplicação antes de usar a API.")
    token = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    if int(token.get("expires_at", 0)) <= int(time.time()) + 120:
        token = refresh_access_token(token)
    value = str(token.get("access_token", ""))
    if not value:
        raise MeliError("Token de acesso ausente.")
    return value


def refresh_access_token(current: dict[str, Any] | None = None) -> dict[str, Any]:
    current = current or json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    refresh_token = str(current.get("refresh_token", ""))
    if not refresh_token:
        raise MeliError("Refresh token ausente; faça a autorização novamente.")
    client_id, client_secret, _ = _credentials()
    token = _post_form(TOKEN_URL, {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    })
    _save_token(token)
    return token


def api_get(path: str) -> Any:
    request = urllib.request.Request(
        API_URL + "/" + path.lstrip("/"),
        headers={"Authorization": f"Bearer {access_token()}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise MeliError(f"API Mercado Livre retornou HTTP {error.code}: {detail[:300]}") from error
    except urllib.error.URLError as error:
        raise MeliError(f"Falha ao consultar a API: {error.reason}") from error


def _credentials() -> tuple[str, str, str]:
    values = (
        os.getenv("MELI_CLIENT_ID", "").strip(),
        os.getenv("MELI_CLIENT_SECRET", "").strip(),
        os.getenv("MELI_REDIRECT_URI", "").strip(),
    )
    if not all(values):
        raise MeliError("Configure MELI_CLIENT_ID, MELI_CLIENT_SECRET e MELI_REDIRECT_URI no .env.")
    return values


def _post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise MeliError(f"OAuth Mercado Livre retornou HTTP {error.code}: {detail[:300]}") from error
    except urllib.error.URLError as error:
        raise MeliError(f"Falha no OAuth do Mercado Livre: {error.reason}") from error
    if not isinstance(result, dict) or not result.get("access_token"):
        raise MeliError("Resposta OAuth sem access token.")
    return result


def _save_token(token: dict[str, Any]) -> None:
    saved = dict(token)
    saved["expires_at"] = int(time.time()) + int(saved.get("expires_in", 21600))
    _write_private_json(TOKEN_PATH, saved)


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
