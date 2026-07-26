import unittest
from email.message import Message
from unittest.mock import patch

from loot_ofertas.deal_sources import (
    DealCandidate,
    _pelando_candidate,
    _promobit_candidate,
    canonical_store,
    clean_product_url,
    resolve_promobit_url,
    trusted_product_url,
)


class FakePage:
    def __init__(self, text):
        self.data = text.encode()
        self.headers = Message()
        self.headers["Content-Type"] = "text/html; charset=utf-8"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit=-1):
        return self.data[:limit]


class DealSourcesTests(unittest.TestCase):
    def test_reads_pelando_product_and_calculates_original_price(self):
        candidate = _pelando_candidate({
            "id": 10,
            "title": "Monitor Gamer 144 Hz",
            "price": 800,
            "discountPercentage": 20,
            "temperature": 250,
            "commentCount": 8,
            "viewStats": {"count": 1200},
            "sourceUrl": "https://www.magazineluiza.com.br/monitor/p/abc123/?utm_source=pelando",
            "code": "GAMER10",
            "store": {"name": "Magazine Luiza"},
        })

        self.assertIsNotNone(candidate)
        self.assertEqual("magalu", candidate.store)
        self.assertEqual(1000.0, candidate.original_price)
        self.assertEqual("GAMER10", candidate.coupon)
        self.assertNotIn("utm_source", candidate.url)
        self.assertGreater(candidate.community_score, 0)

    def test_rejects_coupon_only_pelando_entry(self):
        self.assertIsNone(_pelando_candidate({
            "title": "Cupom geral", "price": None,
            "sourceUrl": "https://www.amazon.com.br", "store": {"name": "Amazon"},
        }))

    def test_reads_promobit_but_keeps_it_unresolved(self):
        candidate = _promobit_candidate({
            "offerId": 42,
            "offerTitle": "SSD NVMe 1TB",
            "offerPrice": 299.9,
            "offerOldPrice": 399.9,
            "offerSlug": "ssd-nvme-1tb",
            "storeName": "KaBuM",
        })

        self.assertEqual("kabum", candidate.store)
        self.assertFalse(trusted_product_url(candidate.url, candidate.store))

    def test_store_host_must_match_declared_store(self):
        self.assertTrue(trusted_product_url("https://www.amazon.com.br/dp/B012345678", "amazon"))
        self.assertFalse(trusted_product_url("https://example.com/dp/B012345678", "amazon"))

    def test_clean_url_keeps_product_parameters(self):
        cleaned = clean_product_url(
            "https://www.mercadolivre.com.br/p/MLB1?wid=MLB2&utm_source=x&ref=abc"
        )
        self.assertIn("wid=MLB2", cleaned)
        self.assertNotIn("utm_source", cleaned)
        self.assertNotIn("ref=", cleaned)

    def test_store_aliases(self):
        self.assertEqual("mercadolivre", canonical_store("Mercado Livre"))
        self.assertEqual("magalu", canonical_store("Magazine Você"))
        self.assertEqual("kabum", canonical_store("KaBuM!"))

    @patch("urllib.request.urlopen")
    def test_resolves_promobit_ued_without_affiliate_tracking(self, urlopen):
        urlopen.return_value = FakePage(
            '<a href="https://awin.example/click?ued='
            'https%3A%2F%2Fwww.kabum.com.br%2Fproduto%2F123%2Fssd%3Futm_source%3Dx">'
        )
        candidate = DealCandidate(
            "SSD Gamer", 299, "kabum", "https://www.promobit.com.br/oferta/ssd",
            "promobit", "123", community_score=80,
        )

        resolved = resolve_promobit_url(candidate)

        self.assertEqual("https://www.kabum.com.br/produto/123/ssd", resolved)


if __name__ == "__main__":
    unittest.main()
