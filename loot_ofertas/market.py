from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import statistics
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import Offer
from .coupons import coupon_discount


TRUSTED_STORES = {
    "amazon": "Amazon", "amazon.com.br": "Amazon",
    "magalu": "Magalu", "magazine luiza": "Magalu", "magazinevoce": "Magalu",
    "mercado livre": "Mercado Livre", "mercadolivre": "Mercado Livre",
    "kabum": "KaBuM!", "ka bu m": "KaBuM!",
    "pichau": "Pichau", "terabyte": "TerabyteShop",
    "fast shop": "Fast Shop", "casas bahia": "Casas Bahia",
    "dell": "Dell", "lenovo": "Lenovo", "samsung": "Samsung",
    "shopee": "Shopee",
}
STOPWORDS = {
    "a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "para", "com",
    "novo", "nova", "preto", "preta", "branco", "branca", "bivolt", "127v", "220v",
}


@dataclass(slots=True)
class MarketQuote:
    title: str
    store: str
    price: float
    source_url: str
    shipping_price: float | None = None
    rating: float | None = None
    reviews: int | None = None
    source: str = "portfolio"

    @property
    def effective_price(self) -> float:
        return round(self.price + (self.shipping_price or 0), 2)


@dataclass(slots=True)
class DealAssessment:
    label: str
    score: float
    current_price: float
    market_median: float | None
    best_competitor_price: float | None
    market_savings_percent: float | None
    competitor_count: int
    history_median: float | None
    history_savings_percent: float | None
    confidence: str
    reasons: list[str]


