from __future__ import annotations

import logging
import re
import sys
import tomllib
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from math import ceil
from pathlib import Path

from platformdirs import user_log_dir
from PySide6.QtCore import (
    QObject,
    QPoint,
    QRectF,
    QRunnable,
    QSettings,
    QSize,
    QStringListModel,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPixmap,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextOption,
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
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QScrollBar,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from .currencies import CURRENCY_ALIASES, CURRENCY_CODES
from .engine import RESERVED_NAMES, TIMEZONES, evaluate_document
from .formatting import DEFAULT_DECIMAL_PLACES
from .models import LineResult
from .numi_import import normalize_numi_import
from .rates import default_rate_provider
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
FONT_SIZE_KEY = "editor/fontSize"
DEFAULT_FONT_SIZE = 14
WINDOW_SIZE_KEY = "window/size"
SETTINGS_ORGANIZATION = "gattacus.uk"
SETTINGS_ORGANIZATION_DOMAIN = "uk.gattacus"
SETTINGS_APPLICATION = "Pnumi"
DEFAULT_WINDOW_SIZE = QSize(920, 640)
DEFAULT_DOCUMENT_TEXT = "Cost: $20 + 56 EUR\nDiscounted: prev - 5% off\n\n1 meter 20 cm in cm\nround(1 month in days)"
SHOW_COMPLETIONS_SHORTCUTS = [QKeySequence("Meta+Space" if sys.platform == "darwin" else "Ctrl+Space")]
CLIPBOARD_THOUSANDS_SEPARATOR_RE = re.compile(r"(?<=\d)[ ,'\u2018\u2019](?=\d{3}(?:\D|$))")
RESULT_COLUMN_LEFT_PADDING = 8
RESULT_COLUMN_RIGHT_PADDING = 22
MIN_RESULT_COLUMN_WIDTH = 56
MAX_EVALUATION_WORKERS = 4


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


class ResultHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self.error_format = QTextCharFormat()
        self.error_format.setForeground(QColor("#ef4444"))

    def set_theme(self, theme: EditorTheme) -> None:
        if theme == LIGHT_THEME:
            self.error_format.setForeground(QColor("#ef4444"))
        else:
            self.error_format.setForeground(QColor("#f87171"))
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        if text.startswith("Error:"):
            self.setFormat(0, len(text), self.error_format)


class ResultPane(StripedPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.theme = LIGHT_THEME
        self.highlighter = ResultHighlighter(self.document())
        self.highlighter.set_theme(self.theme)
        self._hovered_result_line: int | None = None
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("resultPane")
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        option = self.document().defaultTextOption()
        option.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.document().setDefaultTextOption(option)

    def content_width(self, lines: list[str]) -> int:
        text_width = max((self.fontMetrics().horizontalAdvance(line) for line in lines if line), default=0)
        document_margin_width = ceil(self.document().documentMargin() * 2)
        result_padding = RESULT_COLUMN_LEFT_PADDING + RESULT_COLUMN_RIGHT_PADDING
        return max(MIN_RESULT_COLUMN_WIDTH, text_width + result_padding + document_margin_width)

    def fit_to_content(self, lines: list[str]) -> None:
        width = self.content_width(lines)
        self.setMinimumWidth(width)
        self.setMaximumWidth(width)

    def set_theme(self, theme: EditorTheme) -> None:
        self.theme = theme
        self.highlighter.set_theme(theme)
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
            self.viewport().setCursor(
                Qt.CursorShape.PointingHandCursor if line is not None else Qt.CursorShape.IBeamCursor
            )
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
            if result and not result.startswith("Error:"):
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
        text = self._result_text_for_line(line)
        if text.startswith("Error:"):
            return None
        return line

    def _result_pill_rect(self, line: int) -> QRectF | None:
        text = self._result_text_for_line(line)
        if not text:
            return None
        block = self.document().findBlockByNumber(line)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor_rect = self.cursorRect(cursor)
        width = self.fontMetrics().horizontalAdvance(text)
        height = max(cursor_rect.height(), self.fontMetrics().height())
        right = min(self.viewport().width(), cursor_rect.x() + 8)
        left = max(0, right - width - 16)
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
        self.warning_format = QTextCharFormat()
        self.warning_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self.warning_format.setUnderlineColor(QColor("red"))
        self._variable_words: list[str] = []

    def set_theme(self, theme: EditorTheme) -> None:
        self.comment_format.setForeground(theme.comment)
        self.variable_format.setForeground(theme.variable)
        self.keyword_format.setForeground(theme.keyword)
        self.warning_format.setForeground(theme.variable)
        self.rehighlight()

    def set_variable_words(self, words: list[str]) -> None:
        self._variable_words = sorted({word for word in words if word}, key=len, reverse=True)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for match in HIGHLIGHT_KEYWORD_RE.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.keyword_format)
        for word in self._variable_words:
            for match in re.finditer(rf"\b{re.escape(word)}\b", text):
                fmt = self.warning_format if word.lower() in TIER2_NAMES else self.variable_format
                self.setFormat(match.start(), match.end() - match.start(), fmt)
        assignment = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", text)
        if assignment:
            var_name = assignment.group(1)
            fmt = self.warning_format if var_name.lower() in TIER2_NAMES else self.variable_format
            self.setFormat(assignment.start(1), assignment.end(1) - assignment.start(1), fmt)
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
        font_size: int = DEFAULT_FONT_SIZE,
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
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 72)
        self.font_size_spinbox.setValue(font_size)
        font_size_row = QWidget()
        font_size_layout = QHBoxLayout(font_size_row)
        font_size_layout.setContentsMargins(0, 0, 0, 0)
        font_size_layout.addWidget(QLabel("Font size"))
        font_size_layout.addWidget(self.font_size_spinbox)
        font_size_layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.alternating_row_background_checkbox)
        layout.addWidget(theme_mode_row)
        layout.addWidget(decimal_places_row)
        layout.addWidget(font_size_row)
        layout.addWidget(buttons)

    def alternating_row_background_enabled(self) -> bool:
        return self.alternating_row_background_checkbox.isChecked()

    def dark_mode_enabled(self) -> bool:
        return self.theme_mode() == THEME_MODE_DARK

    def theme_mode(self) -> str:
        return str(self.theme_mode_combo.currentData())

    def result_decimal_places(self) -> int:
        return self.result_decimal_places_spinbox.value()

    def font_size(self) -> int:
        return self.font_size_spinbox.value()


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


