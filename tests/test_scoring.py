import unittest

from loot_ofertas.models import Offer
from loot_ofertas.scoring import calculate_score


class ScoringTests(unittest.TestCase):
    def test_gaming_offer_with_discount_scores_high(self):
        offer = Offer(
            title="Mouse Gamer RGB", affiliate_url="https://example.com/a",
            price=100, original_price=200, commission_percent=5, store="magalu",
        )
        self.assertGreaterEqual(calculate_score(offer), 60)

    def test_unrelated_offer_is_penalized(self):
        offer = Offer(title="Panela", affiliate_url="https://example.com/b", price=100, store="magalu")
        self.assertLess(calculate_score(offer), 0)


if __name__ == "__main__":
    unittest.main()

