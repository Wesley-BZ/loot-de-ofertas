from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .capture import (
    MAX_PAGE_BYTES,
    CaptureError,
    CapturedPage,
    _ProductMetadataParser,
    _find_product,
    _first_price,
    _first_text,
    _image_url,
    _text_or_none,
)
from .models import Offer


MAGALU_HOSTS = ("magazineluiza.com.br", "magazinevoce.com.br")


def capture_magalu(url: str, timeout: int = 25) -> CapturedPage:
    _validate_url(url)
    candidates = list(dict.fromkeys((magalu_affiliate_url(url), url)))
    last_error: Exception | None = None
    for candidate in candidates:
        request = urllib.request.Request(candidate, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml", "Accept-Language": "pt-BR,pt;q=0.9",
        })
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                final_url = response.geturl()
                _validate_url(final_url)
                data = response.read(MAX_PAGE_BYTES + 1)
                if len(data) > MAX_PAGE_BYTES:
                    raise CaptureError("A página do Magalu excedeu 5 MB")
                charset = response.headers.get_content_charset() or "utf-8"
            return capture_magalu_html(data.decode(charset, errors="replace"), final_url)
        except CaptureError:
            raise
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            last_error = error
    raise CaptureError(f"Não foi possível abrir o produto Magalu: {last_error}") from last_error


def capture_magalu_browser(url: str, timeout: int = 35, session_dir: str | Path = ".magalu-session") -> CapturedPage:
    _validate_url(url)
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as error:
        raise CaptureError("O navegador do Magalu requer Selenium") from error
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1365,900")
    options.add_argument(f"--user-data-dir={Path(session_dir).resolve()}")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(magalu_affiliate_url(url))
        WebDriverWait(driver, timeout).until(
            lambda browser: browser.find_elements(By.CSS_SELECTOR, "script[type='application/ld+json']")
        )
        return capture_magalu_html(driver.page_source, driver.current_url)
    except CaptureError:
        raise
    except Exception as error:
        raise CaptureError(f"O navegador não conseguiu ler o Magalu: {error}") from error
    finally:
        driver.quit()


def capture_magalu_html(html: str, final_url: str) -> CapturedPage:
    _validate_url(final_url)
    parser = _ProductMetadataParser()
    parser.feed(html)
    product = _find_product(parser.json_ld)
    title = _first_text(product.get("name") if product else None, parser.meta.get("og:title"))
    offers = product.get("offers") if product else None
    if isinstance(offers, list):
        offers = next((item for item in offers if isinstance(item, dict)), {})
    offers = offers if isinstance(offers, dict) else {}
    price = _first_price(
        offers.get("price"), offers.get("lowPrice"), parser.meta.get("product:price:amount"),
        parser.meta.get("og:price:amount"),
    )
    original = _first_price(
        parser.meta.get("product:original_price:amount"), parser.meta.get("original_price")
    )
    if not title or price is None:
        raise CaptureError("A página do Magalu não expôs título ou preço")
    product_id = _product_id(final_url, product)
    image = _image_url(product.get("image") if product else None) or parser.meta.get("og:image")
    seller = offers.get("seller")
    seller_name = seller.get("name") if isinstance(seller, dict) else None
    availability = str(offers.get("availability") or "").casefold()
    affiliate_url = magalu_affiliate_url(final_url)
    offer = Offer(
        title=title, affiliate_url=affiliate_url, source_url=final_url,
        product_key=f"magalu:{product_id}" if product_id else None,
        price=price, original_price=original if original and original > price else None,
        store="magalu", image_url=image, seller_name=_text_or_none(seller_name),
        available=not any(term in availability for term in ("outofstock", "soldout", "discontinued")),
    )
    return CapturedPage(offer, final_url)


def magalu_affiliate_url(url: str) -> str:
    store_url = os.getenv("MAGALU_STORE_URL", "").strip()
    parsed = urllib.parse.urlsplit(url)
    if "magazinevoce.com.br" in (parsed.hostname or ""):
        return url
    if not store_url or "sualoja" in store_url.casefold():
        return url
    return store_url.rstrip("/") + "/" + parsed.path.lstrip("/")


def _product_id(url: str, product: dict) -> str:
    for value in (product.get("sku"), product.get("productID"), product.get("mpn")):
        if value:
            return re.sub(r"[^A-Za-z0-9_-]", "", str(value)).casefold()
    match = re.search(r"/p/([A-Za-z0-9_-]+)", urllib.parse.urlsplit(url).path, re.IGNORECASE)
    return match.group(1).casefold() if match else ""


def _validate_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url.strip())
    host = (parsed.hostname or "").casefold()
    if parsed.scheme not in {"http", "https"} or not any(
        host == domain or host.endswith("." + domain) for domain in MAGALU_HOSTS
    ):
        raise CaptureError("O link não pertence ao Magalu ou Magazine Você")
