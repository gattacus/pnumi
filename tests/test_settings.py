from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings, QSize

from pnumi.formatting import DEFAULT_DECIMAL_PLACES
from pnumi.settings import (
    ALTERNATING_ROW_BACKGROUND_KEY,
    DARK_MODE_KEY,
    FONT_SIZE_KEY,
    RESULT_DECIMAL_PLACES_KEY,
    TABS_COUNT_KEY,
    TABS_CURRENT_KEY,
    THEME_MODE_DARK,
    THEME_MODE_KEY,
    THEME_MODE_LIGHT,
    THEME_MODE_SYSTEM,
    THEME_MODES,
    WINDOW_SIZE_KEY,
    AppSettings,
    _validate_bool,
    _validate_size,
    _validate_theme_mode,
    load_settings,
    save_settings,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def qsettings(tmp_path) -> QSettings:
    """Return a QSettings instance backed by a temp file."""
    return QSettings(str(tmp_path / "test.conf"), QSettings.Format.IniFormat)


@pytest.fixture
def clean_settings(qsettings: QSettings) -> AppSettings:
    """Load settings from empty QSettings (all defaults)."""
    return AppSettings.load(qsettings)


# ── Defaults ──────────────────────────────────────────────────────────────────


class TestDefaults:
    def test_all_defaults_from_empty_store(self, clean_settings: AppSettings) -> None:
        assert clean_settings.alternating_row_background is True
        assert clean_settings.theme_mode == THEME_MODE_LIGHT
        assert clean_settings.result_decimal_places == DEFAULT_DECIMAL_PLACES
        assert clean_settings.font_size == 14
        assert clean_settings.window_size == QSize(920, 640)
        assert clean_settings.tabs_count == 0
        assert clean_settings.tabs_current == 0

    def test_theme_mode_effective_defaults_to_light(self, clean_settings: AppSettings) -> None:
        assert clean_settings.theme_mode_effective == THEME_MODE_LIGHT


# ── Validator Functions ───────────────────────────────────────────────────────


class TestValidateBool:
    def test_native_bool_true(self) -> None:
        assert _validate_bool(True) is True

    def test_native_bool_false(self) -> None:
        assert _validate_bool(False) is False

    def test_string_true(self) -> None:
        assert _validate_bool("true") is True

    def test_string_yes(self) -> None:
        assert _validate_bool("yes") is True

    def test_string_on(self) -> None:
        assert _validate_bool("on") is True

    def test_string_1(self) -> None:
        assert _validate_bool("1") is True

    def test_string_false(self) -> None:
        assert _validate_bool("false") is False

    def test_string_no(self) -> None:
        assert _validate_bool("no") is False

    def test_string_0(self) -> None:
        assert _validate_bool("0") is False

    def test_integer_1(self) -> None:
        assert _validate_bool(1) is True

    def test_integer_0(self) -> None:
        assert _validate_bool(0) is False


class TestValidateThemeMode:
    def test_bool_true_becomes_dark(self) -> None:
        assert _validate_theme_mode(True) == THEME_MODE_DARK

    def test_bool_false_becomes_light(self) -> None:
        assert _validate_theme_mode(False) == THEME_MODE_LIGHT

    def test_valid_system(self) -> None:
        assert _validate_theme_mode(THEME_MODE_SYSTEM) == THEME_MODE_SYSTEM

    def test_valid_light(self) -> None:
        assert _validate_theme_mode(THEME_MODE_LIGHT) == THEME_MODE_LIGHT

    def test_valid_dark(self) -> None:
        assert _validate_theme_mode(THEME_MODE_DARK) == THEME_MODE_DARK

    def test_invalid_string_returns_light_default(self) -> None:
        assert _validate_theme_mode("invalid") == THEME_MODE_LIGHT

    def test_none_returns_light_default(self) -> None:
        assert _validate_theme_mode(None) == THEME_MODE_LIGHT


class TestValidateSize:
    def test_valid_qsize(self) -> None:
        size = QSize(800, 600)
        assert _validate_size(size, QSize(920, 640)) == size

    def test_invalid_qsize_returns_default(self) -> None:
        default = QSize(920, 640)
        assert _validate_size(QSize(), default) == default

    def test_none_returns_default(self) -> None:
        default = QSize(920, 640)
        assert _validate_size(None, default) == default

    def test_string_returns_default(self) -> None:
        default = QSize(920, 640)
        assert _validate_size("800x600", default) == default


# ── AppSettings Validation ───────────────────────────────────────────────────


class TestAppSettingsValidation:
    @pytest.mark.parametrize(
        ("key", "attribute", "raw", "expected"),
        [
            (FONT_SIZE_KEY, "font_size", "200", 72),
            (FONT_SIZE_KEY, "font_size", "2", 8),
            (RESULT_DECIMAL_PLACES_KEY, "result_decimal_places", "50", 20),
            (RESULT_DECIMAL_PLACES_KEY, "result_decimal_places", "-5", 0),
            (TABS_COUNT_KEY, "tabs_count", "999", 100),
            (TABS_CURRENT_KEY, "tabs_current", "-1", 0),
        ],
    )
    def test_numeric_strings_are_clamped_after_store_reload(self, tmp_path, key, attribute, raw, expected) -> None:
        path = str(tmp_path / "strings.ini")
        stored = QSettings(path, QSettings.Format.IniFormat)
        stored.setValue(key, raw)
        stored.sync()

        loaded = AppSettings.load(QSettings(path, QSettings.Format.IniFormat))
        assert getattr(loaded, attribute) == expected

    def test_clamps_font_size_below_min(self, qsettings: QSettings, caplog) -> None:
        qsettings.setValue(FONT_SIZE_KEY, 2)
        settings = AppSettings.load(qsettings)
        assert settings.font_size == 8
        assert "clamped" in caplog.text.lower() or "8" in caplog.text

    def test_clamps_font_size_above_max(self, qsettings: QSettings, caplog) -> None:
        qsettings.setValue(FONT_SIZE_KEY, 200)
        settings = AppSettings.load(qsettings)
        assert settings.font_size == 72

    def test_clamps_decimal_places_below_min(self, qsettings: QSettings) -> None:
        qsettings.setValue(RESULT_DECIMAL_PLACES_KEY, -5)
        settings = AppSettings.load(qsettings)
        assert settings.result_decimal_places == 0

    def test_clamps_decimal_places_above_max(self, qsettings: QSettings) -> None:
        qsettings.setValue(RESULT_DECIMAL_PLACES_KEY, 50)
        settings = AppSettings.load(qsettings)
        assert settings.result_decimal_places == 20

    def test_clamps_tabs_count_above_max(self, qsettings: QSettings) -> None:
        qsettings.setValue(TABS_COUNT_KEY, 999)
        settings = AppSettings.load(qsettings)
        assert settings.tabs_count == 100

    def test_rejects_invalid_theme_mode(self, qsettings: QSettings, caplog) -> None:
        qsettings.setValue(THEME_MODE_KEY, "invalid_theme")
        settings = AppSettings.load(qsettings)
        assert settings.theme_mode == THEME_MODE_LIGHT

    def test_invalid_string_for_int_uses_default(self, qsettings: QSettings, caplog) -> None:
        qsettings.setValue(FONT_SIZE_KEY, "not_a_number")
        settings = AppSettings.load(qsettings)
        assert settings.font_size == 14

    def test_none_value_uses_default(self, qsettings: QSettings) -> None:
        qsettings.remove(FONT_SIZE_KEY)
        settings = AppSettings.load(qsettings)
        assert settings.font_size == 14

    def test_valid_window_size_preserved(self, qsettings: QSettings) -> None:
        qsettings.setValue(WINDOW_SIZE_KEY, QSize(1200, 800))
        settings = AppSettings.load(qsettings)
        assert settings.window_size == QSize(1200, 800)

    def test_invalid_window_size_uses_default(self, qsettings: QSettings) -> None:
        qsettings.setValue(WINDOW_SIZE_KEY, "invalid")
        settings = AppSettings.load(qsettings)
        assert settings.window_size == QSize(920, 640)


# ── Legacy darkMode Migration ────────────────────────────────────────────────


class TestLegacyDarkModeMigration:
    @pytest.mark.parametrize("mode", [THEME_MODE_LIGHT, THEME_MODE_SYSTEM])
    def test_theme_changes_override_legacy_value_and_survive_reload(self, qsettings, mode) -> None:
        qsettings.setValue(DARK_MODE_KEY, True)
        settings = AppSettings.load(qsettings)
        assert settings.theme_mode == THEME_MODE_DARK

        settings.set_theme_mode(mode)
        assert settings.theme_mode_effective == mode
        settings.save(qsettings)
        assert AppSettings.load(qsettings).theme_mode_effective == mode

    def test_saving_migrated_theme_preserves_it(self, qsettings) -> None:
        qsettings.setValue(DARK_MODE_KEY, True)
        settings = AppSettings.load(qsettings)
        settings.save(qsettings)
        assert AppSettings.load(qsettings).theme_mode_effective == THEME_MODE_DARK

    def test_legacy_dark_mode_true_migrates_to_dark(self, qsettings: QSettings) -> None:
        qsettings.setValue(DARK_MODE_KEY, True)
        settings = AppSettings.load(qsettings)
        assert settings.theme_mode_effective == THEME_MODE_DARK

    def test_legacy_dark_mode_false_migrates_to_light(self, qsettings: QSettings) -> None:
        qsettings.setValue(DARK_MODE_KEY, False)
        settings = AppSettings.load(qsettings)
        assert settings.theme_mode_effective == THEME_MODE_LIGHT

    def test_legacy_dark_mode_string_true(self, qsettings: QSettings) -> None:
        qsettings.setValue(DARK_MODE_KEY, "true")
        settings = AppSettings.load(qsettings)
        assert settings.theme_mode_effective == THEME_MODE_DARK

    def test_explicit_theme_mode_wins_over_legacy(self, qsettings: QSettings) -> None:
        qsettings.setValue(DARK_MODE_KEY, True)
        qsettings.setValue(THEME_MODE_KEY, THEME_MODE_LIGHT)
        settings = AppSettings.load(qsettings)
        assert settings.theme_mode_effective == THEME_MODE_LIGHT

    def test_explicit_theme_mode_system_wins(self, qsettings: QSettings) -> None:
        qsettings.setValue(DARK_MODE_KEY, False)
        qsettings.setValue(THEME_MODE_KEY, THEME_MODE_SYSTEM)
        settings = AppSettings.load(qsettings)
        assert settings.theme_mode_effective == THEME_MODE_SYSTEM


# ── Roundtrip Save/Load ──────────────────────────────────────────────────────


class TestRoundtrip:
    def test_save_and_reload_preserves_values(self, qsettings: QSettings) -> None:
        settings = AppSettings.load(qsettings)
        settings.font_size = 20
        settings.result_decimal_places = 12
        settings.alternating_row_background = False
        settings.theme_mode = THEME_MODE_SYSTEM
        settings.save(qsettings)

        reloaded = AppSettings.load(qsettings)
        assert reloaded.font_size == 20
        assert reloaded.result_decimal_places == 12
        assert reloaded.alternating_row_background is False
        assert reloaded.theme_mode == THEME_MODE_SYSTEM

    def test_save_and_reload_window_size(self, qsettings: QSettings) -> None:
        settings = AppSettings.load(qsettings)
        settings.window_size = QSize(1400, 900)
        settings.save(qsettings)

        reloaded = AppSettings.load(qsettings)
        assert reloaded.window_size == QSize(1400, 900)

    def test_load_settings_helper(self, qsettings: QSettings) -> None:
        qsettings.setValue(FONT_SIZE_KEY, 18)
        result = load_settings(qsettings)
        assert result.font_size == 18

    def test_save_settings_helper(self, qsettings: QSettings) -> None:
        settings = AppSettings()
        settings.font_size = 22
        save_settings(qsettings, settings)
        assert qsettings.value(FONT_SIZE_KEY) == 22


# ── Convenience Setters ──────────────────────────────────────────────────────


class TestConvenienceSetters:
    def test_set_font_size_clamps_low(self) -> None:
        s = AppSettings()
        result = s.set_font_size(1)
        assert s.font_size == 8
        assert result == 8

    def test_set_font_size_clamps_high(self) -> None:
        s = AppSettings()
        result = s.set_font_size(200)
        assert s.font_size == 72
        assert result == 72

    def test_set_font_size_valid(self) -> None:
        s = AppSettings()
        result = s.set_font_size(24)
        assert s.font_size == 24
        assert result == 24

    def test_set_decimal_places_clamps_low(self) -> None:
        s = AppSettings()
        result = s.set_result_decimal_places(-3)
        assert s.result_decimal_places == 0
        assert result == 0

    def test_set_decimal_places_clamps_high(self) -> None:
        s = AppSettings()
        result = s.set_result_decimal_places(50)
        assert s.result_decimal_places == 20
        assert result == 20

    def test_set_decimal_places_valid(self) -> None:
        s = AppSettings()
        result = s.set_result_decimal_places(10)
        assert s.result_decimal_places == 10
        assert result == 10

    def test_set_theme_mode_valid(self) -> None:
        s = AppSettings()
        s.set_theme_mode(THEME_MODE_SYSTEM)
        assert s.theme_mode == THEME_MODE_SYSTEM

    def test_set_theme_mode_invalid_defaults_to_light(self) -> None:
        s = AppSettings()
        s.set_theme_mode("invalid")
        assert s.theme_mode == THEME_MODE_LIGHT

    def test_set_alternating_row_background(self) -> None:
        s = AppSettings()
        s.set_alternating_row_background(False)
        assert s.alternating_row_background is False

    def test_set_tabs_count_clamps(self) -> None:
        s = AppSettings()
        result = s.set_tabs_count(500)
        assert s.tabs_count == 100
        assert result == 100

    def test_set_tabs_current_clamps_to_count(self) -> None:
        s = AppSettings()
        s.tabs_count = 3
        result = s.set_tabs_current(10)
        assert s.tabs_current == 2
        assert result == 2

    @pytest.mark.parametrize(("count", "index", "expected"), [(0, -1, 0), (1, 10, 0), (3, -1, 0), (3, 1, 1)])
    def test_set_tabs_current_handles_empty_and_valid_ranges(self, count, index, expected) -> None:
        settings = AppSettings(tabs_count=count)
        assert settings.set_tabs_current(index) == expected


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_qsettings_all_defaults(self, qsettings: QSettings) -> None:
        settings = AppSettings.load(qsettings)
        assert settings.font_size == 14
        assert settings.result_decimal_places == DEFAULT_DECIMAL_PLACES

    def test_bool_stored_as_int_string(self, qsettings: QSettings) -> None:
        qsettings.setValue(ALTERNATING_ROW_BACKGROUND_KEY, "0")
        settings = AppSettings.load(qsettings)
        assert settings.alternating_row_background is False

    def test_mixed_valid_and_invalid_settings(self, qsettings: QSettings) -> None:
        qsettings.setValue(FONT_SIZE_KEY, 20)
        qsettings.setValue(RESULT_DECIMAL_PLACES_KEY, "invalid")
        settings = AppSettings.load(qsettings)
        assert settings.font_size == 20
        assert settings.result_decimal_places == DEFAULT_DECIMAL_PLACES

    def test_all_theme_modes_are_valid(self) -> None:
        for mode in THEME_MODES:
            s = AppSettings()
            s.set_theme_mode(mode)
            assert s.theme_mode == mode

    def test_window_size_zero_uses_default(self, qsettings: QSettings) -> None:
        qsettings.setValue(WINDOW_SIZE_KEY, QSize(0, 0))
        settings = AppSettings.load(qsettings)
        assert settings.window_size == QSize(920, 640)

    def test_tabs_current_capped_by_count_via_setter(self, qsettings: QSettings) -> None:
        qsettings.setValue(TABS_COUNT_KEY, 3)
        qsettings.setValue(TABS_CURRENT_KEY, 10)
        settings = AppSettings.load(qsettings)
        assert settings.tabs_count == 3
        assert settings.tabs_current == 10
        result = settings.set_tabs_current(10)
        assert result == 2
