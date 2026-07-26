from __future__ import annotations

import hashlib
import re
import unicodedata
import urllib.parse


TRACKING_PARAMETERS = {
    "aff_id", "affiliate", "awc", "clickid", "gclid", "matt_tool",
    "partner_id", "ref", "ref_", "srsltid", "utm_campaign", "utm_content",
    "utm_medium", "utm_source", "utm_term",
}


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.strip())
    host = parsed.netloc.casefold().removeprefix("www.").removeprefix("m.")
    path = re.sub(r"/+", "/", parsed.path).rstrip("/") or "/"
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = sorted((key, value) for key, value in query if key.casefold() not in TRACKING_PARAMETERS)
    return urllib.parse.urlunsplit((parsed.scheme.casefold() or "https", host, path, urllib.parse.urlencode(query), ""))


def product_identity(store: str, url: str, title: str = "") -> str:
    normalized = normalize_url(url)
    host_path = urllib.parse.urlsplit(normalized)
    text = urllib.parse.unquote(f"{host_path.netloc}{host_path.path}?{host_path.query}")
    catalog_match = re.search(r"/p/(MLB\d+)(?:[/?]|$)", text, re.IGNORECASE)
    if catalog_match:
        return f"mercadolivre:catalog:{catalog_match.group(1).upper()}"
    patterns = (
        ("mercadolivre", r"\b(MLB-?\d+)\b"),
        ("amazon", r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)"),
        ("magalu", r"/p/([a-z0-9]+)(?:[/?]|$)"),
        ("kabum", r"/produto/(\d+)(?:[/?]|$)"),
        ("shopee", r"(?:-|/)(\d+)\.(\d+)(?:[/?]|$)"),
        ("aliexpress", r"/(?:item/)?(\d{8,})\.html"),
    )
    for prefix, pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            identifier = "-".join(group.upper() for group in match.groups())
            if prefix == "mercadolivre":
                identifier = identifier.replace("-", "")
            return f"{prefix}:{identifier}"
    slug = unicodedata.normalize("NFKD", title.casefold())
    slug = "".join(char for char in slug if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:80]
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"{store.casefold().strip()}:{slug or digest}:{digest}"


def product_family_identity(title: str) -> str | None:
    """Group phone color/seller variants while preserving model and memory."""
    normalized = unicodedata.normalize("NFKD", title.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    model_patterns = (
        ("samsung-galaxy", r"\bgalaxy\s+([asmz]\d{2,3}(?:\s*(?:fe|ultra|plus))?)\b"),
        ("iphone", r"\biphone\s+(\d{1,2}(?:\s*(?:pro|max|plus|mini))?)\b"),
        ("motorola-moto", r"\bmoto\s+([a-z]\d{1,3}(?:\s*(?:power|play|plus|ultra))?)\b"),
        ("xiaomi-redmi", r"\bredmi\s+([a-z0-9]+(?:\s*(?:pro|plus|ultra))?)\b"),
        ("xiaomi-poco", r"\bpoco\s+([a-z0-9]+(?:\s*(?:pro|plus|ultra))?)\b"),
    )
    family = model = None
    for candidate_family, pattern in model_patterns:
        match = re.search(pattern, normalized)
        if match:
            family, model = candidate_family, re.sub(r"\s+", "-", match.group(1).strip())
            break
    if not family or not model:
        return None
    storage_match = re.search(r"\b(64|128|256|512|1024)\s*gb\b", normalized)
    ram_match = re.search(r"\b(?:ram\s*)?(\d{1,2})\s*gb\s*ram\b", normalized)
    network = "5g" if re.search(r"\b5g\b", normalized) else "4g"
    storage = f"{storage_match.group(1)}gb" if storage_match else "storage-unknown"
    ram = f"{ram_match.group(1)}gb" if ram_match else "ram-unknown"
    return f"phone:{family}:{model}:{storage}:{ram}:{network}"
