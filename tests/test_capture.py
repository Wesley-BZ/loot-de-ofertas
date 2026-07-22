import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from loot_ofertas.capture import CaptureError, capture_mercado_livre, save_message
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
