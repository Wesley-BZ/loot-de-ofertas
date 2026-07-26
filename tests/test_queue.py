import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loot_ofertas.database import OfferRepository
from loot_ofertas.identity import product_identity
from loot_ofertas.models import Offer
from loot_ofertas.scheduling import PublicationPolicy


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tempdir.name) / "offers.db"
        self.repo = OfferRepository(self.path)
        self.repo.initialize()
        self.policy = PublicationPolicy(
            min_interval_minutes=20,
            daily_limit=15,
            category_daily_limit=3,
            start_hour=9,
            end_hour=22,
            repeat_cooldown_days=7,
            absolute_repeat_cooldown_days=3,
            repeat_price_drop_percent=10,
        )
        self.now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone(timedelta(hours=-3)))

    def tearDown(self):
        self.tempdir.cleanup()

    def add_mouse(self, price=100):
        return self.repo.add(
            Offer(
                "Mouse Gamer RGB", "https://mercadolivre.com.br/MLB-123456",
                price, "mercado livre", original_price=200,
            )
        )

    def test_same_product_updates_offer_and_records_price_history(self):
        first_id = self.add_mouse(100)
        second_id = self.add_mouse(80)
        self.assertEqual(first_id, second_id)
        with self.repo.connection() as connection:
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM offers").fetchone()[0])
            self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM price_history").fetchone()[0])

    def test_same_product_merges_community_sources_and_keeps_strongest_signal(self):
        first = Offer(
            "Processador Ryzen", "https://kabum.com.br/produto/426262/processador",
            1900, "kabum", coupon="PELANDO10",
            discovery_source="pelando", community_score=90,
        )
        second = Offer(
            "AMD Ryzen 7800X3D", "https://www.kabum.com.br/produto/426262/outro-slug",
            1899, "kabum", discovery_source="promobit", community_score=40,
        )
        first_id = self.repo.add(first)
        second_id = self.repo.add(second)
        merged = self.repo.get(second_id)
        self.assertEqual(first_id, second_id)
        self.assertEqual("pelando + promobit", merged.discovery_source)
        self.assertEqual(90, merged.community_score)
        self.assertEqual("PELANDO10", merged.coupon)

    def test_publication_gate_blocks_twenty_minute_interval(self):
        offer_id = self.add_mouse()
        self.repo.mark_published(offer_id, "wppconnect", "mouse_gamer")
        with self.repo.connection() as connection:
            stamp = (self.now - timedelta(minutes=5)).astimezone(timezone.utc).isoformat()
            connection.execute("UPDATE publication_history SET published_at=?", (stamp,))
        decision = self.repo.publication_decision("wppconnect", self.policy, self.now)
        self.assertFalse(decision.allowed)
        self.assertGreaterEqual(decision.wait_seconds, 14 * 60)

    def test_publication_gate_allows_small_scheduler_drift(self):
        offer_id = self.add_mouse()
        self.repo.mark_published(offer_id, "wppconnect", "mouse_gamer")
        with self.repo.connection() as connection:
            stamp = (self.now - timedelta(minutes=19, seconds=35)).astimezone(timezone.utc).isoformat()
            connection.execute("UPDATE publication_history SET published_at=?", (stamp,))
        self.assertTrue(self.repo.publication_decision("wppconnect", self.policy, self.now).allowed)

    def test_product_only_repeats_early_after_ten_percent_drop(self):
        offer_id = self.add_mouse(100)
        self.repo.mark_published(offer_id, "wppconnect", "mouse_gamer")
        with self.repo.connection() as connection:
            stamp = (self.now - timedelta(days=4)).astimezone(timezone.utc).isoformat()
            connection.execute("UPDATE publication_history SET published_at=?", (stamp,))
        self.add_mouse(95)
        self.assertEqual([], self.repo.eligible_ready("wppconnect", self.policy, now=self.now))
        self.add_mouse(90)
        self.assertEqual(1, len(self.repo.eligible_ready("wppconnect", self.policy, now=self.now)))

    def test_product_never_repeats_inside_absolute_three_day_window(self):
        offer_id = self.add_mouse(100)
        self.repo.mark_published(offer_id, "wppconnect", "mouse_gamer")
        with self.repo.connection() as connection:
            stamp = (self.now - timedelta(days=2)).astimezone(timezone.utc).isoformat()
            connection.execute("UPDATE publication_history SET published_at=?", (stamp,))
        self.add_mouse(50)
        self.assertEqual([], self.repo.eligible_ready("wppconnect", self.policy, now=self.now))

    def test_outside_active_hours_is_blocked(self):
        early = self.now.replace(hour=8)
        self.assertFalse(self.repo.publication_decision("wppconnect", self.policy, early).allowed)

    def test_marketplace_ids_are_stable(self):
        self.assertEqual(
            "mercadolivre:MLB123456",
            product_identity("mercado livre", "https://produto.mercadolivre.com.br/MLB-123456?utm_source=x"),
        )
        self.assertEqual(
            "mercadolivre:MLB6208586170",
            product_identity(
                "mercado livre",
                "https://www.mercadolivre.com.br/produto/up/MLBU3766913692?pdp_filters=item_id%3AMLB6208586170",
            ),
        )
        self.assertEqual(
            "mercadolivre:catalog:MLB54987753",
            product_identity(
                "mercadolivre",
                "https://www.mercadolivre.com.br/galaxy-a17/p/MLB54987753"
                "?pdp_filters=item_id%3AMLB4732041735&wid=MLB4732041735",
            ),
        )
        self.assertEqual(
            "amazon:B0ABC12345",
            product_identity("amazon", "https://amazon.com.br/dp/B0ABC12345?ref_=abc"),
        )
        self.assertEqual(
            "kabum:426262",
            product_identity("kabum", "https://www.kabum.com.br/produto/426262/slug-a"),
        )
        self.assertEqual(
            "magalu:238306600",
            product_identity("magalu", "https://www.magazinevoce.com.br/loja/notebook/p/238306600/in/nota/"),
        )


class MigrationTests(unittest.TestCase):
    def test_old_database_is_migrated_without_losing_offer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """CREATE TABLE offers(
                        id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, title TEXT,
                        affiliate_url TEXT, price REAL, store TEXT, score REAL,
                        status TEXT, created_at TEXT
                    )"""
                )
                connection.execute(
                    "INSERT INTO offers VALUES(1, 'x', 'Mouse Gamer', 'https://loja/item', 99, 'loja', 40, 'ready', CURRENT_TIMESTAMP)"
                )
                connection.commit()
            finally:
                connection.close()
            repo = OfferRepository(path)
            repo.initialize()
            offer = repo.ready()[0]
            self.assertEqual("Mouse Gamer", offer.title)
            self.assertTrue(offer.product_key)


if __name__ == "__main__":
    unittest.main()
