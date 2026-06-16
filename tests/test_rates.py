from __future__ import annotations

from decimal import Decimal

from pnumi.rates import CompositeRateProvider, RateProvider, StaticRateProvider


class FailingProvider(RateProvider):
    def get_rate(self, base: str, quote: str, at=None) -> Decimal:
        raise LookupError("boom")


def test_static_rate_reverse() -> None:
    provider = StaticRateProvider({("USD", "EUR"): Decimal("0.8")})
    assert provider.get_rate("EUR", "USD") == Decimal("1.25")


def test_composite_fallback() -> None:
    provider = CompositeRateProvider([FailingProvider(), StaticRateProvider({("USD", "CHF"): Decimal("0.9")})])
    assert provider.get_rate("USD", "CHF") == Decimal("0.9")
