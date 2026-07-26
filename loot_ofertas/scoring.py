from __future__ import annotations

import os
import unicodedata

from .models import Offer

GAMING_TERMS = {
    "gamer": 18,
    "gaming": 18,
    "playstation": 20,
    "ps5": 20,
    "xbox": 20,
    "nintendo": 20,
    "switch": 14,
    "steam deck": 20,
    "placa de video": 20,
    "placa mae": 14,
    "processador": 14,
    "ryzen": 14,
    "intel core": 12,
    "ddr4": 10,
    "ddr5": 12,
    "geforce": 18,
    "radeon": 18,
    "monitor": 12,
    "teclado": 10,
    "mouse": 10,
    "headset": 12,
    "controle": 10,
    "cadeira": 8,
    "ssd": 10,
    "memoria ram": 10,
    "notebook": 8,
    "pc": 5,
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.lower())
    return "".join(char for char in value if not unicodedata.combining(char))


def calculate_score(offer: Offer) -> float:
    text = _normalize(f"{offer.title} {offer.category or ''}")
    relevance = max((weight for term, weight in GAMING_TERMS.items() if term in text), default=-30)
    discount = min(offer.discount_percent, 60) * 0.9
    commission = min(offer.commission_percent or 0, 15) * 0.6
    coupon_bonus = 5 if offer.coupon else 0
    community_bonus = min(max(offer.community_score, 0), 100) * 0.15
    affiliate_stores = {
        value.strip().casefold()
        for value in os.getenv("LOOT_AFFILIATE_STORES", "magalu,shopee,aliexpress").split(",")
        if value.strip()
    }
    has_affiliate_link = (
        offer.store.casefold() in affiliate_stores
        and (
            bool(offer.source_url and offer.affiliate_url != offer.source_url)
            or (
                offer.store.casefold() == "magalu"
                and bool(os.getenv("MAGALU_PROMOTER_ID", "").strip())
            )
        )
    )
    affiliate_bonus = float(os.getenv("LOOT_AFFILIATE_BONUS", "12")) if has_affiliate_link else 0
    return round(
        relevance + discount + commission + coupon_bonus + affiliate_bonus + community_bonus,
        2,
    )
