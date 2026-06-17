from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from pnumi.engine import evaluate_line
from pnumi.models import DocumentContext
from pnumi.rates import StaticRateProvider


class MockDateTime:
    @classmethod
    def now(cls, tz=None):
        base = datetime(2026, 6, 17, 21, 27, 10, tzinfo=UTC)
        if tz is not None:
            return base.astimezone(tz)
        return datetime(2026, 6, 17, 23, 27, 10)

    @classmethod
    def fromtimestamp(cls, timestamp, tz=None):
        return datetime.fromtimestamp(timestamp, tz)


class MockDate:
    @classmethod
    def today(cls):
        return date(2026, 6, 17)


def get_test_context() -> DocumentContext:
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
                ("BTC", "USD"): Decimal("55000"),
                ("BTC", "CHF"): Decimal("50000"),
                ("CHF", "USD"): Decimal("1.1"),
                ("ETH", "EUR"): Decimal("1800"),
                ("SOL", "USD"): Decimal("150"),
            }
        )
    )


@patch("pnumi.engine.datetime", MockDateTime)
@patch("pnumi.engine.date", MockDate)
def test_all_guide_examples() -> None:
    guide_path = Path(__file__).resolve().parents[1] / "docs" / "USER_GUIDE.md"
    content = guide_path.read_text(encoding="utf-8")

    # Extract all text code blocks
    code_blocks = re.findall(r"```text\n(.*?)\n```", content, re.DOTALL)

    for block_idx, block in enumerate(code_blocks):
        ctx = get_test_context()
        lines = block.splitlines()

        for line_idx, line in enumerate(lines):
            line_stripped = line.strip()
            # Ignore comments, blank lines, or visual separator notes
            if not line_stripped or line_stripped.startswith("#") or line_stripped.startswith("//"):
                evaluate_line(line, ctx)
                continue

            # Check if there is an expected result annotated
            if "#" in line:
                expr, _, expected = line.partition("#")
                expr = expr.strip()
                expected = expected.strip()

                # Clean up parenthetical explanations from expected result
                if "(" in expected:
                    expected = expected.split("(")[0].strip()

                # Special checks for timezone specific daylight savings outputs
                # which can format with or without a space or vary between systems
                result = evaluate_line(expr, ctx)
                assert result.ok, f"Block {block_idx}, line {line_idx + 1} failed to evaluate: {expr!r}. Diagnostics: {result.diagnostics}"

                display_clean = result.display.strip()
                # Compare cleaned display with expected result
                assert display_clean == expected, (
                    f"Block {block_idx}, line {line_idx + 1} failed: {expr!r}.\n"
                    f"Expected: {expected!r}\n"
                    f"Got:      {display_clean!r}"
                )
            else:
                # Just execute the line (e.g. variable declarations)
                result = evaluate_line(line, ctx)
                assert result.ok, f"Block {block_idx}, line {line_idx + 1} failed to evaluate: {line!r}. Diagnostics: {result.diagnostics}"
