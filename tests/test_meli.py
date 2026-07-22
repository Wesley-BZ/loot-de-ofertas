import json
from urllib.parse import parse_qs, urlsplit

import pytest

from loot_ofertas import meli


def test_authorization_url_uses_pkce_and_saves_state(tmp_path, monkeypatch):
    monkeypatch.setenv("MELI_CLIENT_ID", "123")
    monkeypatch.setenv("MELI_CLIENT_SECRET", "secret")
    monkeypatch.setenv("MELI_REDIRECT_URI", "https://example.com/callback")
    monkeypatch.setattr(meli, "AUTH_STATE_PATH", tmp_path / "auth.json")

    url = meli.authorization_url()
    params = parse_qs(urlsplit(url).query)
    saved = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))

    assert params["client_id"] == ["123"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == [saved["state"]]
    assert saved["code_verifier"]


def test_exchange_rejects_wrong_state(tmp_path, monkeypatch):
    auth_path = tmp_path / "auth.json"
    auth_path.write_text('{"state":"right","code_verifier":"verifier"}', encoding="utf-8")
    monkeypatch.setattr(meli, "AUTH_STATE_PATH", auth_path)

    with pytest.raises(meli.MeliError, match="state"):
        meli.exchange_callback("https://example.com/callback?code=abc&state=wrong")
