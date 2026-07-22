from __future__ import annotations

import csv
from pathlib import Path

from .database import OfferRepository
from .models import Offer


def _optional_float(value: str | None) -> float | None:
    if not value or not value.strip():
        return None
    return float(value.replace(".", "").replace(",", ".") if "," in value else value)


def import_csv(path: str | Path, repository: OfferRepository) -> int:
    count = 0
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            repository.add(
                Offer(
                    title=row["title"].strip(),
                    affiliate_url=row["affiliate_url"].strip(),
                    price=float(row["price"].replace(".", "").replace(",", ".") if "," in row["price"] else row["price"]),
                    original_price=_optional_float(row.get("original_price")),
                    commission_percent=_optional_float(row.get("commission_percent")),
                    store=row["store"].strip(),
                    coupon=(row.get("coupon") or "").strip() or None,
                    image_url=(row.get("image_url") or "").strip() or None,
                    category=(row.get("category") or "").strip() or None,
                )
            )
            count += 1
    return count

