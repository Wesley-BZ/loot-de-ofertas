from loot_ofertas.market import MarketQuote, assess_deal, same_product
from loot_ofertas.models import Offer


def test_current_market_can_make_offer_imperdivel_even_without_history():
    offer = Offer("Monitor LG UltraGear 24GN60R", "https://loja/a", 699, "magalu", original_price=999)
    quotes = [
        MarketQuote("Monitor Gamer LG UltraGear 24GN60R", "Amazon", 849, "https://a"),
        MarketQuote("LG UltraGear 24GN60R Monitor", "KaBuM!", 899, "https://b"),
    ]
    assessment = assess_deal(offer, quotes, [])
    assert assessment.label == "imperdivel"
    assert assessment.confidence == "media"


def test_history_does_not_veto_good_current_market_price():
    offer = Offer("SSD Kingston NV2 1TB", "https://loja/a", 349, "magalu")
    quotes = [MarketQuote("SSD Kingston NV2 1TB", "Amazon", 399, "https://a")]
    assessment = assess_deal(offer, quotes, [300, 310, 320, 330])
    assert assessment.label in {"excelente", "promocao"}


def test_product_matching_rejects_different_models():
    assert same_product("Monitor LG 24GN60R 24", "Monitor Gamer LG 24GN60R")
    assert not same_product("Monitor LG 24GN60R", "Monitor LG 27GN800")
    assert not same_product(
        "Computador Intel Core i5 3470 16GB SSD 120GB Windows 10",
        "Computador Intel Core i5 8GB SSD 120GB Windows 10",
    )


def test_magalu_discount_can_rank_before_google_comparison():
    offer = Offer("Mouse Gamer Logitech G203", "https://magazinevoce.com/produto", 116, "magalu", original_price=157)
    assessment = assess_deal(offer, [], [])
    assert assessment.label == "promocao_loja"
    assert "Magazine Você" in " ".join(assessment.reasons)


def test_coupon_reduces_effective_price_in_comparison():
    offer = Offer("Mouse Gamer Logitech G203", "https://magazinevoce.com/produto", 120, "magalu", coupon="CUPOM20 (R$ 20 OFF)")
    quote = MarketQuote(offer.title, "Amazon", 110, "https://amazon.example")
    assessment = assess_deal(offer, [quote], [])
    assert assessment.current_price == 100
    assert any("cupom" in reason for reason in assessment.reasons)
