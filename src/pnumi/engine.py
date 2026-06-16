from __future__ import annotations

import ast
import math
import operator
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, DivisionByZero, InvalidOperation, getcontext
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

from .formatting import format_value
from .models import DocumentContext, DocumentResult, LineResult, Value
from .rates import default_rate_provider
from .units import SCALE_SUFFIXES, canonical_unit, convert_magnitude

getcontext().prec = 28

CURRENCY_ALIASES = {
    "$": "USD",
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "cad": "CAD",
    "chf": "CHF",
    "btc": "BTC",
    "bitcoin": "BTC",
    "eth": "ETH",
    "ethereum": "ETH",
}

TIMEZONES = {
    "utc": "UTC",
    "gmt": "UTC",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "new york": "America/New_York",
    "berlin": "Europe/Berlin",
    "madrid": "Europe/Madrid",
    "hkt": "Asia/Hong_Kong",
    "hong kong": "Asia/Hong_Kong",
    "london": "Europe/London",
    "zurich": "Europe/Zurich",
}

CONVERSION_RE = re.compile(r"\s+(?:in|into|as|to)\s+", re.IGNORECASE)
ASSIGN_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")
DECIMAL_NUMBER_PATTERN = r"\d+(?:[ ,']\d{3})*(?:\.\d+)?|\d*\.\d+"
THOUSANDS_SEPARATOR_RE = re.compile(r"(?<=\d)[ ,'](?=\d{3}(?:\D|$))")
NUMBER_UNIT_RE = re.compile(
    rf"(?P<prefix>[$€£])?\s*(?P<num>(?:0x[0-9a-fA-F]+|0o[0-7]+|0b[01]+|{DECIMAL_NUMBER_PATTERN}))\s*(?P<suffix>[A-Za-z°][A-Za-z0-9° ]*)?"
)
VALUE_TOKEN_RE = re.compile(
    rf"(?P<prefix>[$€£])?\s*(?P<num>(?:0x[0-9a-fA-F]+|0o[0-7]+|0b[01]+|{DECIMAL_NUMBER_PATTERN}))\s*(?P<suffix>[A-Za-z°][A-Za-z0-9°]*(?:\s+[A-Za-z°][A-Za-z0-9°]*)?)?"
)


def evaluate_document(text: str, options: dict | None = None) -> DocumentResult:
    context = DocumentContext(rate_provider=(options or {}).get("rate_provider") if options else None)
    if context.rate_provider is None:
        context.rate_provider = default_rate_provider()
    results: list[LineResult] = []
    for line in text.splitlines():
        result = evaluate_line(line, context)
        results.append(result)
    return DocumentResult(results)


def evaluate_line(text: str, context: DocumentContext | None = None) -> LineResult:
    context = context or DocumentContext(rate_provider=default_rate_provider())
    if context.rate_provider is None:
        context.rate_provider = default_rate_provider()
    original = text
    stripped = text.strip()
    result = LineResult(input_text=original, span=(0, len(original)))
    if not stripped:
        context.reset_section()
        return result
    if stripped.startswith("#") or stripped.startswith("//"):
        return result
    expression = _strip_formatting(text)
    if not expression:
        return result
    assignment = ASSIGN_RE.match(expression)
    target_name: str | None = None
    if assignment:
        target_name = assignment.group(1)
        expression = assignment.group(2)
    try:
        value, scientific = _evaluate_expression(expression, context)
        if target_name:
            context.variables[target_name] = value
            if target_name in {"em", "ppi"} and value.magnitude is not None:
                context.settings[target_name] = value.magnitude
        result.value = value
        result.display = format_value(value, scientific=scientific)
        context.remember(value)
        return result
    except Exception as exc:
        result.diagnostics.append(str(exc))
        result.display = ""
        return result


def _strip_formatting(text: str) -> str:
    text = re.sub(r'"[^"]*"', "", text)
    if "//" in text:
        text = text.split("//", 1)[0]
    if ":" in text:
        left, right = text.split(":", 1)
        if re.fullmatch(r"\s*[A-Za-z][A-Za-z0-9 _-]*\s*", left):
            text = right
    return text.strip()


