from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, QSettings, QSize, QStringListModel, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QPainter,
    QPixmap,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QScrollBar,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .currencies import CURRENCY_ALIASES, CURRENCY_CODES
from .engine import TIMEZONES, evaluate_document
from .formatting import DEFAULT_DECIMAL_PLACES
from .numi_import import normalize_numi_import
from .units import ALIASES as UNIT_ALIASES

ALTERNATE_ROW_BACKGROUND = QColor("#efd046")
DOCUMENT_BACKGROUND = QColor("#f7d74c")
COMMENT_MARKDOWN_COLOR = QColor("#075f73")
VARIABLE_HIGHLIGHT_COLOR = QColor("#4b2e83")
KEYWORD_HIGHLIGHT_COLOR = QColor("#6b2f10")
ALTERNATING_ROW_BACKGROUND_KEY = "editor/alternatingRowBackground"
DARK_MODE_KEY = "editor/darkMode"
THEME_MODE_KEY = "editor/themeMode"
THEME_MODE_SYSTEM = "system"
THEME_MODE_LIGHT = "light"
THEME_MODE_DARK = "dark"
THEME_MODES = {THEME_MODE_SYSTEM, THEME_MODE_LIGHT, THEME_MODE_DARK}
LAST_CONTENT_KEY = "editor/lastContent"
RESULT_DECIMAL_PLACES_KEY = "results/decimalPlaces"
WINDOW_SIZE_KEY = "window/size"
SETTINGS_ORGANIZATION = "gattacus.uk"
SETTINGS_ORGANIZATION_DOMAIN = "uk.gattacus"
SETTINGS_APPLICATION = "Pnumi"
DEFAULT_WINDOW_SIZE = QSize(920, 640)
DEFAULT_DOCUMENT_TEXT = "Cost: $20 + 56 EUR\nDiscounted: prev - 5% off\n\n1 meter 20 cm in cm\nround(1 month in days)"
SHOW_COMPLETIONS_SHORTCUTS = [QKeySequence("Meta+Space" if sys.platform == "darwin" else "Ctrl+Space")]
CLIPBOARD_THOUSANDS_SEPARATOR_RE = re.compile(r"(?<=\d)[ ,'\u2018\u2019](?=\d{3}(?:\D|$))")


def is_show_completions_shortcut(event: QKeyEvent) -> bool:
    event_sequence = QKeySequence(event.keyCombination())
    return any(
        event_sequence.matches(shortcut) == QKeySequence.SequenceMatch.ExactMatch
        for shortcut in SHOW_COMPLETIONS_SHORTCUTS
    )


@dataclass(frozen=True)
class EditorTheme:
    document_background: QColor
    alternate_row_background: QColor
    editor_text: QColor
    result_text: QColor
    comment: QColor
    variable: QColor
    keyword: QColor
    selection_background: QColor
    selection_text: QColor


LIGHT_THEME = EditorTheme(
    document_background=DOCUMENT_BACKGROUND,
    alternate_row_background=ALTERNATE_ROW_BACKGROUND,
    editor_text=QColor("#27251d"),
    result_text=QColor("#746522"),
    comment=COMMENT_MARKDOWN_COLOR,
    variable=VARIABLE_HIGHLIGHT_COLOR,
    keyword=KEYWORD_HIGHLIGHT_COLOR,
    selection_background=QColor("#3b82f6"),
    selection_text=QColor("#ffffff"),
)
DARK_THEME = EditorTheme(
    document_background=QColor("#1f211a"),
    alternate_row_background=QColor("#282b21"),
    editor_text=QColor("#f4eecf"),
    result_text=QColor("#c6bb79"),
    comment=QColor("#80d7e8"),
    variable=QColor("#d3b5ff"),
    keyword=QColor("#ffb37a"),
    selection_background=QColor("#4f7cff"),
    selection_text=QColor("#ffffff"),
)


