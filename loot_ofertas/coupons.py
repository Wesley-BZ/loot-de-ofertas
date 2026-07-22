from __future__ import annotations

import hashlib
import re
import urllib.request
from functools import lru_cache

from .models import Offer


WELCOME_BANNER = "https://especiais.magazineluiza.com.br/assets/mvc/0901_bemvindo10.png"
WELCOME_BANNER_SHA256 = "fcafe7d0ba585e8961a9d691dbdaec3c55a8ec7f0e0e61016c0479a9a73194a2"


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


@lru_cache(maxsize=4)
def verified_magalu_coupons(page_url: str) -> tuple[str, ...]:
    """Retorna apenas cupons cujos banners e condições foram verificados."""
    html = _download(page_url).decode("utf-8", errors="replace")
    image_urls = set(re.findall(r'https://[^"\s]+?\.png', html, flags=re.IGNORECASE))
    coupons: list[str] = []
    if WELCOME_BANNER in image_urls:
        banner_hash = hashlib.sha256(_download(WELCOME_BANNER)).hexdigest()
        if banner_hash == WELCOME_BANNER_SHA256:
            coupons.append("BEMVINDO20 (R$ 20 OFF na 1ª compra acima de R$ 80)")
    return tuple(coupons)


def coupon_for_offer(offer: Offer, page_url: str) -> str | None:
    if offer.store.casefold() != "magalu" or offer.price < 80:
        return None
    try:
        coupons = verified_magalu_coupons(page_url)
    except (OSError, TimeoutError):
        return None
    return coupons[0] if coupons else None