def _evaluate_expression(expression: str, context: DocumentContext) -> tuple[Value, bool]:
    expression = expression.strip()
    scientific = bool(re.search(r"\b(?:sci|scientific)\b", expression, re.IGNORECASE))
    expression = re.sub(r"\b(?:sci|scientific)\b", "", expression, flags=re.IGNORECASE).strip()
    lower = expression.lower()
    if lower in {"sum", "total"}:
        return _aggregate(context.section_results, average=False), scientific
    if lower in {"average", "avg"}:
        return _aggregate(context.section_results, average=True), scientific
    if lower == "prev":
        if not context.previous_results:
            raise ValueError("No previous result")
        return context.previous_results[-1], scientific
    time_value = _try_time_expression(expression)
    if time_value is not None:
        return time_value, scientific
    date_math = _try_date_math(expression, context)
    if date_math is not None:
        return date_math, scientific
    percentage = _try_percentage(expression, context)
    if percentage is not None:
        return percentage, scientific
    wrapped = _try_wrapped_function(expression, context)
    if wrapped is not None:
        return wrapped, scientific
    prefixed = _try_prefix_function(expression, context)
    if prefixed is not None:
        return prefixed, scientific
    if CONVERSION_RE.search(expression):
        left, right = CONVERSION_RE.split(expression, maxsplit=1)
        source, _ = _evaluate_expression(left, context)
        return _convert(source, right.strip(), context), scientific
    parsed = _parse_value(expression, context)
    if parsed is not None:
        return parsed, scientific
    valued = _try_valued_arithmetic(expression, context)
    if valued is not None:
        return valued, scientific
    return Value.number(_eval_numeric(expression, context)), scientific


def _aggregate(values: list[Value], average: bool) -> Value:
    usable = [v for v in values if v.magnitude is not None]
    if not usable:
        return Value.number(0)
    first = usable[0]
    total = first.magnitude or Decimal("0")
    same_currency = first.currency
    same_unit = first.unit
    for value in usable[1:]:
        if value.currency != same_currency:
            same_currency = None
        if value.unit != same_unit:
            same_unit = None
        total += value.magnitude or Decimal("0")
    if average:
        total /= Decimal(len(usable))
    return Value(magnitude=total, unit=same_unit, currency=same_currency)


def _convert(value: Value, target: str, context: DocumentContext) -> Value:
    target = target.strip()
    if value.magnitude is not None and target.lower() in {"hex", "hexadecimal"}:
        return Value(text=hex(int(value.magnitude)))
    if value.magnitude is not None and target.lower() in {"bin", "binary"}:
        return Value(text=bin(int(value.magnitude)))
    if value.magnitude is not None and target.lower() in {"oct", "octal"}:
        return Value(text=oct(int(value.magnitude)))
    currency = _currency_code(target)
    if value.is_money and currency:
        rate = context.rate_provider.get_rate(value.currency or "", currency)
        return Value.money((value.magnitude or Decimal("0")) * rate, currency)
    if value.magnitude is not None and value.unit:
        converted = convert_magnitude(
            value.magnitude,
            value.unit,
            target,
            ppi=context.settings.get("ppi", Decimal("96")),
            em=context.settings.get("em", Decimal("16")),
        )
        target_unit = canonical_unit(target, ppi=context.settings.get("ppi", Decimal("96")), em=context.settings.get("em", Decimal("16")))
        return Value.number(converted, target_unit.canonical if target_unit else target)
    if value.magnitude is not None and currency:
        return Value.money(value.magnitude, currency)
    if value.magnitude is not None:
        target_unit = canonical_unit(target, ppi=context.settings.get("ppi", Decimal("96")), em=context.settings.get("em", Decimal("16")))
        if target_unit:
            return Value.number(value.magnitude, target_unit.canonical)
    raise ValueError(f"Cannot convert to {target}")


