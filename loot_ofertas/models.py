from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Offer:
    title: str
    affiliate_url: str
    price: float
    store: str
    original_price: float | None = None
    commission_percent: float | None = None
    coupon: str | None = None
    image_url: str | None = None
    category: str | None = None
    score: float = 0
    id: int | None = None
    headline: str | None = None
    product_key: str | None = None
    source_url: str | None = None
    seller_name: str | None = None
    seller_rating: float | None = None
    review_count: int | None = None
    sold_count: int | None = None
    shipping_price: float | None = None
    available: bool = True
    status: str = "ready"

    @property
    def discount_percent(self) -> float:
        if not self.original_price or self.original_price <= self.price:
            return 0.0
        return round((1 - self.price / self.original_price) * 100, 1)