class MarketRepository:
    def __init__(self, database: str | Path):
        self.database = str(database)

    def initialize(self) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    normalized_title TEXT NOT NULL,
                    store TEXT NOT NULL,
                    price REAL NOT NULL,
                    shipping_price REAL,
                    source_url TEXT NOT NULL,
                    rating REAL,
                    reviews INTEGER,
                    source TEXT NOT NULL,
                    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_market_quotes_time
                    ON market_quotes(observed_at DESC);
                CREATE TABLE IF NOT EXISTS deal_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    offer_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    score REAL NOT NULL,
                    market_median REAL,
                    best_competitor_price REAL,
                    market_savings_percent REAL,
                    competitor_count INTEGER NOT NULL,
                    history_median REAL,
                    history_savings_percent REAL,
                    confidence TEXT NOT NULL,
                    reasons TEXT NOT NULL,
                    assessed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_deal_assessments_offer
                    ON deal_assessments(offer_id, assessed_at DESC);
                """
            )

    def record(self, quote: MarketQuote) -> None:
        self.initialize()
        with sqlite3.connect(self.database) as connection:
            last = connection.execute(
                """SELECT price, shipping_price, observed_at FROM market_quotes
                   WHERE normalized_title=? AND store=? ORDER BY id DESC LIMIT 1""",
                (_normalize(quote.title), quote.store),
            ).fetchone()
            if last and float(last[0]) == quote.price and last[1] == quote.shipping_price:
                observed = datetime.fromisoformat(str(last[2]).replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - observed < timedelta(hours=6):
                    return
            connection.execute(
                """INSERT INTO market_quotes(
                    title, normalized_title, store, price, shipping_price, source_url,
                    rating, reviews, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (quote.title, _normalize(quote.title), quote.store, quote.price,
                 quote.shipping_price, quote.source_url, quote.rating, quote.reviews, quote.source),
            )

    def matching_quotes(self, title: str, hours: int = 48) -> list[MarketQuote]:
        self.initialize()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM market_quotes WHERE observed_at>=? ORDER BY id DESC", (cutoff,)
            ).fetchall()
        latest: dict[str, MarketQuote] = {}
        for row in rows:
            if row["store"] in latest or not same_product(title, row["title"]):
                continue
            latest[row["store"]] = MarketQuote(
                title=row["title"], store=row["store"], price=float(row["price"]),
                shipping_price=row["shipping_price"], source_url=row["source_url"],
                rating=row["rating"], reviews=row["reviews"], source=row["source"],
            )
        return list(latest.values())

    def save_assessment(self, offer_id: int, assessment: DealAssessment) -> None:
        self.initialize()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                """INSERT INTO deal_assessments(
                    offer_id, label, score, market_median, best_competitor_price,
                    market_savings_percent, competitor_count, history_median,
                    history_savings_percent, confidence, reasons
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (offer_id, assessment.label, assessment.score, assessment.market_median,
                 assessment.best_competitor_price, assessment.market_savings_percent,
                 assessment.competitor_count, assessment.history_median,
                 assessment.history_savings_percent, assessment.confidence,
                 json.dumps(assessment.reasons, ensure_ascii=False)),
            )


def assess_deal(offer: Offer, quotes: list[MarketQuote], history_prices: list[float]) -> DealAssessment:
    discount_value = coupon_discount(offer)
    current = round(max(0, offer.price - discount_value) + (offer.shipping_price or 0), 2)
    competitors = [q for q in quotes if normalize_store(q.store) != normalize_store(offer.store)]
    competitor_prices = [q.effective_price for q in competitors if q.effective_price > 0]
    market_median = statistics.median(competitor_prices) if competitor_prices else None
    best = min(competitor_prices) if competitor_prices else None
    market_savings = ((market_median - current) / market_median * 100) if market_median else None
    valid_history = [float(price) for price in history_prices if price > 0]
    history_median = statistics.median(valid_history) if len(valid_history) >= 3 else None
    history_savings = ((history_median - current) / history_median * 100) if history_median else None
    claimed = offer.discount_percent
    reasons: list[str] = []
    if market_savings is not None:
        reasons.append(f"{market_savings:.1f}% abaixo da mediana atual de outras lojas")
    if best is not None and current < best:
        reasons.append(f"R$ {best-current:.2f} abaixo do concorrente mais barato")
    if claimed >= 10:
        reasons.append(f"desconto anunciado de {claimed:.1f}%")
    if discount_value > 0:
        reasons.append(f"cupom reduz R$ {discount_value:.2f} quando as condições forem atendidas")
    if history_savings is not None:
        relation = "abaixo" if history_savings >= 0 else "acima"
        reasons.append(f"{abs(history_savings):.1f}% {relation} da mediana histórica própria")

    count = len(competitor_prices)
    beats_best = best is not None and current <= best * 0.95
    strong_market = market_savings is not None and market_savings >= 12
    fair_market = market_savings is not None and market_savings >= 5
    if count >= 2 and strong_market and beats_best:
        label = "imperdivel"
    elif count >= 1 and (strong_market or beats_best):
        label = "excelente"
    elif count >= 1 and (fair_market or (claimed >= 15 and current <= (market_median or current) * 1.03)):
        label = "promocao"
    elif count == 0 and normalize_store(offer.store) == "Magalu" and claimed >= 10:
        label = "promocao_loja"
        reasons.append("desconto confirmado dentro da loja Magazine Você")
    elif count == 0 and claimed >= 20:
        label = "potencial_promocao"
        reasons.append("aguardando comparação com outras lojas")
    else:
        label = "preco_comum"

    score = claimed * 0.45
    score += max(-20, min(50, market_savings or 0)) * 1.6
    score += max(-10, min(20, history_savings or 0)) * 0.25
    score += min(count, 4) * 4
    confidence = "alta" if count >= 3 else "media" if count >= 1 else "baixa"
    return DealAssessment(
        label=label, score=round(score, 2), current_price=current,
        market_median=round(market_median, 2) if market_median else None,
        best_competitor_price=round(best, 2) if best else None,
        market_savings_percent=round(market_savings, 1) if market_savings is not None else None,
        competitor_count=count, history_median=round(history_median, 2) if history_median else None,
        history_savings_percent=round(history_savings, 1) if history_savings is not None else None,
        confidence=confidence, reasons=reasons,
    )


def google_shopping_quotes(title: str) -> list[MarketQuote]:
    api_key = os.getenv("SERPAPI_API_KEY", "").strip()
    if not api_key:
        return []
    params = urllib.parse.urlencode({
        "engine": "google_shopping", "q": title, "gl": "br", "hl": "pt-br",
        "location": os.getenv("SHOPPING_LOCATION", "Brazil"), "api_key": api_key,
    })
    request = urllib.request.Request(
        "https://serpapi.com/search.json?" + params,
        headers={"Accept": "application/json", "User-Agent": "LootDeOfertas/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            payload = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Falha no comparador Google Shopping: {error}") from error
    quotes: list[MarketQuote] = []
    for item in payload.get("shopping_results", []):
        source = str(item.get("source") or "").strip()
        price = item.get("extracted_price")
        candidate_title = str(item.get("title") or "")
        if not source or not isinstance(price, (int, float)) or price <= 0:
            continue
        if not same_product(title, candidate_title) or item.get("second_hand_condition"):
            continue
        store = normalize_store(source)
        if store not in set(TRUSTED_STORES.values()):
            continue
        delivery = _shipping_from_text(str(item.get("delivery") or ""))
        quotes.append(MarketQuote(
            title=candidate_title, store=store, price=float(price),
            shipping_price=delivery, source_url=str(item.get("product_link") or ""),
            rating=_float_or_none(item.get("rating")), reviews=_int_or_none(item.get("reviews")),
            source="google_shopping",
        ))
    return quotes


def same_product(left: str, right: str) -> bool:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return False
    left_models = {token for token in left_tokens if any(char.isdigit() for char in token) and len(token) >= 3}
    right_models = {token for token in right_tokens if any(char.isdigit() for char in token) and len(token) >= 3}
    if left_models and right_models and not (left_models & right_models):
        return False
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return overlap >= 0.34 or bool(left_models & right_models) and overlap >= 0.22


def normalize_store(value: str) -> str:
    normalized = _normalize(value)
    return next((label for key, label in TRUSTED_STORES.items() if key in normalized), value.strip())


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in _normalize(value).split() if len(token) >= 2 and token not in STOPWORDS}


def _shipping_from_text(value: str) -> float | None:
    normalized = _normalize(value)
    if "gratis" in normalized or "free" in normalized:
        return 0.0
    match = re.search(r"(?:r\$)?\s*(\d+[.,]\d{2})", value.casefold())
    return float(match.group(1).replace(",", ".")) if match else None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
