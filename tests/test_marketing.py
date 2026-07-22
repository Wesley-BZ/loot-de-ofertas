import unittest

from loot_ofertas.formatting import format_offer
from loot_ofertas.marketing import PHRASES, category_for, headline_for
from loot_ofertas.product_catalog import PRODUCT_PROFILES
from loot_ofertas.models import Offer


class MarketingTests(unittest.TestCase):
    def test_mouse_gets_mouse_headline(self):
        offer = Offer("Mouse Gamer sem fio", "https://example.com/mouse", 88.79, "magalu")
        self.assertEqual("mouse_wireless", category_for(offer))
        headline = headline_for(offer)
        self.assertTrue(any(headline.startswith(phrase) for phrase in PHRASES["mouse_wireless"]))

    def test_recent_headline_is_not_repeated(self):
        offer = Offer("Mouse Gamer sem fio", "https://example.com/mouse", 88.79, "magalu")
        first = headline_for(offer)
        self.assertNotEqual(first, headline_for(offer, {first}))

    def test_catalog_has_100_products_and_100_unique_phrases_each(self):
        self.assertEqual(100, len(PRODUCT_PROFILES))
        for profile in PRODUCT_PROFILES:
            self.assertEqual(100, len(PHRASES[profile.key]), profile.key)
            self.assertEqual(100, len(set(PHRASES[profile.key])), profile.key)

    def test_headline_avoids_last_ten_for_same_product_type(self):
        offer = Offer("Mouse Gamer sem fio", "https://example.com/mouse", 88.79, "magalu")
        category = category_for(offer)
        blocked = {f"{phrase} 🎯📶" for phrase in PHRASES[category][:10]}
        self.assertNotIn(headline_for(offer, blocked), blocked)

    def test_common_marketplace_titles_get_specific_profiles(self):
        samples = {
            "Teclado mecânico Redragon switch red": "keyboard_mechanical",
            "SSD Kingston NV2 1TB NVMe M.2": "ssd_nvme",
            "Console PlayStation 5 Slim": "ps5_console",
            "Controle sem fio Xbox Series": "xbox_controller",
            "Kit Fan RGB Corsair 120mm": "case_fan",
        }
        for title, expected in samples.items():
            offer = Offer(title, "https://example.com", 100, "teste")
            self.assertEqual(expected, category_for(offer), title)

    def test_message_matches_compact_promo_style(self):
        offer = Offer(
            "Mouse Gamer", "https://example.com", 88.79, "magalu",
            coupon="BEMVINDO20 (1ª compra acima de R$ 80)",
        )
        message = format_offer(offer)
        self.assertIn("Use o Cupom: *BEMVINDO20*", message)
        self.assertIn("Loja: Magalu", message)
        self.assertNotIn("OFERTA GAMER", message)


if __name__ == "__main__":
    unittest.main()
