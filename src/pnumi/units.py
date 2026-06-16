from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class UnitDef:
    canonical: str
    dimension: str
    ratio: Decimal
    offset: Decimal = Decimal("0")


def d(value: str) -> Decimal:
    return Decimal(value)


UNIT_DEFS: dict[str, UnitDef] = {}
ALIASES: dict[str, str] = {}


def add_unit(canonical: str, dimension: str, ratio: str, aliases: list[str], offset: str = "0") -> None:
    UNIT_DEFS[canonical] = UnitDef(canonical, dimension, d(ratio), d(offset))
    for alias in aliases + [canonical]:
        ALIASES[alias.lower()] = canonical


def add_ratio_units() -> None:
    add_unit("m", "length", "1", ["meter", "meters", "metre", "metres"])
    add_unit("mm", "length", "0.001", ["millimeter", "millimeters", "millimetre", "millimetres"])
    add_unit("cm", "length", "0.01", ["centimeter", "centimeters", "centimetre", "centimetres"])
    add_unit("km", "length", "1000", ["kilometer", "kilometers", "kilometre", "kilometres"])
    add_unit("mil", "length", "0.0000254", ["mils"])
    add_unit("pt", "length", "0.00035277777777777777778", ["point", "points"])
    add_unit("line", "length", "0.0021166666666666666667", ["lines"])
    add_unit("inch", "length", "0.0254", ["inch", "inches"])
    add_unit("hand", "length", "0.1016", ["hands"])
    add_unit("ft", "length", "0.3048", ["foot", "feet"])
    add_unit("yd", "length", "0.9144", ["yard", "yards"])
    add_unit("rod", "length", "5.0292", ["rods"])
    add_unit("chain", "length", "20.1168", ["chains"])
    add_unit("furlong", "length", "201.168", ["furlongs"])
    add_unit("mile", "length", "1609.344", ["miles"])
    add_unit("cable", "length", "185.2", ["cables"])
    add_unit("nmi", "length", "1852", ["nautical mile", "nautical miles"])
    add_unit("league", "length", "4828.032", ["leagues"])

    add_unit("m2", "area", "1", ["sqm", "square meter", "square meters", "square metre", "square metres"])
    add_unit("hectare", "area", "10000", ["hectares", "ha"])
    add_unit("are", "area", "100", ["ares"])
    add_unit("acre", "area", "4046.8564224", ["acres"])

    add_unit("m3", "volume", "1", ["cbm", "cubic meter", "cubic meters", "cubic metre", "cubic metres"])
    add_unit("l", "volume", "0.001", ["liter", "liters", "litre", "litres"])
    add_unit("pint", "volume", "0.000473176473", ["pints"])
    add_unit("quart", "volume", "0.000946352946", ["quarts"])
    add_unit("gallon", "volume", "0.003785411784", ["gallons"])
    add_unit("tsp", "volume", "0.00000492892159375", ["tea spoon", "tea spoons", "teaspoon", "teaspoons"])
    add_unit("tbsp", "volume", "0.00001478676478125", ["table spoon", "table spoons", "tablespoon", "tablespoons"])
    add_unit("cup", "volume", "0.0002365882365", ["cups"])

    add_unit("g", "weight", "1", ["gram", "grams"])
    add_unit("kg", "weight", "1000", ["kilogram", "kilograms"])
    add_unit("tonne", "weight", "1000000", ["tonnes"])
    add_unit("carat", "weight", "0.2", ["carats"])
    add_unit("centner", "weight", "100000", ["centners"])
    add_unit("lb", "weight", "453.59237", ["pound", "pounds"])
    add_unit("stone", "weight", "6350.29318", ["stones"])
    add_unit("oz", "weight", "28.349523125", ["ounce", "ounces"])

    add_unit("rad", "angle", "1", ["radian", "radians"])
    add_unit("deg", "angle", "0.017453292519943295769", ["degree", "degrees", "°"])

    add_unit("bit", "data", "1", ["bits", "b"])
    add_unit("byte", "data", "8", ["bytes", "B"])
    add_unit("kb", "data", "1000", ["kilobit", "kilobits"])
    add_unit("kB", "data", "8000", ["kilobyte", "kilobytes", "KB"])
    add_unit("Kib", "data", "1024", ["kibibit", "kibibits"])
    add_unit("KiB", "data", "8192", ["kibibyte", "kibibytes"])
    add_unit("MB", "data", "8000000", ["megabyte", "megabytes"])
    add_unit("GB", "data", "8000000000", ["gigabyte", "gigabytes"])

    add_unit("second", "duration", "1", ["sec", "secs", "s", "seconds"])
    add_unit("minute", "duration", "60", ["min", "mins", "minutes"])
    add_unit("hour", "duration", "3600", ["h", "hr", "hrs", "hours"])
    add_unit("day", "duration", "86400", ["days"])
    add_unit("week", "duration", "604800", ["weeks"])
    add_unit("month", "duration", "2628000", ["months"])
    add_unit("year", "duration", "31536000", ["years"])

    add_unit("px", "css", "1", ["pixel", "pixels"])
    add_unit("em", "css", "16", ["ems"])


def add_temperature_units() -> None:
    add_unit("K", "temperature", "1", ["kelvin", "kelvins"])
    add_unit("C", "temperature", "1", ["celsius", "°c"], "273.15")
    add_unit("F", "temperature", "0.55555555555555555556", ["fahrenheit", "°f"], "255.37222222222222222222")


add_ratio_units()
add_temperature_units()


SCALE_SUFFIXES = {
    "k": Decimal("1000"),
    "thousand": Decimal("1000"),
    "M": Decimal("1000000"),
    "million": Decimal("1000000"),
    "billion": Decimal("1000000000"),
}

SI_PREFIXES = {
    "pico": Decimal("1e-12"),
    "nano": Decimal("1e-9"),
    "micro": Decimal("1e-6"),
    "milli": Decimal("1e-3"),
    "centi": Decimal("1e-2"),
    "kilo": Decimal("1e3"),
    "mega": Decimal("1e6"),
    "giga": Decimal("1e9"),
}


def canonical_unit(name: str, ppi: Decimal = Decimal("96"), em: Decimal = Decimal("16")) -> UnitDef | None:
    raw = " ".join(name.strip().split())
    lowered = raw.lower()
    if lowered in ALIASES:
        unit = UNIT_DEFS[ALIASES[lowered]]
        if unit.canonical == "px":
            return UnitDef("px", "length", Decimal("0.0254") / ppi)
        if unit.canonical == "em":
            return UnitDef("em", "length", (Decimal("0.0254") / ppi) * em)
        return unit
    for prefix, multiplier in SI_PREFIXES.items():
        if lowered.startswith(prefix):
            base_name = lowered[len(prefix) :]
            base = canonical_unit(base_name, ppi=ppi, em=em)
            if base and base.dimension in {"length", "weight", "data"}:
                return UnitDef(raw, base.dimension, base.ratio * multiplier)
    return None


def convert_magnitude(value: Decimal, from_unit: str, to_unit: str, ppi: Decimal = Decimal("96"), em: Decimal = Decimal("16")) -> Decimal:
    source = canonical_unit(from_unit, ppi=ppi, em=em)
    target = canonical_unit(to_unit, ppi=ppi, em=em)
    if source is None:
        raise ValueError(f"Unknown unit: {from_unit}")
    if target is None:
        raise ValueError(f"Unknown unit: {to_unit}")
    if source.dimension != target.dimension:
        raise ValueError(f"Cannot convert {from_unit} to {to_unit}")
    base = (value * source.ratio) + source.offset
    return (base - target.offset) / target.ratio
