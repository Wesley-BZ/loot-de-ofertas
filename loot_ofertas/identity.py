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
    patterns = (
        ("mercadolivre", r"\b(MLB-?\d+)\b"),
        ("amazon", r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?]|$)"),
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
