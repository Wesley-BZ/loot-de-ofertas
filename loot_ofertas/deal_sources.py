from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


PELANDO_API = "https://api-web.pelando.com.br/feed/highlights"
PELANDO_SITE = "https://www.pelando.com.br"
PROMOBIT_SITE = "https://www.promobit.com.br"


@dataclass(frozen=True, slots=True)
class DealCandidate:
    title: str
    price: float
    store: str
    url: str
    source: str
    external_id: str
    original_price: float | None = None
    coupon: str | None = None


@dataclass(frozen=True, slots=True)
class CommunityDiscovery:
    candidates: list[DealCandidate]
    errors: list[str]


STORE_ALIASES = {
    "amazon": "amazon",
    "magalu": "magalu",
    "magazine luiza": "magalu",
    "magazine você": "magalu",
    "magazine voce": "magalu",
    "mercado livre": "mercadolivre",
    "mercadolivre": "mercadolivre",
    "kabum": "kabum",
    "ka bu m": "kabum",
    "pichau": "pichau",
    "terabyte": "terabyte",
    "terabyte shop": "terabyte",
    "fast shop": "fastshop",
    "casas bahia": "casasbahia",
    "dell": "dell",
    "lenovo": "lenovo",
    "samsung": "samsung",
    "shopee": "shopee",
    "aliexpress": "aliexpress",
}

STORE_HOSTS = {
    "amazon": ("amazon.com.br",),
    "magalu": ("magazineluiza.com.br", "magazinevoce.com.br", "influenciadormagalu.com.br"),
    "mercadolivre": ("mercadolivre.com.br", "mercadolibre.com"),
    "kabum": ("kabum.com.br",),
    "pichau": ("pichau.com.br",),
    "terabyte": ("terabyteshop.com.br",),
    "fastshop": ("fastshop.com.br",),
    "casasbahia": ("casasbahia.com.br",),
    "dell": ("dell.com",),
    "lenovo": ("lenovo.com",),
    "samsung": ("samsung.com",),
    "shopee": ("shopee.com.br",),
    "aliexpress": ("aliexpress.com",),
}

# Commercial priority: our active affiliate first, then large marketplaces and
# specialist technology stores, followed by manufacturer/department stores.
STORE_PRIORITY = (
    "magalu", "mercadolivre", "amazon", "kabum", "pichau", "terabyte",
    "fastshop", "casasbahia", "dell", "lenovo", "samsung", "shopee", "aliexpress",
)

TRACKING_PARAMETERS = {
    "aff_fcid", "aff_fsk", "aff_platform", "aff_trace_key", "awc", "clickid",
    "gclid", "irclickid", "ref", "ref_", "social_share", "spm", "tag",
    "utm_campaign", "utm_content", "utm_medium", "utm_source", "utm_term",
}


