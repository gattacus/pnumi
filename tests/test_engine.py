from __future__ import annotations

from decimal import Decimal

from pnumi.engine import evaluate_document, evaluate_line
from pnumi.models import DocumentContext
from pnumi.rates import StaticRateProvider


def context() -> DocumentContext:
    return DocumentContext(
        rate_provider=StaticRateProvider(
            {
                ("USD", "EUR"): Decimal("0.9"),
                ("USD", "CAD"): Decimal("1.25"),
                ("RUB", "USD"): Decimal("0.012"),
                ("JPY", "CHF"): Decimal("0.0055"),
                ("INR", "USD"): Decimal("0.012"),
                ("PLN", "USD"): Decimal("0.25"),
                ("SEK", "USD"): Decimal("0.095"),
                ("NOK", "USD"): Decimal("0.092"),
                ("XMR", "CHF"): Decimal("140"),
                ("LTC", "USD"): Decimal("85"),
            }
        )
    )


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
    assert evaluate_line("v + 10", ctx).display == "30 USD"
    assert evaluate_line("Cost: $20", ctx).display == "20 USD"
    assert evaluate_line("Discounted: prev - 5", ctx).display == "15 USD"
    assert evaluate_line("sum", ctx).display == "85 USD"
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
    assert evaluate_line("$50 as a % of $100", ctx).display == "50 %"


def test_percentage_variables_apply_to_base_values() -> None:
    result = evaluate_document("return = 5%\nmoney = 1000\nmoney + return")

    assert result.displays == ["5 %", "1'000", "1'050"]


def test_percentage_variables_support_numi_style_arithmetic() -> None:
    ctx = context()
    assert evaluate_line("return = 5%", ctx).display == "5 %"
    assert evaluate_line("money = 1000", ctx).display == "1'000"
    assert evaluate_line("money + return", ctx).display == "1'050"
    assert evaluate_line("money - return", ctx).display == "950"
    assert evaluate_line("money * return", ctx).display == "50"
    assert evaluate_line("money / return", ctx).display == "20'000"
    assert evaluate_line("return * money", ctx).display == "50"


def test_percentage_addition_matches_numi_operand_ordering() -> None:
    result = evaluate_document(
        "return = 5%\n"
        "money = 1000 eur\n"
        "other_money = 1000\n"
        "money + return\n"
        "5% + money\n"
        "other_money + return\n"
        "5% + other_money\n"
        "5% - other_money",
        {"rate_provider": context().rate_provider},
    )

    assert result.displays == ["5 %", "1'000 EUR", "1'000", "1'050 EUR", "", "1'050", "1'005 %", "-995 %"]


def test_percentage_left_addition_only_accepts_plain_numbers() -> None:
    ctx = context()
    assert evaluate_line("5% + 1000", ctx).display == "1'005 %"
    assert evaluate_line("5% + 10%", ctx).display == "15 %"

    money_result = evaluate_line("5% + 1000 eur", ctx)
    assert not money_result.ok
    assert money_result.display == ""

    unit_result = evaluate_line("5% + 1000 m", ctx)
    assert not unit_result.ok
    assert unit_result.display == ""


def test_percentage_left_subtraction_only_accepts_plain_numbers() -> None:
    ctx = context()
    assert evaluate_line("5% - 1000", ctx).display == "-995 %"
    assert evaluate_line("5% - 10%", ctx).display == "-5 %"

    money_result = evaluate_line("5% - 1000 eur", ctx)
    assert not money_result.ok
    assert money_result.display == ""

    unit_result = evaluate_line("5% - 1000 m", ctx)
    assert not unit_result.ok
    assert unit_result.display == ""


def test_units_and_css() -> None:
    ctx = context()
    assert evaluate_line("1 meter in cm", ctx).display == "100 cm"
    assert evaluate_line("1 meter 20 cm in cm", ctx).display == "120 cm"
    assert evaluate_line("12 pt in px", ctx).display == "16 px"
    evaluate_line("ppi = 326", ctx)
    assert evaluate_line("1 cm in px", ctx).display == "128.3464566929 px"


def test_typed_arithmetic_propagates_variable_units() -> None:
    ctx = context()
    assert evaluate_line("ticket = 79 eur", ctx).display == "79 EUR"
    assert evaluate_line("2*ticket", ctx).display == "158 EUR"
    assert evaluate_line("ticket * 2", ctx).display == "158 EUR"
    assert evaluate_line("ticket / 2", ctx).display == "39.5 EUR"
    assert evaluate_line("ticket + 10", ctx).display == "89 EUR"
    assert evaluate_line("10 - ticket", ctx).display == "-69 EUR"