def _try_wrapped_function(expression: str, context: DocumentContext) -> Value | None:
    match = re.match(r"^(?P<name>[A-Za-z]+)\((?P<body>.+)\)$", expression.strip())
    if not match:
        match = re.match(r"^(?P<name>root)\s+(?P<first>.+?)\s+\((?P<body>.+)\)$", expression.strip(), re.IGNORECASE)
        if not match:
            return None
        first, _ = _evaluate_expression(match.group("first"), context)
        body, _ = _evaluate_expression(match.group("body"), context)
        result = _call_function("root", [first.magnitude or Decimal("0"), body.magnitude or Decimal("0")])
        return _same_kind(body, result)
    if match.group("name").lower() == "fromunix":
        seconds = _eval_numeric(match.group("body"), context)
        return Value.date_time(datetime.fromtimestamp(float(seconds), tz=timezone.utc))
    body, _ = _evaluate_expression(match.group("body"), context)
    result = _call_function(match.group("name"), [body.magnitude or Decimal("0")])
    return _same_kind(body, result) if body.unit or body.currency else Value.number(result)


def _try_prefix_function(expression: str, context: DocumentContext) -> Value | None:
    match = re.match(r"^(?P<name>sqrt|cbrt|abs|ln|log|fact|round|ceil|floor|sin|cos|tan|arcsin|arccos|arctan|sinh|cosh|tanh|fromunix)\s+(.+)$", expression.strip(), re.IGNORECASE)
    if not match:
        return None
    name = match.group("name").lower()
    body_text = expression.strip()[len(match.group("name")) :].strip()
    if name == "fromunix":
        seconds = _eval_numeric(body_text, context)
        return Value.date_time(datetime.fromtimestamp(float(seconds), tz=timezone.utc))
    body, _ = _evaluate_expression(body_text, context)
    magnitude = body.magnitude or Decimal("0")
    if name in {"sin", "cos", "tan"} and body.unit == "deg":
        magnitude = convert_magnitude(magnitude, "deg", "rad")
    result = _call_function(name, [magnitude])
    if name in {"round", "ceil", "floor"} and (body.unit or body.currency):
        return _same_kind(body, result)
    return Value.number(result)


def _try_valued_arithmetic(expression: str, context: DocumentContext) -> Value | None:
    tokens = list(_iter_value_tokens(expression, context))
    if not tokens:
        return None
    typed = [item for item in tokens if item[2].currency or item[2].unit]
    if not typed:
        return None
    target = typed[0][2]
    normalized_parts: list[str] = []
    cursor = 0
    previous_was_value = False
    for start, end, value in tokens:
        gap = expression[cursor:start]
        if previous_was_value and not gap.strip():
            gap = "+"
        normalized_parts.append(_normalize_numeric(gap, context))
        normalized_parts.append(str(_coerce_for_arithmetic(value, target, context)))
        cursor = end
        previous_was_value = True
    normalized_parts.append(_normalize_numeric(expression[cursor:], context))
    magnitude = _eval_numeric("".join(normalized_parts), context)
    return Value(magnitude=magnitude, unit=target.unit, currency=target.currency)


def _iter_value_tokens(expression: str, context: DocumentContext):
    for match in VALUE_TOKEN_RE.finditer(expression):
        token = match.group(0)
        if not token.strip():
            continue
        value = _parse_value(token, context)
        if value is not None:
            yield match.start(), match.end(), value


def _coerce_for_arithmetic(value: Value, target: Value, context: DocumentContext) -> Decimal:
    magnitude = value.magnitude or Decimal("0")
    if target.currency:
        if value.currency is None:
            return magnitude
        if value.currency == target.currency:
            return magnitude
        rate = context.rate_provider.get_rate(value.currency, target.currency)
        return magnitude * rate
    if target.unit:
        if value.unit is None:
            return magnitude
        if value.unit == target.unit:
            return magnitude
        return convert_magnitude(
            magnitude,
            value.unit,
            target.unit,
            ppi=context.settings.get("ppi", Decimal("96")),
            em=context.settings.get("em", Decimal("16")),
        )
    return magnitude


