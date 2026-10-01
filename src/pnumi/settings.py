from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QSettings, QSize

from .formatting import DEFAULT_DECIMAL_PLACES

logger = logging.getLogger(__name__)

# ── Keys ──────────────────────────────────────────────────────────────────────

ALTERNATING_ROW_BACKGROUND_KEY = "editor/alternatingRowBackground"
DARK_MODE_KEY = "editor/darkMode"
THEME_MODE_KEY = "editor/themeMode"
RESULT_DECIMAL_PLACES_KEY = "results/decimalPlaces"
FONT_SIZE_KEY = "editor/fontSize"
WINDOW_SIZE_KEY = "window/size"
TABS_COUNT_KEY = "tabs/count"
TABS_CURRENT_KEY = "tabs/current"

# ── Theme modes ───────────────────────────────────────────────────────────────

THEME_MODE_SYSTEM = "system"
THEME_MODE_LIGHT = "light"
THEME_MODE_DARK = "dark"
THEME_MODES = {THEME_MODE_SYSTEM, THEME_MODE_LIGHT, THEME_MODE_DARK}

# ── Field descriptor ──────────────────────────────────────────────────────────

Validator = Callable[[Any], Any]


@dataclass(frozen=True)
class SettingsField:
    """Describes a single validated setting."""

    key: str
    default: Any
    min_value: Any | None = None
    max_value: Any | None = None
    allowed_values: set[Any] | None = None
    validator: Validator | None = None


# ── Registry of all app settings ──────────────────────────────────────────────


def _validate_theme_mode(value: Any) -> str:
    if isinstance(value, bool):
        return THEME_MODE_DARK if value else THEME_MODE_LIGHT
    if isinstance(value, str) and value in THEME_MODES:
        return value
    return THEME_MODE_LIGHT


def _validate_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _validate_size(value: Any, default: QSize) -> QSize:
    if isinstance(value, QSize) and value.isValid() and value.width() > 0 and value.height() > 0:
        return value
    return default


# Preferences and session metadata managed by AppSettings.
FIELDS: dict[str, SettingsField] = {
    "alternating_row_background": SettingsField(
        key=ALTERNATING_ROW_BACKGROUND_KEY,
        default=True,
        validator=_validate_bool,
    ),
    "theme_mode": SettingsField(
        key=THEME_MODE_KEY,
        default=THEME_MODE_LIGHT,
        allowed_values=THEME_MODES,
        validator=_validate_theme_mode,
    ),
    "result_decimal_places": SettingsField(
        key=RESULT_DECIMAL_PLACES_KEY,
        default=DEFAULT_DECIMAL_PLACES,
        min_value=0,
        max_value=20,
    ),
    "font_size": SettingsField(
        key=FONT_SIZE_KEY,
        default=14,
        min_value=8,
        max_value=72,
    ),
    "window_size": SettingsField(
        key=WINDOW_SIZE_KEY,
        default=QSize(920, 640),
        validator=lambda v, _d=QSize(920, 640): _validate_size(v, _d),
    ),
    "tabs_count": SettingsField(
        key=TABS_COUNT_KEY,
        default=0,
        min_value=0,
        max_value=100,
    ),
    "tabs_current": SettingsField(
        key=TABS_CURRENT_KEY,
        default=0,
        min_value=0,
        max_value=100,
    ),
}


# ── Validated settings container ──────────────────────────────────────────────