class EvaluationWorkerSignals(QObject):
    finished = Signal(int, str, object, str)


class EvaluationWorker(QRunnable):
    def __init__(self, revision: int, text: str, decimal_places: int) -> None:
        super().__init__()
        self.revision = revision
        self.text = text
        self.decimal_places = decimal_places
        self.signals = EvaluationWorkerSignals()

    def run(self) -> None:
        try:
            document = evaluate_document(
                self.text,
                {
                    "decimal_places": self.decimal_places,
                    "rate_provider": default_rate_provider(),
                },
            )
            self.signals.finished.emit(self.revision, self.text, document.line_results, "")
        except Exception as exc:
            self.signals.finished.emit(self.revision, self.text, [], str(exc))


def _clipboard_result_text(text: str) -> str:
    return CLIPBOARD_THOUSANDS_SEPARATOR_RE.sub("", text)


STATIC_COMPLETIONS = sorted(
    {
        "abs",
        "arccos",
        "arcsin",
        "arctan",
        "as",
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
        "to",
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

TIER2_NAMES = {
    *(word.lower() for word in UNIT_ALIASES.keys()),
    *(word.lower() for word in CURRENCY_ALIASES.keys()),
    *(word.lower() for word in CURRENCY_CODES)
} - RESERVED_NAMES


class CompletionTextEdit(StripedPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self._line_errors: dict[int, str] = {}
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
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

    def set_line_errors(self, errors: dict[int, str]) -> None:
        self._line_errors = errors

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        cursor = self.cursorForPosition(pos)
        line = cursor.blockNumber()
        if line in self._line_errors:
            QToolTip.showText(event.globalPosition().toPoint(), self._line_errors[line], self.viewport())
            super().mouseMoveEvent(event)
            return

        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        word = cursor.selectedText()
        if word and word.lower() in TIER2_NAMES and word in self._dynamic_words:
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"Warning: '{word}' shadows a built-in unit or currency",
                self.viewport(),
            )
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().leaveEvent(event)



class Sheet(QWidget):
    def __init__(
        self,
        settings: QSettings,
        parent: QWidget | None = None,
        content: str = "",
        path: Path | None = None,
        title: str = "",
    ) -> None:
        super().__init__(parent)
        self.settings = settings
        self.current_path = path
        self.custom_title = title

        self.editor = CompletionTextEdit()
        self.editor.setObjectName("editor")
        self.editor.setPlaceholderText("Type calculations here")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self.results = ResultPane()
        self.document_scrollbar = QScrollBar(Qt.Orientation.Vertical)

        font = QFont("Menlo")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font_size = _settings_int(settings, FONT_SIZE_KEY, DEFAULT_FONT_SIZE, minimum=8, maximum=72)
        font.setPointSize(font_size)
        self.editor.setFont(font)
        self.results.setFont(font)

        self.document_surface = DocumentSurface(self.editor, self.results, self.document_scrollbar)
        self.splitter = self.document_surface.splitter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.document_surface)

        self.editor.updateRequest.connect(self._sync_result_scroll)
        self.editor.updateRequest.connect(lambda *_: self.document_surface.update())
        self.editor.verticalScrollBar().valueChanged.connect(self._sync_scrollbar_value)
        self.editor.verticalScrollBar().rangeChanged.connect(self._sync_scrollbar_range)
        self.document_scrollbar.valueChanged.connect(self._set_document_scroll)

        if content:
            self.editor.setPlainText(content)

    def set_theme(self, theme: EditorTheme) -> None:
        self.document_surface.set_theme(theme)
        self.results.set_theme(theme)
        self.editor.highlighter.set_theme(theme)

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

    def sync_scrollbar_range(self) -> None:
        source = self.editor.verticalScrollBar()
        self._sync_scrollbar_range(source.minimum(), source.maximum())


class TabBar(QTabBar):
    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            index = self.tabAt(event.position().toPoint())
            if index != -1:
                self.tabCloseRequested.emit(index)
                event.accept()
                return
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Pnumi")
        self.settings = settings or _app_settings()
        self.alternating_row_background = _settings_bool(self.settings, ALTERNATING_ROW_BACKGROUND_KEY, True)
        self.theme_mode = _settings_theme_mode(self.settings)
        self.dark_mode = False
        self.result_decimal_places = _settings_int(
            self.settings, RESULT_DECIMAL_PLACES_KEY, DEFAULT_DECIMAL_PLACES, minimum=0, maximum=20
        )
        self.font_size = _settings_int(self.settings, FONT_SIZE_KEY, DEFAULT_FONT_SIZE, minimum=8, maximum=72)
        self._loading_window_state = True
        self._loading_content = True
        self._evaluation_pool = QThreadPool(self)
        self._evaluation_pool.setMaxThreadCount(MAX_EVALUATION_WORKERS)
        self._evaluation_revision = 0
        self._active_evaluations = 0
        self._pending_evaluation: tuple[int, str, int] | None = None
        self._evaluation_workers: set[EvaluationWorker] = set()
        self.resize(_settings_size(self.settings, WINDOW_SIZE_KEY, DEFAULT_WINDOW_SIZE))

        # Set up Tab Bar
        self.tab_bar = TabBar()
        self.tab_bar.setTabsClosable(False)
        self.tab_bar.setMovable(True)
        self.tab_bar.tabCloseRequested.connect(self.close_tab)
        self.tab_bar.currentChanged.connect(self.switch_tab)
        self.tab_bar.tabMoved.connect(self.move_tab)
        self.tab_bar.tabBarDoubleClicked.connect(self.rename_tab_dialog)

        # Plus button for new tab
        self.new_tab_button = QToolButton()
        self.new_tab_button.setText("+")
        self.new_tab_button.setToolTip("New Sheet")
        self.new_tab_button.clicked.connect(self.add_new_empty_tab)

        # Tab container for horizontal layout
        self.tab_container = QWidget()
        self.tab_container.setObjectName("tabContainer")
        tab_layout = QHBoxLayout(self.tab_container)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        tab_layout.addWidget(self.tab_bar)
        tab_layout.addWidget(self.new_tab_button)
        tab_layout.addStretch(1)

        # Stacked Widget
        self.stacked_widget = QStackedWidget()

        central_widget = QWidget()
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tab_container)
        layout.addWidget(self.stacked_widget)
        self.setCentralWidget(central_widget)

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(80)
        self._update_timer.timeout.connect(self.recalculate)

        self._build_actions()
        self._connect_system_theme_changes()
        self.apply_settings()

        self.load_tabs()

        self._loading_content = False
        self._loading_window_state = False
        self.recalculate()
        self.refresh_autocomplete()

    @property
    def current_sheet(self) -> Sheet | None:
        return self.stacked_widget.currentWidget()

    @property
    def editor(self) -> CompletionTextEdit | None:
        sheet = self.current_sheet
        return sheet.editor if sheet else None

    @property
    def results(self) -> ResultPane | None:
        sheet = self.current_sheet
        return sheet.results if sheet else None

    @property
    def document_surface(self) -> DocumentSurface | None:
        sheet = self.current_sheet
        return sheet.document_surface if sheet else None

    @property
    def document_scrollbar(self) -> QScrollBar | None:
        sheet = self.current_sheet
        return sheet.document_scrollbar if sheet else None

    @property
    def splitter(self) -> QSplitter | None:
        sheet = self.current_sheet
        return sheet.splitter if sheet else None

    @property
    def current_path(self) -> Path | None:
        sheet = self.current_sheet
        return sheet.current_path if sheet else None

    @current_path.setter
    def current_path(self, value: Path | None) -> None:
        sheet = self.current_sheet
        if sheet:
            sheet.current_path = value
            if value:
                sheet.custom_title = value.name
            self._update_tab_titles()

    def add_sheet(self, content: str = "", path: Path | None = None, title: str = "") -> Sheet:
        # Generate default title if not provided
        if not title:
            if path:
                title = path.name
            else:
                existing_titles = set()
                for i in range(self.stacked_widget.count()):
                    widget = self.stacked_widget.widget(i)
                    if hasattr(widget, "custom_title"):
                        existing_titles.add(widget.custom_title)
                n = 1
                while f"Sheet {n}" in existing_titles:
                    n += 1
                title = f"Sheet {n}"

        sheet = Sheet(self.settings, self, content, path, title)

        # Apply current dark mode setting to the sheet
        theme = DARK_THEME if self.dark_mode else LIGHT_THEME
        sheet.set_theme(theme)

        # Apply alternating background
        sheet.editor.set_alternating_row_background_enabled(self.alternating_row_background)
        sheet.results.set_alternating_row_background_enabled(self.alternating_row_background)
        sheet.document_surface.set_alternating_row_background_enabled(self.alternating_row_background)

        # Connect textChanged signals
        sheet.editor.textChanged.connect(lambda: self._on_sheet_text_changed(sheet))
        sheet.editor.textChanged.connect(self._save_tabs_state)

        self.stacked_widget.addWidget(sheet)
        index = self.tab_bar.addTab("")  # Title set by _update_tab_titles

        # Add custom close button to override low-contrast OS defaults on macOS/etc.
        btn = QToolButton()
        btn.setText("×")
        btn.setObjectName("tabCloseButton")
        btn.setToolTip("Close Tab")
        btn.clicked.connect(lambda _, s=sheet: self.close_sheet(s))
        self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.LeftSide, None)
        self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
        self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, btn)

        self._update_tab_titles()
        self._update_tab_bar_visibility()

        return sheet

    def close_sheet(self, sheet: Sheet) -> None:
        index = self.stacked_widget.indexOf(sheet)
        if index != -1:
            self.close_tab(index)

    def add_new_empty_tab(self) -> None:
        sheet = self.add_sheet("")
        index = self.stacked_widget.indexOf(sheet)
        self.stacked_widget.setCurrentIndex(index)
        self.tab_bar.setCurrentIndex(index)
        if self.editor:
            self.editor.setFocus()

    def close_tab(self, index: int) -> None:
        sheet = self.stacked_widget.widget(index)
        if sheet and sheet.editor and sheet.editor.toPlainText().strip():
            reply = QMessageBox.question(
                self,
                "Close Tab",
                "Are you sure you want to close this tab?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        if self.stacked_widget.count() <= 1:
            if self.editor:
                self.editor.clear()
            return

        widget = self.stacked_widget.widget(index)
        self.stacked_widget.removeWidget(widget)
        widget.deleteLater()

        self.tab_bar.removeTab(index)

        self._update_tab_titles()
        self._update_tab_bar_visibility()
        self._save_tabs_state()
        self.recalculate()
        self.refresh_autocomplete()

    def switch_tab(self, index: int) -> None:
        if 0 <= index < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(index)
            self.recalculate()
            self.refresh_autocomplete()
            self._save_tabs_state()

    def move_tab(self, from_index: int, to_index: int) -> None:
        widget = self.stacked_widget.widget(from_index)
        self.stacked_widget.removeWidget(widget)
        self.stacked_widget.insertWidget(to_index, widget)
        # Keep current synchronized
        self.stacked_widget.setCurrentWidget(widget)
        self.tab_bar.setCurrentIndex(to_index)
        self._update_tab_titles()
        self._save_tabs_state()

    def rename_tab_dialog(self, index: int) -> None:
        if 0 <= index < self.tab_bar.count():
            sheet = self.stacked_widget.widget(index)
            current_title = sheet.custom_title
            new_title, ok = QInputDialog.getText(self, "Rename Sheet", "Enter new name:", text=current_title)
            if ok and new_title.strip():
                sheet.custom_title = new_title.strip()
                self._update_tab_titles()
                self._save_tabs_state()

    def _update_tab_titles(self) -> None:
        for i in range(self.tab_bar.count()):
            sheet = self.stacked_widget.widget(i)
            self.tab_bar.setTabText(i, sheet.custom_title)

    def _update_tab_bar_visibility(self) -> None:
        visible = self.tab_bar.count() > 1
        self.tab_container.setVisible(visible)

    def _on_sheet_text_changed(self, sheet: Sheet) -> None:
        if sheet == self.current_sheet:
            self._update_timer.start()
            self.refresh_autocomplete()

    def _save_tabs_state(self) -> None:
        if self._loading_content:
            return

        count = self.stacked_widget.count()
        self.settings.setValue("tabs/count", count)
        self.settings.setValue("tabs/current", self.stacked_widget.currentIndex())

        for i in range(count):
            sheet = self.stacked_widget.widget(i)
            self.settings.setValue(f"tabs/{i}/content", sheet.editor.toPlainText())
            self.settings.setValue(f"tabs/{i}/path", str(sheet.current_path) if sheet.current_path else "")
            self.settings.setValue(f"tabs/{i}/title", sheet.custom_title)

        if self.editor:
            self.settings.setValue(LAST_CONTENT_KEY, self.editor.toPlainText())

        self.settings.sync()

    def load_tabs(self) -> None:
        self._loading_content = True

        count = _settings_int(self.settings, "tabs/count", 0, minimum=0, maximum=100)
        current_index = _settings_int(self.settings, "tabs/current", 0, minimum=0, maximum=100)

        loaded_any = False
        if count > 0:
            for i in range(count):
                content = self.settings.value(f"tabs/{i}/content", "")
                path_str = self.settings.value(f"tabs/{i}/path", "")
                title = self.settings.value(f"tabs/{i}/title", "")
                path = Path(path_str) if path_str else None

                if not isinstance(content, str):
                    content = ""

                self.add_sheet(content, path, title if isinstance(title, str) else "")
                loaded_any = True

        if not loaded_any:
            legacy_content = self.settings.value(LAST_CONTENT_KEY, None)
            if isinstance(legacy_content, str):
                self.add_sheet(legacy_content)
            else:
                self.add_sheet(DEFAULT_DOCUMENT_TEXT)

        if 0 <= current_index < self.stacked_widget.count():
            self.stacked_widget.setCurrentIndex(current_index)
            self.tab_bar.setCurrentIndex(current_index)
        else:
            self.stacked_widget.setCurrentIndex(0)
            self.tab_bar.setCurrentIndex(0)

        self._update_tab_bar_visibility()
        self._update_tab_titles()
        self._loading_content = False

    def _build_actions(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        edit_menu = self.menuBar().addMenu("&Edit")
        help_menu = self.menuBar().addMenu("&Help")

        new_tab_action = QAction("&New Tab", self)
        new_tab_action.setShortcut(QKeySequence.StandardKey.AddTab)
        new_tab_action.triggered.connect(self.add_new_empty_tab)
        file_menu.addAction(new_tab_action)

        close_tab_action = QAction("&Close Tab", self)
        close_tab_action.setShortcut(QKeySequence.StandardKey.Close)
        close_tab_action.triggered.connect(lambda: self.close_tab(self.tab_bar.currentIndex()))
        file_menu.addAction(close_tab_action)

        file_menu.addSeparator()

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
        delete_all_action.triggered.connect(lambda: self.editor.clear() if self.editor else None)
        edit_menu.addAction(delete_all_action)

        surround_action = QAction("Surround with &Parentheses", self)
        surround_action.setObjectName("surroundAction")
        if sys.platform == "win32":
            surround_action.setShortcuts([QKeySequence("Ctrl+Shift+9"), QKeySequence("Ctrl+Shift+0")])
        else:
            surround_action.setShortcut(QKeySequence("Ctrl+Shift+0"))
        surround_action.triggered.connect(self.surround_with_parentheses)
        edit_menu.addAction(surround_action)

        show_completions_action = QAction("Show &Completions", self)
        show_completions_action.setObjectName("showCompletionsAction")
        show_completions_action.setShortcuts(SHOW_COMPLETIONS_SHORTCUTS)
        show_completions_action.triggered.connect(lambda: self.editor.open_completion_popup() if self.editor else None)
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
        for i in range(self.stacked_widget.count()):
            self.stacked_widget.widget(i).set_theme(theme)

        # Backgrounds and borders for visual tab bar separation
        tab_bar_bg = theme.alternate_row_background.name()
        active_tab_bg = theme.document_background.name()
        tab_border_color = "rgba(255, 255, 255, 0.08)" if self.dark_mode else "rgba(0, 0, 0, 0.12)"
        hover_bg = "rgba(255, 255, 255, 0.05)" if self.dark_mode else "rgba(0, 0, 0, 0.05)"
        close_hover_bg = "rgba(255, 255, 255, 0.15)" if self.dark_mode else "rgba(0, 0, 0, 0.1)"

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
            #resultPane {{
                color: {theme.result_text.name()};
                background: transparent;
                padding-left: {RESULT_COLUMN_LEFT_PADDING}px;
                padding-right: {RESULT_COLUMN_RIGHT_PADDING}px;
            }}
            QMenuBar {{ background: {theme.document_background.name()}; color: {theme.editor_text.name()}; }}
            QSplitter::handle {{ background: {theme.document_background.name()}; }}
            #tabContainer {{
                background: {tab_bar_bg};
                border-bottom: 1px solid {tab_border_color};
            }}
            QTabBar {{
                background: {tab_bar_bg};
            }}
            QTabBar::tab {{
                background: transparent;
                color: {theme.editor_text.name()};
                padding: 6px 12px;
                border: none;
                font-family: 'SF Pro Text', -apple-system, sans-serif;
                font-size: 13px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background: {active_tab_bg};
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:!selected {{
                font-weight: normal;
                color: rgba({theme.editor_text.red()}, {theme.editor_text.green()}, {theme.editor_text.blue()}, 0.65);
            }}
            QTabBar::tab:!selected:hover {{
                background: {hover_bg};
                color: rgba({theme.editor_text.red()}, {theme.editor_text.green()}, {theme.editor_text.blue()}, 0.85);
            }}
            QTabBar::close-button {{
                image: none;
                width: 0px;
                height: 0px;
            }}
            #tabCloseButton {{
                color: {theme.editor_text.name()};
                background: transparent;
                border: none;
                font-family: 'SF Pro Text', -apple-system, sans-serif;
                font-size: 14px;
                font-weight: bold;
                padding: 0px 4px;
                margin-left: 4px;
            }}
            #tabCloseButton:hover {{
                background: {close_hover_bg};
                border-radius: 2px;
            }}
            QToolButton {{
                background: transparent;
                border: none;
                color: {theme.editor_text.name()};
                font-size: 16px;
                padding: 2px 8px;
            }}
            QToolButton:hover {{
                background: {hover_bg};
                border-radius: 4px;
            }}
            """
        )

    def recalculate(self) -> None:
        if not self.editor:
            return
        self._evaluation_revision += 1
        self._pending_evaluation = (self._evaluation_revision, self.editor.toPlainText(), self.result_decimal_places)
        self._start_pending_evaluation()

    def _start_pending_evaluation(self) -> None:
        if self._active_evaluations >= MAX_EVALUATION_WORKERS or self._pending_evaluation is None:
            return
        revision, text, decimal_places = self._pending_evaluation
        self._pending_evaluation = None
        self._active_evaluations += 1
        worker = EvaluationWorker(revision, text, decimal_places)
        self._evaluation_workers.add(worker)

        def handle_finished(
            revision: int, text: str, displays: object, error: str, *, worker: EvaluationWorker = worker
        ) -> None:
            self._handle_evaluation_finished(worker, revision, text, displays, error)

        worker.signals.finished.connect(handle_finished)
        self._evaluation_pool.start(worker)

    def _handle_evaluation_finished(
        self, worker: EvaluationWorker, revision: int, text: str, displays: object, error: str
    ) -> None:
        self._evaluation_workers.discard(worker)
        self._active_evaluations = max(0, self._active_evaluations - 1)
        if not isValid(self):
            return
        if not self.editor:
            return
        try:
            current_text = self.editor.toPlainText()
        except RuntimeError:
            return
        if revision == self._evaluation_revision and text == current_text:
            line_results = displays if isinstance(displays, list) else []
            if error:
                line_results = []
            self._apply_evaluation_results(line_results)
        self._start_pending_evaluation()

    def _apply_evaluation_results(self, line_results: list[LineResult]) -> None:
        if not self.results:
            return
        displays = []
        line_errors = {}
        for idx, line in enumerate(line_results):
            if line.diagnostics:
                displays.append(f"Error: {line.diagnostics[0]}")
                line_errors[idx] = line.diagnostics[0]
            else:
                displays.append(line.display)
        if not line_results and self.editor:
            displays = ["" for _ in self.editor.toPlainText().splitlines()]

        self.results.setPlainText("\n".join(displays))
        self.results.fit_to_content(displays)
        self.results.update_alternating_row_backgrounds()
        if self.editor:
            self.editor.set_line_errors(line_errors)
        if self.document_surface:
            self.document_surface.update()
        if self.current_sheet:
            self.current_sheet.sync_scrollbar_range()

    def refresh_autocomplete(self) -> None:
        if self.editor:
            self.editor.set_dynamic_words(_document_variables(self.editor.toPlainText()))

    def _initial_document_text(self) -> str:
        value = self.settings.value(LAST_CONTENT_KEY, DEFAULT_DOCUMENT_TEXT)
        return value if isinstance(value, str) else DEFAULT_DOCUMENT_TEXT

    def _save_last_content(self) -> None:
        if self._loading_content:
            return
        if self.editor:
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
        self._evaluation_revision += 1
        self._pending_evaluation = None
        self._evaluation_pool.clear()
        self._save_tabs_state()
        self._save_window_size()
        super().closeEvent(event)

    def apply_settings(self) -> None:
        self.dark_mode = self._theme_mode_is_dark()
        for i in range(self.stacked_widget.count()):
            sheet = self.stacked_widget.widget(i)
            sheet.editor.set_alternating_row_background_enabled(self.alternating_row_background)
            sheet.results.set_alternating_row_background_enabled(self.alternating_row_background)
            sheet.document_surface.set_alternating_row_background_enabled(self.alternating_row_background)
            font = sheet.editor.font()
            font.setPointSize(self.font_size)
            sheet.editor.setFont(font)
            sheet.results.setFont(font)
            sheet.results.fit_to_content(sheet.results.toPlainText().splitlines())
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

    def set_font_size(self, size: int) -> None:
        self.font_size = max(8, min(int(size), 72))
        self.settings.setValue(FONT_SIZE_KEY, self.font_size)
        self.apply_settings()

    def open_settings_dialog(self) -> None:
        dialog = SettingsDialog(
            self.alternating_row_background,
            self.theme_mode,
            self.result_decimal_places,
            self.font_size,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_alternating_row_background(dialog.alternating_row_background_enabled())
            self.set_theme_mode(dialog.theme_mode())
            self.set_result_decimal_places(dialog.result_decimal_places())
            self.set_font_size(dialog.font_size())

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
        if not self.editor or not self.results:
            return ""
        cursor = self.editor.textCursor()
        line = cursor.blockNumber()
        lines = self.results.toPlainText().splitlines()
        return lines[line] if line < len(lines) else ""

    def copy_current_result(self) -> None:
        text = self.current_result_text()
        if text.startswith("Error:"):
            text = ""
        QApplication.clipboard().setText(_clipboard_result_text(text))

    def copy_all(self) -> None:
        if not self.editor or not self.results:
            return
        source = self.editor.toPlainText().splitlines()
        results = self.results.toPlainText().splitlines()
        rows = []
        for index, line in enumerate(source):
            result = _clipboard_result_text(results[index]) if index < len(results) else ""
            if result.startswith("Error:"):
                result = ""
            rows.append(f"{line}\t{result}" if result else line)
        QApplication.clipboard().setText("\n".join(rows))

    def surround_with_parentheses(self) -> None:
        if not self.editor:
            return
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        text = cursor.selectedText()
        cursor.insertText(f"({text})")

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import", "", "Numi files (*.numi);;Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        self.current_path = Path(path)
        if self.editor:
            self.editor.setPlainText(normalize_numi_import(self.current_path.read_text(encoding="utf-8")))

    def export_file(self) -> None:
        if not self.editor:
            return
        start = str(self.current_path) if self.current_path else "Untitled.numi"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export", start, "Numi files (*.numi);;Text files (*.txt);;All files (*)"
        )
        if not path:
            return
        target = Path(path)
        if target.suffix == "":
            target = target.with_suffix(".numi")
        target.write_text(self.editor.toPlainText(), encoding="utf-8")
        self.current_path = target

    def print_document(self) -> None:
        if not self.editor:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec():
            self.editor.print_(printer)

    def show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Pnumi", message)


def run(argv: list[str]) -> int:
    _configure_logging()
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


def _configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        log_dir = Path(user_log_dir("Pnumi", "Pnumi"))
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.insert(0, logging.FileHandler(log_dir / "pnumi.log", encoding="utf-8"))
    except Exception:
        pass
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


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