def discover_community_deals(limit: int = 60) -> CommunityDiscovery:
    candidates: dict[str, DealCandidate] = {}
    errors: list[str] = []
    for name, fetcher in (("pelando", fetch_pelando), ("promobit", fetch_promobit)):
        try:
            rows = fetcher(limit)
        except (ValueError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            errors.append(f"{name}: {error}")
            continue
        for candidate in rows:
            key = f"{candidate.store}:{candidate.external_id or candidate.url}"
            candidates[key] = candidate
    priority = {store: position for position, store in enumerate(STORE_PRIORITY)}
    ordered = sorted(
        candidates.values(),
        key=lambda candidate: (
            priority.get(candidate.store, len(priority)),
            0 if candidate.source == "pelando" else 1,
        ),
    )
    return CommunityDiscovery(ordered, errors)


def fetch_pelando(limit: int = 60) -> list[DealCandidate]:
    query = urllib.parse.urlencode({"scenario": "Main-Feed", "limit": max(1, min(limit, 100))})
    request = urllib.request.Request(
        f"{PELANDO_API}?{query}",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Origin": PELANDO_SITE,
            "Referer": PELANDO_SITE + "/",
            "x-sosho-unlogged-id": str(uuid.uuid4()),
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("deals") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("o feed mudou de formato")
    return [candidate for row in rows if (candidate := _pelando_candidate(row))]


def fetch_promobit(limit: int = 60) -> list[DealCandidate]:
    request = urllib.request.Request(
        PROMOBIT_SITE,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        html = response.read(5_000_000).decode(
            response.headers.get_content_charset() or "utf-8", errors="replace"
        )
    parser = _NextDataParser()
    parser.feed(html)
    if not isinstance(parser.payload, dict):
        raise ValueError("a página não expôs __NEXT_DATA__")
    candidates: list[DealCandidate] = []
    for node in _iter_dicts(parser.payload):
        if "offerPrice" not in node or "offerTitle" not in node:
            continue
        candidate = _promobit_candidate(node)
        if candidate:
            candidates.append(candidate)
            if len(candidates) >= limit:
                break
    return candidates


def canonical_store(name: str, url: str = "") -> str:
    normalized = " ".join(name.casefold().strip().split())
    if normalized in STORE_ALIASES:
        return STORE_ALIASES[normalized]
    host = (urllib.parse.urlsplit(url).hostname or "").casefold()
    for store, hosts in STORE_HOSTS.items():
        if any(host == domain or host.endswith("." + domain) for domain in hosts):
            return store
    return normalized.replace(" ", "") or "outra"


def trusted_product_url(url: str, store: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme in {"http", "https"} and any(
        host == domain or host.endswith("." + domain)
        for domain in STORE_HOSTS.get(store, ())
    )


def clean_product_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    clean_pairs = [
        (key, value) for key, value in pairs
        if key.casefold() not in TRACKING_PARAMETERS and not key.casefold().startswith("utm_")
    ]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(clean_pairs), "")
    )


def _pelando_candidate(row: Any) -> DealCandidate | None:
    if not isinstance(row, dict):
        return None
    title = str(row.get("title") or "").strip()
    url = str(row.get("sourceUrl") or "").strip()
    price = _number(row.get("price"))
    store_data = row.get("store") or {}
    store_name = str(store_data.get("name") or "") if isinstance(store_data, dict) else ""
    store = canonical_store(store_name, url)
    if not title or not url or price is None or price < 1:
        return None
    discount = _number(row.get("discountPercentage"))
    original = round(price / (1 - discount / 100), 2) if discount and 0 < discount < 100 else None
    return DealCandidate(
        title=title, price=price, original_price=original,
        coupon=str(row.get("code") or "").strip() or None,
        store=store, url=clean_product_url(url), source="pelando",
        external_id=str(row.get("id") or row.get("slug") or url),
    )


def _promobit_candidate(row: dict[str, Any]) -> DealCandidate | None:
    title = str(row.get("offerTitle") or "").strip()
    price = _number(row.get("offerPrice"))
    slug = str(row.get("offerSlug") or "").strip()
    if not title or not slug or price is None or price < 1:
        return None
    return DealCandidate(
        title=title, price=price, original_price=_number(row.get("offerOldPrice")),
        coupon=str(row.get("offerCoupon") or "").strip() or None,
        store=canonical_store(str(row.get("storeName") or "")),
        url=f"{PROMOBIT_SITE}/oferta/{slug}", source="promobit",
        external_id=str(row.get("offerId") or slug),
    )


def _number(value: Any) -> float | None:
    try:
        result = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _iter_dicts(value: Any):
    queue = [value]
    while queue:
        current = queue.pop()
        if isinstance(current, dict):
            yield current
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current)


class _NextDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.payload: Any = None
        self._buffer: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "script" and values.get("id") == "__NEXT_DATA__":
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._buffer is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "script" or self._buffer is None:
            return
        raw = "".join(self._buffer)
        self._buffer = None
        try:
            self.payload = json.loads(raw)
        except json.JSONDecodeError:
            self.payload = None
