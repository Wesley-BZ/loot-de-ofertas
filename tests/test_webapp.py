from fastapi.testclient import TestClient

from loot_ofertas.webapp import app


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
