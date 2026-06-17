from __future__ import annotations

import re

from .engine import evaluate_line
from .models import DocumentContext

RESULT_SEPARATOR_RE = re.compile(r"\s+=\s+")


def normalize_numi_import(text: str) -> str:
    lines: list[str] = []
    context = DocumentContext()
    for raw_line in text.splitlines(keepends=True):
        line, line_ending = _split_line_ending(raw_line)
        normalized = _strip_exported_result(line, context) or line
        evaluate_line(normalized, context)
        lines.append(f"{normalized}{line_ending}")
    return "".join(lines)


def _strip_exported_result(line: str, context: DocumentContext) -> str | None:
    for separator in reversed(list(RESULT_SEPARATOR_RE.finditer(line))):
        candidate = line[: separator.start()].rstrip()
        exported_result = line[separator.end() :].strip()
        if not candidate or not exported_result:
            continue
        probe_context = _clone_context(context)
        result = evaluate_line(candidate, probe_context)
        if result.display and _canonical_result(result.display) == _canonical_result(exported_result):
            return candidate
    return None


def _canonical_result(text: str) -> str:
    text = text.replace("\u00a0", " ").strip()
    text = re.sub(r"(?<=\d)[\s,'\u2018\u2019](?=\d)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def _clone_context(context: DocumentContext) -> DocumentContext:
    return DocumentContext(
        variables=dict(context.variables),
        previous_results=list(context.previous_results),
        section_results=list(context.section_results),
        rate_provider=context.rate_provider,
        settings=dict(context.settings),
    )


def _split_line_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""
