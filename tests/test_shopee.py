import hashlib
import json
from unittest.mock import patch

from loot_ofertas.shopee import (
    ShopeeAffiliateClient, _offer_from_node, shopee_item_id,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, *_):
        return json.dumps(self.payload).encode()


def test_request_uses_exact_shopee_sha256_signature():
    client = ShopeeAffiliateClient("123", "secret")
    with patch("loot_ofertas.shopee.time.time", return_value=1700000000), patch(
        "loot_ofertas.shopee.urllib.request.urlopen",
        return_value=FakeResponse({"data": {"ok": True}}),
    ) as urlopen:
        assert client.request("{ ping }") == {"ok": True}
    request = urlopen.call_args.args[0]
    payload = request.data.decode()
    signature = hashlib.sha256(f"1231700000000{payload}secret".encode()).hexdigest()
    assert request.headers["Authorization"] == (
        f"SHA256 Credential=123, Timestamp=1700000000, Signature={signature}"
    )


def test_offer_node_uses_affiliate_link_and_commercial_signals():
    offer = _offer_from_node({
        "itemId": 987654,
        "productName": "Mouse Gamer Sem Fio",
        "productLink": "https://shopee.com.br/mouse-i.123.987654",
        "offerLink": "https://s.shopee.com.br/affiliate",
        "imageUrl": "https://cf.shopee.com.br/file/mouse",
        "priceMin": "99.90",
        "priceDiscountRate": "0.50",
        "sales": "10000",
        "ratingStar": "4.9",
        "commissionRate": "0.12",
        "shopName": "Loja Gamer",
    })
    assert offer is not None
    assert offer.product_key == "shopee:987654"
    assert offer.affiliate_url == "https://s.shopee.com.br/affiliate"
    assert offer.original_price == 199.8
    assert offer.commission_percent == 12
    assert offer.sold_count == 10000
    assert offer.community_score > 70


def test_extracts_item_id_from_brazilian_product_links():
    assert shopee_item_id("https://shopee.com.br/mouse-gamer-i.123456.987654") == 987654
    assert shopee_item_id("https://shopee.com.br/product/123456/987654") == 987654


def test_products_sends_item_id_as_int64_string():
    client = ShopeeAffiliateClient("123", "secret")
    captured = {}

    def fake_request(query, variables=None, timeout=30):
        captured["query"] = query
        captured["variables"] = variables
        return {"productOfferV2": {"nodes": []}}

    with patch.object(client, "request", side_effect=fake_request):
        client.products(item_id=9876543210123, limit=1)

    assert "$itemId: Int64!" in captured["query"]
    assert captured["variables"]["itemId"] == "9876543210123"
