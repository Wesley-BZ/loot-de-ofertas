from fastapi.testclient import TestClient

from loot_ofertas.webapp import app
from loot_ofertas.database import OfferRepository
from loot_ofertas.market import MarketRepository
from loot_ofertas.models import Offer


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
