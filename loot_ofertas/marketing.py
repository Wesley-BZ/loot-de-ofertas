from __future__ import annotations

import random
import unicodedata
from functools import lru_cache

from .models import Offer
from .product_catalog import PRODUCT_PROFILES, ProductProfile


OPENINGS = (
    "OLHA O DROP: {label}",
    "ACHADO LIBERADO: {label}",
    "O SETUP CHAMOU: {label}",
    "LOOT DO DIA: {label}",
    "UPGRADE AVISTADO: {label}",
    "MISSÃO NOVA: GARANTIR {label}",
    "ITEM RARO NA TELA: {label}",
    "O LOBBY PEDIU: {label}",
    "BUFF DISPONÍVEL: {label}",
    "CHECKPOINT DA OFERTA: {label}",
)

FINISHES = (
    "— {benefit}",
    "— PREÇO NO EASY, GAME NO HARD",
    "— SEM DAR GAME OVER NO BOLSO",
    "— CORRE ANTES DO PREÇO RESPAWNAR",
    "— O BOLSO NÃO PRECISA TILTAR",
    "— UPGRADE BOM É UPGRADE BARATO",
    "— PRA SUBIR O SETUP DE ELO",
    "— DROP BOM NÃO FICA MUITO TEMPO NO MAPA",
    "— DÁ O BUFF QUE FALTAVA NO SETUP",
    "— SE PISCAR, OUTRO PLAYER LEVA",
)


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in value if not unicodedata.combining(char))


@lru_cache(maxsize=None)
def phrases_for(category: str) -> tuple[str, ...]:
    profile = _profile_by_key(category)
    return tuple(
        f"{opening.format(label=profile.label)} {finish.format(benefit=profile.benefit)}"
        for opening in OPENINGS
        for finish in FINISHES
    )


def _profile_by_key(key: str) -> ProductProfile:
    return next(profile for profile in PRODUCT_PROFILES if profile.key == key)


def profile_for(offer: Offer) -> ProductProfile:
    text = _normalize(f"{offer.title} {offer.category or ''}")
    for profile in PRODUCT_PROFILES:
        if any(_normalize(term) in text for term in profile.terms):
            return profile
    # O catálogo é focado em itens gamer; um título ainda desconhecido recebe o
    # tom genérico sem quebrar a publicação e pode ser catalogado depois.
    return ProductProfile("generic", "ACHADO GAMER", (), "LOOT BOM SEM NERFAR O BOLSO", "🎮🔥")


def category_for(offer: Offer) -> str:
    return profile_for(offer).key


def headline_for(offer: Offer, excluded: set[str] | None = None) -> str:
    profile = profile_for(offer)
    choices = phrases_for(profile.key) if profile.key != "generic" else tuple(
        f"{opening.format(label=profile.label)} {finish.format(benefit=profile.benefit)}"
        for opening in OPENINGS for finish in FINISHES
    )
    excluded = excluded or set()
    available = [f"{candidate} {profile.emoji}" for candidate in choices]
    available = [headline for headline in available if headline not in excluded]
    # Se todo o catálogo tiver sido bloqueado por uma chamada externa, libera a
    # coleção completa para que a publicação nunca fique sem título.
    if not available:
        available = [f"{candidate} {profile.emoji}" for candidate in choices]
    return random.SystemRandom().choice(available)


# Compatibilidade com os testes e consumidores existentes. Cada uma das 100
# categorias possui exatamente 100 chamadas; a categoria genérica também.
PHRASES: dict[str, tuple[str, ...]] = {
    profile.key: phrases_for(profile.key) for profile in PRODUCT_PROFILES
}
PHRASES["generic"] = tuple(
    f"{opening.format(label='ACHADO GAMER')} {finish.format(benefit='LOOT BOM SEM NERFAR O BOLSO')}"
    for opening in OPENINGS for finish in FINISHES
)
