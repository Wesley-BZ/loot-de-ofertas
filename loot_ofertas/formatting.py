from __future__ import annotations

import re
import urllib.parse

from .marketing import headline_for
from .models import Offer


def money(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def store_name(value: str) -> str:
    names = {
        "mercadolivre": "Mercado Livre",
        "mercado livre": "Mercado Livre",
        "aliexpress": "AliExpress",
        "magalu": "Magalu",
        "shopee": "Shopee",
        "amazon": "Amazon",
    }
    return names.get(value.casefold().strip(), value.title())


def format_offer(offer: Offer) -> str:
    lines = [offer.headline or headline_for(offer), "", offer.title, ""]
    if offer.original_price and offer.original_price > offer.price:
        lines.append(f"De {money(offer.original_price)} por {money(offer.price)}")
    else:
        lines.append(f"Por {money(offer.price)}")
    if offer.coupon:
        code, _, condition = offer.coupon.partition(" ")
        lines.append(f"Use o Cupom: *{code}* 🎟️")
        if condition:
            lines.append(condition)
    lines.extend(["", f"Loja: {store_name(offer.store)}", compact_offer_url(offer)])
    if offer.source_url and offer.source_url != offer.affiliate_url:
        lines.append("Link de afiliado")
    return "\n".join(lines)


def compact_offer_url(offer: Offer) -> str:
    """Return a compact public URL without changing Magalu affiliate attribution."""
    url = offer.affiliate_url.strip()
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if host == "meli.la" or host.endswith(".meli.la"):
        return url
    if "mercadolivre.com" in host or "mercadolibre.com" in host:
        query = urllib.parse.parse_qs(parsed.query)
        candidates = [query.get("wid", [""])[0], offer.product_key or "", url]
        item_id = next(
            (match.group(0).upper() for value in candidates if (match := re.search(r"MLB\d+", value, re.I))),
            "",
        )
        if item_id:
            number = item_id.removeprefix("MLB")
            return f"https://produto.mercadolivre.com.br/MLB-{number}-_JM"
    if "magazineluiza.com.br" in host or "magazinevoce.com.br" in host:
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        kept = [(key, value) for key, value in query if not key.casefold().startswith("utm_")]
        return urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(kept)))
    return url
