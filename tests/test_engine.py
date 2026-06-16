from __future__ import annotations

from decimal import Decimal

from pnumi.engine import evaluate_document, evaluate_line
from pnumi.models import DocumentContext
from pnumi.rates import StaticRateProvider


def context() -> DocumentContext:
    return DocumentContext(rate_provider=StaticRateProvider({("USD", "EUR"): Decimal("0.9"), ("USD", "CAD"): Decimal("1.25")}))


def test_arithmetic_and_word_operators() -> None:
    ctx = context()
    assert evaluate_line("8 times 9", ctx).display == "72"
    assert evaluate_line("6 (3)", ctx).display == "18"
    assert evaluate_line("2 plus 3 multiplied by 4", ctx).display == "14"


def test_number_bases_and_scientific_format() -> None:
    ctx = context()
    assert evaluate_line("0b110111011", ctx).display == "443"
    assert evaluate_line("0o1435343 in hex", ctx).display == "0x63ae3"
    assert "e" in evaluate_line("5 300 scientific", ctx).display


def test_single_quote_thousands_separator() -> None:
    ctx = context()
    assert evaluate_line("1'000 + 2", ctx).display == "1'002"
    assert evaluate_line("$1'000", ctx).display == "1'000 USD"
    assert evaluate_line("1'200 meter in cm", ctx).display == "120'000 cm"
    assert evaluate_line("-12'345.67", ctx).display == "-12'345.67"


def test_variables_prev_sum_and_average() -> None:
    ctx = context()
    assert evaluate_line("v = $20", ctx).display == "20 USD"
    assert evaluate_line("v + 10", ctx).display == "30"
    assert evaluate_line("Cost: $20", ctx).display == "20 USD"
    assert evaluate_line("Discounted: prev - 5", ctx).display == "15"
    assert evaluate_line("sum", ctx).display == "85"
    assert evaluate_line("", ctx).display == ""
    evaluate_line("$10", ctx)
    evaluate_line("$20", ctx)
    assert evaluate_line("avg", ctx).display == "15 USD"


def test_comments_labels_and_headers() -> None:
    ctx = context()
    assert evaluate_line("# Header", ctx).display == ""
    assert evaluate_line("// comment", ctx).display == ""
    assert evaluate_line('Price: $275 for the "Model 227"', ctx).display == "275 USD"


def test_percentages() -> None:
    ctx = context()
    assert evaluate_line("20% of $10", ctx).display == "2 USD"
    assert evaluate_line("5% on $30", ctx).display == "31.5 USD"
    assert evaluate_line("6% off 40 EUR", ctx).display == "37.6 EUR"
    assert evaluate_line("$50 as a % of $100", ctx).display == "50 percent"


def test_units_and_css() -> None:
    ctx = context()
    assert evaluate_line("1 meter in cm", ctx).display == "100 cm"
    assert evaluate_line("1 meter 20 cm in cm", ctx).display == "120 cm"
    assert evaluate_line("12 pt in px", ctx).display == "16 px"
    evaluate_line("ppi = 326", ctx)
    assert evaluate_line("1 cm in px", ctx).display == "128.3464566929 px"


def test_functions_and_dates() -> None:
    ctx = context()
    assert evaluate_line("sqrt 16", ctx).display == "4"
    assert evaluate_line("root 2 (9)", ctx).display == "3"
    assert evaluate_line("round(1 month in days)", ctx).display == "30 day"
    assert evaluate_line("fromunix(1446587186)", ctx).display.startswith("2015-11-03")
    assert evaluate_line("today + 2 weeks", ctx).ok


def test_currency_conversion() -> None:
    ctx = context()
    assert evaluate_line("$30 in EUR", ctx).display == "27 EUR"
    assert evaluate_line("$30 CAD + 5 USD", ctx).ok


def test_document_evaluation() -> None:
    result = evaluate_document("Line 1: $10\nLine 2: $20\nResult: average", {"rate_provider": context().rate_provider})
    assert result.displays == ["10 USD", "20 USD", "15 USD"]
