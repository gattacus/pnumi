from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextCursor

from pnumi.ui import LINK_MODIFIER, CompletionTextEdit


@pytest.fixture
def editor(qtbot):
    widget = CompletionTextEdit()
    qtbot.addWidget(widget)
    return widget


def select(editor, position, anchor=None):
    cursor = editor.textCursor()
    cursor.setPosition(position if anchor is None else anchor)
    cursor.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)


def key(editor, code, modifiers):
    editor.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, code, modifiers))


def assert_undo_redo(editor, before, after):
    assert editor.toPlainText() == after
    editor.undo()
    assert editor.toPlainText() == before
    editor.redo()
    assert editor.toPlainText() == after


@pytest.mark.parametrize("modifier", [Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.MetaModifier])
@pytest.mark.parametrize(
    ("before", "position", "after", "new_position"),
    [
        ("one\ntwo", 1, "one\none\ntwo", 5),
        ("one\ntwo", 5, "one\ntwo\ntwo", 9),
        ("one\n", 4, "one\n\n", 5),
        ("", 0, "\n", 1),
        ("😀\ntwo", 2, "😀\n😀\ntwo", 5),
    ],
)
def test_duplicate_line(editor, modifier, before, position, after, new_position):
    editor.setPlainText(before)
    select(editor, position)
    key(editor, Qt.Key.Key_D, modifier)
    assert editor.textCursor().position() == new_position
    assert_undo_redo(editor, before, after)


@pytest.mark.parametrize(("position", "anchor"), [(5, 1), (1, 5)])
def test_duplicate_multiline_selection(editor, position, anchor):
    editor.setPlainText("one\ntwo")
    select(editor, position, anchor)
    key(editor, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    assert editor.textCursor().selectedText() == "ne\u2029t"
    assert_undo_redo(editor, "one\ntwo", "one\ntne\ntwo")


@pytest.mark.parametrize(
    ("before", "position", "direction", "after", "new_position"),
    [
        ("one\ntwo", 1, 1, "two\none", 5),
        ("one\ntwo", 5, -1, "two\none", 1),
        ("one\ntwo\n", 5, 1, "one\n\ntwo", 6),
        ("one\ntwo\n", 8, -1, "one\n\ntwo", 4),
        ("one\ntwo\nthree\n", 5, -1, "two\none\nthree\n", 1),
        ("😀\ntwo", 4, -1, "two\n😀", 1),
        ("one\n😀", 1, 1, "😀\none", 4),
    ],
)
def test_move_line(editor, before, position, direction, after, new_position):
    editor.setPlainText(before)
    select(editor, position)
    code = Qt.Key.Key_Up if direction < 0 else Qt.Key.Key_Down
    key(editor, code, Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
    assert editor.textCursor().position() == new_position
    assert_undo_redo(editor, before, after)


@pytest.mark.parametrize(("position", "anchor"), [(8, 4), (4, 8)])
def test_move_selected_lines_excludes_block_at_selection_end(editor, position, anchor):
    before = "one\ntwo\nthree"
    editor.setPlainText(before)
    select(editor, position, anchor)
    key(editor, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
    assert editor.textCursor().position() == min(position + 6, 13)
    assert editor.textCursor().anchor() == min(anchor + 6, 13)
    assert editor.textCursor().selectedText() == "two"
    assert_undo_redo(editor, before, "one\nthree\ntwo")


@pytest.mark.parametrize(("position", "direction"), [(0, -1), (5, 1)])
def test_move_at_document_boundary_is_noop(editor, position, direction):
    editor.setPlainText("one\ntwo")
    select(editor, position)
    editor._move_current_line_or_selection(direction)
    assert editor.toPlainText() == "one\ntwo"
    assert editor.textCursor().position() == position
    assert not editor.document().isUndoAvailable()


def test_move_keeps_earlier_undo_history(editor):
    editor.setPlainText("one\ntwo")
    select(editor, 7)
    editor.insertPlainText("!")
    editor._move_current_line_or_selection(-1)
    assert editor.toPlainText() == "two!\none"
    editor.undo()
    assert editor.toPlainText() == "one\ntwo!"
    editor.undo()
    assert editor.toPlainText() == "one\ntwo"


@pytest.mark.parametrize(
    ("before", "position", "anchor", "after"),
    [
        ("one\ntwo", 1, None, "two"),
        ("one\ntwo", 5, None, "one"),
        ("one\n", 4, None, "one"),
        ("😀\ntwo", 2, None, "two"),
        ("one\ntwo\nthree", 8, 4, "one\nthree"),
        ("one\ntwo\nthree", 4, 8, "one\nthree"),
    ],
)
def test_delete_line_or_selected_lines(editor, before, position, anchor, after):
    editor.setPlainText(before)
    select(editor, position, anchor)
    key(editor, Qt.Key.Key_Backspace, Qt.KeyboardModifier.ControlModifier)
    assert_undo_redo(editor, before, after)


def test_extra_modifiers_do_not_trigger_line_shortcuts(editor):
    event = QKeyEvent(
        QKeyEvent.Type.KeyPress, Qt.Key.Key_Backspace,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
    )
    assert not editor._handle_editor_shortcut_keypress(event)


@pytest.mark.parametrize("modifier", [LINK_MODIFIER, Qt.KeyboardModifier.NoModifier])
def test_url_opens_only_on_modifier_click(editor, qtbot, monkeypatch, modifier):
    opened = []
    monkeypatch.setattr("pnumi.ui.QDesktopServices.openUrl", lambda url: opened.append(url.toString()))
    editor.setPlainText("https://example.com")
    editor.show()
    select(editor, 8)
    point = editor.cursorRect().center()
    qtbot.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, modifier, point)
    assert opened == (["https://example.com"] if modifier == LINK_MODIFIER else [])


@pytest.mark.parametrize("direction", [-1, 1])
@pytest.mark.parametrize("reversed_selection", [False, True])
def test_move_multiple_selected_lines(editor, direction, reversed_selection):
    before = "a\nb\nc\nd"
    editor.setPlainText(before)
    select(editor, 5 if not reversed_selection else 2, 2 if not reversed_selection else 5)
    editor._move_current_line_or_selection(direction)
    assert editor.textCursor().selectedText() == "b\u2029c"
    assert (editor.textCursor().position() < editor.textCursor().anchor()) == reversed_selection
    assert_undo_redo(editor, before, "b\nc\na\nd" if direction < 0 else "a\nd\nb\nc")


@pytest.mark.parametrize("operation", ["duplicate", "move"])
def test_line_edits_preserve_character_formatting(editor, operation):
    from PySide6.QtGui import QColor, QTextCharFormat

    editor.setPlainText("one\ntwo")
    select(editor, 3, 0)
    format_ = QTextCharFormat()
    format_.setForeground(QColor("#ff0000"))
    editor.textCursor().mergeCharFormat(format_)
    select(editor, 1)
    if operation == "duplicate":
        editor._duplicate_selection_or_line()
    else:
        editor._move_current_line_or_selection(1)
    select(editor, 5, 4)
    assert editor.textCursor().charFormat().foreground().color().name() == "#ff0000"
