from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class Value:
    magnitude: Decimal | None = None
    unit: str | None = None
    currency: str | None = None
    when: datetime | date | None = None
    duration: timedelta | None = None
    text: str | None = None

    @classmethod
    def number(cls, value: Decimal | int | float | str, unit: str | None = None) -> "Value":
        return cls(magnitude=Decimal(str(value)), unit=unit)

    @classmethod
    def money(cls, value: Decimal | int | float | str, currency: str) -> "Value":
        return cls(magnitude=Decimal(str(value)), currency=currency.upper())

    @classmethod
    def date_time(cls, value: datetime | date) -> "Value":
        return cls(when=value)

    @classmethod
    def delta(cls, value: timedelta) -> "Value":
        return cls(duration=value)

    @property
    def is_number(self) -> bool:
        return self.magnitude is not None and self.currency is None

    @property
    def is_money(self) -> bool:
        return self.magnitude is not None and self.currency is not None

    @property
    def is_date_time(self) -> bool:
        return self.when is not None

    @property
    def is_duration(self) -> bool:
        return self.duration is not None


@dataclass
class LineResult:
    input_text: str
    display: str = ""
    value: Value | None = None
    diagnostics: list[str] = field(default_factory=list)
    span: tuple[int, int] | None = None

    @property
    def ok(self) -> bool:
        return not self.diagnostics


@dataclass
class DocumentResult:
    line_results: list[LineResult]

    @property
    def displays(self) -> list[str]:
        return [line.display for line in self.line_results]


class RateProvider(Protocol):
    def get_rate(self, base: str, quote: str, at: date | None = None) -> Decimal:
        ...


@dataclass
class DocumentContext:
    variables: dict[str, Value] = field(default_factory=dict)
    previous_results: list[Value] = field(default_factory=list)
    section_results: list[Value] = field(default_factory=list)
    rate_provider: RateProvider | None = None
    settings: dict[str, Any] = field(default_factory=lambda: {"em": Decimal("16"), "ppi": Decimal("96")})

    def reset_section(self) -> None:
        self.section_results.clear()

    def remember(self, value: Value | None) -> None:
        if value is None:
            return
        if value.magnitude is not None:
            self.previous_results.append(value)
            self.section_results.append(value)
