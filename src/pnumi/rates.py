from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

from .currencies import CRYPTO_CODES, ISO_4217_CODES

logger = logging.getLogger(__name__)


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


class YahooFinanceRateProvider(RateProvider):
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
        reverse_cached = self._cached(quote, base, at)
        if reverse_cached is not None:
            rate = Decimal("1") / reverse_cached
            self._write_cache(base, quote, at, {"rate": str(rate), "fetched_at": datetime.now(UTC).isoformat()})
            return rate
        rate = self._fetch_rate(base, quote, at)
        self._write_cache(base, quote, at, {"rate": str(rate), "fetched_at": datetime.now(UTC).isoformat()})
        return rate

    def _path(self, base: str, quote: str, at: date | None) -> Path:
        date_key = at.isoformat() if at else "latest"
        return self.cache_dir / f"yahoo-finance-{base}-{quote}-{date_key}.json"

    def _cached(self, base: str, quote: str, at: date | None) -> Decimal | None:
        path = self._path(base, quote, at)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if at is None:
                fetched = datetime.fromisoformat(data["fetched_at"])
                if datetime.now(UTC) - fetched > self.ttl:
                    return None
            return Decimal(str(data["rate"]))
        except Exception:
            return None

    def _write_cache(self, base: str, quote: str, at: date | None, data: dict[str, Any]) -> None:
        self._path(base, quote, at).write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def _fetch_rate(self, base: str, quote: str, at: date | None) -> Decimal:
        for symbol, invert in _yahoo_symbol_candidates(base, quote):
            price = self._fetch_symbol_price(symbol, at)
            if price is not None:
                return (Decimal("1") / price) if invert else price
        if base != "USD" and quote != "USD":
            base_usd = self.get_rate(base, "USD", at)
            quote_usd = self.get_rate(quote, "USD", at)
            return base_usd / quote_usd
        raise LookupError(f"No Yahoo Finance rate for {base}/{quote}")

    def _fetch_symbol_price(self, symbol: str, at: date | None) -> Decimal | None:
        try:
            import yfinance as yf
        except ImportError as exc:
            raise LookupError("yfinance is not installed") from exc
        ticker = yf.Ticker(symbol)
        if at is None:
            price = self._latest_price(ticker)
            return Decimal(str(price)) if price is not None else None
        price = self._historical_price(ticker, at)
        return Decimal(str(price)) if price is not None else None

    def _latest_price(self, ticker: Any) -> Any | None:
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info:
            try:
                price = fast_info.get("last_price")
            except AttributeError:
                price = getattr(fast_info, "last_price", None)
            if price is not None:
                return price
        history = ticker.history(period="5d", interval="1d", auto_adjust=False)
        return _last_close(history)

    def _historical_price(self, ticker: Any, at: date) -> Any | None:
        history = ticker.history(start=at.isoformat(), end=(at + timedelta(days=1)).isoformat(), interval="1d", auto_adjust=False)
        return _last_close(history)


def _last_close(history: Any) -> Any | None:
    if history is None or getattr(history, "empty", False):
        return None
    try:
        close = history["Close"].dropna()
        if getattr(close, "empty", False):
            return None
        return close.iloc[-1]
    except Exception:
        return None


def _yahoo_symbols(base: str, quote: str) -> list[str]:
    return [symbol for symbol, _ in _yahoo_symbol_candidates(base, quote)]


def _yahoo_symbol_candidates(base: str, quote: str) -> list[tuple[str, bool]]:
    base = base.upper()
    quote = quote.upper()
    if base in ISO_4217_CODES and quote in ISO_4217_CODES:
        return [(f"{base}{quote}=X", False)]
    if base in CRYPTO_CODES and quote in ISO_4217_CODES:
        return [(f"{base}-{quote}", False)]
    if base in ISO_4217_CODES and quote in CRYPTO_CODES:
        return [(f"{quote}-{base}", True)]
    if base in CRYPTO_CODES and quote in CRYPTO_CODES:
        return [(f"{base}-{quote}", False), (f"{quote}-{base}", True)]
    return []


class CompositeRateProvider(RateProvider):
    def __init__(self, providers: list[RateProvider], warn_on_fallback: bool = False) -> None:
        self.providers = providers
        self.warn_on_fallback = warn_on_fallback

    def get_rate(self, base: str, quote: str, at: date | None = None) -> Decimal:
        failures: list[tuple[RateProvider, Exception]] = []
        for provider in self.providers:
            try:
                rate = provider.get_rate(base, quote, at)
            except Exception as exc:
                failures.append((provider, exc))
                continue
            if failures and self.warn_on_fallback:
                failed_provider, last_error = failures[-1]
                logger.warning(
                    "Using fallback %s rate for %s/%s because %s could not provide a rate: %s",
                    provider.__class__.__name__,
                    base.upper(),
                    quote.upper(),
                    failed_provider.__class__.__name__,
                    last_error,
                )
            return rate
        raise LookupError(f"No rate for {base}/{quote}") from failures[-1][1] if failures else None


def fallback_rate_provider() -> RateProvider:
    return StaticRateProvider(
        {
            ("USD", "EUR"): Decimal("0.92"),
            ("USD", "CAD"): Decimal("1.35"),
            ("USD", "GBP"): Decimal("0.79"),
            ("USD", "CHF"): Decimal("0.89"),
            ("BTC", "USD"): Decimal("65000"),
            ("ETH", "USD"): Decimal("3500"),
        }
    )


def default_rate_provider() -> RateProvider:
    return CompositeRateProvider([YahooFinanceRateProvider(), fallback_rate_provider()], warn_on_fallback=True)
