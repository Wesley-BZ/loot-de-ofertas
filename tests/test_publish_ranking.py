from loot_ofertas.cli import rank_offers_for_publication
from loot_ofertas.models import Offer


def test_best_complete_score_is_published_first():
    first = Offer("Produto A", "https://a", 100, "magalu", score=55, id=1)
    second = Offer("Produto B", "https://b", 100, "mercado_livre", score=40, id=2)
    rejected = Offer("Produto C", "https://c", 100, "magalu", score=100, id=3)

    ranked = rank_offers_for_publication(
        [first, second, rejected],
        {1: ("promocao", 10), 2: ("excelente", 40), 3: ("preco_comum", 100)},
    )

    assert [offer.id for offer in ranked] == [3, 2, 1]


def test_offer_without_market_validation_can_still_be_published():
    offer = Offer("Produto sem comparação", "https://a", 100, "magalu", score=50, id=1)

    assert rank_offers_for_publication([offer], {}) == [offer]