def _try_percentage(expression: str, context: DocumentContext) -> Value | None:
    match = re.match(r"^(.+?)\s+as\s+a\s+%\s+of\s+(.+)$", expression, re.IGNORECASE)
    if match:
        a, _ = _evaluate_expression(match.group(1), context)
        b, _ = _evaluate_expression(match.group(2), context)
        return Value.number(((a.magnitude or Decimal("0")) / (b.magnitude or Decimal("0"))) * Decimal("100"), "percent")
    match = re.match(r"^(.+?)\s+as\s+a\s+%\s+on\s+(.+)$", expression, re.IGNORECASE)
    if match:
        a, _ = _evaluate_expression(match.group(1), context)
        b, _ = _evaluate_expression(match.group(2), context)
        return Value.number((((a.magnitude or Decimal("0")) / (b.magnitude or Decimal("0"))) - Decimal("1")) * Decimal("100"), "percent")
    match = re.match(r"^(.+?)\s+as\s+a\s+%\s+off\s+(.+)$", expression, re.IGNORECASE)
    if match:
        a, _ = _evaluate_expression(match.group(1), context)
        b, _ = _evaluate_expression(match.group(2), context)
        return Value.number((Decimal("1") - ((a.magnitude or Decimal("0")) / (b.magnitude or Decimal("0")))) * Decimal("100"), "percent")
    match = re.match(r"^(.+?)%\s+of\s+what\s+is\s+(.+)$", expression, re.IGNORECASE)
    if match:
        percent = _eval_numeric(match.group(1), context) / Decimal("100")
        value, _ = _evaluate_expression(match.group(2), context)
        return _same_kind(value, (value.magnitude or Decimal("0")) / percent)
    match = re.match(r"^(.+?)%\s+on\s+what\s+is\s+(.+)$", expression, re.IGNORECASE)
    if match:
        percent = Decimal("1") + (_eval_numeric(match.group(1), context) / Decimal("100"))
        value, _ = _evaluate_expression(match.group(2), context)
        return _same_kind(value, (value.magnitude or Decimal("0")) / percent)
    match = re.match(r"^(.+?)%\s+off\s+what\s+is\s+(.+)$", expression, re.IGNORECASE)
    if match:
        percent = Decimal("1") - (_eval_numeric(match.group(1), context) / Decimal("100"))
        value, _ = _evaluate_expression(match.group(2), context)
        return _same_kind(value, (value.magnitude or Decimal("0")) / percent)
    match = re.match(r"^(.+?)%\s+of\s+(.+)$", expression, re.IGNORECASE)
    if match:
        percent = _eval_numeric(match.group(1), context) / Decimal("100")
        value, _ = _evaluate_expression(match.group(2), context)
        return _same_kind(value, (value.magnitude or Decimal("0")) * percent)
    match = re.match(r"^(.+?)%\s+on\s+(.+)$", expression, re.IGNORECASE)
    if match:
        percent = _eval_numeric(match.group(1), context) / Decimal("100")
        value, _ = _evaluate_expression(match.group(2), context)
        return _same_kind(value, (value.magnitude or Decimal("0")) * (Decimal("1") + percent))
    match = re.match(r"^(.+?)%\s+off\s+(.+)$", expression, re.IGNORECASE)
    if match:
        percent = _eval_numeric(match.group(1), context) / Decimal("100")
        value, _ = _evaluate_expression(match.group(2), context)
        return _same_kind(value, (value.magnitude or Decimal("0")) * (Decimal("1") - percent))
    return None


def _same_kind(value: Value, magnitude: Decimal) -> Value:
    return Value(magnitude=magnitude, unit=value.unit, currency=value.currency)


