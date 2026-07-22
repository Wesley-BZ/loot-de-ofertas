from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .identity import product_identity
from .meli import MeliError, api_get
from .models import Offer


MAX_PAGE_BYTES = 5_000_000
MERCADO_LIVRE_HOSTS = ("mercadolivre.com.br", "mercadolibre.com")


class CaptureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CapturedPage:
    offer: Offer
    final_url: str


def capture_mercado_livre_api(url: str) -> CapturedPage:
    _validate_http_url(url)
    _validate_mercado_livre_host(url)
    decoded = urllib.parse.unquote(url)
    catalog_match = re.search(r"\b(MLBU\d+)\b", decoded, re.IGNORECASE)
    if not catalog_match:
        raise CaptureError("O link não contém o identificador de catálogo MLBU")
    catalog_id = catalog_match.group(1).upper()
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    requested_item = str(query.get("wid", [""])[0]).upper()
    if not re.fullmatch(r"MLB\d+", requested_item):
        requested_item = next(
            (value.upper() for value in re.findall(r"\bMLB\d+\b", decoded, re.IGNORECASE)), ""
        )
    try:
        listing_data = api_get(f"products/{catalog_id}/items")
        results = listing_data.get("results", []) if isinstance(listing_data, dict) else []
        listing = next(
            (row for row in results if str(row.get("item_id", "")).upper() == requested_item),
            results[0] if results else None,
        )
        if not isinstance(listing, dict):
            raise CaptureError("A API não retornou ofertas para esse produto")
        product = api_get(f"user-products/{listing.get('user_product_id') or catalog_id}")
        seller = api_get(f"users/{listing['seller_id']}")
        category = api_get(f"categories/{listing['category_id']}")
    except (MeliError, KeyError) as error:
        raise CaptureError(f"A API do Mercado Livre não conseguiu ler o produto: {error}") from error

    title = str(product.get("name") or product.get("family_name") or "").strip()
    price = _first_price(listing.get("price"))
    if not title or price is None:
        raise CaptureError("A API retornou o produto sem título ou preço")
    original_price = _first_price(listing.get("original_price"))
    pictures = product.get("pictures") or []
    image_url = next(
        (str(picture.get("secure_url")) for picture in pictures if picture.get("secure_url")),
        product.get("thumbnail"),
    )
    reputation = seller.get("seller_reputation") or {}
    rating_match = re.match(r"(\d+)", str(reputation.get("level_id") or ""))
    transactions = reputation.get("transactions") or {}
    shipping = listing.get("shipping") or {}
    item_id = str(listing.get("item_id") or requested_item).upper()
    offer = Offer(
        title=title,
        affiliate_url=url,
        source_url=url,
        product_key=f"mercadolivre:{item_id.casefold()}",
        price=price,
        original_price=original_price if original_price and original_price > price else None,
        store="mercadolivre",
        image_url=str(image_url) if image_url else None,
        category=str(category.get("name") or ""),
        seller_name=str(seller.get("nickname") or "") or None,
        seller_rating=float(rating_match.group(1)) if rating_match else None,
        sold_count=int(transactions.get("total") or 0),
        shipping_price=0.0 if shipping.get("free_shipping") else None,
        available=True,
    )
    return CapturedPage(offer, url)


class _ProductMetadataParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.json_ld: list[Any] = []
        self._json_buffer: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "meta":
            key = attributes.get("property") or attributes.get("name") or attributes.get("itemprop")
            if key and attributes.get("content"):
                self.meta[key.casefold()] = attributes["content"].strip()
        if tag.casefold() == "script" and attributes.get("type", "").casefold() == "application/ld+json":
            self._json_buffer = []

    def handle_data(self, data: str) -> None:
        if self._json_buffer is not None:
            self._json_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "script" or self._json_buffer is None:
            return
        raw = "".join(self._json_buffer).strip()
        self._json_buffer = None
        if not raw:
            return
        try:
            self.json_ld.append(json.loads(raw))
        except json.JSONDecodeError:
            return


