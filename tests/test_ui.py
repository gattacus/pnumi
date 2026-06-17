from __future__ import annotations

import sys
import threading
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtGui import QAction, QColor, QTextCursor, QKeySequence
from PySide6.QtWidgets import QApplication

from pnumi.rates import StaticRateProvider
from pnumi.ui import (
    COMMENT_MARKDOWN_COLOR,
    DARK_MODE_KEY,
    DARK_THEME,
    DEFAULT_DOCUMENT_TEXT,
    KEYWORD_HIGHLIGHT_COLOR,
    LAST_CONTENT_KEY,
    LIGHT_THEME,
    RESULT_DECIMAL_PLACES_KEY,
    SHOW_COMPLETIONS_SHORTCUTS,
    THEME_MODE_DARK,
    THEME_MODE_KEY,
    THEME_MODE_LIGHT,
    THEME_MODE_SYSTEM,
    VARIABLE_HIGHLIGHT_COLOR,
    AboutDialog,
    CompletionTextEdit,
    MainWindow,
    SettingsDialog,
)


@pytest.fixture(autouse=True)
def _static_ui_rates(monkeypatch) -> None:
    monkeypatch.setattr(
        "pnumi.ui.default_rate_provider",
        lambda: StaticRateProvider(
            {
                ("USD", "EUR"): Decimal("0.92"),
                ("USD", "CAD"): Decimal("1.35"),
                ("USD", "GBP"): Decimal("0.79"),
                ("USD", "CHF"): Decimal("0.89"),
                ("BTC", "USD"): Decimal("65000"),
                ("ETH", "USD"): Decimal("3500"),
            }
        ),
    )


