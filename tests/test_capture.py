import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from loot_ofertas.capture import (
    CaptureError, _coupon_from_api, capture_mercado_livre,
    capture_mercado_livre_api, save_message,
)
from loot_ofertas.database import OfferRepository


class FakeResponse:
    def __init__(self, html, url="https://produto.mercadolivre.com.br/MLB-123456-mouse-gamer"):
        self.data = html.encode("utf-8")
        self.url = url
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit=-1):
        return self.data[:limit] if limit >= 0 else self.data

    def geturl(self):
        return self.url


def product_html(price="189.90"):
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Mouse Gamer Logitech G305 sem fio",
        "image": ["https://http2.mlstatic.com/mouse.jpg"],
        "offers": {
            "@type": "Offer",
            "price": price,
            "availability": "https://schema.org/InStock",
            "seller": {"@type": "Organization", "name": "Loja Oficial Logitech"},
        },
    }
    return f"""<html><head>
        <meta property="product:original_price:amount" content="299,90">
        <script type="application/ld+json">{json.dumps(product)}</script>
        </head></html>"""


class CaptureTests(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_extracts_structured_product_data(self, urlopen):
        urlopen.return_value = FakeResponse(product_html())
        captured = capture_mercado_livre("https://produto.mercadolivre.com.br/MLB-123456")
        offer = captured.offer
        self.assertEqual("Mouse Gamer Logitech G305 sem fio", offer.title)
        self.assertEqual(189.90, offer.price)
        self.assertEqual(299.90, offer.original_price)
        self.assertEqual("Loja Oficial Logitech", offer.seller_name)
        self.assertEqual("mercadolivre:MLB123456", offer.product_key)
        self.assertTrue(offer.available)

    def test_rejects_non_mercado_livre_before_opening(self):
        with patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(CaptureError):
                capture_mercado_livre("https://example.com/produto")
            urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_rejects_page_without_price(self, urlopen):
        urlopen.return_value = FakeResponse(
            '<script type="application/ld+json">{"@type":"Product","name":"Mouse"}</script>'
        )
        with self.assertRaisesRegex(CaptureError, "preço válido"):
            capture_mercado_livre("https://mercadolivre.com.br/MLB-123456")

    @patch("urllib.request.urlopen")
    def test_extracts_public_coupon_from_page(self, urlopen):
        urlopen.return_value = FakeResponse(product_html() + '<script>window.offer={"coupon_code":"GAMER20"}</script>')

        captured = capture_mercado_livre("https://produto.mercadolivre.com.br/MLB-123456")

        self.assertEqual("GAMER20", captured.offer.coupon)

    def test_extracts_coupon_when_api_includes_campaign_code(self):
        payload = {"promotions": [{"type": "SELLER_COUPON_CAMPAIGN", "code": "CADEIRA15"}]}

        self.assertEqual("CADEIRA15", _coupon_from_api(payload))

    @patch("loot_ofertas.capture.api_get")
    def test_api_capture_accepts_regular_mlb_item_link(self, api_get):
        api_get.side_effect = [
            {
                "id": "MLB123456",
                "title": "Monitor Gamer 24 polegadas",
                "price": 699.90,
                "original_price": 899.90,
                "seller_id": 77,
                "category_id": "MLB99245",
                "secure_thumbnail": "https://http2.mlstatic.com/monitor.jpg",
                "shipping": {"free_shipping": True},
            },
            {
                "nickname": "LOJA_OFICIAL",
                "seller_reputation": {"level_id": "5_green", "transactions": {"total": 500}},
            },
            {"name": "Monitores"},
        ]

        captured = capture_mercado_livre_api(
            "https://produto.mercadolivre.com.br/MLB-123456-monitor-gamer"
        )

        self.assertEqual("Monitor Gamer 24 polegadas", captured.offer.title)
        self.assertEqual(699.90, captured.offer.price)
        self.assertEqual("mercadolivre:mlb123456", captured.offer.product_key)
        self.assertEqual("https://http2.mlstatic.com/monitor.jpg", captured.offer.image_url)
        self.assertEqual(0.0, captured.offer.shipping_price)
        self.assertEqual("items/MLB123456", api_get.call_args_list[0].args[0])

    @patch("loot_ofertas.capture.api_get")
    def test_api_capture_uses_product_catalog_for_p_link(self, api_get):
        api_get.side_effect = [
            {"results": [{
                "item_id": "MLB4089347501",
                "price": 429.0,
                "original_price": 850.0,
                "seller_id": 77,
                "category_id": "MLB99245",
                "shipping": {"free_shipping": True},
            }]},
            {
                "name": "Monitor Gamer AOC",
                "pictures": [{"secure_url": "https://http2.mlstatic.com/aoc.jpg"}],
            },
            {"nickname": "AOC_OFICIAL", "seller_reputation": {"transactions": {"total": 100}}},
            {"name": "Monitores"},
        ]

        captured = capture_mercado_livre_api(
            "https://www.mercadolivre.com.br/monitor/p/MLB50200257"
            "?pdp_filters=item_id%3AMLB4089347501&wid=MLB4089347501"
        )

        self.assertEqual(429.0, captured.offer.price)
        self.assertEqual("mercadolivre:mlb4089347501", captured.offer.product_key)
        self.assertEqual("products/MLB50200257/items", api_get.call_args_list[0].args[0])
        self.assertEqual("products/MLB50200257", api_get.call_args_list[1].args[0])

    @patch("urllib.request.urlopen")
    def test_capture_updates_database_and_saves_message(self, urlopen):
        with tempfile.TemporaryDirectory() as directory:
            repo = OfferRepository(Path(directory) / "offers.db")
            repo.initialize()
            urlopen.return_value = FakeResponse(product_html("189.90"))
            first = capture_mercado_livre("https://produto.mercadolivre.com.br/MLB-123456")
            first_id = repo.add(first.offer)
            urlopen.return_value = FakeResponse(product_html("169.90"))
            second = capture_mercado_livre("https://produto.mercadolivre.com.br/MLB-123456")
            second_id = repo.add(second.offer)
            self.assertEqual(first_id, second_id)
            self.assertEqual(169.90, repo.get(first_id).price)
            path = save_message("mensagem gamer", first_id, Path(directory) / "messages")
            self.assertEqual("mensagem gamer", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
