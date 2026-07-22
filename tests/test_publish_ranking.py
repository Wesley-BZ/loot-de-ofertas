from loot_ofertas.cli import rank_approved_offers
from loot_ofertas.models import Offer


def test_best_complete_score_is_published_first():
    first = Offer("Produto A", "https://a", 100, "magalu", score=55, id=1)
    second = Offer("Produto B", "https://b", 100, "mercado_livre", score=40, id=2)
    rejected = Offer("Produto C", "https://c", 100, "magalu", score=100, id=3)

    ranked = rank_approved_offers(
        [first, second, rejected],
        {1: ("promocao", 10), 2: ("excelente", 40), 3: ("preco_comum", 100)},
    )

    assert [offer.id for offer in ranked] == [2, 1]
