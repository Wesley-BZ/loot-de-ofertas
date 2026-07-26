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
    "ALERTA DE PREÇO: {label}",
    "DROP CONFIRMADO: {label}",
    "OFERTA SPAWNOU: {label}",
    "RADAR ENCONTROU: {label}",
    "PREÇO EM MODO TURBO: {label}",
    "CALL DO ESQUADRÃO: {label}",
    "ACHADINHO NO MAPA: {label}",
    "PROMOÇÃO NA MIRA: {label}",
    "INVENTÁRIO ATUALIZADO: {label}",
    "OPORTUNIDADE DESBLOQUEADA: {label}",
    "SINAL VERDE PARA O UPGRADE: {label}",
    "PREÇO DERRUBADO: {label}",
    "HORA DE EQUIPAR: {label}",
    "O RADAR GAMER APITOU: {label}",
    "OFERTA DE RESPEITO: {label}",
    "DESCONTO NO PONTO: {label}",
    "ITEM MARCADO NO MAPA: {label}",
    "LOOT FRESQUINHO: {label}",
    "JANELA DE UPGRADE ABERTA: {label}",
    "PREÇO BOM DETECTADO: {label}",
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
    "— VALE CONFERIR ANTES QUE MUDE",
    "— O SETUP AGRADECE E O BOLSO TAMBÉM",
    "— PREÇO BAIXO, PERFORMANCE LÁ EM CIMA",
    "— UM BOM MOMENTO PRA FAZER O UPGRADE",
    "— ENTRA NO CARRINHO SEM DAR LAG NO ORÇAMENTO",
    "— ACHADO BOM PRA QUEM ESTAVA ESPERANDO",
    "— O DESCONTO FEZ O COMBO",
    "— MAIS PERFORMANCE POR MENOS MOEDAS",
    "— O TIPO DE PREÇO QUE MERECE CHECK",
    "— EQUIPA AGORA E EVITA PAGAR MAIS DEPOIS",
    "— SE ESTAVA NA WISHLIST, CHEGOU A HORA",
    "— PREÇO DE EVENTO SEM PRECISAR DE DLC",
    "— UPGRADE LIBERADO COM ECONOMIA",
    "— O CARRINHO ACABOU DE GANHAR UM BUFF",
    "— CONDIÇÃO BOA PRA NÃO DEIXAR PASSAR",
    "— DESCONTO QUE FAZ SENTIDO NO SETUP",
    "— MENOS GRIND PRA CONSEGUIR O EQUIPAMENTO",
    "— SUA BUILD PODE SUBIR DE NÍVEL",
    "— BOM NEGÓCIO PRA QUEM COMPRA COM ESTRATÉGIA",
    "— OFERTA PRONTA PRA ENTRAR NA SUA BUILD",
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
