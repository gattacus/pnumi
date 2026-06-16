from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSize, QSettings, Qt
from PySide6.QtGui import QAction, QColor, QTextCursor
from PySide6.QtWidgets import QApplication

from pnumi.ui import (
    COMMENT_MARKDOWN_COLOR,
    DARK_THEME,
    DEFAULT_DOCUMENT_TEXT,
    KEYWORD_HIGHLIGHT_COLOR,
    LAST_CONTENT_KEY,
    LIGHT_THEME,
    SHOW_COMPLETIONS_SHORTCUTS,
    VARIABLE_HIGHLIGHT_COLOR,
    SettingsDialog,
    CompletionTextEdit,
    MainWindow,
)


def _window_with_test_settings(qtbot, tmp_path, name: str = "settings") -> MainWindow:
    window = MainWindow(settings=QSettings(str(tmp_path / f"{name}.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(window)
    return window


def test_typing_updates_results(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window.editor.setPlainText("8 times 9")
    qtbot.waitUntil(lambda: window.results.toPlainText().strip() == "72", timeout=1000)


def test_copy_current_result(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window.editor.setPlainText("8 times 9")
    qtbot.waitUntil(lambda: window.results.toPlainText().strip() == "72", timeout=1000)
    window.copy_current_result()
    assert QApplication.clipboard().text() == "72"


def test_clicking_hovered_result_copies_that_result(qtbot, tmp_path) -> None:
    window = _window_with_test_settings(qtbot, tmp_path)
    window.show()
    qtbot.waitExposed(window)
    window.editor.setPlainText("8 times 9\n5 + 6")
    qtbot.waitUntil(lambda: window.results.toPlainText().splitlines() == ["72", "11"], timeout=1000)

    rect = window.results._result_pill_rect(1)
    assert rect is not None
    point = rect.center().toPoint()

    qtbot.mouseMove(window.results.viewport(), point)
    assert window.results.result_at_position(point) == "11"

    qtbot.mouseClick(window.results.viewport(), Qt.MouseButton.LeftButton, pos=point)

    assert QApplication.clipboard().text() == "11"


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
    assert not window.dark_mode
    assert window.document_surface.theme == LIGHT_THEME

    window.set_dark_mode(True)

    assert window.dark_mode
    assert window.document_surface.theme == DARK_THEME
    assert DARK_THEME.document_background.name() in window.styleSheet()
    settings.sync()
    reloaded = MainWindow(settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(reloaded)
    assert reloaded.dark_mode
    assert reloaded.document_surface.theme == DARK_THEME


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
    assert window.splitter.handleWidth() == 0
    assert window.document_surface.layout().spacing() == 0


def test_settings_dialog_exposes_alternating_row_background(qtbot) -> None:
    dialog = SettingsDialog(False, True)
    qtbot.addWidget(dialog)

    assert not dialog.alternating_row_background_enabled()
    assert dialog.dark_mode_enabled()
    dialog.alternating_row_background_checkbox.setChecked(True)
    dialog.dark_mode_checkbox.setChecked(False)
    assert dialog.alternating_row_background_enabled()
    assert not dialog.dark_mode_enabled()


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


def _format_color_at(formats, index: int) -> QColor | None:
    for item in formats:
        if item.start <= index < item.start + item.length:
            return item.format.foreground().color()
    return None
