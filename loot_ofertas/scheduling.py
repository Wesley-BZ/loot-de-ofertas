from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class PublicationPolicy:
    min_interval_minutes: int = 20
    daily_limit: int = 15
    category_daily_limit: int = 3
    start_hour: int = 9
    end_hour: int = 22
    repeat_cooldown_days: int = 7
    repeat_price_drop_percent: float = 10
    timezone_name: str = "America/Sao_Paulo"

    @classmethod
    def from_env(cls) -> "PublicationPolicy":
        return cls(
            min_interval_minutes=int(os.getenv("LOOT_MIN_INTERVAL_MINUTES", "20")),
            daily_limit=int(os.getenv("LOOT_DAILY_LIMIT", "15")),
            category_daily_limit=int(os.getenv("LOOT_CATEGORY_DAILY_LIMIT", "3")),
            start_hour=int(os.getenv("LOOT_START_HOUR", "9")),
            end_hour=int(os.getenv("LOOT_END_HOUR", "22")),
            repeat_cooldown_days=int(os.getenv("LOOT_REPEAT_COOLDOWN_DAYS", "7")),
            repeat_price_drop_percent=float(os.getenv("LOOT_REPEAT_PRICE_DROP_PERCENT", "10")),
            timezone_name=os.getenv("LOOT_TIMEZONE", "America/Sao_Paulo"),
        )

    @property
    def timezone(self):
        try:
            return ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError:
            if self.timezone_name == "America/Sao_Paulo":
                return timezone(timedelta(hours=-3), "America/Sao_Paulo")
            raise

    def local_now(self, now: datetime | None = None) -> datetime:
        if now is None:
            return datetime.now(self.timezone)
        if now.tzinfo is None:
            return now.replace(tzinfo=self.timezone)
        return now.astimezone(self.timezone)

    def is_active_hour(self, now: datetime | None = None) -> bool:
        local = self.local_now(now)
        return time(self.start_hour) <= local.time().replace(tzinfo=None) < time(self.end_hour)

    def local_day_bounds_utc(self, now: datetime | None = None) -> tuple[datetime, datetime]:
        local = self.local_now(now)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PublicationDecision:
    allowed: bool
    reason: str
    wait_seconds: int = 0


def parse_database_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_channel(channel: str) -> str:
    return "whatsapp" if channel in {"whatsapp", "whatsapp-web", "wppconnect"} else channel
