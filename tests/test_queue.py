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

    def test_publication_gate_blocks_twenty_minute_interval(self):
        offer_id = self.add_mouse()
        self.repo.mark_published(offer_id, "wppconnect", "mouse_gamer")
        with self.repo.connection() as connection:
            stamp = (self.now - timedelta(minutes=5)).astimezone(timezone.utc).isoformat()
            connection.execute("UPDATE publication_history SET published_at=?", (stamp,))
        decision = self.repo.publication_decision("wppconnect", self.policy, self.now)
        self.assertFalse(decision.allowed)
        self.assertGreaterEqual(decision.wait_seconds, 14 * 60)

    def test_product_only_repeats_early_after_ten_percent_drop(self):
        offer_id = self.add_mouse(100)
        self.repo.mark_published(offer_id, "wppconnect", "mouse_gamer")
        with self.repo.connection() as connection:
            stamp = (self.now - timedelta(days=1)).astimezone(timezone.utc).isoformat()
            connection.execute("UPDATE publication_history SET published_at=?", (stamp,))
        self.add_mouse(95)
        self.assertEqual([], self.repo.eligible_ready("wppconnect", self.policy, now=self.now))
        self.add_mouse(90)
        self.assertEqual(1, len(self.repo.eligible_ready("wppconnect", self.policy, now=self.now)))

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
            "amazon:B0ABC12345",
            product_identity("amazon", "https://amazon.com.br/dp/B0ABC12345?ref_=abc"),
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
