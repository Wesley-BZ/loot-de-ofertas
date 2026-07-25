from fastapi.testclient import TestClient

from loot_ofertas.webapp import app
from loot_ofertas.database import OfferRepository
from loot_ofertas.market import MarketRepository
from loot_ofertas.models import Offer
from loot_ofertas.capture import CaptureError


def test_webhook_accepts_and_deduplicates_notification(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_DATABASE", str(tmp_path / "webhooks.db"))
    client = TestClient(app)
    payload = {
        "_id": "notification-1",
        "topic": "items",
        "resource": "/items/MLB123",
        "user_id": 123,
        "application_id": 456,
    }

    assert client.post("/webhooks/mercadolivre", json=payload).json() == {"status": "ok"}
    assert client.post("/webhooks/mercadolivre", json=payload).json() == {"status": "ok"}


def test_webhook_rejects_wrong_application(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBHOOK_DATABASE", str(tmp_path / "webhooks.db"))
    monkeypatch.setenv("MELI_CLIENT_ID", "expected")
    client = TestClient(app)

    response = client.post(
        "/webhooks/mercadolivre",
        json={"application_id": "wrong", "topic": "items"},
    )

    assert response.status_code == 403


def test_dashboard_serves_monitoring_data(tmp_path, monkeypatch):
    database = tmp_path / "loot.db"
    repo = OfferRepository(database)
    repo.initialize()
    MarketRepository(database).initialize()
    repo.add(Offer("Mouse Gamer", "https://example.com/mouse", 99.9, "magalu"))
    monkeypatch.setenv("LOOT_DATABASE", str(database))
    monkeypatch.setenv("WEBHOOK_DATABASE", str(tmp_path / "webhooks.db"))
    monkeypatch.setenv("WPP_BASE_URL", "")
    monkeypatch.setenv("WPP_SESSION", "")
    monkeypatch.setenv("WPP_TOKEN", "")
    client = TestClient(app)

    page = client.get("/")
    payload = client.get("/api/dashboard").json()

    assert page.status_code == 200
    assert "Loot de Ofertas" in page.text
    assert payload["stats"]["total"] == 1
    assert payload["offers"][0]["title"] == "Mouse Gamer"
    assert "scheduler" in payload["bot"]
    assert len(payload["integrations"]) >= 5
    assert "recent_errors" in payload
    assert "WPP_TOKEN" not in str(payload)


def test_manual_offer_can_be_saved_from_dashboard(tmp_path, monkeypatch):
    database = tmp_path / "loot.db"
    monkeypatch.setenv("LOOT_DATABASE", str(database))
    client = TestClient(app)

    response = client.post("/api/offers", json={
        "url": "https://shopee.com.br/produto",
        "title": "Mouse Gamer RGB",
        "price": 79.9,
        "original_price": 109.9,
        "store": "shopee",
        "coupon": "GAMER10",
        "publish_now": False,
    })

    assert response.status_code == 200
    assert response.json()["published"] is False
    assert OfferRepository(database).ready(10)[0].store == "shopee"


def test_inspect_returns_editable_fields_when_store_blocks_capture(monkeypatch):
    monkeypatch.setattr(
        "loot_ofertas.webapp._capture_url",
        lambda url: (_ for _ in ()).throw(CaptureError("bloqueado")),
    )
    client = TestClient(app)

    response = client.post("/api/offers/inspect", json={"url": "https://shopee.com.br/item"})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["offer"]["store"] == "shopee"
