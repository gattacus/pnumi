from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from platformdirs import user_cache_dir


class RateProvider:
    def get_rate(self, base: str, quote: str, at: date | None = None) -> Decimal:
        raise NotImplementedError


@dataclass
class StaticRateProvider(RateProvider):
    rates: dict[tuple[str, str], Decimal]

    def get_rate(self, base: str, quote: str, at: date | None = None) -> Decimal:
        base = base.upper()
        quote = quote.upper()
        if base == quote:
            return Decimal("1")
        direct = self.rates.get((base, quote))
        if direct is not None:
            return direct
        reverse = self.rates.get((quote, base))
        if reverse is not None:
            return Decimal("1") / reverse
        usd_base = self.rates.get((base, "USD"))
        usd_quote = self.rates.get(("USD", quote))
        if usd_base is not None and usd_quote is not None:
            return usd_base * usd_quote
        raise LookupError(f"No rate for {base}/{quote}")


class FrankfurterRateProvider(RateProvider):
    def __init__(self, cache_dir: Path | None = None, ttl: timedelta = timedelta(hours=8)) -> None:
        self.cache_dir = cache_dir or Path(user_cache_dir("Pnumi", "Pnumi"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl

    def get_rate(self, base: str, quote: str, at: date | None = None) -> Decimal:
        base = base.upper()
        quote = quote.upper()
        if base == quote:
            return Decimal("1")
        cached = self._cached(base, quote, at)
        if cached is not None:
            return cached
        url = f"https://api.frankfurter.dev/v2/rate/{base}/{quote}"
        if at is not None:
            url = f"{url}?date={at.isoformat()}"
        response = httpx.get(url, timeout=8)
        response.raise_for_status()
        data = response.json()
        rate = Decimal(str(data["rate"]))
        self._write_cache(base, quote, at, {"rate": str(rate), "fetched_at": datetime.now(timezone.utc).isoformat()})
        return rate

    def _path(self, base: str, quote: str, at: date | None) -> Path:
        date_key = at.isoformat() if at else "latest"
        return self.cache_dir / f"frankfurter-{base}-{quote}-{date_key}.json"

    def _cached(self, base: str, quote: str, at: date | None) -> Decimal | None:
        path = self._path(base, quote, at)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if at is None:
                fetched = datetime.fromisoformat(data["fetched_at"])
                if datetime.now(timezone.utc) - fetched > self.ttl:
                    return None
            return Decimal(str(data["rate"]))
        except Exception:
            return None

    def _write_cache(self, base: str, quote: str, at: date | None, data: dict[str, Any]) -> None:
        self._path(base, quote, at).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


class CompositeRateProvider(RateProvider):
    def __init__(self, providers: list[RateProvider]) -> None:
        self.providers = providers

    def get_rate(self, base: str, quote: str, at: date | None = None) -> Decimal:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                return provider.get_rate(base, quote, at)
            except Exception as exc:
                last_error = exc
        raise LookupError(f"No rate for {base}/{quote}") from last_error


def default_rate_provider() -> RateProvider:
    fallback = StaticRateProvider(
        {
            ("USD", "EUR"): Decimal("0.92"),
            ("USD", "CAD"): Decimal("1.35"),
            ("USD", "GBP"): Decimal("0.79"),
            ("USD", "CHF"): Decimal("0.89"),
            ("BTC", "USD"): Decimal("65000"),
            ("ETH", "USD"): Decimal("3500"),
        }
    )
    providers: list[RateProvider] = [FrankfurterRateProvider(), fallback]
    if os.environ.get("COINGECKO_API_KEY"):
        providers.insert(0, CoinGeckoRateProvider(os.environ["COINGECKO_API_KEY"]))
    return CompositeRateProvider(providers)


class CoinGeckoRateProvider(RateProvider):
    COIN_IDS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin"}

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def get_rate(self, base: str, quote: str, at: date | None = None) -> Decimal:
        if at is not None:
            raise LookupError("CoinGecko provider only supports latest rates")
        coin = self.COIN_IDS.get(base.upper())
        if coin is None:
            raise LookupError(f"Unsupported crypto currency: {base}")
        quote = quote.lower()
        response = httpx.get(
            "https://pro-api.coingecko.com/api/v3/simple/price",
            params={"ids": coin, "vs_currencies": quote, "include_last_updated_at": "true"},
            headers={"x-cg-pro-api-key": self.api_key},
            timeout=8,
        )
        response.raise_for_status()
        data = response.json()
        return Decimal(str(data[coin][quote]))