class StripedPlainTextEdit(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self._alternating_row_background_enabled = True
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setAutoFillBackground(False)
        self.viewport().setAutoFillBackground(False)
        self.textChanged.connect(self.update_alternating_row_backgrounds)

    def alternating_row_background_enabled(self) -> bool:
        return self._alternating_row_background_enabled

    def set_alternating_row_background_enabled(self, enabled: bool) -> None:
        self._alternating_row_background_enabled = enabled
        self.update_alternating_row_backgrounds()

    def update_alternating_row_backgrounds(self) -> None:
        self.viewport().update()


class DocumentSurface(QWidget):
    def __init__(self, editor: QPlainTextEdit, results: QPlainTextEdit, scrollbar: QScrollBar) -> None:
        super().__init__()
        self.setObjectName("documentSurface")
        self.editor = editor
        self.results = results
        self.scrollbar = scrollbar
        self._alternating_row_background_enabled = True
        self.theme = LIGHT_THEME

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("documentSplitter")
        splitter.setHandleWidth(0)
        splitter.addWidget(editor)
        splitter.addWidget(results)
        splitter.setSizes([650, 270])
        self.splitter = splitter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(splitter)
        layout.addWidget(scrollbar)

    def alternating_row_background_enabled(self) -> bool:
        return self._alternating_row_background_enabled

    def set_alternating_row_background_enabled(self, enabled: bool) -> None:
        self._alternating_row_background_enabled = enabled
        self.update()

    def set_theme(self, theme: EditorTheme) -> None:
        self.theme = theme
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(event.rect(), self.theme.document_background)
        if self._alternating_row_background_enabled:
            self._paint_alternating_rows(painter)

    def _paint_alternating_rows(self, painter: QPainter) -> None:
        viewport = self.editor.viewport()
        viewport_top = viewport.mapTo(self, QPoint(0, 0)).y()
        viewport_bottom = viewport.mapTo(self, QPoint(0, viewport.height())).y()
        block = self.editor.document().firstBlock()
        offset = self.editor.contentOffset()
        while block.isValid():
            top = self.editor.blockBoundingGeometry(block).translated(offset).top()
            height = self.editor.blockBoundingRect(block).height()
            y = int(viewport_top + top)
            if y >= viewport_bottom:
                break
            if y + height >= viewport_top and block.blockNumber() % 2 == 1:
                painter.fillRect(0, y, self.width(), max(1, int(height)), self.theme.alternate_row_background)
            block = block.next()


class ResultPane(StripedPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.theme = LIGHT_THEME
        self._hovered_result_line: int | None = None
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setObjectName("resultPane")
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def set_theme(self, theme: EditorTheme) -> None:
        self.theme = theme
        self.viewport().update()

    def result_at_position(self, position: QPoint) -> str:
        line = self._result_line_at_position(position)
        return self._result_text_for_line(line) if line is not None else ""

    def paintEvent(self, event) -> None:
        self._paint_hovered_result_pill()
        super().paintEvent(event)

    def mouseMoveEvent(self, event) -> None:
        line = self._result_line_at_position(event.position().toPoint())
        if line != self._hovered_result_line:
            self._hovered_result_line = line
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if line is not None else Qt.CursorShape.IBeamCursor)
            self.viewport().update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hovered_result_line is not None:
            self._hovered_result_line = None
            self.viewport().unsetCursor()
            self.viewport().update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            result = self.result_at_position(event.position().toPoint())
            if result:
                QApplication.clipboard().setText(_clipboard_result_text(result))
                event.accept()
                return
        super().mousePressEvent(event)

    def _paint_hovered_result_pill(self) -> None:
        if self._hovered_result_line is None:
            return
        rect = self._result_pill_rect(self._hovered_result_line)
        if rect is None:
            return
        fill = QColor(self.theme.selection_background)
        fill.setAlpha(44 if self.theme == LIGHT_THEME else 58)
        border = QColor(self.theme.selection_background)
        border.setAlpha(110)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(border)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

    def _result_line_at_position(self, position: QPoint) -> int | None:
        cursor = self.cursorForPosition(position)
        line = cursor.blockNumber()
        rect = self._result_pill_rect(line)
        if rect is None or not rect.contains(position):
            return None
        return line

    def _result_pill_rect(self, line: int) -> QRectF | None:
        text = self._result_text_for_line(line)
        if not text:
            return None
        block = self.document().findBlockByNumber(line)
        cursor = QTextCursor(block)
        cursor_rect = self.cursorRect(cursor)
        width = self.fontMetrics().horizontalAdvance(text)
        height = max(cursor_rect.height(), self.fontMetrics().height())
        left = max(0, cursor_rect.x() - 8)
        right = cursor_rect.x() + width + 8
        return QRectF(left, cursor_rect.y() + 1, max(1, right - left), max(1, height - 2))

    def _result_text_for_line(self, line: int | None) -> str:
        if line is None:
            return ""
        block = self.document().findBlockByNumber(line)
        return block.text() if block.isValid() else ""


class CommentMarkdownHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(COMMENT_MARKDOWN_COLOR)
        self.variable_format = QTextCharFormat()
        self.variable_format.setForeground(VARIABLE_HIGHLIGHT_COLOR)
        self.keyword_format = QTextCharFormat()
        self.keyword_format.setForeground(KEYWORD_HIGHLIGHT_COLOR)
        self._variable_words: list[str] = []

    def set_theme(self, theme: EditorTheme) -> None:
        self.comment_format.setForeground(theme.comment)
        self.variable_format.setForeground(theme.variable)
        self.keyword_format.setForeground(theme.keyword)
        self.rehighlight()

    def set_variable_words(self, words: list[str]) -> None:
        self._variable_words = sorted({word for word in words if word}, key=len, reverse=True)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for match in HIGHLIGHT_KEYWORD_RE.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)
        for word in self._variable_words:
            for match in re.finditer(rf"\b{re.escape(word)}\b", text):
                self.setFormat(match.start(), match.end() - match.start(), self.variable_format)
        assignment = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", text)
        if assignment:
            self.setFormat(assignment.start(1), assignment.end(1) - assignment.start(1), self.variable_format)
        stripped = text.lstrip()
        leading_spaces = len(text) - len(stripped)
        if stripped.startswith("#") or stripped.startswith("//"):
            self.setFormat(leading_spaces, len(stripped), self.comment_format)
            return
        comment = re.search(r"(?<!\S)(#|//).*$", text)
        if comment:
            self.setFormat(comment.start(), len(text) - comment.start(), self.comment_format)


