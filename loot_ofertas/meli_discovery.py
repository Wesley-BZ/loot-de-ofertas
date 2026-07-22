from __future__ import annotations

import re
import unicodedata
import urllib.parse
from dataclasses import dataclass
from typing import Any

from .capture import CaptureError, _first_price
from .meli import MeliError, api_get
from .models import Offer


MELI_GAMER_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("MLB99245", "monitores"),
    ("MLB1652", "notebooks"),
    ("MLB1649", "computadores"),
    ("MLB1672", "HDs e SSDs"),
    ("MLB1694", "memórias RAM"),
    ("MLB1693", "processadores"),
    ("MLB5867", "roteadores"),
    ("MLB73364", "webcams"),
    ("MLB99889", "tablets"),
    ("MLB1055", "celulares"),
    ("MLB11172", "consoles"),
    ("MLB439596", "headsets gamer"),
    ("MLB439599", "microfones gamer"),
    ("MLB439598", "cadeiras gamer"),
    ("MLB448170", "controles gamer"),
)


@dataclass(frozen=True, slots=True)
class MeliDiscovery:
    offers: list[Offer]
    errors: list[str]


def discover_meli_highlights(limit: int = 30) -> MeliDiscovery:
    ranked: list[tuple[int, str, str]] = []
    errors: list[str] = []
    for category_id, category_name in MELI_GAMER_CATEGORIES:
        try:
            payload = api_get(f"highlights/MLB/category/{category_id}")
            for row in payload.get("content", []) if isinstance(payload, dict) else []:
                product_id = str(row.get("id") or "").upper()
                if row.get("type") == "PRODUCT" and re.fullmatch(r"MLB\d+", product_id):
                    ranked.append((int(row.get("position") or 999), product_id, category_name))
        except MeliError as error:
            errors.append(f"{category_name}: {error}")

    # Intercala categorias pelos mais vendidos, evitando que uma única área ocupe todo o limite.
    ranked.sort(key=lambda row: row[0])
    found: dict[str, Offer] = {}
    for position, product_id, category_name in ranked:
        try:
            offer = _offer_from_product(product_id, category_name)
        except (MeliError, CaptureError, KeyError) as error:
            errors.append(f"{product_id}: {error}")
            continue
        found[offer.product_key or offer.affiliate_url] = offer
        if len(found) >= limit:
            break
    return MeliDiscovery(list(found.values()), errors)


def _offer_from_product(product_id: str, category_name: str) -> Offer:
    product = api_get(f"products/{product_id}")
    listings_payload = api_get(f"products/{product_id}/items")
    listings = listings_payload.get("results", []) if isinstance(listings_payload, dict) else []
    valid = [row for row in listings if isinstance(row, dict) and _first_price(row.get("price"))]
    if not valid:
        raise CaptureError("produto sem oferta disponível")
    listing = min(valid, key=lambda row: _first_price(row.get("price")) or float("inf"))
    title = str(product.get("name") or product.get("family_name") or "").strip()
    price = _first_price(listing.get("price"))
    if not title or price is None:
        raise CaptureError("produto sem título ou preço")
    original = _first_price(listing.get("original_price"))
    item_id = str(listing.get("item_id") or "").upper()
    if not re.fullmatch(r"MLB\d+", item_id):
        raise CaptureError("oferta sem item_id")
    pictures = product.get("pictures") or []
    image = next(
        (str(row.get("secure_url")) for row in pictures if isinstance(row, dict) and row.get("secure_url")),
        None,
    )
    shipping = listing.get("shipping") or {}
    link = _catalog_link(product_id, item_id, title)
    return Offer(
        title=title,
        affiliate_url=link,
        source_url=link,
        product_key=f"mercadolivre:{item_id.casefold()}",
        price=price,
        original_price=original if original and original > price else None,
        store="mercadolivre",
        image_url=image,
        category=category_name,
        shipping_price=0.0 if shipping.get("free_shipping") else None,
        available=True,
    )


def _catalog_link(product_id: str, item_id: str, title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:120] or "produto"
    query = urllib.parse.urlencode({"pdp_filters": f"item_id:{item_id}", "wid": item_id})
    return f"https://www.mercadolivre.com.br/{slug}/p/{product_id}?{query}"
