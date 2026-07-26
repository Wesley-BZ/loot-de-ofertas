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

    def test_affiliate_store_receives_priority_bonus(self):
        offer = Offer(
            title="Mouse Gamer", affiliate_url="https://s.shopee.test/afiliado",
            source_url="https://shopee.test/item", price=100, store="shopee",
        )
        other = Offer(title="Mouse Gamer", affiliate_url="https://outra.test/item", price=100, store="outra")

        self.assertEqual(calculate_score(offer) - calculate_score(other), 12)

    def test_community_signal_adds_capped_bonus(self):
        ordinary = Offer("Mouse Gamer", "https://loja/item", 100, "outra")
        popular = Offer(
            "Mouse Gamer", "https://loja/item2", 100, "outra",
            discovery_source="pelando", community_score=100,
        )

        self.assertEqual(15, calculate_score(popular) - calculate_score(ordinary))


if __name__ == "__main__":
    unittest.main()
