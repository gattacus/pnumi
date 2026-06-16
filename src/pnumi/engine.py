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
COMPOUND_UNIT_SEGMENT_PATTERN = r"[A-Za-z°][A-Za-z0-9°]*"
THOUSANDS_SEPARATOR_RE = re.compile(r"(?<=\d)[ ,'](?=\d{3}(?:\D|$))")
PERCENT_VALUE_RE = re.compile(rf"^(?P<num>(?:0x[0-9a-fA-F]+|0o[0-7]+|0b[01]+|{DECIMAL_NUMBER_PATTERN}))\s*%$")
COMPOUND_VALUE_RE = re.compile(
    rf"^(?P<num>(?:0x[0-9a-fA-F]+|0o[0-7]+|0b[01]+|{DECIMAL_NUMBER_PATTERN}))\s*(?P<suffix>{COMPOUND_UNIT_SEGMENT_PATTERN}(?:\s*/\s*{COMPOUND_UNIT_SEGMENT_PATTERN})+)$"
)
NUMBER_UNIT_RE = re.compile(
    rf"(?P<prefix>[$€£])?\s*(?P<num>(?:0x[0-9a-fA-F]+|0o[0-7]+|0b[01]+|{DECIMAL_NUMBER_PATTERN}))\s*(?P<suffix>[A-Za-z°][A-Za-z0-9° ]*)?"
)
VALUE_TOKEN_RE = re.compile(
    rf"(?P<prefix>[$€£])?\s*(?P<num>(?:0x[0-9a-fA-F]+|0o[0-7]+|0b[01]+|{DECIMAL_NUMBER_PATTERN}))\s*(?P<suffix>%|[A-Za-z°][A-Za-z0-9°]*(?:\s+[A-Za-z°][A-Za-z0-9°]*)?(?:\s*/\s*[A-Za-z°][A-Za-z0-9°]*)*)?"
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
    typed = _try_typed_arithmetic(expression, context)
    if typed is not None:
        return typed, scientific
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


def _try_typed_arithmetic(expression: str, context: DocumentContext) -> Value | None:
    normalized, literals, has_typed_value = _prepare_typed_expression(expression, context)
    if not has_typed_value:
        return None
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError:
        return None
    return _eval_value_ast(tree.body, context, literals)


def _prepare_typed_expression(expression: str, context: DocumentContext) -> tuple[str, dict[str, Value], bool]:
    literals: dict[str, Value] = {}
    parts: list[str] = []
    cursor = 0
    previous_was_literal = False
    has_typed_value = _expression_mentions_typed_name(expression, context)
    for match in VALUE_TOKEN_RE.finditer(expression):
        token = match.group(0)
        if not token.strip():
            continue
        value = _parse_value(token, context)
        if value is None or not _has_kind(value):
            continue
        gap = expression[cursor : match.start()]
        if previous_was_literal and not gap.strip():
            gap = "+"
        placeholder = f"__value{len(literals)}"
        literals[placeholder] = value
        parts.append(gap)
        parts.append(placeholder)
        cursor = match.end()
        previous_was_literal = True
        has_typed_value = True
    parts.append(expression[cursor:])
    normalized = _normalize_numeric("".join(parts), context, replace_values=False)
    normalized, has_named_typed_value = _replace_value_names_with_literals(normalized, context, literals)
    has_typed_value = has_typed_value or has_named_typed_value
    return normalized, literals, has_typed_value


def _replace_value_names_with_literals(expression: str, context: DocumentContext, literals: dict[str, Value]) -> tuple[str, bool]:
    has_typed_value = False

    def replace(match: re.Match[str]) -> str:
        nonlocal has_typed_value
        name = match.group(0)
        if name in literals:
            return name
        if name.lower() == "prev":
            if not context.previous_results:
                return name
            value = context.previous_results[-1]
        else:
            value = context.variables.get(name)
            if value is None:
                return name
        if value.magnitude is None:
            return name
        placeholder = f"__value{len(literals)}"
        literals[placeholder] = value
        has_typed_value = has_typed_value or _has_kind(value)
        return placeholder

    return re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\b", replace, expression), has_typed_value


def _expression_mentions_typed_name(expression: str, context: DocumentContext) -> bool:
    for match in re.finditer(r"\b[A-Za-z_][A-Za-z0-9_]*\b", expression):
        name = match.group(0)
        if name.lower() == "prev":
            return bool(context.previous_results and _has_kind(context.previous_results[-1]))
        value = context.variables.get(name)
        if value is not None and _has_kind(value):
            return True
    return False


def _eval_value_ast(node: ast.AST, context: DocumentContext, literals: dict[str, Value]) -> Value:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return Value.number(Decimal(str(node.value)))
    if isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_BINOPS:
        left = _eval_value_ast(node.left, context, literals)
        right = _eval_value_ast(node.right, context, literals)
        return _eval_value_binop(left, right, node.op, context)
    if isinstance(node, ast.UnaryOp):
        value = _eval_value_ast(node.operand, context, literals)
        if isinstance(node.op, ast.USub):
            return _same_kind(value, -_magnitude(value))
        if isinstance(node.op, ast.UAdd):
            return value
    if isinstance(node, ast.Name):
        if node.id in literals:
            return literals[node.id]
        if node.id.lower() == "pi":
            return Value.number(Decimal(str(math.pi)))
        if node.id.lower() == "e":
            return Value.number(Decimal(str(math.e)))
        if node.id.lower() == "prev":
            if not context.previous_results:
                raise ValueError("No previous result")
            return context.previous_results[-1]
        value = context.variables.get(node.id)
        if value and value.magnitude is not None:
            return value
        raise ValueError(f"Unknown variable: {node.id}")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [_eval_value_ast(arg, context, literals) for arg in node.args]
        result = _call_function(node.func.id, [_magnitude(arg) for arg in args])
        if args and node.func.id.lower() in {"round", "ceil", "floor"} and _has_kind(args[0]):
            return _same_kind(args[0], result)
        return Value.number(result)
    raise ValueError("Unsupported expression")


def _eval_value_binop(left: Value, right: Value, op: ast.operator, context: DocumentContext) -> Value:
    if isinstance(op, ast.Add):
        return _add_values(left, right, context)
    if isinstance(op, ast.Sub):
        return _subtract_values(left, right, context)
    if isinstance(op, ast.Mult):
        return _multiply_values(left, right, context)
    if isinstance(op, ast.Div):
        return _divide_values(left, right, context)
    if isinstance(op, ast.Mod):
        return _mod_values(left, right, context)
    if isinstance(op, ast.Pow):
        return _pow_values(left, right)
    if _has_kind(left) or _has_kind(right):
        raise ValueError("Unsupported typed arithmetic")
    return Value.number(ALLOWED_BINOPS[type(op)](_magnitude(left), _magnitude(right)))


def _add_values(left: Value, right: Value, context: DocumentContext) -> Value:
    if _is_percent(right) and not _is_percent(left):
        return _same_kind(left, _magnitude(left) * (Decimal("1") + _percent_ratio(right)))
    if _is_percent(left) and not _is_percent(right):
        if _has_kind(right):
            raise ValueError("Cannot add a typed value to a percentage")
        return Value.number(_magnitude(left) + _magnitude(right), "percent")
    target = left if _has_kind(left) else right
    right_magnitude = _coerce_value_to_target(right, target, context)
    return _same_kind(target, _magnitude(left) + right_magnitude)


def _subtract_values(left: Value, right: Value, context: DocumentContext) -> Value:
    if _is_percent(right) and not _is_percent(left):
        return _same_kind(left, _magnitude(left) * (Decimal("1") - _percent_ratio(right)))
    if _is_percent(left) and not _is_percent(right):
        if _has_kind(right):
            raise ValueError("Cannot subtract a typed value from a percentage")
        return Value.number(_magnitude(left) - _magnitude(right), "percent")
    target = left if _has_kind(left) else right
    right_magnitude = _coerce_value_to_target(right, target, context)
    return _same_kind(target, _magnitude(left) - right_magnitude)


def _multiply_values(left: Value, right: Value, context: DocumentContext) -> Value:
    if _is_percent(left) and _is_percent(right):
        return Value.number(_magnitude(left) * _percent_ratio(right), "percent")
    if _is_percent(right):
        return _same_kind(left, _magnitude(left) * _percent_ratio(right))
    if _is_percent(left):
        return _same_kind(right, _magnitude(right) * _percent_ratio(left))
    if not _has_kind(left) and not _has_kind(right):
        return Value.number(_magnitude(left) * _magnitude(right))
    if not _has_kind(right):
        return _same_kind(left, _magnitude(left) * _magnitude(right))
    if not _has_kind(left):
        return _same_kind(right, _magnitude(left) * _magnitude(right))
    if left.currency and right.currency:
        raise ValueError("Cannot multiply currencies")
    return _combine_value_products(left, right, "*", context)


def _divide_values(left: Value, right: Value, context: DocumentContext) -> Value:
    if _is_percent(right) and not _is_percent(left):
        return _same_kind(left, _magnitude(left) / _percent_ratio(right))
    if _is_percent(left) and _is_percent(right):
        return Value.number(_magnitude(left) / _magnitude(right))
    if _is_percent(left):
        raise ValueError("Cannot divide a percentage by a value")
    if not _has_kind(left) and not _has_kind(right):
        return Value.number(_magnitude(left) / _magnitude(right))
    if not _has_kind(right):
        return _same_kind(left, _magnitude(left) / _magnitude(right))
    if not _has_kind(left):
        return _combine_value_products(left, right, "/", context)
    if left.currency and right.currency:
        right_magnitude = _coerce_value_to_target(right, left, context)
        return Value.number(_magnitude(left) / right_magnitude)
    if left.unit and right.unit and _compatible_units(left.unit, right.unit, context):
        right_magnitude = _coerce_value_to_target(right, left, context)
        return Value.number(_magnitude(left) / right_magnitude)
    return _combine_value_products(left, right, "/", context)


def _mod_values(left: Value, right: Value, context: DocumentContext) -> Value:
    target = left if _has_kind(left) else right
    right_magnitude = _coerce_value_to_target(right, target, context)
    return _same_kind(target, _magnitude(left) % right_magnitude)


def _pow_values(left: Value, right: Value) -> Value:
    exponent = _magnitude(right)
    magnitude = _magnitude(left) ** exponent
    if not _has_kind(left):
        return Value.number(magnitude)
    if _has_kind(right):
        raise ValueError("Exponent must be unitless")
    if exponent == 1:
        return _same_kind(left, magnitude)
    if exponent == 0:
        return Value.number(magnitude)
    if exponent == exponent.to_integral():
        return Value.number(magnitude, f"{_kind_label(left)}^{int(exponent)}")
    raise ValueError("Fractional powers of typed values are unsupported")


def _coerce_value_to_target(value: Value, target: Value, context: DocumentContext) -> Decimal:
    magnitude = _magnitude(value)
    if not _has_kind(value):
        return magnitude
    if target.currency:
        if value.currency is None:
            raise ValueError(f"Cannot combine {_kind_label(value)} with {target.currency}")
        if value.currency == target.currency:
            return magnitude
        rate = context.rate_provider.get_rate(value.currency, target.currency)
        return magnitude * rate
    if target.unit:
        if value.unit is None:
            raise ValueError(f"Cannot combine {_kind_label(value)} with {target.unit}")
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


def _compatible_units(left: str, right: str, context: DocumentContext) -> bool:
    if left == right:
        return True
    try:
        convert_magnitude(
            Decimal("1"),
            right,
            left,
            ppi=context.settings.get("ppi", Decimal("96")),
            em=context.settings.get("em", Decimal("16")),
        )
        return True
    except ValueError:
        return False


def _magnitude(value: Value) -> Decimal:
    return value.magnitude or Decimal("0")


def _is_percent(value: Value) -> bool:
    return value.unit == "percent"


def _percent_ratio(value: Value) -> Decimal:
    return _magnitude(value) / Decimal("100")


def _has_kind(value: Value) -> bool:
    return bool(value.unit or value.currency)


def _kind_label(value: Value) -> str:
    if value.currency:
        return value.currency
    if value.unit:
        return _compound_unit_label(value.unit)
    return ""


def _compound_unit_label(unit: str) -> str:
    return {"hour": "h", "minute": "min", "second": "s"}.get(unit, unit)


def _combine_value_products(left: Value, right: Value, operator_text: str, context: DocumentContext | None = None) -> Value:
    left_factors = _value_unit_factors(left, context)
    right_factors = _value_unit_factors(right, context)
    direction = 1 if operator_text == "*" else -1
    adjusted_right_magnitude, adjusted_right_factors = _align_factors_for_cancellation(
        _magnitude(right),
        left_factors,
        right_factors,
        direction,
        context,
    )
    magnitude = _magnitude(left) * adjusted_right_magnitude if operator_text == "*" else _magnitude(left) / adjusted_right_magnitude
    result_factors = dict(left_factors)
    for label, exponent in adjusted_right_factors.items():
        result_factors[label] = result_factors.get(label, 0) + (exponent * direction)
        if result_factors[label] == 0:
            del result_factors[label]
    return _value_from_unit_factors(magnitude, result_factors)


def _value_unit_factors(value: Value, context: DocumentContext | None = None) -> dict[str, int]:
    if value.currency:
        return {value.currency: 1}
    if value.unit:
        return _unit_label_factors(value.unit, context)
    return {}


def _unit_label_factors(label: str, context: DocumentContext | None = None) -> dict[str, int]:
    factors: dict[str, int] = {}
    operator_text = "*"
    for part in re.split(r"([*/])", label):
        part = part.strip()
        if not part:
            continue
        if part in {"*", "/"}:
            operator_text = part
            continue
        factor, exponent = _parse_unit_factor(part, context)
        signed_exponent = exponent if operator_text == "*" else -exponent
        factors[factor] = factors.get(factor, 0) + signed_exponent
        if factors[factor] == 0:
            del factors[factor]
    return factors


def _parse_unit_factor(part: str, context: DocumentContext | None = None) -> tuple[str, int]:
    name, separator, exponent_text = part.partition("^")
    exponent = int(exponent_text) if separator else 1
    currency = _currency_code(name)
    if currency:
        return currency, exponent
    ppi = context.settings.get("ppi", Decimal("96")) if context else Decimal("96")
    em = context.settings.get("em", Decimal("16")) if context else Decimal("16")
    unit = canonical_unit(name, ppi=ppi, em=em)
    if unit:
        return unit.canonical, exponent
    return name, exponent


def _align_factors_for_cancellation(
    magnitude: Decimal,
    existing_factors: dict[str, int],
    incoming_factors: dict[str, int],
    direction: int,
    context: DocumentContext | None,
) -> tuple[Decimal, dict[str, int]]:
    adjusted = dict(incoming_factors)
    adjusted_magnitude = magnitude
    for incoming_label, exponent in list(incoming_factors.items()):
        effective_exponent = exponent * direction
        if effective_exponent == 0:
            continue
        target_label = _find_cancelling_factor(incoming_label, effective_exponent, existing_factors, context)
        if target_label is None or target_label == incoming_label:
            continue
        conversion = _unit_conversion_factor(incoming_label, target_label, context)
        adjusted_magnitude *= conversion ** abs(exponent)
        adjusted[incoming_label] -= exponent
        if adjusted[incoming_label] == 0:
            del adjusted[incoming_label]
        adjusted[target_label] = adjusted.get(target_label, 0) + exponent
    return adjusted_magnitude, adjusted


def _find_cancelling_factor(
    incoming_label: str,
    incoming_exponent: int,
    existing_factors: dict[str, int],
    context: DocumentContext | None,
) -> str | None:
    for existing_label, existing_exponent in existing_factors.items():
        if existing_exponent * incoming_exponent >= 0:
            continue
        if existing_label == incoming_label:
            return existing_label
        if _unit_conversion_factor(incoming_label, existing_label, context) is not None:
            return existing_label
    return None


def _unit_conversion_factor(from_unit: str, to_unit: str, context: DocumentContext | None) -> Decimal | None:
    try:
        return convert_magnitude(
            Decimal("1"),
            from_unit,
            to_unit,
            ppi=context.settings.get("ppi", Decimal("96")) if context else Decimal("96"),
            em=context.settings.get("em", Decimal("16")) if context else Decimal("16"),
        )
    except ValueError:
        return None


def _value_from_unit_factors(magnitude: Decimal, factors: dict[str, int]) -> Value:
    if not factors:
        return Value.number(magnitude)
    if len(factors) == 1:
        [(label, exponent)] = factors.items()
        if exponent == 1 and _currency_code(label):
            return Value.money(magnitude, label)
    return Value.number(magnitude, _format_unit_factors(factors))


def _format_unit_factors(factors: dict[str, int]) -> str:
    positive = [(label, exponent) for label, exponent in factors.items() if exponent > 0]
    negative = [(label, -exponent) for label, exponent in factors.items() if exponent < 0]
    numerator = "*".join(_format_unit_factor(label, exponent) for label, exponent in positive) or "1"
    denominator = "*".join(_format_unit_factor(label, exponent) for label, exponent in negative)
    return f"{numerator}/{denominator}" if denominator else numerator


def _format_unit_factor(label: str, exponent: int) -> str:
    display = _compound_unit_label(label)
    return display if exponent == 1 else f"{display}^{exponent}"


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
    percent_match = PERCENT_VALUE_RE.fullmatch(expression)
    if percent_match:
        return Value.number(_parse_decimal(percent_match.group("num")), "percent")
    compound_match = COMPOUND_VALUE_RE.fullmatch(expression)
    if compound_match:
        number = _parse_decimal(compound_match.group("num"))
        suffix = compound_match.group("suffix")
        return Value.number(number, _format_unit_factors(_unit_label_factors(suffix, context)))
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


def _normalize_numeric(expression: str, context: DocumentContext, replace_values: bool = True) -> str:
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
    if replace_values:
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