def _parse_value(expression: str, context: DocumentContext) -> Value | None:
    expression = expression.strip()
    if expression.lower() == "today":
        return Value.date_time(date.today())
    if expression.lower() == "now":
        return Value.date_time(datetime.now().replace(microsecond=0))
    match = NUMBER_UNIT_RE.fullmatch(expression)
    if not match:
        return None
    number = _parse_decimal(match.group("num"))
    suffix = (match.group("suffix") or "").strip()
    prefix = match.group("prefix")
    if prefix:
        return Value.money(number, _currency_code(suffix) or _currency_code(prefix) or "USD")
    if suffix in SCALE_SUFFIXES:
        return Value.number(number * SCALE_SUFFIXES[suffix])
    currency = _currency_code(suffix)
    if currency:
        return Value.money(number, currency)
    if suffix.endswith("%"):
        return Value.number(number, "percent")
    unit = canonical_unit(suffix, ppi=context.settings.get("ppi", Decimal("96")), em=context.settings.get("em", Decimal("16"))) if suffix else None
    if unit:
        return Value.number(number, unit.canonical)
    if suffix:
        scale = SCALE_SUFFIXES.get(suffix)
        if scale:
            return Value.number(number * scale)
        return None
    return Value.number(number)


def _parse_decimal(text: str) -> Decimal:
    text = _strip_thousands_separators(text.strip())
    if text.lower().startswith("0x"):
        return Decimal(int(text, 16))
    if text.lower().startswith("0o"):
        return Decimal(int(text, 8))
    if text.lower().startswith("0b"):
        return Decimal(int(text, 2))
    return Decimal(text)


def _strip_thousands_separators(text: str) -> str:
    return THOUSANDS_SEPARATOR_RE.sub("", text)


def _currency_code(text: str | None) -> str | None:
    if not text:
        return None
    clean = text.strip()
    if clean.upper() in {"USD", "EUR", "CAD", "GBP", "CHF", "JPY", "AUD", "BTC", "ETH", "SOL", "DOGE"}:
        return clean.upper()
    return CURRENCY_ALIASES.get(clean.lower())


