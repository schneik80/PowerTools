# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
"""Unit tests for the Related Data template cache reader.

``_load_templates_from_cache`` must treat a missing, corrupt, empty or non-dict
cache file as a miss (None) so the command falls through to the live fetch
instead of raising inside a command handler.
"""

import importlib
from pathlib import Path

PT_PKG = Path(__file__).resolve().parent.parent.name
entry = importlib.import_module(f"{PT_PKG}.commands.relateddata.entry")


def test_missing_file_is_a_miss(tmp_path) -> None:
    assert entry._load_templates_from_cache(str(tmp_path / "hub.json")) is None


def test_corrupt_file_is_a_miss(tmp_path) -> None:
    path = tmp_path / "hub.json"
    path.write_text("{", encoding="utf-8")
    assert entry._load_templates_from_cache(str(path)) is None


def test_empty_or_non_dict_is_a_miss(tmp_path) -> None:
    path = tmp_path / "hub.json"
    path.write_text("{}", encoding="utf-8")
    assert entry._load_templates_from_cache(str(path)) is None
    path.write_text("[1, 2]", encoding="utf-8")
    assert entry._load_templates_from_cache(str(path)) is None


def test_valid_cache_is_returned(tmp_path) -> None:
    path = tmp_path / "hub.json"
    path.write_text('{"Adict": {"name": "A", "urn": "urn:1"}}', encoding="utf-8")
    assert entry._load_templates_from_cache(str(path)) == {
        "Adict": {"name": "A", "urn": "urn:1"}
    }
