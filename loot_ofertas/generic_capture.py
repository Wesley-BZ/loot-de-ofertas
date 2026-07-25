from __future__ import annotations

import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any

from .capture import CaptureError
from .identity import product_identity
from .models import Offer


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.documents: list[Any] = []
        self._buffer: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "meta":
            key = values.get("property") or values.get("name") or values.get("itemprop")
            if key and values.get("content"):
                self.meta[key.casefold()] = values["content"].strip()
        if tag.casefold() == "script" and values.get("type", "").casefold() == "application/ld+json":
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._buffer is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "script" or self._buffer is None:
            return
        raw = "".join(self._buffer).strip()
        self._buffer = None
        try:
            self.documents.append(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            pass


def capture_generic_product(url: str, timeout: int = 25) -> Offer:
    _validate_public_url(url)
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
            _validate_public_url(final_url)
            data = response.read(5_000_001)
            if len(data) > 5_000_000:
                raise CaptureError("A página excedeu o limite de 5 MB")
            charset = response.headers.get_content_charset() or "utf-8"
    except CaptureError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        raise CaptureError(f"A loja bloqueou a leitura automática: {error}") from error

    parser = _MetadataParser()
    parser.feed(data.decode(charset, errors="replace"))
    product = _find_product(parser.documents)
    offers = product.get("offers") if product else {}
    if isinstance(offers, list):
        offers = next((value for value in offers if isinstance(value, dict)), {})
    offers = offers if isinstance(offers, dict) else {}
    title = _first_text(
        product.get("name") if product else None,
        parser.meta.get("og:title"),
        parser.meta.get("twitter:title"),
    )
    price = _price(
        offers.get("price"),
        offers.get("lowPrice"),
        parser.meta.get("product:price:amount"),
        parser.meta.get("og:price:amount"),
    )
    if not title or not price:
        raise CaptureError("Não encontrei título e preço; preencha esses campos manualmente")
    original = _price(
        parser.meta.get("product:original_price:amount"),
        parser.meta.get("original_price"),
        offers.get("highPrice"),
    )
    image = product.get("image") if product else None
    if isinstance(image, list):
        image = next((value for value in image if isinstance(value, str)), None)
    if isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")
    image = image or parser.meta.get("og:image")
    host = (urllib.parse.urlsplit(final_url).hostname or "").casefold()
    store = _store_from_host(host)
    return Offer(
        title=str(title),
        affiliate_url=final_url,
        source_url=final_url,
        price=price,
        original_price=original if original and original > price else None,
        store=store,
        image_url=str(image) if image else None,
        product_key=product_identity(store, final_url, str(title)),
    )


def store_from_url(url: str) -> str:
    host = (urllib.parse.urlsplit(url).hostname or "").casefold()
    return _store_from_host(host)


def _store_from_host(host: str) -> str:
    if "shopee" in host:
        return "shopee"
    if "aliexpress" in host:
        return "aliexpress"
    if "amazon" in host:
        return "amazon"
    return host.removeprefix("www.").split(".", 1)[0] or "outra"


def _validate_public_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CaptureError("Informe um link HTTP ou HTTPS válido")
    if parsed.hostname.casefold() == "localhost":
        raise CaptureError("Endereços locais não são permitidos")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise CaptureError("Não consegui localizar o endereço da loja") from error
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise CaptureError("Endereços privados ou locais não são permitidos")


def _find_product(documents: list[Any]) -> dict[str, Any]:
    queue = list(documents)
    while queue:
        value = queue.pop(0)
        if isinstance(value, list):
            queue.extend(value)
        elif isinstance(value, dict):
            if isinstance(value.get("@graph"), list):
                queue.extend(value["@graph"])
            kinds = value.get("@type")
            kinds = kinds if isinstance(kinds, list) else [kinds]
            if any(str(kind).casefold() == "product" for kind in kinds):
                return value
    return {}


def _first_text(*values: Any) -> str | None:
    return next((str(value).strip() for value in values if value is not None and str(value).strip()), None)


def _price(*values: Any) -> float | None:
    import re

    for value in values:
        if value is None:
            continue
        text = re.sub(r"[^0-9,.-]", "", str(value))
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            result = round(float(text), 2)
        except ValueError:
            continue
        if result > 0:
            return result
    return None
