from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .formatting import format_offer
from .models import Offer


class WppConnectError(RuntimeError):
    """Erro retornado pelo WPPConnect Server."""


class WppConnectClient:
    def __init__(self, base_url: str, session: str, token: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.token = token.removeprefix("Bearer ").strip()
        self.timeout = timeout

    def _request(self, method: str, endpoint: str, payload: dict | None = None) -> Any:
        url = f"{self.base_url}/api/{urllib.parse.quote(self.session, safe='')}/{endpoint}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self.token}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise WppConnectError(f"WPPConnect recusou a operação ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise WppConnectError(
                f"Não foi possível acessar o WPPConnect em {self.base_url}. "
                "Confirme que o servidor está iniciado."
            ) from exc

    def start_session(self) -> dict:
        return self._request("POST", "start-session", {"waitQrCode": True})

    def status(self) -> dict:
        return self._request("GET", "status-session")

    def groups(self) -> list[dict]:
        result = self._request("GET", "all-groups")
        groups = result.get("response", result) if isinstance(result, dict) else result
        return groups if isinstance(groups, list) else []

    def find_group(self, group_name: str) -> str:
        wanted = group_name.strip().casefold()
        matches: list[str] = []
        for group in self.groups():
            name = str(group.get("name") or group.get("subject") or "").strip()
            group_id = _serialized_id(group.get("id"))
            if name.casefold() == wanted and group_id:
                matches.append(group_id)
        if not matches:
            raise WppConnectError(
                f"Grupo '{group_name}' não encontrado. Execute 'whatsapp-setup --list-groups'."
            )
        if len(matches) > 1:
            raise WppConnectError(
                f"Há mais de um grupo chamado '{group_name}'. Configure WPP_GROUP_ID no .env."
            )
        return matches[0]

    def send_offer(self, group_id: str, offer: Offer, image_mode: str = "link-preview") -> dict:
        message = format_offer(offer)
        if offer.image_url and image_mode.casefold() == "link-preview":
            message = f"{offer.image_url}\n\n{message}"
        return self._request(
            "POST", "send-message", {"phone": group_id, "isGroup": True, "message": message}
        )


def save_qr_code(response: Any, destination: str | Path = "outbox/whatsapp-qr.png") -> Path | None:
    value = _find_qr_data(response)
    if not value:
        return None
    encoded = value.split(",", 1)[1] if value.startswith("data:image") and "," in value else value
    try:
        image = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)
    return path.resolve()


def group_rows(groups: list[dict]) -> list[tuple[str, str]]:
    rows = []
    for group in groups:
        group_id = _serialized_id(group.get("id"))
        name = str(group.get("name") or group.get("subject") or "(sem nome)")
        if group_id:
            rows.append((name, group_id))
    return sorted(rows, key=lambda row: row[0].casefold())


def _serialized_id(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("_serialized") or value.get("serialized") or "")
    return ""


def _find_qr_data(value: Any) -> str | None:
    if isinstance(value, str) and (value.startswith("data:image") or len(value) > 500):
        return value
    if isinstance(value, dict):
        for key in ("qrcode", "qrCode", "qr", "base64"):
            if key in value:
                found = _find_qr_data(value[key])
                if found:
                    return found
        for nested in value.values():
            found = _find_qr_data(nested)
            if found:
                return found
    if isinstance(value, list):
        for nested in value:
            found = _find_qr_data(nested)
            if found:
                return found
    return None