def test_typed_arithmetic_converts_compatible_units_and_currencies() -> None:
    ctx = context()
    assert evaluate_line("trip = 1 km", ctx).display == "1 km"
    assert evaluate_line("trip + 500 m", ctx).display == "1.5 km"
    assert evaluate_line("500 m + trip", ctx).display == "1'500 m"
    assert evaluate_line("$30 CAD + 5 USD", ctx).display == "36.25 CAD"
    assert evaluate_line("$30 + 5 EUR", ctx).display == "35.5555555556 USD"


def test_typed_arithmetic_combines_and_cancels_units() -> None:
    ctx = context()
    assert evaluate_line("10km / 2h", ctx).display == "5 km/h"
    assert evaluate_line("speed = 10km / 2h", ctx).display == "5 km/h"
    assert evaluate_line("speed * 3", ctx).display == "15 km/h"
    assert evaluate_line("2 * speed", ctx).display == "10 km/h"
    assert evaluate_line("speed + speed", ctx).display == "10 km/h"
    assert evaluate_line("1 / 2h", ctx).display == "0.5 1/h"
    assert evaluate_line("1 / speed", ctx).display == "0.2 h/km"
    assert evaluate_line("1 m / 100 cm", ctx).display == "1"
    assert evaluate_line("2 m * 3 second", ctx).display == "6 m*s"
    assert evaluate_line("(2 m)^2", ctx).display == "4 m^2"


def test_typed_arithmetic_combines_currency_and_units_for_rates() -> None:
    ctx = context()
    assert evaluate_line("10 EUR / 2h", ctx).display == "5 EUR/h"
    assert evaluate_line("rate = 10 EUR / 2h", ctx).display == "5 EUR/h"
    assert evaluate_line("rate * 3", ctx).display == "15 EUR/h"


def test_compound_unit_literals_and_distance_normalization() -> None:
    result = evaluate_document("speed = 500km/h\ntime = 5min\ndistance = speed * time", {"rate_provider": context().rate_provider})

    assert result.displays == ["500 km/h", "5 minute", "41.6666666667 km"]


def test_compound_unit_literals_normalize_other_compatible_factors() -> None:
    ctx = context()
    assert evaluate_line("120km/2h", ctx).display == "60 km/h"
    assert evaluate_line("pace = 120km/2h", ctx).display == "60 km/h"
    assert evaluate_line("pace * 30min", ctx).display == "30 km"
    assert evaluate_line("500m/min * 2h", ctx).display == "60'000 m"


def test_compound_units_cancel_to_dimensionless_values() -> None:
    ctx = context()
    assert evaluate_line("90km/h / 30km/h", ctx).display == "3"
    assert evaluate_line("1 / 500km/h", ctx).display == "0.002 h/km"
    assert evaluate_line("2kg/m * 50cm", ctx).display == "1 kg"


def test_compound_currency_rates_normalize_with_time_units() -> None:
    ctx = context()
    assert evaluate_line("10EUR/h * 30min", ctx).display == "5 EUR"
    assert evaluate_line("budget_rate = 10EUR/h", ctx).display == "10 EUR/h"
    assert evaluate_line("budget_rate * 15min", ctx).display == "2.5 EUR"


def test_typed_arithmetic_rejects_incompatible_addition() -> None:
    ctx = context()
    result = evaluate_line("1 m + 2 second", ctx)
    assert not result.ok
    assert result.display == ""
    result = evaluate_line("1 m + 2 EUR", ctx)
    assert not result.ok
    assert result.display == ""
    result = evaluate_line("2 EUR * 3 USD", ctx)
    assert not result.ok
    assert result.display == ""


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


def test_currency_registry_accepts_iso_names_signs_and_crypto() -> None:
    ctx = context()

    assert evaluate_line("100 RUB in USD", ctx).display == "1.2 USD"
    assert evaluate_line("50 roubles in euro", ctx).display == "0.54 EUR"
    assert evaluate_line("100 yen in CHF", ctx).display == "0.55 CHF"
    assert evaluate_line("¥100 in CHF", ctx).display == "0.55 CHF"
    assert evaluate_line("₹2500 in USD", ctx).display == "30 USD"
    assert evaluate_line("2500 rupees in USD", ctx).display == "30 USD"
    assert evaluate_line("10 zloty in USD", ctx).display == "2.5 USD"
    assert evaluate_line("10 krona in USD", ctx).display == "0.95 USD"
    assert evaluate_line("10 krone in USD", ctx).display == "0.92 USD"
    assert evaluate_line("1 litecoin in USD", ctx).display == "85 USD"
    assert evaluate_line("1 XMR in CHF", ctx).display == "140 CHF"


def test_valid_currency_with_missing_rate_reports_rate_error() -> None:
    result = evaluate_line("1 AED in USD", context())

    assert not result.ok
    assert result.diagnostics == ["No rate for AED/USD"]


def test_document_evaluation() -> None:
    result = evaluate_document("Line 1: $10\nLine 2: $20\nResult: average", {"rate_provider": context().rate_provider})
    assert result.displays == ["10 USD", "20 USD", "15 USD"]
