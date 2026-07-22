from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
MAGALU_CATEGORY_PATHS = (
    ("informatica", "in"),
    ("games", "ga"),
    ("tablets-ipads-e-e-reader", "tb"),
    ("celulares-e-smartphones", "te"),
    ("casa-inteligente", "ci"),
)
INFORMATICA_ALLOWED_TERMS = {
    "adaptador", "cadeira gamer", "cabo hdmi", "cooler", "computador", "controle",
    "dock", "fonte", "gabinete", "gamepad", "gpu", "hd externo", "headset", "hub usb",
    "memoria", "microfone", "monitor", "mouse", "notebook", "nvme", "pc gamer",
    "placa de video", "placa mae", "processador", "repetidor", "roteador", "ssd",
    "switch", "teclado", "webcam", "wifi",
}
INFORMATICA_BLOCKED_TERMS = {
    "cartucho", "etiqueta", "impressora", "mochila", "papel", "refil de tinta", "scanner",
    "toner",
}


@dataclass(frozen=True, slots=True)
class MagaluDiscovery:
    offers: list[Offer]
    errors: list[str]


def magalu_category_urls(store_url: str | None = None) -> tuple[str, ...]:
    base = (store_url or os.getenv("MAGALU_STORE_URL", "")).strip().rstrip("/")
    if not base:
        raise CaptureError("Configure MAGALU_STORE_URL antes da descoberta")
    _validate_url(base + "/")
    return tuple(f"{base}/{slug}/l/{code}/" for slug, code in MAGALU_CATEGORY_PATHS)


def relevant_magalu_offer(offer: Offer) -> bool:
    source_category = (offer.category or "").casefold()
    if "/informatica/" not in source_category:
        return True
    title = _normalized_text(offer.title)
    if any(term in title for term in INFORMATICA_BLOCKED_TERMS):
        return False
    return any(term in title for term in INFORMATICA_ALLOWED_TERMS)


