from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from .models import Value


def clean_decimal(value: Decimal, max_places: int = 10) -> str:
    if value.is_nan():
        return "NaN"
    if value.is_infinite():
        return "Infinity" if value > 0 else "-Infinity"
    quant = Decimal(1).scaleb(-max_places)
    rounded = value.quantize(quant, rounding=ROUND_HALF_UP).normalize()
    if rounded == rounded.to_integral():
        return str(rounded.quantize(Decimal(1)))
    return format(rounded, "f")


def group_thousands(text: str) -> str:
    if text in {"NaN", "Infinity", "-Infinity"}:
        return text
    sign = ""
    if text.startswith("-"):
        sign = "-"
        text = text[1:]
    integer, separator, fraction = text.partition(".")
    groups: list[str] = []
    while len(integer) > 3:
        groups.append(integer[-3:])
        integer = integer[:-3]
    groups.append(integer)
    grouped = "'".join(reversed(groups))
    return f"{sign}{grouped}{separator}{fraction}"


def format_value(value: Value | None, scientific: bool = False) -> str:
    if value is None:
        return ""
    if value.text is not None:
        return value.text
    if value.when is not None:
        if isinstance(value.when, datetime):
            return value.when.strftime("%Y-%m-%d %H:%M:%S %Z").strip()
        if isinstance(value.when, date):
            return value.when.isoformat()
    if value.duration is not None:
        seconds = Decimal(str(value.duration.total_seconds()))
        return f"{clean_decimal(seconds)} sec"
    if value.magnitude is None:
        return ""
    if scientific:
        base = f"{value.magnitude:.10E}".replace("E+", "e").replace("E", "e")
    else:
        base = group_thousands(clean_decimal(value.magnitude))
    if value.currency:
        return f"{base} {value.currency}"
    if value.unit:
        return f"{base} {value.unit}"
    return base