def capture_mercado_livre(url: str, timeout: int = 25) -> CapturedPage:
    _validate_http_url(url)
    _validate_mercado_livre_host(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "pt-BR,pt;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            _validate_mercado_livre_host(final_url)
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise CaptureError(f"A página retornou um conteúdo inesperado: {content_type}")
            data = response.read(MAX_PAGE_BYTES + 1)
            if len(data) > MAX_PAGE_BYTES:
                raise CaptureError("A página do produto excedeu o limite de 5 MB")
            charset = response.headers.get_content_charset() or "utf-8"
    except CaptureError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise CaptureError(f"Não foi possível abrir o produto: {exc}") from exc

    return capture_mercado_livre_html(data.decode(charset, errors="replace"), final_url)


def capture_mercado_livre_browser(
    url: str,
    timeout: int = 35,
    session_dir: str | Path = ".capture-session",
) -> CapturedPage:
    _validate_http_url(url)
    _validate_mercado_livre_host(url)
    try:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as exc:
        raise CaptureError("O fallback de navegador requer Selenium") from exc
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1365,900")
    options.add_argument(f"--user-data-dir={Path(session_dir).resolve()}")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            lambda browser: browser.find_elements(By.CSS_SELECTOR, "script[type='application/ld+json']")
        )
        final_url = driver.current_url
        _validate_mercado_livre_host(final_url)
        captured = capture_mercado_livre_html(driver.page_source, final_url)
        previous = driver.find_elements(By.CSS_SELECTOR, "s.andes-money-amount")
        if previous:
            previous_price = _first_price(previous[0].text)
            if previous_price and previous_price > captured.offer.price:
                captured.offer.original_price = previous_price
        return captured
    except CaptureError:
        raise
    except Exception as exc:
        raise CaptureError(f"O navegador não conseguiu ler o produto: {exc}") from exc
    finally:
        driver.quit()


def capture_mercado_livre_html(html: str, final_url: str) -> CapturedPage:
    _validate_mercado_livre_host(final_url)
    parser = _ProductMetadataParser()
    parser.feed(html)
    product = _find_product(parser.json_ld)
    title = _first_text(
        product.get("name") if product else None,
        parser.meta.get("og:title"),
        parser.meta.get("twitter:title"),
    )
    offers = product.get("offers") if product else None
    if isinstance(offers, list):
        offers = next((item for item in offers if isinstance(item, dict)), None)
    offers = offers if isinstance(offers, dict) else {}
    price = _first_price(
        offers.get("price"),
        offers.get("lowPrice"),
        parser.meta.get("product:price:amount"),
        parser.meta.get("og:price:amount"),
    )
    original_price = _first_price(
        parser.meta.get("product:original_price:amount"),
        parser.meta.get("original_price"),
    )
    if not title:
        raise CaptureError("Não encontrei o título do produto na página")
    if price is None or price <= 0:
        raise CaptureError("Não encontrei um preço válido na página")
    if original_price is not None and original_price <= price:
        original_price = None
    image = _image_url(product.get("image") if product else None) or parser.meta.get("og:image")
    seller = offers.get("seller")
    seller_name = seller.get("name") if isinstance(seller, dict) else None
    availability = str(offers.get("availability", "")).casefold()
    available = not any(term in availability for term in ("outofstock", "discontinued", "soldout"))
    key = product_identity("mercadolivre", final_url, title)
    offer = Offer(
        title=title.strip(),
        affiliate_url=final_url,
        source_url=final_url,
        product_key=key,
        price=price,
        original_price=original_price,
        store="mercadolivre",
        image_url=image,
        seller_name=_text_or_none(seller_name),
        available=available,
    )
    return CapturedPage(offer, final_url)


def save_message(message: str, offer_id: int, directory: str | Path = "outbox/captured") -> Path:
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"oferta-{offer_id}.txt"
    path.write_text(message, encoding="utf-8")
    return path


def _validate_http_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CaptureError("Informe um link HTTP ou HTTPS válido")


def _validate_mercado_livre_host(url: str) -> None:
    host = (urllib.parse.urlsplit(url).hostname or "").casefold()
    if not any(host == domain or host.endswith(f".{domain}") for domain in MERCADO_LIVRE_HOSTS):
        raise CaptureError("O link final não pertence ao Mercado Livre")


def _find_product(documents: list[Any]) -> dict[str, Any]:
    queue = list(documents)
    while queue:
        item = queue.pop(0)
        if isinstance(item, list):
            queue.extend(item)
            continue
        if not isinstance(item, dict):
            continue
        graph = item.get("@graph")
        if isinstance(graph, list):
            queue.extend(graph)
        kind = item.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(value).casefold() == "product" for value in kinds):
            return item
    return {}


def _first_text(*values: Any) -> str | None:
    return next((str(value).strip() for value in values if value is not None and str(value).strip()), None)


def _first_price(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        text = re.sub(r"[^0-9,.-]", "", str(value).strip())
        if not text:
            continue
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            return round(float(text), 2)
        except ValueError:
            continue
    return None


def _image_url(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return next((item for item in value if isinstance(item, str)), None)
    if isinstance(value, dict):
        return _first_text(value.get("url"), value.get("contentUrl"))
    return None


def _text_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
