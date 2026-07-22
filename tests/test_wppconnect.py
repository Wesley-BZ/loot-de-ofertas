import base64
import json
from unittest.mock import patch

from loot_ofertas.models import Offer
from loot_ofertas.wppconnect import WppConnectClient, group_rows, save_qr_code


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_find_group_accepts_serialized_id():
    client = WppConnectClient("http://localhost:21465", "loot", "secret")
    with patch.object(
        client,
        "groups",
        return_value=[{"name": "Loot de Ofertas", "id": {"_serialized": "123@g.us"}}],
    ):
        assert client.find_group("loot de ofertas") == "123@g.us"


def test_send_offer_posts_group_message():
    client = WppConnectClient("http://localhost:21465", "loot", "secret")
    offer = Offer(title="Mouse", affiliate_url="https://loja/item", price=99, store="Loja")
    with patch("urllib.request.urlopen", return_value=FakeResponse({"status": "success"})) as open_mock:
        result = client.send_offer("123@g.us", offer, "none")
    request = open_mock.call_args.args[0]
    payload = json.loads(request.data)
    assert request.full_url.endswith("/api/loot/send-message")
    assert request.headers["Authorization"] == "Bearer secret"
    assert payload["phone"] == "123@g.us"
    assert payload["isGroup"] is True
    assert result["status"] == "success"


def test_save_qr_code(tmp_path):
    png = b"\x89PNG\r\n\x1a\n"
    response = {"response": {"qrcode": "data:image/png;base64," + base64.b64encode(png).decode()}}
    path = save_qr_code(response, tmp_path / "qr.png")
    assert path.read_bytes() == png


def test_group_rows_are_sorted():
    rows = group_rows(
        [
            {"name": "Zeta", "id": "2@g.us"},
            {"subject": "Alpha", "id": {"_serialized": "1@g.us"}},
        ]
    )
    assert rows == [("Alpha", "1@g.us"), ("Zeta", "2@g.us")]
