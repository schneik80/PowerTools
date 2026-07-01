"""Unit tests for settings_store.validate() (T8b: reject unknown top-level keys).

validate() gates an imported preferences file before it REPLACES the active
settings, so it must accept a well-formed file and reject anything malformed or
carrying unexpected top-level keys (a hardening measure against injected
payloads). The module uses package-relative imports, so it is loaded via its
full package path with the conftest scaffolding in place.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
settings_store = importlib.import_module(f"{PT_PKG}.settings_store")


def _valid_payload() -> dict:
    """Return a minimal structurally-valid preferences payload."""
    return {"general": {}, "groups": {}, "commands": {}}


def test_accepts_well_formed_payload() -> None:
    """A dict with the required dict sections validates."""
    assert settings_store.validate(_valid_payload()) is True


def test_accepts_known_optional_keys() -> None:
    """version and command_settings are known keys and are allowed."""
    payload = _valid_payload()
    payload["version"] = 1
    payload["command_settings"] = {}

    assert settings_store.validate(payload) is True


def test_rejects_unknown_top_level_key() -> None:
    """An unexpected top-level key (e.g. an injected payload) is rejected."""
    payload = _valid_payload()
    payload["evil"] = {"do": "harm"}

    assert settings_store.validate(payload) is False


def test_rejects_non_dict() -> None:
    """A non-dict (e.g. a JSON array) is not a valid preferences file."""
    assert settings_store.validate([1, 2, 3]) is False


def test_rejects_missing_required_section() -> None:
    """Omitting a required section (commands) fails validation."""
    payload = {"general": {}, "groups": {}}

    assert settings_store.validate(payload) is False


def test_rejects_wrong_type_for_section() -> None:
    """A required section present but of the wrong type fails validation."""
    payload = {"general": [], "groups": {}, "commands": {}}

    assert settings_store.validate(payload) is False
