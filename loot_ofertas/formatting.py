from __future__ import annotations

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
    lines.extend(["", f"Loja: {store_name(offer.store)}", offer.affiliate_url])
    if offer.source_url and offer.source_url != offer.affiliate_url:
        lines.append("Link de afiliado")
    return "\n".join(lines)
