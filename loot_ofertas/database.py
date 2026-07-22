from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .identity import product_identity
from .models import Offer
from .scheduling import (
    PublicationDecision,
    PublicationPolicy,
    normalize_channel,
    parse_database_datetime,
)
from .scoring import calculate_score


SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    affiliate_url TEXT NOT NULL,
    price REAL NOT NULL CHECK(price >= 0),
    original_price REAL,
    commission_percent REAL,
    store TEXT NOT NULL,
    coupon TEXT,
    image_url TEXT,
    category TEXT,
    headline TEXT,
    score REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TEXT,
    product_key TEXT,
    source_url TEXT,
    seller_name TEXT,
    seller_rating REAL,
    review_count INTEGER,
    sold_count INTEGER,
    shipping_price REAL,
    available INTEGER NOT NULL DEFAULT 1,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_offers_ready_score ON offers(status, score DESC);
CREATE INDEX IF NOT EXISTS idx_offers_product_key ON offers(product_key);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_key TEXT NOT NULL,
    offer_id INTEGER,
    price REAL NOT NULL CHECK(price >= 0),
    original_price REAL,
    shipping_price REAL,
    available INTEGER NOT NULL DEFAULT 1,
    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_key, observed_at DESC);

CREATE TABLE IF NOT EXISTS publication_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    offer_id INTEGER,
    product_key TEXT NOT NULL,
    channel TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    headline TEXT,
    published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_publications_channel_time
    ON publication_history(channel, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_publications_product_time
    ON publication_history(product_key, published_at DESC);

CREATE TABLE IF NOT EXISTS headline_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    headline TEXT NOT NULL,
    offer_id INTEGER,
    used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


MIGRATION_COLUMNS: dict[str, str] = {
    "headline": "TEXT",
    "product_key": "TEXT",
    "source_url": "TEXT",
    "seller_name": "TEXT",
    "seller_rating": "REAL",
    "review_count": "INTEGER",
    "sold_count": "INTEGER",
    "shipping_price": "REAL",
    "available": "INTEGER NOT NULL DEFAULT 1",
    "last_seen_at": "TEXT",
}


class OfferRepository:
    def __init__(self, path: str | Path):
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def connection(self):
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            # Migra primeiro bancos antigos, pois índices do novo schema usam
            # colunas que ainda não existiam no MVP.
            connection.execute(
                """CREATE TABLE IF NOT EXISTS offers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    affiliate_url TEXT NOT NULL,
                    price REAL NOT NULL,
                    store TEXT NOT NULL,
                    score REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ready',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(offers)")}
            legacy_columns = {
                "original_price": "REAL", "commission_percent": "REAL", "coupon": "TEXT",
                "image_url": "TEXT", "category": "TEXT", "published_at": "TEXT",
            }
            for name, definition in {**legacy_columns, **MIGRATION_COLUMNS}.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE offers ADD COLUMN {name} {definition}")
            connection.executescript(SCHEMA)
            self._backfill_product_keys(connection)
            connection.execute(
                """INSERT INTO publication_history(
                    offer_id, product_key, channel, category, price, headline, published_at
                )
                SELECT o.id, o.product_key, 'unknown', COALESCE(o.category, 'generic'),
                       o.price, o.headline, o.published_at
                FROM offers o
                WHERE o.published_at IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM publication_history p WHERE p.offer_id = o.id
                  )"""
            )

    def _backfill_product_keys(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT id, store, affiliate_url, source_url, title FROM offers WHERE product_key IS NULL"
        ).fetchall()
        for row in rows:
            source_url = row["source_url"] or row["affiliate_url"]
            key = product_identity(row["store"], source_url, row["title"])
            connection.execute(
                """UPDATE offers SET product_key=?, source_url=COALESCE(source_url, ?),
                   last_seen_at=COALESCE(last_seen_at, created_at, CURRENT_TIMESTAMP)
                   WHERE id=?""",
                (key, source_url, row["id"]),
            )

    def add(self, offer: Offer) -> int:
        offer.score = calculate_score(offer)
        source_url = offer.source_url or offer.affiliate_url
        offer.product_key = offer.product_key or product_identity(offer.store, source_url, offer.title)
        fingerprint = hashlib.sha256(offer.product_key.encode("utf-8")).hexdigest()
        with self.connection() as connection:
            existing = connection.execute(
                "SELECT id, fingerprint FROM offers WHERE product_key=? ORDER BY id DESC LIMIT 1",
                (offer.product_key,),
            ).fetchone()
            values = (
                offer.title, offer.affiliate_url, offer.price, offer.original_price,
                offer.commission_percent, offer.store, offer.coupon, offer.image_url,
                offer.category, offer.score, offer.product_key, source_url, offer.seller_name,
                offer.seller_rating, offer.review_count, offer.sold_count,
                offer.shipping_price, int(offer.available),
            )
            if existing:
                offer_id = int(existing["id"])
                connection.execute(
                    """UPDATE offers SET
                        title=?, affiliate_url=?, price=?, original_price=?, commission_percent=?,
                        store=?, coupon=?, image_url=?, category=?, score=?, product_key=?, source_url=?,
                        seller_name=?, seller_rating=?, review_count=?, sold_count=?, shipping_price=?,
                        available=?, status='ready', last_seen_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (*values, offer_id),
                )
            else:
                cursor = connection.execute(
                    """INSERT INTO offers (
                        fingerprint, title, affiliate_url, price, original_price,
                        commission_percent, store, coupon, image_url, category, score,
                        product_key, source_url, seller_name, seller_rating, review_count,
                        sold_count, shipping_price, available, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    RETURNING id""",
                    (fingerprint, *values),
                )
                offer_id = int(cursor.fetchone()[0])
            self._record_price(connection, offer_id, offer)
            return offer_id

    def _record_price(self, connection: sqlite3.Connection, offer_id: int, offer: Offer) -> None:
        last = connection.execute(
            """SELECT price, original_price, shipping_price, available, observed_at
               FROM price_history WHERE product_key=? ORDER BY id DESC LIMIT 1""",
            (offer.product_key,),
        ).fetchone()
        unchanged = last and (
            float(last["price"]) == offer.price
            and last["original_price"] == offer.original_price
            and last["shipping_price"] == offer.shipping_price
            and bool(last["available"]) == offer.available
        )
        if unchanged and datetime.now(timezone.utc) - parse_database_datetime(last["observed_at"]) < timedelta(hours=6):
            return
        connection.execute(
            """INSERT INTO price_history(
                product_key, offer_id, price, original_price, shipping_price, available
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                offer.product_key, offer_id, offer.price, offer.original_price,
                offer.shipping_price, int(offer.available),
            ),
        )

    def ready(self, limit: int = 10, min_score: float = 0) -> list[Offer]:
        with self.connection() as connection:
            rows = connection.execute(
                """SELECT * FROM offers
                   WHERE status = 'ready' AND available = 1 AND score >= ?
                   ORDER BY score DESC, created_at ASC LIMIT ?""",
                (min_score, limit),
            ).fetchall()
        return [self._offer_from_row(row) for row in rows]

    def get(self, offer_id: int) -> Offer | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
        return self._offer_from_row(row) if row else None

    def eligible_ready(
        self,
        channel: str,
        policy: PublicationPolicy,
        limit: int = 10,
        min_score: float = 0,
        now: datetime | None = None,
    ) -> list[Offer]:
        normalized_channel = normalize_channel(channel)
        candidates = self.ready(max(limit * 10, 100), min_score)
        local_now = policy.local_now(now)
        day_start, day_end = policy.local_day_bounds_utc(local_now)
        cooldown_start = local_now.astimezone(timezone.utc) - timedelta(days=policy.repeat_cooldown_days)
        with self.connection() as connection:
            publications = connection.execute(
                "SELECT * FROM publication_history WHERE channel=? ORDER BY id DESC",
                (normalized_channel,),
            ).fetchall()
        today = [row for row in publications if day_start <= parse_database_datetime(row["published_at"]) < day_end]
        category_counts: dict[str, int] = {}
        for row in today:
            category_counts[row["category"]] = category_counts.get(row["category"], 0) + 1
        eligible: list[Offer] = []
        selected_categories = dict(category_counts)
        from .marketing import category_for

        for offer in candidates:
            category = category_for(offer)
            if selected_categories.get(category, 0) >= policy.category_daily_limit:
                continue
            previous = next((row for row in publications if row["product_key"] == offer.product_key), None)
            if previous and parse_database_datetime(previous["published_at"]) >= cooldown_start:
                required_price = float(previous["price"]) * (1 - policy.repeat_price_drop_percent / 100)
                if offer.price > required_price:
                    continue
            eligible.append(offer)
            selected_categories[category] = selected_categories.get(category, 0) + 1
            if len(eligible) >= limit:
                break
        return eligible

    def publication_decision(
        self,
        channel: str,
        policy: PublicationPolicy,
        now: datetime | None = None,
    ) -> PublicationDecision:
        local_now = policy.local_now(now)
        if not policy.is_active_hour(local_now):
            return PublicationDecision(False, "fora do horário de publicação")
        normalized_channel = normalize_channel(channel)
        day_start, day_end = policy.local_day_bounds_utc(local_now)
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT published_at FROM publication_history WHERE channel=? ORDER BY id DESC",
                (normalized_channel,),
            ).fetchall()
        timestamps = [parse_database_datetime(row["published_at"]) for row in rows]
        if sum(day_start <= stamp < day_end for stamp in timestamps) >= policy.daily_limit:
            return PublicationDecision(False, "limite diário atingido")
        if timestamps:
            elapsed = local_now.astimezone(timezone.utc) - timestamps[0]
            interval = timedelta(minutes=policy.min_interval_minutes)
            if elapsed < interval:
                wait = max(1, int((interval - elapsed).total_seconds()))
                return PublicationDecision(False, "intervalo mínimo ainda não terminou", wait)
        return PublicationDecision(True, "publicação liberada")

    def mark_published(self, offer_id: int, channel: str = "unknown", category: str = "generic") -> None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
            if row is None:
                raise ValueError(f"Oferta {offer_id} não encontrada")
            connection.execute(
                "UPDATE offers SET status='published', published_at=CURRENT_TIMESTAMP WHERE id=?",
                (offer_id,),
            )
            connection.execute(
                """INSERT INTO publication_history(
                    offer_id, product_key, channel, category, price, headline
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    offer_id, row["product_key"], normalize_channel(channel), category,
                    row["price"], row["headline"],
                ),
            )

    def recent_headlines(self, category: str, limit: int) -> set[str]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT headline FROM headline_history WHERE category=? ORDER BY id DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        return {str(row[0]) for row in rows}

    def record_headline(self, offer: Offer, category: str) -> None:
        if not offer.headline:
            return
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO headline_history(category, headline, offer_id) VALUES (?, ?, ?)",
                (category, offer.headline, offer.id),
            )
            connection.execute("UPDATE offers SET headline=? WHERE id=?", (offer.headline, offer.id))

    @staticmethod
    def _offer_from_row(row: sqlite3.Row) -> Offer:
        values = {key: row[key] for key in Offer.__dataclass_fields__ if key in row.keys()}
        values["available"] = bool(values.get("available", True))
        return Offer(**values)
