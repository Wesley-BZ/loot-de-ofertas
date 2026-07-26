import unittest

from loot_ofertas.deal_sources import (
    _pelando_candidate,
    _promobit_candidate,
    canonical_store,
    clean_product_url,
    trusted_product_url,
)


class DealSourcesTests(unittest.TestCase):
    def test_reads_pelando_product_and_calculates_original_price(self):
        candidate = _pelando_candidate({
            "id": 10,
            "title": "Monitor Gamer 144 Hz",
            "price": 800,
            "discountPercentage": 20,
            "sourceUrl": "https://www.magazineluiza.com.br/monitor/p/abc123/?utm_source=pelando",
            "code": "GAMER10",
            "store": {"name": "Magazine Luiza"},
        })

        self.assertIsNotNone(candidate)
        self.assertEqual("magalu", candidate.store)
        self.assertEqual(1000.0, candidate.original_price)
        self.assertEqual("GAMER10", candidate.coupon)
        self.assertNotIn("utm_source", candidate.url)

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


if __name__ == "__main__":
    unittest.main()
