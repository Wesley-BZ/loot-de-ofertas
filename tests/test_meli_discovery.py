from unittest.mock import patch

from loot_ofertas.meli_discovery import _catalog_link, discover_meli_highlights


def test_catalog_link_contains_product_and_item_ids():
    link = _catalog_link("MLB43961384", "MLB7168599690", "Monitor LG Gamer 24")
    assert "/p/MLB43961384" in link
    assert "wid=MLB7168599690" in link
    assert "item_id%3AMLB7168599690" in link


@patch("loot_ofertas.meli_discovery.MELI_GAMER_CATEGORIES", (("MLB99245", "monitores"),))
@patch("loot_ofertas.meli_discovery.api_get")
def test_discovers_best_seller_using_official_product_api(api_get):
    def response(path):
        if path.startswith("highlights/"):
            return {"content": [{"id": "MLB43961384", "position": 1, "type": "PRODUCT"}]}
        if path == "products/MLB43961384":
            return {"name": "Monitor LG Gamer 24", "pictures": [{"secure_url": "https://img/test.jpg"}]}
        if path == "products/MLB43961384/items":
            return {"results": [{
                "item_id": "MLB7168599690", "price": 649, "original_price": 799,
                "shipping": {"free_shipping": True},
            }]}
        raise AssertionError(path)

    api_get.side_effect = response
    result = discover_meli_highlights(limit=5)

    assert len(result.offers) == 1
    assert result.offers[0].price == 649
    assert result.offers[0].original_price == 799
    assert result.offers[0].shipping_price == 0
    assert result.offers[0].product_key == "mercadolivre:mlb7168599690"
