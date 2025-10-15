
import json
import os
from typing import Dict

FEATURE_JSON_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "config",
    "feature_flags.json",
)

_FEATURE_FLAGS: Dict[str, bool] = {}


def _load_feature_flags() -> Dict[str, bool]:
    """Load feature configuration from disk into the in-memory cache."""

    global _FEATURE_FLAGS

    try:
        with open(FEATURE_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except FileNotFoundError:
        print(f"[FeatureConfig] Missing configuration file: {FEATURE_JSON_PATH}")
        data = {}
    except Exception as exc:  # pragma: no cover - log unexpected errors
        print(f"[FeatureConfig] Error reading config: {exc}")
        data = {}

    # Normalise values to booleans; ignore non-bool values silently.
    _FEATURE_FLAGS = {key: bool(value) for key, value in data.items()}
    return _FEATURE_FLAGS


def _ensure_flags_loaded() -> None:
    if not _FEATURE_FLAGS:
        _load_feature_flags()


def is_feature_enabled(feature_name: str) -> bool:
    _ensure_flags_loaded()
    return _FEATURE_FLAGS.get(feature_name, False)


def is_enabled(feature_key: str) -> bool:
    """Return whether a feature is enabled."""

    _ensure_flags_loaded()
    return _FEATURE_FLAGS.get(feature_key, False)


def feature_disabled_text(feature_key: str, locale: str = "en") -> str:
    """Return a user-facing message explaining that a feature is disabled.
    You can customize the copy per-locale/feature here as needed."""

    MESSAGES = {
        "en": "This feature is currently disabled by configuration.",
        "lt": "Ši funkcija šiuo metu išjungta pagal nustatymus.",
        "ru": "Эта функция сейчас отключена настройками.",
    }
    # If you want per-feature copy, extend this mapping to a dict of dicts.
    return MESSAGES.get(locale, MESSAGES["en"])


def reload_feature_flags() -> Dict[str, bool]:
    """Public helper allowing other modules to refresh feature flags."""

    return _load_feature_flags()
