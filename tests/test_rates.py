from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

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


def test_default_rate_provider_fetches(monkeypatch) -> None:
    def fake_fetch(self, base: str, quote: str, at=None):
        assert (base, quote) == ("EUR", "USD")
        return Decimal("1.08")

    monkeypatch.setattr(YahooFinanceRateProvider, "_cached", lambda self, base, quote, at=None: None)
    monkeypatch.setattr(YahooFinanceRateProvider, "_write_cache", lambda self, base, quote, at, data: None)
    monkeypatch.setattr(YahooFinanceRateProvider, "_fetch_rate", fake_fetch)

    assert default_rate_provider().get_rate("EUR", "USD") == Decimal("1.08")


def test_default_rate_provider_raises_lookup_error(monkeypatch) -> None:
    def fake_fetch(self, base: str, quote: str, at=None):
        raise LookupError("offline")

    monkeypatch.setattr(YahooFinanceRateProvider, "_cached", lambda self, base, quote, at=None: None)
    monkeypatch.setattr(YahooFinanceRateProvider, "_write_cache", lambda self, base, quote, at, data: None)
    monkeypatch.setattr(YahooFinanceRateProvider, "_fetch_rate", fake_fetch)

    import pytest

    with pytest.raises(LookupError, match="offline"):
        default_rate_provider().get_rate("EUR", "USD")


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


def test_fetch_symbol_price_latest_via_fast_info(monkeypatch) -> None:
    import yfinance as yf

    mock_ticker = MagicMock()

    # Mock fast_info as an object having last_price or get("last_price")
    class FakeFastInfo:
        def get(self, key):
            if key == "last_price":
                return 123.45
            return None

    mock_ticker.fast_info = FakeFastInfo()
    monkeypatch.setattr(yf, "Ticker", lambda symbol: mock_ticker)

    provider = YahooFinanceRateProvider()
    price = provider._fetch_symbol_price("AAPL", None)
    assert price == Decimal("123.45")


def test_fetch_symbol_price_latest_via_history(monkeypatch) -> None:
    import pandas as pd
    import yfinance as yf

    mock_ticker = MagicMock()
    mock_ticker.fast_info = None

    # history returns a pandas DataFrame
    df = pd.DataFrame({"Close": [120.0, 122.5, None, 123.0]})
    mock_ticker.history.return_value = df
    monkeypatch.setattr(yf, "Ticker", lambda symbol: mock_ticker)

    provider = YahooFinanceRateProvider()
    price = provider._fetch_symbol_price("AAPL", None)
    assert price == Decimal("123")
    mock_ticker.history.assert_called_once_with(period="5d", interval="1d", auto_adjust=False)


def test_fetch_symbol_price_historical(monkeypatch) -> None:
    from datetime import date

    import pandas as pd
    import yfinance as yf

    mock_ticker = MagicMock()
    df = pd.DataFrame({"Close": [115.0]})
    mock_ticker.history.return_value = df
    monkeypatch.setattr(yf, "Ticker", lambda symbol: mock_ticker)

    provider = YahooFinanceRateProvider()
    price = provider._fetch_symbol_price("AAPL", date(2026, 6, 10))
    assert price == Decimal("115")
    mock_ticker.history.assert_called_once_with(start="2026-06-10", end="2026-06-11", interval="1d", auto_adjust=False)
