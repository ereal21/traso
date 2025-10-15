
import json
import os

FEATURE_JSON_PATH = os.path.join(os.path.dirname(__file__), '..', 'config', 'feature_flags.json')

def is_feature_enabled(feature_name: str) -> bool:
    try:
        with open(FEATURE_JSON_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get(feature_name, False)
    except Exception as e:
        print(f"[FeatureConfig] Error reading config: {e}")
        return False



# --- Added by automated fix ---
try:
    from typing import Optional
except Exception:
    Optional = None

_FEATURE_FLAGS = globals().get("_FEATURE_FLAGS", {
    # Populate with your actual flags
    # "assistant_management": True,
})

def is_enabled(feature_key: str) -> bool:
    """Return whether a feature is enabled. Uses in-memory _FEATURE_FLAGS; 
    override this function if your project has a different source of truth."""
    return bool(_FEATURE_FLAGS.get(feature_key, False))

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
# --- End automated fix ---