def _try_time_expression(expression: str) -> Value | None:
    lower = expression.lower().strip()
    if lower in {"time", "now"}:
        return Value.date_time(datetime.now().replace(microsecond=0))
    match = re.match(r"^(?P<zone>.+?)\s+(?:time|now)$", lower)
    if match and match.group("zone") in TIMEZONES:
        return Value.date_time(datetime.now(ZoneInfo(TIMEZONES[match.group("zone")])).replace(microsecond=0))
    match = re.match(r"^(?:time|now)\s+in\s+(?P<zone>.+)$", lower)
    if match and match.group("zone") in TIMEZONES:
        return Value.date_time(datetime.now(ZoneInfo(TIMEZONES[match.group("zone")])).replace(microsecond=0))
    match = re.match(r"^(?P<date>.+?)\s+(?:in|to)\s+(?P<zone>[A-Za-z ]+)$", expression, re.IGNORECASE)
    if match and match.group("zone").lower() in TIMEZONES:
        try:
            parsed = date_parser.parse(match.group("date"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        return Value.date_time(parsed.astimezone(ZoneInfo(TIMEZONES[match.group("zone").lower()])).replace(microsecond=0))
    return None


def _try_date_math(expression: str, context: DocumentContext) -> Value | None:
    match = re.match(r"^(today|now)\s*([+-])\s*(.+)$", expression.strip(), re.IGNORECASE)
    if not match:
        return None
    base = date.today() if match.group(1).lower() == "today" else datetime.now().replace(microsecond=0)
    delta_value, _ = _evaluate_expression(match.group(3), context)
    if delta_value.magnitude is not None and delta_value.unit:
        seconds = convert_magnitude(
            delta_value.magnitude,
            delta_value.unit,
            "second",
            ppi=context.settings.get("ppi", Decimal("96")),
            em=context.settings.get("em", Decimal("16")),
        )
        delta = timedelta(seconds=float(seconds))
    elif delta_value.duration is not None:
        delta = delta_value.duration
    else:
        return None
    if match.group(2) == "-":
        delta = -delta
    return Value.date_time(base + delta)


def _eval_numeric(expression: str, context: DocumentContext) -> Decimal:
    normalized = _normalize_numeric(expression, context)
    try:
        tree = ast.parse(normalized, mode="eval")
        return _eval_ast(tree.body, context)
    except (SyntaxError, InvalidOperation, DivisionByZero) as exc:
        raise ValueError(f"Invalid expression: {expression}") from exc


def _normalize_numeric(expression: str, context: DocumentContext) -> str:
    text = expression
    text = text.replace("×", "*").replace("÷", "/").replace("−", "-")
    text = re.sub(r"\bmultiplied\s+by\b", "*", text, flags=re.IGNORECASE)
    replacements = {
        r"\bplus\b": "+",
        r"\band\b": "+",
        r"\bwith\b": "+",
        r"\bminus\b": "-",
        r"\bsubtract\b": "-",
        r"\bwithout\b": "-",
        r"\btimes\b": "*",
        r"\bmul\b": "*",
        r"\bdivide\s+by\b": "/",
        r"\bdivide\b": "/",
        r"\bxor\b": "^",
        r"\bmod\b": "%",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = text.replace("^", "**")
    text = re.sub(r"(\d)\s*\(", r"\1*(", text)
    text = re.sub(r"\)\s*(\d)", r")*\1", text)
    text = re.sub(r"\bpi\b", "pi", text, flags=re.IGNORECASE)
    text = re.sub(r"\be\b", "e", text, flags=re.IGNORECASE)
    text = _strip_thousands_separators(text)
    for name, value in context.variables.items():
        if value.magnitude is not None:
            text = re.sub(rf"\b{re.escape(name)}\b", f"({value.magnitude})", text)
    if context.previous_results:
        prev = context.previous_results[-1]
        if prev.magnitude is not None:
            text = re.sub(r"\bprev\b", f"({prev.magnitude})", text, flags=re.IGNORECASE)
    return text


ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.BitAnd: lambda a, b: Decimal(int(a) & int(b)),
    ast.BitOr: lambda a, b: Decimal(int(a) | int(b)),
    ast.BitXor: lambda a, b: Decimal(int(a) ^ int(b)),
    ast.LShift: lambda a, b: Decimal(int(a) << int(b)),
    ast.RShift: lambda a, b: Decimal(int(a) >> int(b)),
}


def _eval_ast(node: ast.AST, context: DocumentContext) -> Decimal:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return Decimal(str(node.value))
    if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINOPS:
        return ALLOWED_BINOPS[type(node.op)](_eval_ast(node.left, context), _eval_ast(node.right, context))
    if isinstance(node, ast.UnaryOp):
        value = _eval_ast(node.operand, context)
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return value
    if isinstance(node, ast.Name):
        if node.id.lower() == "pi":
            return Decimal(str(math.pi))
        if node.id.lower() == "e":
            return Decimal(str(math.e))
        value = context.variables.get(node.id)
        if value and value.magnitude is not None:
            return value.magnitude
        raise ValueError(f"Unknown variable: {node.id}")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [_eval_ast(arg, context) for arg in node.args]
        return _call_function(node.func.id, args)
    raise ValueError("Unsupported expression")


def _call_function(name: str, args: list[Decimal]) -> Decimal:
    name = name.lower()
    one = args[0] if args else Decimal("0")
    if name == "sqrt":
        return Decimal(str(math.sqrt(float(one))))
    if name == "cbrt":
        return Decimal(str(math.copysign(abs(float(one)) ** (1 / 3), float(one))))
    if name == "abs":
        return abs(one)
    if name == "ln":
        return Decimal(str(math.log(float(one))))
    if name == "log":
        if len(args) == 2:
            return Decimal(str(math.log(float(args[1]), float(args[0]))))
        return Decimal(str(math.log10(float(one))))
    if name == "fact":
        return Decimal(math.factorial(int(one)))
    if name == "round":
        return one.quantize(Decimal(1))
    if name == "ceil":
        return Decimal(math.ceil(float(one)))
    if name == "floor":
        return Decimal(math.floor(float(one)))
    if name in {"sin", "cos", "tan", "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh"}:
        func = getattr(math, {"arcsin": "asin", "arccos": "acos", "arctan": "atan"}.get(name, name))
        return Decimal(str(func(float(one))))
    if name == "root" and len(args) == 2:
        return Decimal(str(float(args[1]) ** (1 / float(args[0]))))
    if name == "fromunix":
        return Decimal(int(one))
    raise ValueError(f"Unknown function: {name}")