class SettingsDialog(QDialog):
    def __init__(
        self,
        alternating_row_background: bool,
        theme_mode: str | bool,
        result_decimal_places: int = DEFAULT_DECIMAL_PLACES,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.alternating_row_background_checkbox = QCheckBox("Alternating row background")
        self.alternating_row_background_checkbox.setChecked(alternating_row_background)
        self.theme_mode_combo = QComboBox()
        self.theme_mode_combo.addItem("Follow system", THEME_MODE_SYSTEM)
        self.theme_mode_combo.addItem("Light", THEME_MODE_LIGHT)
        self.theme_mode_combo.addItem("Dark", THEME_MODE_DARK)
        current_theme_mode = _normalize_theme_mode(theme_mode)
        self.theme_mode_combo.setCurrentIndex(max(0, self.theme_mode_combo.findData(current_theme_mode)))
        theme_mode_row = QWidget()
        theme_mode_layout = QHBoxLayout(theme_mode_row)
        theme_mode_layout.setContentsMargins(0, 0, 0, 0)
        theme_mode_layout.addWidget(QLabel("Theme"))
        theme_mode_layout.addWidget(self.theme_mode_combo)
        theme_mode_layout.addStretch(1)
        self.result_decimal_places_spinbox = QSpinBox()
        self.result_decimal_places_spinbox.setRange(0, 20)
        self.result_decimal_places_spinbox.setValue(result_decimal_places)
        decimal_places_row = QWidget()
        decimal_places_layout = QHBoxLayout(decimal_places_row)
        decimal_places_layout.setContentsMargins(0, 0, 0, 0)
        decimal_places_layout.addWidget(QLabel("Result decimal places"))
        decimal_places_layout.addWidget(self.result_decimal_places_spinbox)
        decimal_places_layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.alternating_row_background_checkbox)
        layout.addWidget(theme_mode_row)
        layout.addWidget(decimal_places_row)
        layout.addWidget(buttons)

    def alternating_row_background_enabled(self) -> bool:
        return self.alternating_row_background_checkbox.isChecked()

    def dark_mode_enabled(self) -> bool:
        return self.theme_mode() == THEME_MODE_DARK

    def theme_mode(self) -> str:
        return str(self.theme_mode_combo.currentData())

    def result_decimal_places(self) -> int:
        return self.result_decimal_places_spinbox.value()


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Pnumi")
        self.setWindowIcon(_app_icon())
        self.setModal(True)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("aboutIcon")
        icon = _app_icon_pixmap(96)
        if not icon.isNull():
            self.icon_label.setPixmap(icon)
        self.icon_label.setFixedSize(104, 104)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Pnumi")
        title.setObjectName("aboutTitle")
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 7)
        title_font.setBold(True)
        title.setFont(title_font)

        self.version_label = QLabel(f"Version {_app_version()}")
        self.version_label.setObjectName("aboutVersion")
        self.description_label = QLabel("A Python/PySide6 natural language calculator.")
        self.description_label.setObjectName("aboutDescription")
        license_label = QLabel("Released under the MIT License.")
        license_label.setObjectName("aboutLicense")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        text_layout.addWidget(title)
        text_layout.addWidget(self.version_label)
        text_layout.addWidget(self.description_label)
        text_layout.addWidget(license_label)
        text_layout.addStretch(1)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)
        content_layout.addWidget(self.icon_label)
        content_layout.addLayout(text_layout, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(content_layout)
        layout.addWidget(buttons)


def _clipboard_result_text(text: str) -> str:
    return CLIPBOARD_THOUSANDS_SEPARATOR_RE.sub("", text)


STATIC_COMPLETIONS = sorted(
    {
        "abs",
        "arccos",
        "arcsin",
        "arctan",
        "average",
        "avg",
        "bin",
        "binary",
        "cbrt",
        "ceil",
        "cos",
        "cosh",
        "day",
        "days",
        "divide",
        "divide by",
        "floor",
        "fromunix",
        "hex",
        "hexadecimal",
        "hour",
        "hours",
        "in",
        "into",
        "ln",
        "log",
        "minus",
        "mod",
        "month",
        "months",
        "now",
        "oct",
        "octal",
        "off",
        "on",
        "percent",
        "pi",
        "plus",
        "prev",
        "round",
        "sci",
        "scientific",
        "sin",
        "sinh",
        "sqrt",
        "sum",
        "tan",
        "tanh",
        "time",
        "times",
        "today",
        "total",
        "week",
        "weeks",
        "year",
        "years",
        *UNIT_ALIASES.keys(),
        *CURRENCY_ALIASES.keys(),
        *CURRENCY_CODES,
        *TIMEZONES.keys(),
    },
    key=str.casefold,
)
HIGHLIGHT_KEYWORDS = sorted(
    {word for word in STATIC_COMPLETIONS if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:\s+[A-Za-z][A-Za-z0-9_]*)*", word)},
    key=len,
    reverse=True,
)
HIGHLIGHT_KEYWORD_RE = re.compile(
    r"(?<![A-Za-z_])(?:"
    + "|".join(re.escape(word).replace(r"\ ", r"\s+") for word in HIGHLIGHT_KEYWORDS)
    + r")(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


class CompletionTextEdit(StripedPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self._static_words = STATIC_COMPLETIONS
        self._dynamic_words: list[str] = []
        self.highlighter = CommentMarkdownHighlighter(self.document())
        self._model = QStringListModel(self)
        self.completer = QCompleter(self._model, self)
        self.completer.setWidget(self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.activated.connect(self.insert_completion)
        self.refresh_completions()

    def set_dynamic_words(self, words: list[str]) -> None:
        cleaned = sorted({word for word in words if word}, key=str.casefold)
        if cleaned != self._dynamic_words:
            self._dynamic_words = cleaned
            self.refresh_completions()
            self.highlighter.set_variable_words(cleaned)

    def completion_words(self) -> list[str]:
        return self._model.stringList()

    def refresh_completions(self) -> None:
        self._model.setStringList(sorted({*self._static_words, *self._dynamic_words}, key=str.casefold))

    def insert_completion(self, completion: str) -> None:
        cursor = self.textCursor()
        prefix = self.text_under_cursor()
        if prefix:
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix))
        cursor.insertText(completion)
        self.setTextCursor(cursor)

    def text_under_cursor(self) -> str:
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        selected = cursor.selectedText()
        return selected if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", selected) else ""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.completer.popup().isVisible() and event.key() in {
            Qt.Key.Key_Enter,
            Qt.Key.Key_Return,
            Qt.Key.Key_Escape,
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
        }:
            event.ignore()
            return
        manual_trigger = is_show_completions_shortcut(event)
        if not manual_trigger:
            super().keyPressEvent(event)
        prefix = self.text_under_cursor()
        if manual_trigger:
            self.show_completions(prefix)
        else:
            self.completer.popup().hide()

    def open_completion_popup(self) -> None:
        self.show_completions(self.text_under_cursor())

    def show_completions(self, prefix: str) -> None:
        self.completer.setCompletionPrefix(prefix)
        if self.completer.completionCount() == 0:
            self.completer.popup().hide()
            return
        popup = self.completer.popup()
        popup.setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width() + 24)
        self.completer.complete(rect)


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Pnumi")
        self.current_path: Path | None = None
        self.settings = settings or _app_settings()
        self.alternating_row_background = _settings_bool(self.settings, ALTERNATING_ROW_BACKGROUND_KEY, True)
        self.theme_mode = _settings_theme_mode(self.settings)
        self.dark_mode = False
        self.result_decimal_places = _settings_int(self.settings, RESULT_DECIMAL_PLACES_KEY, DEFAULT_DECIMAL_PLACES, minimum=0, maximum=20)
        self._loading_window_state = True
        self._loading_content = True
        self.resize(_settings_size(self.settings, WINDOW_SIZE_KEY, DEFAULT_WINDOW_SIZE))
        self.editor = CompletionTextEdit()
        self.editor.setObjectName("editor")
        self.editor.setPlaceholderText("Type calculations here")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.results = ResultPane()
        self.document_scrollbar = QScrollBar(Qt.Orientation.Vertical)
        font = QFont("Menlo")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(14)
        self.editor.setFont(font)
        self.results.setFont(font)

        self.document_surface = DocumentSurface(self.editor, self.results, self.document_scrollbar)
        self.splitter = self.document_surface.splitter
        self.setCentralWidget(self.document_surface)
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(80)
        self._update_timer.timeout.connect(self.recalculate)
        self.editor.textChanged.connect(self._update_timer.start)
        self.editor.textChanged.connect(self.refresh_autocomplete)
        self.editor.textChanged.connect(self.document_surface.update)
        self.editor.textChanged.connect(self._save_last_content)
        self.editor.updateRequest.connect(self._sync_result_scroll)
        self.editor.updateRequest.connect(lambda *_: self.document_surface.update())
        self.editor.verticalScrollBar().valueChanged.connect(self._sync_scrollbar_value)
        self.editor.verticalScrollBar().rangeChanged.connect(self._sync_scrollbar_range)
        self.document_scrollbar.valueChanged.connect(self._set_document_scroll)
        self._build_actions()
        self._connect_system_theme_changes()
        self.apply_settings()
        self.editor.setPlainText(self._initial_document_text())
        self._loading_content = False
        self._loading_window_state = False

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        edit_menu = self.menuBar().addMenu("&Edit")
        help_menu = self.menuBar().addMenu("&Help")

        open_action = QAction("&Import", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.import_file)
        file_menu.addAction(open_action)

        export_action = QAction("&Export", self)
        export_action.setShortcut(QKeySequence.StandardKey.Save)
        export_action.triggered.connect(self.export_file)
        file_menu.addAction(export_action)

        print_action = QAction("&Print", self)
        print_action.setShortcut(QKeySequence.StandardKey.Print)
        print_action.triggered.connect(self.print_document)
        file_menu.addAction(print_action)

        copy_result_action = QAction("Copy Current &Result", self)
        copy_result_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy_result_action.triggered.connect(self.copy_current_result)
        edit_menu.addAction(copy_result_action)

        copy_all_action = QAction("Copy &All", self)
        copy_all_action.setShortcut(QKeySequence("Alt+Ctrl+C"))
        copy_all_action.triggered.connect(self.copy_all)
        edit_menu.addAction(copy_all_action)

        delete_all_action = QAction("&Delete All", self)
        delete_all_action.setShortcut(QKeySequence("Alt+Ctrl+Backspace"))
        delete_all_action.triggered.connect(self.editor.clear)
        edit_menu.addAction(delete_all_action)

        surround_action = QAction("Surround with &Parentheses", self)
        surround_action.setShortcut(QKeySequence("Ctrl+Shift+0"))
        surround_action.triggered.connect(self.surround_with_parentheses)
        edit_menu.addAction(surround_action)

        show_completions_action = QAction("Show &Completions", self)
        show_completions_action.setObjectName("showCompletionsAction")
        show_completions_action.setShortcuts(SHOW_COMPLETIONS_SHORTCUTS)
        show_completions_action.triggered.connect(self.editor.open_completion_popup)
        edit_menu.addAction(show_completions_action)

        settings_action = QAction("&Settings...", self)
        settings_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        settings_action.setShortcut(QKeySequence.StandardKey.Preferences)
        settings_action.triggered.connect(self.open_settings_dialog)
        edit_menu.addAction(settings_action)

        about_action = QAction("&About Pnumi", self)
        about_action.setObjectName("aboutAction")
        about_action.setMenuRole(QAction.MenuRole.AboutRole)
        about_action.triggered.connect(self.open_about_dialog)
        help_menu.addAction(about_action)

    def _apply_style(self) -> None:
        theme = DARK_THEME if self.dark_mode else LIGHT_THEME
        self.document_surface.set_theme(theme)
        self.results.set_theme(theme)
        self.editor.highlighter.set_theme(theme)
        self.setStyleSheet(
            f"""
            QMainWindow {{ background: {theme.document_background.name()}; }}
            #documentSurface {{ background: {theme.document_background.name()}; }}
            QPlainTextEdit {{
                border: 0;
                padding: 22px;
                background: transparent;
                color: {theme.editor_text.name()};
                selection-background-color: {theme.selection_background.name()};
                selection-color: {theme.selection_text.name()};
            }}
            QPlainTextEdit > QWidget {{ background: transparent; }}
            #resultPane {{ color: {theme.result_text.name()}; background: transparent; }}
            QMenuBar {{ background: {theme.document_background.name()}; color: {theme.editor_text.name()}; }}
            QSplitter::handle {{ background: {theme.document_background.name()}; }}
            """
        )

    def _sync_result_scroll(self) -> None:
        self.results.verticalScrollBar().setValue(self.editor.verticalScrollBar().value())

    def _sync_scrollbar_value(self, value: int) -> None:
        self.document_scrollbar.setValue(value)
        self._sync_result_scroll()
        self.document_surface.update()

    def _sync_scrollbar_range(self, minimum: int, maximum: int) -> None:
        source = self.editor.verticalScrollBar()
        self.document_scrollbar.setRange(minimum, maximum)
        self.document_scrollbar.setPageStep(source.pageStep())
        self.document_scrollbar.setSingleStep(source.singleStep())
        self.document_scrollbar.setValue(source.value())

    def _set_document_scroll(self, value: int) -> None:
        self.editor.verticalScrollBar().setValue(value)
        self.results.verticalScrollBar().setValue(value)
        self.document_surface.update()

    def recalculate(self) -> None:
        document = evaluate_document(self.editor.toPlainText(), {"decimal_places": self.result_decimal_places})
        self.results.setPlainText("\n".join(document.displays))
        self.results.update_alternating_row_backgrounds()
        self.document_surface.update()
        self._sync_scrollbar_range(self.editor.verticalScrollBar().minimum(), self.editor.verticalScrollBar().maximum())

    def refresh_autocomplete(self) -> None:
        self.editor.set_dynamic_words(_document_variables(self.editor.toPlainText()))

    def _initial_document_text(self) -> str:
        value = self.settings.value(LAST_CONTENT_KEY, DEFAULT_DOCUMENT_TEXT)
        return value if isinstance(value, str) else DEFAULT_DOCUMENT_TEXT

    def _save_last_content(self) -> None:
        if self._loading_content:
            return
        self.settings.setValue(LAST_CONTENT_KEY, self.editor.toPlainText())
        self.settings.sync()

    def _save_window_size(self) -> None:
        if self._loading_window_state:
            return
        self.settings.setValue(WINDOW_SIZE_KEY, self.size())
        self.settings.sync()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._save_window_size()

    def closeEvent(self, event) -> None:
        self._save_window_size()
        super().closeEvent(event)

    def apply_settings(self) -> None:
        self.dark_mode = self._theme_mode_is_dark()
        self.editor.set_alternating_row_background_enabled(self.alternating_row_background)
        self.results.set_alternating_row_background_enabled(self.alternating_row_background)
        self.document_surface.set_alternating_row_background_enabled(self.alternating_row_background)
        self._apply_style()

    def set_alternating_row_background(self, enabled: bool) -> None:
        self.alternating_row_background = enabled
        self.settings.setValue(ALTERNATING_ROW_BACKGROUND_KEY, enabled)
        self.apply_settings()

    def set_dark_mode(self, enabled: bool) -> None:
        self.set_theme_mode(THEME_MODE_DARK if enabled else THEME_MODE_LIGHT)

    def set_theme_mode(self, mode: str) -> None:
        self.theme_mode = _normalize_theme_mode(mode)
        self.settings.setValue(THEME_MODE_KEY, self.theme_mode)
        self.apply_settings()
        self.settings.setValue(DARK_MODE_KEY, self.dark_mode)

    def set_result_decimal_places(self, places: int) -> None:
        self.result_decimal_places = max(0, min(int(places), 20))
        self.settings.setValue(RESULT_DECIMAL_PLACES_KEY, self.result_decimal_places)
        self.recalculate()

    def open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self.alternating_row_background, self.theme_mode, self.result_decimal_places, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_alternating_row_background(dialog.alternating_row_background_enabled())
            self.set_theme_mode(dialog.theme_mode())
            self.set_result_decimal_places(dialog.result_decimal_places())

    def open_about_dialog(self) -> None:
        AboutDialog(self).exec()

    def _connect_system_theme_changes(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        style_hints = app.styleHints()
        color_scheme_changed = getattr(style_hints, "colorSchemeChanged", None)
        if color_scheme_changed is not None:
            color_scheme_changed.connect(self._handle_system_color_scheme_changed)

    def _handle_system_color_scheme_changed(self, *_args) -> None:
        if self.theme_mode == THEME_MODE_SYSTEM:
            self.apply_settings()

    def _theme_mode_is_dark(self) -> bool:
        if self.theme_mode == THEME_MODE_DARK:
            return True
        if self.theme_mode == THEME_MODE_SYSTEM:
            return self._system_dark_mode()
        return False

    def _system_dark_mode(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark

    def current_result_text(self) -> str:
        cursor = self.editor.textCursor()
        line = cursor.blockNumber()
        lines = self.results.toPlainText().splitlines()
        return lines[line] if line < len(lines) else ""

    def copy_current_result(self) -> None:
        QApplication.clipboard().setText(_clipboard_result_text(self.current_result_text()))

    def copy_all(self) -> None:
        source = self.editor.toPlainText().splitlines()
        results = self.results.toPlainText().splitlines()
        rows = []
        for index, line in enumerate(source):
            result = _clipboard_result_text(results[index]) if index < len(results) else ""
            rows.append(f"{line}\t{result}" if result else line)
        QApplication.clipboard().setText("\n".join(rows))

    def surround_with_parentheses(self) -> None:
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        text = cursor.selectedText()
        cursor.insertText(f"({text})")

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import", "", "Numi files (*.numi);;Text files (*.txt);;All files (*)")
        if not path:
            return
        self.current_path = Path(path)
        self.editor.setPlainText(normalize_numi_import(self.current_path.read_text(encoding="utf-8")))

    def export_file(self) -> None:
        start = str(self.current_path) if self.current_path else "Untitled.numi"
        path, _ = QFileDialog.getSaveFileName(self, "Export", start, "Numi files (*.numi);;Text files (*.txt);;All files (*)")
        if not path:
            return
        target = Path(path)
        if target.suffix == "":
            target = target.with_suffix(".numi")
        target.write_text(self.editor.toPlainText(), encoding="utf-8")
        self.current_path = target

    def print_document(self) -> None:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec():
            self.editor.print_(printer)

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Pnumi", message)


def run(argv: list[str]) -> int:
    app = QApplication(argv)
    app.setOrganizationName(SETTINGS_ORGANIZATION)
    app.setOrganizationDomain(SETTINGS_ORGANIZATION_DOMAIN)
    app.setApplicationName(SETTINGS_APPLICATION)
    app.setApplicationVersion(_app_version())
    app.setWindowIcon(_app_icon())
    window = MainWindow()
    window.setWindowIcon(_app_icon())
    window.show()
    return app.exec()


def _app_settings() -> QSettings:
    return QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)


def _app_icon() -> QIcon:
    path = _resource_path("assets", "pnumi-icon.png")
    return QIcon(str(path)) if path.is_file() else QIcon()


def _app_icon_pixmap(size: int) -> QPixmap:
    pixmap = QPixmap(str(_resource_path("assets", "pnumi-icon.png")))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _app_version() -> str:
    try:
        return version("pnumi")
    except PackageNotFoundError:
        pyproject = _resource_path("pyproject.toml")
        if pyproject.is_file():
            return str(tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"])
    return "unknown"


def _resource_path(*parts: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root.joinpath(*parts)


def _document_variables(text: str) -> list[str]:
    words: list[str] = []
    for line in text.splitlines():
        match = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if match:
            words.append(match.group(1))
    return words


def _settings_bool(settings: QSettings, key: str, default: bool) -> bool:
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_theme_mode(value: str | bool) -> str:
    if isinstance(value, bool):
        return THEME_MODE_DARK if value else THEME_MODE_LIGHT
    return value if value in THEME_MODES else THEME_MODE_LIGHT


def _settings_theme_mode(settings: QSettings) -> str:
    value = settings.value(THEME_MODE_KEY)
    if isinstance(value, str) and value in THEME_MODES:
        return value
    return THEME_MODE_DARK if _settings_bool(settings, DARK_MODE_KEY, False) else THEME_MODE_LIGHT


def _settings_int(settings: QSettings, key: str, default: int, minimum: int, maximum: int) -> int:
    value = settings.value(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _settings_size(settings: QSettings, key: str, default: QSize) -> QSize:
    value = settings.value(key, default)
    if isinstance(value, QSize) and value.isValid():
        return value
    return default
