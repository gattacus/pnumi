from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from pnumi.rates import (
    CompositeRateProvider,
    RateProvider,
    StaticRateProvider,
    YahooFinanceRateProvider,
    _yahoo_symbol_candidates,
    _yahoo_symbols,
    default_rate_provider,
)


class FailingProvider(RateProvider):
    def get_rate(self, base: str, quote: str, at=None) -> Decimal:
        raise LookupError("boom")


def test_static_rate_reverse() -> None:
    provider = StaticRateProvider({("USD", "EUR"): Decimal("0.8")})
    assert provider.get_rate("EUR", "USD") == Decimal("1.25")


def test_composite_fallback() -> None:
    provider = CompositeRateProvider([FailingProvider(), StaticRateProvider({("USD", "CHF"): Decimal("0.9")})])
    assert provider.get_rate("USD", "CHF") == Decimal("0.9")


def test_yahoo_symbols_for_fiat_and_crypto() -> None:
    assert _yahoo_symbols("EUR", "USD") == ["EURUSD=X"]
    assert _yahoo_symbols("BTC", "USD") == ["BTC-USD"]
    assert _yahoo_symbols("USD", "BTC") == ["BTC-USD"]


def test_yahoo_symbol_candidates_mark_inverted_crypto_quotes() -> None:
    assert _yahoo_symbol_candidates("USD", "BTC") == [("BTC-USD", True)]


def test_yahoo_finance_rate_provider_fetches_direct_fiat(monkeypatch, tmp_path) -> None:
    provider = YahooFinanceRateProvider(cache_dir=tmp_path)
    calls: list[tuple[str, object | None]] = []

    def fake_fetch(symbol: str, at=None):
        calls.append((symbol, at))
        return Decimal("1.08") if symbol == "EURUSD=X" else None

    monkeypatch.setattr(provider, "_fetch_symbol_price", fake_fetch)

    assert provider.get_rate("EUR", "USD") == Decimal("1.08")
    assert calls == [("EURUSD=X", None)]


def test_yahoo_finance_rate_provider_reads_latest_chart_price(monkeypatch, tmp_path) -> None:
    provider = YahooFinanceRateProvider(cache_dir=tmp_path)

    def fake_fetch_chart(symbol: str, params: dict[str, str]):
        assert symbol == "EURUSD=X"
        assert params == {"range": "5d", "interval": "1d"}
        return {"chart": {"result": [{"meta": {"regularMarketPrice": 1.1601}, "indicators": {"quote": [{"close": [1.15]}]}}]}}

    monkeypatch.setattr(provider, "_fetch_chart", fake_fetch_chart)

    assert provider.get_rate("EUR", "USD") == Decimal("1.1601")


def test_yahoo_finance_rate_provider_reads_historical_chart_close(monkeypatch, tmp_path) -> None:
    provider = YahooFinanceRateProvider(cache_dir=tmp_path)

    def fake_fetch_chart(symbol: str, params: dict[str, str]):
        assert symbol == "BTC-USD"
        assert params["interval"] == "1d"
        assert int(params["period1"]) < int(params["period2"])
        return {"chart": {"result": [{"indicators": {"quote": [{"close": [65000.0, None, 66000.5]}]}}]}}

    monkeypatch.setattr(provider, "_fetch_chart", fake_fetch_chart)

    assert provider.get_rate("BTC", "USD", date(2026, 6, 17)) == Decimal("66000.5")


def test_yahoo_finance_rate_provider_fetches_direct_crypto(monkeypatch, tmp_path) -> None:
    provider = YahooFinanceRateProvider(cache_dir=tmp_path)

    def fake_fetch(symbol: str, at=None):
        return Decimal("65000") if symbol == "BTC-USD" else None

    monkeypatch.setattr(provider, "_fetch_symbol_price", fake_fetch)

    assert provider.get_rate("BTC", "USD") == Decimal("65000")


def test_yahoo_finance_rate_provider_inverts_crypto_quote(monkeypatch, tmp_path) -> None:
    provider = YahooFinanceRateProvider(cache_dir=tmp_path)
    calls: list[tuple[str, object | None]] = []

    def fake_fetch(symbol: str, at=None):
        calls.append((symbol, at))
        return Decimal("50000") if symbol == "BTC-USD" else None

    monkeypatch.setattr(provider, "_fetch_symbol_price", fake_fetch)

    assert provider.get_rate("USD", "BTC") == Decimal("0.00002")
    assert calls == [("BTC-USD", None)]


def test_yahoo_finance_rate_provider_uses_reverse_cache_for_crypto(monkeypatch, tmp_path) -> None:
    provider = YahooFinanceRateProvider(cache_dir=tmp_path)
    provider._write_cache("XMR", "USD", None, {"rate": "140", "fetched_at": datetime.now(UTC).isoformat()})

    def fake_fetch(symbol: str, at=None):
        raise AssertionError(f"unexpected fetch for {symbol}")

    monkeypatch.setattr(provider, "_fetch_symbol_price", fake_fetch)

    assert provider.get_rate("USD", "XMR") == Decimal("0.007142857142857142857142857143")


def test_default_rate_provider_fetches_before_fallback(monkeypatch, caplog) -> None:
    def fake_fetch(self, base: str, quote: str, at=None):
        assert (base, quote) == ("EUR", "USD")
        return Decimal("1.08")

    monkeypatch.setattr(YahooFinanceRateProvider, "_cached", lambda self, base, quote, at=None: None)
    monkeypatch.setattr(YahooFinanceRateProvider, "_write_cache", lambda self, base, quote, at, data: None)
    monkeypatch.setattr(YahooFinanceRateProvider, "_fetch_rate", fake_fetch)

    with caplog.at_level(logging.WARNING, logger="pnumi.rates"):
        assert default_rate_provider().get_rate("EUR", "USD") == Decimal("1.08")

    assert "Using fallback" not in caplog.text


def test_default_rate_provider_logs_fallback_warning(monkeypatch, caplog) -> None:
    def fake_fetch(self, base: str, quote: str, at=None):
        raise LookupError("offline")

    monkeypatch.setattr(YahooFinanceRateProvider, "_cached", lambda self, base, quote, at=None: None)
    monkeypatch.setattr(YahooFinanceRateProvider, "_write_cache", lambda self, base, quote, at, data: None)
    monkeypatch.setattr(YahooFinanceRateProvider, "_fetch_rate", fake_fetch)

    with caplog.at_level(logging.WARNING, logger="pnumi.rates"):
        rate = default_rate_provider().get_rate("EUR", "USD")

    assert rate == Decimal("1.086956521739130434782608696")
    assert "Using fallback StaticRateProvider rate for EUR/USD" in caplog.text
    assert "offline" in caplog.text


def test_yahoo_finance_rate_provider_crosses_through_usd(monkeypatch, tmp_path) -> None:
    provider = YahooFinanceRateProvider(cache_dir=tmp_path)

    def fake_fetch(symbol: str, at=None):
        return {
            "BTC-EUR": None,
            "BTC-USD": Decimal("65000"),
            "EURUSD=X": Decimal("1.25"),
        }.get(symbol)

    monkeypatch.setattr(provider, "_fetch_symbol_price", fake_fetch)

    assert provider.get_rate("BTC", "EUR") == Decimal("5.20E+4")
