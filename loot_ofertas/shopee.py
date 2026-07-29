from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from .capture import CaptureError
from .models import Offer


DEFAULT_ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"
DEFAULT_KEYWORDS = (
    "mouse gamer", "teclado gamer", "headset gamer", "monitor gamer",
    "cadeira gamer", "controle gamer", "ssd", "placa de video",
    "processador", "notebook gamer",
)


class ShopeeAffiliateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ShopeeDiscovery:
    offers: list[Offer]
    errors: list[str]


def shopee_configured() -> bool:
    return bool(os.getenv("SHOPEE_APP_ID", "").strip() and os.getenv("SHOPEE_SECRET", "").strip())


class ShopeeAffiliateClient:
    def __init__(
        self,
        app_id: str | None = None,
        secret: str | None = None,
        endpoint: str | None = None,
    ):
        self.app_id = (app_id or os.getenv("SHOPEE_APP_ID", "")).strip()
        self.secret = (secret or os.getenv("SHOPEE_SECRET", "")).strip()
        self.endpoint = (endpoint or os.getenv("SHOPEE_API_URL", DEFAULT_ENDPOINT)).strip()
        if not self.app_id or not self.secret:
            raise ShopeeAffiliateError(
                "Preencha SHOPEE_APP_ID e SHOPEE_SECRET em credenciais-shopee.env"
            )

    def request(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if variables is not None:
            body["variables"] = variables
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        timestamp = int(time.time())
        signature = hashlib.sha256(
            f"{self.app_id}{timestamp}{payload}{self.secret}".encode("utf-8")
        ).hexdigest()
        request = urllib.request.Request(
            self.endpoint,
            data=payload.encode("utf-8"),
            method="POST",
            headers={
                "Authorization": (
                    f"SHA256 Credential={self.app_id}, "
                    f"Timestamp={timestamp}, Signature={signature}"
                ),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            raise ShopeeAffiliateError(f"A API da Shopee não respondeu: {error}") from error
        if not isinstance(result, dict):
            raise ShopeeAffiliateError("A API da Shopee retornou uma resposta inválida")
        errors = result.get("errors")
        if errors:
            messages = "; ".join(
                str(row.get("message") or row) if isinstance(row, dict) else str(row)
                for row in errors
            )
            raise ShopeeAffiliateError(f"Erro da API Shopee: {messages}")
        return result.get("data") or {}

    def products(
        self,
        *,
        keyword: str | None = None,
        item_id: int | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        filters = ["listType: 2", "sortType: 2", "page: 1", "limit: $limit"]
        declarations = ["$limit: Int!"]
        variables: dict[str, Any] = {"limit": max(1, min(limit, 100))}
        if keyword:
            declarations.append("$keyword: String!")
            filters.append("keyword: $keyword")
            variables["keyword"] = keyword
        if item_id is not None:
            declarations.append("$itemId: Int64!")
            filters.append("itemId: $itemId")
            # A Shopee expõe itemId como Int64, cujo valor JSON precisa ser
            # enviado como texto para não perder precisão.
            variables["itemId"] = str(item_id)
        query = f"""
        query Products({', '.join(declarations)}) {{
          productOfferV2({', '.join(filters)}) {{
            nodes {{
              itemId productName productLink offerLink imageUrl
              priceMin priceMax priceDiscountRate sales ratingStar
              commissionRate sellerCommissionRate shopeeCommissionRate commission
              shopId shopName shopType periodStartTime periodEndTime
            }}
            pageInfo {{ page limit hasNextPage }}
          }}
        }}
        """
        data = self.request(query, variables)
        result = data.get("productOfferV2") or {}
        nodes = result.get("nodes") if isinstance(result, dict) else None
        if not isinstance(nodes, list):
            raise ShopeeAffiliateError("productOfferV2 não retornou uma lista de produtos")
        return [row for row in nodes if isinstance(row, dict)]

    def generate_short_link(
        self, origin_url: str, sub_ids: list[str] | None = None
    ) -> str:
        query = """
        mutation ShortLink($input: ShortLinkInput!) {
          generateShortLink(input: $input) { shortLink }
        }
        """
        safe_sub_ids = [
            re.sub(r"[^a-zA-Z0-9_-]+", "_", value)[:50]
            for value in (sub_ids or [])
            if value
        ][:5]
        data = self.request(
            query,
            {"input": {"originUrl": origin_url, "subIds": safe_sub_ids}},
        )
        result = data.get("generateShortLink") or {}
        short_link = str(result.get("shortLink") or "").strip()
        if not short_link:
            raise ShopeeAffiliateError("A Shopee não gerou o shortlink de afiliado")
        return short_link


def discover_shopee_offers(limit: int = 30) -> ShopeeDiscovery:
    client = ShopeeAffiliateClient()
    configured = [
        value.strip()
        for value in os.getenv("SHOPEE_KEYWORDS", ",".join(DEFAULT_KEYWORDS)).split(",")
        if value.strip()
    ]
    keywords = configured or list(DEFAULT_KEYWORDS)
    per_keyword = max(1, math.ceil(limit / len(keywords)))
    offers: dict[str, Offer] = {}
    errors: list[str] = []
    for keyword in keywords:
        try:
            rows = client.products(keyword=keyword, limit=per_keyword)
        except ShopeeAffiliateError as error:
            errors.append(f"{keyword}: {error}")
            continue
        for row in rows:
            offer = _offer_from_node(row)
            if offer:
                offers[offer.product_key or offer.affiliate_url] = offer
                if len(offers) >= limit:
                    break
        if len(offers) >= limit:
            break
    return ShopeeDiscovery(list(offers.values()), errors)


def capture_shopee_product(url: str) -> Offer:
    item_id = shopee_item_id(url)
    if item_id is None:
        raise CaptureError(
            "O link da Shopee não contém o ID do produto; use o link completo da página"
        )
    client = ShopeeAffiliateClient()
    try:
        rows = client.products(item_id=item_id, limit=1)
    except ShopeeAffiliateError as error:
        raise CaptureError(str(error)) from error
    if not rows:
        raise CaptureError("A API da Shopee não encontrou esse produto")
    offer = _offer_from_node(rows[0])
    if not offer:
        raise CaptureError("A API da Shopee retornou o produto sem título ou preço")
    return offer


def shopee_item_id(url: str) -> int | None:
    decoded = urllib.parse.unquote(url)
    patterns = (
        r"(?:-i\.|-|/)(\d+)\.(\d+)(?:[/?]|$)",
        r"/product/\d+/(\d+)(?:[/?]|$)",
        r"[?&]itemId=(\d+)(?:&|$)",
    )
    for pattern in patterns:
        match = re.search(pattern, decoded, re.IGNORECASE)
        if match:
            return int(match.groups()[-1])
    return None


def _offer_from_node(row: dict[str, Any]) -> Offer | None:
    title = str(row.get("productName") or "").strip()
    item_id = str(row.get("itemId") or "").strip()
    price = _number(row.get("priceMin"))
    product_link = str(row.get("productLink") or "").strip()
    affiliate_link = str(row.get("offerLink") or "").strip()
    if not title or not item_id.isdigit() or price is None or not affiliate_link:
        return None
    discount = _rate(row.get("priceDiscountRate"))
    original = round(price / (1 - discount / 100), 2) if 0 < discount < 100 else None
    commission = _rate(row.get("commissionRate"))
    sales = _integer(row.get("sales"))
    rating = _number(row.get("ratingStar"))
    community = min(100.0, math.log10((sales or 0) + 1) * 18 + max(0, (rating or 0) - 4) * 20)
    return Offer(
        title=title,
        affiliate_url=affiliate_link,
        source_url=product_link or affiliate_link,
        product_key=f"shopee:{item_id}",
        price=price,
        original_price=original,
        commission_percent=commission,
        store="shopee",
        image_url=str(row.get("imageUrl") or "").strip() or None,
        seller_name=str(row.get("shopName") or "").strip() or None,
        seller_rating=rating,
        sold_count=sales,
        discovery_source="shopee_api",
        community_score=round(community, 1),
        available=True,
    )


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _rate(value: Any) -> float:
    number = _number(value) or 0
    return round(number * 100 if 0 < number <= 1 else number, 2)
