import os

from loot_ofertas.magalu import capture_magalu_html, magalu_affiliate_url


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