@dataclass
class AppSettings:
    """Validated, typed representation of all application settings.

    Loaded values and convenience setters enforce declared bounds.
    Invalid stored values are clamped or replaced with defaults and logged.
    """

    alternating_row_background: bool = True
    theme_mode: str = THEME_MODE_LIGHT
    result_decimal_places: int = DEFAULT_DECIMAL_PLACES
    font_size: int = 14
    window_size: QSize = field(default_factory=lambda: QSize(920, 640))
    tabs_count: int = 0
    tabs_current: int = 0

    @classmethod
    def load(cls, settings: QSettings) -> AppSettings:
        """Read all settings from QSettings, validate, and apply migration."""
        instance = cls()
        for name, field_def in FIELDS.items():
            raw = settings.value(field_def.key)
            validated = cls._validate_field(raw, field_def, name)
            setattr(instance, name, validated)
        instance._migrate_legacy_dark_mode(settings)
        return instance

    def save(self, settings: QSettings) -> None:
        """Persist all settings back to QSettings."""
        for name, field_def in FIELDS.items():
            value = getattr(self, name)
            settings.setValue(field_def.key, value)
        settings.sync()

    # ── Migration ──────────────────────────────────────────────────────────

    def _migrate_legacy_dark_mode(self, settings: QSettings) -> None:
        """Use legacy darkMode when themeMode is absent or invalid."""
        theme_raw = settings.value(THEME_MODE_KEY)
        if isinstance(theme_raw, str) and theme_raw in THEME_MODES:
            return
        dark_raw = settings.value(DARK_MODE_KEY)
        if dark_raw is not None:
            self.theme_mode = THEME_MODE_DARK if _validate_bool(dark_raw) else THEME_MODE_LIGHT

    @property
    def theme_mode_effective(self) -> str:
        """Return the theme mode after load-time legacy migration."""
        return self.theme_mode

    # ── Validation ─────────────────────────────────────────────────────────

    @staticmethod
    def _validate_field(raw: Any, field_def: SettingsField, name: str) -> Any:
        default = field_def.default

        if raw is None:
            return default

        # Custom validator (handles type coercion)
        if field_def.validator is not None:
            try:
                raw = field_def.validator(raw)
            except Exception as exc:
                logger.warning("Invalid setting %s (%s): %s — using default", name, field_def.key, exc)
                return default

        # Allowed values
        if field_def.allowed_values is not None and raw not in field_def.allowed_values:
            logger.warning(
                "Setting %s has invalid value %r — using default %r",
                name,
                raw,
                default,
            )
            return default

        # Coerce integer values before applying bounds, including values read
        # as strings from an INI-backed QSettings store. Exclude bool defaults.
        if type(default) is int:
            try:
                raw = int(raw)
            except (TypeError, ValueError, OverflowError):
                logger.warning(
                    "Setting %s has non-integer value %r — using default %r",
                    name,
                    raw,
                    default,
                )
                return default

        if field_def.min_value is not None or field_def.max_value is not None:
            clamped = raw
            if field_def.min_value is not None:
                clamped = max(clamped, field_def.min_value)
            if field_def.max_value is not None:
                clamped = min(clamped, field_def.max_value)
            if clamped != raw:
                logger.warning("Setting %s value %r clamped to %r", name, raw, clamped)
            return clamped

        return raw

    # ── Convenience setters (used by UI) ───────────────────────────────────

    def set_alternating_row_background(self, value: bool) -> None:
        self.alternating_row_background = bool(value)

    def set_theme_mode(self, mode: str) -> None:
        normalized = mode if mode in THEME_MODES else THEME_MODE_LIGHT
        self.theme_mode = normalized

    def set_result_decimal_places(self, places: int) -> int:
        self.result_decimal_places = max(0, min(int(places), 20))
        return self.result_decimal_places

    def set_font_size(self, size: int) -> int:
        self.font_size = max(8, min(int(size), 72))
        return self.font_size

    def set_tabs_count(self, count: int) -> int:
        self.tabs_count = max(0, min(int(count), 100))
        return self.tabs_count

    def set_tabs_current(self, index: int) -> int:
        self.tabs_current = max(0, min(int(index), max(0, self.tabs_count - 1)))
        return self.tabs_current


# ── Public helpers ───────────────────────────────────────────

def load_settings(settings: QSettings) -> AppSettings:
    """Load and validate all settings from QSettings."""
    return AppSettings.load(settings)


def save_settings(settings: QSettings, app_settings: AppSettings) -> None:
    """Save validated settings back to QSettings."""
    app_settings.save(settings)
