# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Unit tests for config.loadHub().

loadHub() runs at ``import config`` time, so a raise here means PowerTools.run
is never entered and nothing is logged. A truncated cache/hub.json or an entry
without an ``id`` must therefore degrade to "no hub configured", never raise.
"""

import importlib
from pathlib import Path

import pytest

PT_PKG = Path(__file__).resolve().parent.parent.name
config = importlib.import_module(f"{PT_PKG}.config")


@pytest.fixture
def hub_root(tmp_path, monkeypatch):
    """Point loadHub at a temporary add-in root and restore the globals after."""
    saved = (list(config.COMPANY_HUB), dict(config.COMPANY_HUB_CONFIGS))
    (tmp_path / "cache").mkdir()
    yield tmp_path
    config.COMPANY_HUB, config.COMPANY_HUB_CONFIGS = saved


def _load(hub_root: Path, text: str) -> None:
    (hub_root / "cache" / "hub.json").write_text(text, encoding="utf-8")
    config.loadHub(str(hub_root / "config.py"))


def test_truncated_hub_json_yields_no_hubs(hub_root) -> None:
    _load(hub_root, "{")
    assert config.COMPANY_HUB == []
    assert config.COMPANY_HUB_CONFIGS == {}


def test_entry_without_id_is_dropped(hub_root) -> None:
    _load(hub_root, '{"hubs": [{}]}')
    assert config.COMPANY_HUB == []
    assert config.COMPANY_HUB_CONFIGS == {}


def test_non_dict_entries_and_null_hubs_are_tolerated(hub_root) -> None:
    _load(hub_root, '{"hubs": null}')
    assert config.COMPANY_HUB == []
    _load(hub_root, '{"hubs": ["a", 3, null, {"id": ""}]}')
    assert config.COMPANY_HUB == []
    _load(hub_root, "[]")
    assert config.COMPANY_HUB == []


def test_well_formed_entry_still_loads(hub_root) -> None:
    _load(
        hub_root,
        '{"hubs": [{"id": "h1", "name": "Hub", "project_id": "p", "folder_id": "f"},'
        ' {"name": "no id"}]}',
    )
    assert config.COMPANY_HUB == ["h1"]
    assert config.COMPANY_HUB_CONFIGS["h1"]["name"] == "Hub"
    assert config.COMPANY_HUB_CONFIGS["h1"]["project_id"] == "p"
    assert config.COMPANY_HUB_CONFIGS["h1"]["folder_id"] == "f"
    assert config.COMPANY_HUB_CONFIGS["h1"]["project_name"] == ""


def test_missing_file_yields_no_hubs(hub_root) -> None:
    config.loadHub(str(hub_root / "config.py"))
    assert config.COMPANY_HUB == []
    assert config.COMPANY_HUB_CONFIGS == {}
