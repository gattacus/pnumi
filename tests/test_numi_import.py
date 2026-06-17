from __future__ import annotations

from pnumi.engine import evaluate_document
from pnumi.numi_import import normalize_numi_import


def test_normalize_numi_import_strips_verified_exported_results() -> None:
    imported = (
        "room = 339 # 1 Zimmer, 2 Nachte = 339\n"
        "breakfast = 27 = 27\n"
        "\n"
        "Hotel_Kulanz = 60 = 60\n"
        "room_papa = room + 4×breakfast - Hotel_Kulanz = 387\n"
        "  room_papa_anteilig_pro_kind = room_papa/3 = 129\n"
        "grand_total = room_papa + room_papa_anteilig_pro_kind = 516\n"
        "# Totals\n"
        "grand_total\n"
    )

    normalized = normalize_numi_import(imported)

    assert normalized == (
        "room = 339 # 1 Zimmer, 2 Nachte\n"
        "breakfast = 27\n"
        "\n"
        "Hotel_Kulanz = 60\n"
        "room_papa = room + 4×breakfast - Hotel_Kulanz\n"
        "  room_papa_anteilig_pro_kind = room_papa/3\n"
        "grand_total = room_papa + room_papa_anteilig_pro_kind\n"
        "# Totals\n"
        "grand_total\n"
    )
    assert evaluate_document(normalized).displays == ["339", "27", "", "60", "387", "129", "516", "", "516"]


def test_normalize_numi_import_matches_numi_grouped_results() -> None:
    assert normalize_numi_import("my_total = 1700 + 1 = 1\u2019701") == "my_total = 1700 + 1"


def test_normalize_numi_import_keeps_unverified_equals_text() -> None:
    assert normalize_numi_import("note = 1 = 2") == "note = 1 = 2"
