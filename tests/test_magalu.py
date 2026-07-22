import os

from loot_ofertas.magalu import (
    _offer_from_listing_row,
    capture_magalu_html,
    discover_magalu_html,
    magalu_affiliate_url,
    magalu_category_urls,
)


HTML = """
<html><head><script type="application/ld+json">
{"@type":"Product","name":"Mouse Gamer Logitech G502","sku":"12345",
 "image":"https://example.com/mouse.jpg","offers":{"@type":"Offer","price":"249.90",
 "availability":"https://schema.org/InStock","seller":{"name":"Magalu"}}}
</script></head></html>
"""


def test_capture_magalu_structured_product(monkeypatch):
    monkeypatch.setenv("MAGALU_STORE_URL", "https://www.magazinevoce.com.br/magazineloot/")
    captured = capture_magalu_html(HTML, "https://www.magazineluiza.com.br/mouse/p/12345")
    assert captured.offer.price == 249.90
    assert captured.offer.product_key == "magalu:12345"
    assert "magazineloot" in captured.offer.affiliate_url


def test_keeps_public_url_when_store_is_placeholder(monkeypatch):
    monkeypatch.setenv("MAGALU_STORE_URL", "https://www.magazinevoce.com.br/magazinesualoja/")
    url = "https://www.magazineluiza.com.br/mouse/p/12345"
    assert magalu_affiliate_url(url) == url


def test_adds_promoter_tracking_to_magalu_url(monkeypatch):
    monkeypatch.setenv("MAGALU_PROMOTER_ID", "5774816")
    monkeypatch.setenv("MAGALU_PARTNER_ID", "3440")
    result = magalu_affiliate_url("https://www.magazineluiza.com.br/mouse/p/12345?foo=bar")
    assert "promoter_id=5774816" in result
    assert "partner_id=3440" in result
    assert "utm_campaign=5774816" in result
    assert "foo=bar" in result


def test_builds_expected_magazine_voce_categories(monkeypatch):
    monkeypatch.setenv("MAGALU_STORE_URL", "https://www.magazinevoce.com.br/minhaloja/")
    urls = magalu_category_urls()
    assert len(urls) == 5
    assert urls[0].endswith("/informatica/l/in/")
    assert urls[-1].endswith("/casa-inteligente/l/ci/")


def test_discovers_products_from_category_json_ld(monkeypatch):
    monkeypatch.setenv("MAGALU_PROMOTER_ID", "5774816")
    html = """
    <script type="application/ld+json">{
      "@type":"ItemList", "itemListElement":[
        {"@type":"ListItem", "item":{"@type":"Product", "name":"Notebook Gamer X15",
         "sku":"abc123", "url":"https://www.magazineluiza.com.br/notebook/p/abc123/in/note/",
         "image":"https://example.com/notebook.jpg",
         "offers":{"@type":"AggregateOffer","lowPrice":"2999.90","highPrice":"3999.90"}}}
      ]
    }</script>
    """
    offers = discover_magalu_html(html, "https://www.magazinevoce.com.br/minhaloja/informatica/l/in/")
    assert len(offers) == 1
    assert offers[0].price == 2999.90
    assert offers[0].original_price == 3999.90
    assert "promoter_id=5774816" in offers[0].affiliate_url


def test_listing_row_ignores_installment_value(monkeypatch):
    monkeypatch.setenv("MAGALU_PROMOTER_ID", "5774816")
    offer = _offer_from_listing_row({
        "href": "https://www.magazineluiza.com.br/mouse/p/abc123/in/rato/",
        "title": "Mouse Gamer X11",
        "text": "Mouse Gamer X11\nR$ 199,90\nR$ 129,90\n35% OFF\n10x R$ 12,99",
    }, "https://www.magazinevoce.com.br/minhaloja/informatica/l/in/")
    assert offer is not None
    assert offer.original_price == 199.90
    assert offer.price == 129.90