def discover_magalu_categories(
    urls: tuple[str, ...] | None = None, timeout: int = 25, limit: int = 100
) -> MagaluDiscovery:
    found: dict[str, Offer] = {}
    errors: list[str] = []
    for url in urls or magalu_category_urls():
        request = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml", "Accept-Language": "pt-BR,pt;q=0.9",
        })
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                html = response.read(MAX_PAGE_BYTES + 1)
                if len(html) > MAX_PAGE_BYTES:
                    raise CaptureError("A categoria do Magalu excedeu 5 MB")
                charset = response.headers.get_content_charset() or "utf-8"
                rows = discover_magalu_html(html.decode(charset, errors="replace"), response.geturl())
            for offer in rows:
                found[offer.product_key or offer.affiliate_url] = offer
                if len(found) >= limit:
                    return MagaluDiscovery(list(found.values()), errors)
        except (CaptureError, urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            errors.append(f"{url}: {error}")
    return MagaluDiscovery(list(found.values()), errors)


def discover_magalu_browser(
    urls: tuple[str, ...] | None = None, timeout: int = 35,
    session_dir: str | Path = ".magalu-session", limit: int = 100,
) -> MagaluDiscovery:
    try:
        from selenium import webdriver
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as error:
        raise CaptureError("O navegador do Magalu requer Selenium") from error
    options = webdriver.ChromeOptions()
    if os.getenv("MAGALU_BROWSER_HEADLESS", "true").casefold() not in {"0", "false", "no"}:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1365,1200")
    options.add_argument(f"--user-data-dir={Path(session_dir).resolve()}")
    driver = webdriver.Chrome(options=options)
    found: dict[str, Offer] = {}
    errors: list[str] = []
    try:
        for url in urls or magalu_category_urls():
            try:
                driver.get(url)
                WebDriverWait(driver, timeout).until(lambda browser: browser.execute_script(
                    "return document.querySelectorAll('a[href*=\"/p/\"]').length > 0"
                ))
                rows = driver.execute_script("""
                    return Array.from(document.querySelectorAll('a[href*="/p/"]')).map(a => {
                      const card = a.closest('li, article, [data-testid*="product"], section, div');
                      return {href: a.href, text: (card?.innerText || a.innerText || '').trim(),
                              title: (a.getAttribute('title') || a.querySelector('img')?.alt ||
                                      card?.querySelector('h2, h3')?.innerText || a.innerText || '').trim(),
                              image: a.querySelector('img')?.src || card?.querySelector('img')?.src || ''};
                    }).filter(x => x.href && x.text);
                """)
                for row in rows or []:
                    offer = _offer_from_listing_row(row, driver.current_url)
                    if offer:
                        found[offer.product_key or offer.affiliate_url] = offer
                        if len(found) >= limit:
                            return MagaluDiscovery(list(found.values()), errors)
            except Exception as error:
                errors.append(f"{url}: {error}")
    finally:
        driver.quit()
    return MagaluDiscovery(list(found.values()), errors)


def discover_magalu_html(html: str, final_url: str) -> list[Offer]:
    _validate_url(final_url)
    if "Captcha Magalu" in html or "az-request-captcha" in html:
        raise CaptureError("O Magalu solicitou validação CAPTCHA")
    parser = _ProductMetadataParser()
    parser.feed(html)
    products = _all_products(parser.json_ld)
    offers: dict[str, Offer] = {}
    for product in products:
        title = _first_text(product.get("name"))
        data = product.get("offers")
        if isinstance(data, list):
            data = next((item for item in data if isinstance(item, dict)), {})
        data = data if isinstance(data, dict) else {}
        price = _first_price(data.get("price"), data.get("lowPrice"))
        url = _first_text(product.get("url"), data.get("url"))
        if not title or not url or not price:
            continue
        url = urllib.parse.urljoin(final_url, url)
        try:
            _validate_url(url)
        except CaptureError:
            continue
        product_id = _product_id(url, product)
        original = _first_price(data.get("highPrice"), product.get("originalPrice"))
        offer = Offer(
            title=title, affiliate_url=magalu_affiliate_url(url), source_url=url,
            product_key=f"magalu:{product_id}" if product_id else None,
            price=price, original_price=original if original and original > price else None,
            store="magalu", image_url=_image_url(product.get("image")), available=True,
            category=final_url,
        )
        offers[offer.product_key or offer.affiliate_url] = offer
    return list(offers.values())


def _all_products(documents: list[Any]) -> list[dict[str, Any]]:
    queue: list[Any] = list(documents)
    products: list[dict[str, Any]] = []
    while queue:
        item = queue.pop(0)
        if isinstance(item, list):
            queue.extend(item)
        elif isinstance(item, dict):
            if isinstance(item.get("@graph"), list):
                queue.extend(item["@graph"])
            if isinstance(item.get("itemListElement"), list):
                queue.extend(item["itemListElement"])
            if isinstance(item.get("item"), dict):
                queue.append(item["item"])
            kinds = item.get("@type")
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if any(str(kind).casefold() == "product" for kind in kinds):
                products.append(item)
    return products


def _offer_from_listing_row(row: dict[str, Any], category_url: str) -> Offer | None:
    url = str(row.get("href") or "").strip()
    text = str(row.get("text") or "").strip()
    title = str(row.get("title") or "").strip().splitlines()[0] if row.get("title") else ""
    if not url or not text:
        return None
    prices = [_first_price(value) for value in re.findall(r"R\$\s*[\d.]+(?:,\d{2})?", text)]
    prices = [price for price in prices if price and price > 0]
    if not prices:
        return None
    if not title or len(title) < 5:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        title = next((line for line in lines if "R$" not in line and len(line) >= 8), "")
    if not title:
        return None
    has_discount = bool(re.search(r"\b(?:OFF|desconto)\b", text, re.IGNORECASE))
    original = prices[0] if has_discount and len(prices) >= 2 else 0
    current = prices[1] if has_discount and len(prices) >= 2 else prices[0]
    product_id = _product_id(url, {})
    return Offer(
        title=title, affiliate_url=magalu_affiliate_url(url), source_url=url,
        product_key=f"magalu:{product_id}" if product_id else None,
        price=current, original_price=original if original > current else None,
        store="magalu", image_url=str(row.get("image") or "") or None, available=True,
        category=category_url,
    )


def _normalized_text(value: str) -> str:
    import unicodedata
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


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
    promoter_id = os.getenv("MAGALU_PROMOTER_ID", "").strip()
    partner_id = os.getenv("MAGALU_PARTNER_ID", "3440").strip()
    if promoter_id and "magazineluiza.com.br" in (parsed.hostname or ""):
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        query.update({
            "partner_id": [partner_id],
            "promoter_id": [promoter_id],
            "utm_source": ["divulgador"],
            "utm_medium": ["magalu"],
            "utm_campaign": [promoter_id],
        })
        return urllib.parse.urlunsplit((
            parsed.scheme, parsed.netloc, parsed.path,
            urllib.parse.urlencode(query, doseq=True), parsed.fragment,
        ))
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