def _window_with_test_settings(qtbot, tmp_path, name: str = "settings") -> MainWindow:
    window = MainWindow(settings=QSettings(str(tmp_path / f"{name}.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    return window


def test_typing_updates_results(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window.editor.setPlainText("8 times 9")
    qtbot.waitUntil(lambda: window.results.toPlainText().strip() == "72", timeout=1000)


def test_recalculation_does_not_block_ui_thread(qtbot, tmp_path, monkeypatch) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window._update_timer.stop()
    started = threading.Event()
    release = threading.Event()

    def slow_evaluate_document(text: str, options=None):
        started.set()
        release.wait(timeout=5)
        return SimpleNamespace(displays=[f"{text} result"])

    monkeypatch.setattr("pnumi.ui.evaluate_document", slow_evaluate_document)
    window.editor.setPlainText("slow")
    window._update_timer.stop()

    started_at = time.perf_counter()
    window.recalculate()

    assert time.perf_counter() - started_at < 0.1
    assert started.wait(timeout=1)

    window.set_dark_mode(True)
    assert window.document_surface.theme == DARK_THEME

    window.editor.setPlainText("newer")
    window._update_timer.stop()
    window.recalculate()
    release.set()

    qtbot.waitUntil(lambda: window.results.toPlainText().strip() == "newer result", timeout=1000)


def test_copy_current_result(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window.editor.setPlainText("1000 + 2")
    qtbot.waitUntil(lambda: window.results.toPlainText().strip() == "1'002", timeout=1000)
    window.copy_current_result()
    assert QApplication.clipboard().text() == "1002"


def test_clicking_hovered_result_copies_that_result(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window.show()
    qtbot.waitExposed(window)
    window.editor.setPlainText("8 times 9\n1200 meter in cm")
    qtbot.waitUntil(lambda: window.results.toPlainText().splitlines() == ["72", "120'000 cm"], timeout=1000)

    rect = window.results._result_pill_rect(1)
    assert rect is not None
    point = rect.center().toPoint()

    qtbot.mouseMove(window.results.viewport(), point)
    assert window.results.result_at_position(point) == "120'000 cm"

    qtbot.mouseClick(window.results.viewport(), Qt.MouseButton.LeftButton, pos=point)

    assert QApplication.clipboard().text() == "120000 cm"


def test_results_are_right_aligned_in_a_minimum_width_column(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window.show()
    qtbot.waitExposed(window)
    window.editor.setPlainText("1 + 1\n1761 eur")
    qtbot.waitUntil(lambda: window.results.toPlainText().splitlines() == ["2", "1'761 EUR"], timeout=1000)

    assert window.results.document().defaultTextOption().alignment() == Qt.AlignmentFlag.AlignRight
    assert window.results.minimumWidth() == window.results.maximumWidth()
    assert window.results.minimumWidth() == window.results.content_width(["2", "1'761 EUR"])
    assert window.results.document().size().width() <= window.results.viewport().width()
    rect = window.results._result_pill_rect(1)
    assert rect is not None
    assert rect.right() <= window.results.viewport().width()
    assert window.results.viewport().width() - rect.right() < window.results.fontMetrics().averageCharWidth()


def test_copy_all_omits_thousands_separators_from_results(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window.editor.setPlainText("1'000 + 2\n1200 meter in cm")
    qtbot.waitUntil(lambda: window.results.toPlainText().splitlines() == ["1'002", "120'000 cm"], timeout=1000)

    window.copy_all()

    assert QApplication.clipboard().text() == "1'000 + 2\t1002\n1200 meter in cm\t120000 cm"


def test_autocomplete_contains_builtins_and_document_variables(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window.editor.setPlainText("subtotal = 20\nsub")
    window.refresh_autocomplete()
    words = window.editor.completion_words()
    assert "sqrt" in words
    assert "meter" in words
    assert "USD" in words
    assert "subtotal" in words


def test_autocomplete_inserts_completion(qtbot) -> None:
    editor = CompletionTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("sq")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)
    editor.insert_completion("sqrt")
    assert editor.toPlainText() == "sqrt"


def test_autocomplete_can_be_opened_by_action(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)

    action = window.findChild(QAction, "showCompletionsAction")

    assert action is not None
    assert action.shortcuts() == SHOW_COMPLETIONS_SHORTCUTS


def test_surround_with_parentheses_shortcut(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)

    action = window.findChild(QAction, "surroundAction")

    assert action is not None
    if sys.platform == "win32":
        assert action.shortcuts() == [QKeySequence("Ctrl+Shift+9"), QKeySequence("Ctrl+Shift+0")]
    else:
        assert action.shortcut() == QKeySequence("Ctrl+Shift+0")


def test_open_completion_popup_uses_current_word(qtbot) -> None:
    editor = CompletionTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("sq")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    editor.open_completion_popup()

    assert editor.completer.completionPrefix() == "sq"
    assert editor.completer.completionCount() > 0


def test_autocomplete_opens_from_control_space_shortcut(qtbot) -> None:
    editor = CompletionTextEdit()
    qtbot.addWidget(editor)
    editor.show()
    editor.setFocus()
    editor.setPlainText("sq")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    modifier = Qt.KeyboardModifier.MetaModifier if sys.platform == "darwin" else Qt.KeyboardModifier.ControlModifier
    qtbot.keyClick(editor, Qt.Key.Key_Space, modifier)

    assert editor.toPlainText() == "sq"
    assert editor.completer.completionPrefix() == "sq"
    assert editor.completer.completionCount() > 0


def test_autocomplete_does_not_open_while_typing(qtbot) -> None:
    editor = CompletionTextEdit()
    qtbot.addWidget(editor)
    editor.show()
    editor.setFocus()

    qtbot.keyClicks(editor, "sq")

    assert editor.toPlainText() == "sq"
    assert not editor.completer.popup().isVisible()


def test_alternating_row_background_setting_is_persisted(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert window.editor.alternating_row_background_enabled()
    assert window.results.alternating_row_background_enabled()
    assert window.document_surface.alternating_row_background_enabled()

    window.set_alternating_row_background(False)

    assert not window.editor.alternating_row_background_enabled()
    assert not window.results.alternating_row_background_enabled()
    assert not window.document_surface.alternating_row_background_enabled()
    settings.sync()
    reloaded = MainWindow(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(reloaded)
    assert not reloaded.editor.alternating_row_background_enabled()
    assert not reloaded.results.alternating_row_background_enabled()
    assert not reloaded.document_surface.alternating_row_background_enabled()


def test_dark_mode_setting_is_persisted_and_applied(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    assert window.theme_mode == THEME_MODE_LIGHT
    assert not window.dark_mode
    assert window.document_surface.theme == LIGHT_THEME

    window.set_dark_mode(True)

    assert window.theme_mode == THEME_MODE_DARK
    assert window.dark_mode
    assert window.document_surface.theme == DARK_THEME
    assert DARK_THEME.document_background.name() in window.styleSheet()
    assert settings.value(THEME_MODE_KEY) == THEME_MODE_DARK
    settings.sync()
    reloaded = MainWindow(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(reloaded)
    assert reloaded.theme_mode == THEME_MODE_DARK
    assert reloaded.dark_mode
    assert reloaded.document_surface.theme == DARK_THEME


def test_legacy_dark_mode_setting_is_migrated(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue(DARK_MODE_KEY, True)

    window = MainWindow(settings=settings)
    qtbot.addWidget(window)

    assert window.theme_mode == THEME_MODE_DARK
    assert window.dark_mode
    assert window.document_surface.theme == DARK_THEME


def test_system_theme_mode_tracks_system_color_scheme(qtbot, tmp_path, monkeypatch) -> None:
    system_dark_mode = True
    monkeypatch.setattr(MainWindow, "_system_dark_mode", lambda _self: system_dark_mode)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue(THEME_MODE_KEY, THEME_MODE_SYSTEM)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)

    assert window.theme_mode == THEME_MODE_SYSTEM
    assert window.dark_mode
    assert window.document_surface.theme == DARK_THEME

    system_dark_mode = False
    window._handle_system_color_scheme_changed()

    assert not window.dark_mode
    assert window.document_surface.theme == LIGHT_THEME


def test_result_decimal_places_setting_is_persisted_and_display_only(qtbot, tmp_path) -> None:
    settings_path = tmp_path / "settings.ini"
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.editor.setPlainText("x = 1 / 3\nx * 3")

    window.set_result_decimal_places(2)

    qtbot.waitUntil(lambda: window.results.toPlainText().splitlines() == ["0.33", "1"], timeout=1000)
    assert window.settings.value(RESULT_DECIMAL_PLACES_KEY) == 2
    settings.sync()

    reloaded = MainWindow(settings=QSettings(str(settings_path), QSettings.Format.IniFormat))
    qtbot.addWidget(reloaded)
    assert reloaded.result_decimal_places == 2


def test_window_size_is_persisted_between_sessions(qtbot, tmp_path) -> None:
    settings_path = tmp_path / "settings.ini"
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)

    window.resize(1040, 720)
    window.close()
    settings.sync()

    reloaded = MainWindow(settings=QSettings(str(settings_path), QSettings.Format.IniFormat))
    qtbot.addWidget(reloaded)

    assert reloaded.size() == QSize(1040, 720)


def test_initial_content_uses_first_run_default(qtbot, tmp_path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)

    assert window.editor.toPlainText() == DEFAULT_DOCUMENT_TEXT


def test_initial_content_is_calculated_asynchronously(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)

    qtbot.waitUntil(lambda: (window.results.toPlainText().splitlines() or [""])[0] == "80.8695652174 USD", timeout=1000)


def test_editor_content_is_restored_from_last_session(qtbot, tmp_path) -> None:
    settings_path = tmp_path / "settings.ini"
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.editor.setPlainText("subtotal = 20\nsubtotal * 2")
    settings.sync()

    reloaded = MainWindow(settings=QSettings(str(settings_path), QSettings.Format.IniFormat))
    qtbot.addWidget(reloaded)

    assert reloaded.editor.toPlainText() == "subtotal = 20\nsubtotal * 2"
    assert reloaded.settings.value(LAST_CONTENT_KEY) == "subtotal = 20\nsubtotal * 2"


def test_editor_and_results_share_one_visible_vertical_scrollbar(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)

    assert window.editor.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert window.results.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert window.results.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert window.splitter.handleWidth() == 0
    assert window.document_surface.layout().spacing() == 0


def test_settings_dialog_exposes_display_settings(qtbot) -> None:
    dialog = SettingsDialog(False, THEME_MODE_SYSTEM, 4)
    qtbot.addWidget(dialog)

    assert not dialog.alternating_row_background_enabled()
    assert dialog.theme_mode() == THEME_MODE_SYSTEM
    assert not dialog.dark_mode_enabled()
    assert dialog.result_decimal_places() == 4
    dialog.alternating_row_background_checkbox.setChecked(True)
    dialog.theme_mode_combo.setCurrentIndex(dialog.theme_mode_combo.findData(THEME_MODE_DARK))
    dialog.result_decimal_places_spinbox.setValue(6)
    assert dialog.alternating_row_background_enabled()
    assert dialog.theme_mode() == THEME_MODE_DARK
    assert dialog.dark_mode_enabled()
    assert dialog.result_decimal_places() == 6


def test_about_dialog_shows_app_identity_and_icon(qtbot) -> None:
    dialog = AboutDialog()
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "About Pnumi"
    assert dialog.windowIcon().isNull() is False
    assert dialog.icon_label.pixmap() is not None
    assert dialog.icon_label.pixmap().isNull() is False
    assert dialog.version_label.text().startswith("Version ")
    assert dialog.description_label.text() == "A Python/PySide6 natural language calculator."


def test_about_action_is_available_from_main_window(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)

    action = window.findChild(QAction, "aboutAction")

    assert action is not None
    assert action.text() == "&About Pnumi"
    assert action.menuRole() == QAction.MenuRole.AboutRole


def test_comments_and_markdown_use_distinct_high_contrast_color(qtbot) -> None:
    editor = CompletionTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("room = 339 # note\n# Totals\n1 + 1")
    editor.highlighter.rehighlight()

    first_line_formats = editor.document().firstBlock().layout().formats()
    second_line_formats = editor.document().firstBlock().next().layout().formats()

    assert any(item.format.foreground().color() == COMMENT_MARKDOWN_COLOR for item in first_line_formats)
    assert any(item.format.foreground().color() == COMMENT_MARKDOWN_COLOR for item in second_line_formats)


def test_variables_and_keywords_use_distinct_high_contrast_colors(qtbot) -> None:
    editor = CompletionTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("subtotal = sqrt(49)\nsubtotal + prev")
    editor.set_dynamic_words(["subtotal"])
    editor.highlighter.rehighlight()

    first_line_formats = editor.document().firstBlock().layout().formats()
    second_line_formats = editor.document().firstBlock().next().layout().formats()

    assert _format_color_at(first_line_formats, 0) == VARIABLE_HIGHLIGHT_COLOR
    assert _format_color_at(first_line_formats, 11) == KEYWORD_HIGHLIGHT_COLOR
    assert _format_color_at(second_line_formats, 0) == VARIABLE_HIGHLIGHT_COLOR
    assert _format_color_at(second_line_formats, 11) == KEYWORD_HIGHLIGHT_COLOR


def test_units_are_highlighted_when_adjacent_to_numbers(qtbot) -> None:
    editor = CompletionTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("speed = 500km/h\ntime = 5min\nrate = 10EUR/h")
    editor.highlighter.rehighlight()

    first_line_formats = editor.document().firstBlock().layout().formats()
    second_line_formats = editor.document().firstBlock().next().layout().formats()
    third_line_formats = editor.document().firstBlock().next().next().layout().formats()

    assert _format_color_at(first_line_formats, 11) == KEYWORD_HIGHLIGHT_COLOR
    assert _format_color_at(first_line_formats, 14) == KEYWORD_HIGHLIGHT_COLOR
    assert _format_color_at(second_line_formats, 8) == KEYWORD_HIGHLIGHT_COLOR
    assert _format_color_at(third_line_formats, 9) == KEYWORD_HIGHLIGHT_COLOR
    assert _format_color_at(third_line_formats, 13) == KEYWORD_HIGHLIGHT_COLOR


def test_conversion_keywords_are_highlighted(qtbot) -> None:
    editor = CompletionTextEdit()
    qtbot.addWidget(editor)
    editor.setPlainText("10 USD to EUR\n10 USD in EUR\n10 USD into EUR\n10 USD as EUR")
    editor.highlighter.rehighlight()

    # Get formatting for each line
    block = editor.document().firstBlock()

    # line 1: 10 USD to EUR
    # "to" starts at index 7, length 2
    formats_to = block.layout().formats()
    assert _format_color_at(formats_to, 7) == KEYWORD_HIGHLIGHT_COLOR

    # line 2: 10 USD in EUR
    # "in" starts at index 7, length 2
    block = block.next()
    formats_in = block.layout().formats()
    assert _format_color_at(formats_in, 7) == KEYWORD_HIGHLIGHT_COLOR

    # line 3: 10 USD into EUR
    # "into" starts at index 7, length 4
    block = block.next()
    formats_into = block.layout().formats()
    assert _format_color_at(formats_into, 7) == KEYWORD_HIGHLIGHT_COLOR

    # line 4: 10 USD as EUR
    # "as" starts at index 7, length 2
    block = block.next()
    formats_as = block.layout().formats()
    assert _format_color_at(formats_as, 7) == KEYWORD_HIGHLIGHT_COLOR


def _format_color_at(formats, index: int) -> QColor | None:
    for item in formats:
        if item.start <= index < item.start + item.length:
            return item.format.foreground().color()
    return None

