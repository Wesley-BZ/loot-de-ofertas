import unittest
from unittest.mock import patch

from loot_ofertas.coupons import WELCOME_BANNER, WELCOME_BANNER_SHA256, coupon_for_offer, verified_magalu_coupons
from loot_ofertas.models import Offer


class CouponTests(unittest.TestCase):
    def tearDown(self):
        verified_magalu_coupons.cache_clear()

    @patch("loot_ofertas.coupons._download")
    def test_verified_welcome_coupon_for_eligible_offer(self, download):
        banner = b"verified-banner"
        with patch("loot_ofertas.coupons.WELCOME_BANNER_SHA256", __import__("hashlib").sha256(banner).hexdigest()):
            download.side_effect = [f'<img src="{WELCOME_BANNER}">'.encode(), banner]
            offer = Offer("Mouse gamer", "https://example.com", 88.79, "magalu")
            self.assertIn("BEMVINDO20", coupon_for_offer(offer, "https://coupons.example"))

    @patch("loot_ofertas.coupons._download")
    def test_changed_banner_is_not_announced(self, download):
        download.side_effect = [f'<img src="{WELCOME_BANNER}">'.encode(), b"changed"]
        offer = Offer("Mouse gamer", "https://example.com", 88.79, "magalu")
        self.assertIsNone(coupon_for_offer(offer, "https://coupons.example"))


if __name__ == "__main__":
    unittest.main()
