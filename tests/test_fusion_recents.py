"""Unit tests for ``lib/ptAddInUtils/fusion_recents.py``.

The reader has no ``adsk`` dependency by design — every Fusion-derived value is
passed in — so it is loaded directly from its file path, avoiding the
``ptAddInUtils`` package ``__init__`` (which pulls in ``adsk``).

Coverage centres on the parts that were observed to be surprising in real data:
``docstruct`` is not always JSON and is frequently empty, the stored entry order
is not reliably newest-first, and several user directories can hold a file for
the same hub — one of them stale. Filesystem tests point
``OPTIONS_ROOT_CANDIDATES`` at ``tmp_path``, keeping module-level constants as
the seam, as ``test_recents_utils.py`` established.
"""

import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

_HELPER_PATH = (
    Path(__file__).resolve().parent.parent
    / "lib"
    / "ptAddInUtils"
    / "fusion_recents.py"
)
_spec = importlib.util.spec_from_file_location("pt_fusion_recents", _HELPER_PATH)
fusion_recents = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fusion_recents)


# ---------------------------------------------------------------------------
# intent_from_docstruct
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "type_value,expected",
    [
        ("part-design", "part"),
        ("assembly-design", "assembly"),
        ("hybrid-design", "hybrid"),
    ],
)
def test_intent_from_docstruct_parses_json_type(type_value: str, expected: str) -> None:
    """The normal case: a JSON docstruct whose ``type`` is ``<intent>-<flavour>``."""
    raw = json.dumps({"version": "1.0.0", "type": type_value, "attributes": {}})

    assert fusion_recents.intent_from_docstruct(raw) == expected


def test_intent_from_docstruct_accepts_bare_token() -> None:
    """Some entries store a bare token instead of JSON (observed in real data)."""
    assert fusion_recents.intent_from_docstruct("assembly-experience") == "assembly"


def test_intent_from_docstruct_tolerates_unknown_flavour() -> None:
    """A flavour Fusion has not shipped yet still resolves via its intent prefix."""
    raw = json.dumps({"type": "hybrid-somethingnew"})

    assert fusion_recents.intent_from_docstruct(raw) == "hybrid"


@pytest.mark.parametrize("raw", ["", "   ", "not json at all", "{bad json"])
def test_intent_from_docstruct_blank_and_garbage_return_empty(raw: str) -> None:
    """Empty and unparseable values yield "" rather than raising or guessing.

    "" is a permanent answer for ~25% of designs, not a not-yet: comparing files
    a month apart showed docstruct is never backfilled.
    """
    assert fusion_recents.intent_from_docstruct(raw) == ""


def test_intent_from_docstruct_rejects_unknown_prefix() -> None:
    """A type that is not one of the three intents must not be coerced into one."""
    assert fusion_recents.intent_from_docstruct('{"type": "drawing-standard"}') == ""


def test_intent_from_docstruct_ignores_non_dict_json() -> None:
    """Valid JSON that is not an object falls through to the bare-token path."""
    assert fusion_recents.intent_from_docstruct("[1, 2, 3]") == ""


# ---------------------------------------------------------------------------
# Platform roots
#
# _root_candidates is pure so the Windows layout is checked from a macOS run —
# a typo here would otherwise only surface on a Windows machine. Expectations
# are written with forward slashes and compared after normalizing separators,
# since os.path.join uses the *host* separator whatever platform is asked for.
# ---------------------------------------------------------------------------


def _norm(paths) -> list[str]:
    return [p.replace("\\", "/") for p in paths]


def test_root_candidates_windows_uses_appdata() -> None:
    """%APPDATA% already ends in Roaming, so it must not be appended again."""
    got = fusion_recents._root_candidates(
        "win32", {"APPDATA": r"C:\Users\kevin\AppData\Roaming"}, r"C:\Users\kevin"
    )

    assert _norm(got) == [
        "C:/Users/kevin/AppData/Roaming/Autodesk/Neutron Platform/Options"
    ]


def test_root_candidates_windows_falls_back_to_home_when_appdata_unset() -> None:
    """Fusion may hand the add-in an environment without APPDATA."""
    got = fusion_recents._root_candidates("win32", {}, r"C:\Users\kevin")

    assert _norm(got) == [
        "C:/Users/kevin/AppData/Roaming/Autodesk/Neutron Platform/Options"
    ]


def test_root_candidates_windows_dedupes_equivalent_bases() -> None:
    """APPDATA and the home-derived fallback usually name the same directory."""
    got = fusion_recents._root_candidates(
        "win32",
        {"APPDATA": os.path.join("C:/Users/kevin", "AppData", "Roaming")},
        "C:/Users/kevin",
    )

    assert len(got) == 1


def test_root_candidates_macos() -> None:
    got = fusion_recents._root_candidates("darwin", {}, "/Users/kevin")

    assert _norm(got) == [
        "/Users/kevin/Library/Application Support/Autodesk/Neutron Platform/Options"
    ]


def test_root_candidates_unsupported_platform_is_empty() -> None:
    """Fusion does not ship for Linux; callers fall back to their own cache."""
    assert fusion_recents._root_candidates("linux", {"APPDATA": "/x"}, "/home/k") == ()


# ---------------------------------------------------------------------------
# Hub prefix derivation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://imallc.autodesk360.com", "imallc"),
        ("https://imallc.autodesk360.com/g/projects/123", "imallc"),
        ("https://IMALLC.autodesk360.com", "imallc"),
        ("https://autodesk8083.autodesk360.com:443", "autodesk8083"),
        ("", ""),
    ],
)
def test_hub_prefix_from_web_url(url: str, expected: str) -> None:
    """The site name is the first hostname label, lowercased."""
    assert fusion_recents.hub_prefix_from_web_url(url) == expected


def test_hub_prefix_from_hub_id_team_hub() -> None:
    """A team hub id base64-encodes ``<edition>:<site>``."""
    # "business:imallc"
    assert fusion_recents.hub_prefix_from_hub_id("a.YnVzaW5lc3M6aW1hbGxj") == "imallc"


def test_hub_prefix_from_hub_id_handles_missing_padding() -> None:
    """Fusion strips base64 ``=`` padding; it has to be restored before decoding."""
    import base64

    payload = base64.b64encode(b"business:acme").decode().rstrip("=")
    assert fusion_recents.hub_prefix_from_hub_id(f"a.{payload}") == "acme"


@pytest.mark.parametrize("hub_id", ["", "a.", "a.45637", "a.!!!!", "nodot"])
def test_hub_prefix_from_hub_id_returns_blank_when_not_encoded(hub_id: str) -> None:
    """The API documents ``a.45637`` as valid, so "" is an ordinary outcome."""
    assert fusion_recents.hub_prefix_from_hub_id(hub_id) == ""


# ---------------------------------------------------------------------------
# read_user_hub_options (UTF-16 XML)
# ---------------------------------------------------------------------------

_USER_XML = """<?xml version="1.0" encoding="UTF-16" standalone="no" ?>
<OptionGroups>
    <UserMachineSpecificOptionGroup SchemaVersion="2" UserName="User Machine Options">
        <LastUserHubUserRole UserName="LastUserHubUserRole" Value="ADMIN"/>
        <LastUserHubUrlWip UserName="LastUserHubUrlWip" Value="{url}"/>
        <LastUserHubName UserName="LastUserHubName" Value="Industrial Machine Arts LLC"/>
        <LastUserHubEdition UserName="LastUserHubEdition" Value="business"/>
        <LastUserHubUserId UserName="LastUserHubUserId" Value="{user_id}"/>
        <LastUserHubRegionId UserName="LastUserHubRegionId" Value="us"/>
    </UserMachineSpecificOptionGroup>
</OptionGroups>
"""


def _write_user_dir(
    root: Path,
    name: str,
    user_id: str = "",
    url: str = "https://imallc.autodesk360.com",
) -> Path:
    """Create a user directory with a real UTF-16 options file, as Fusion writes it."""
    user_dir = root / name
    user_dir.mkdir(parents=True, exist_ok=True)
    xml = _USER_XML.format(url=url, user_id=user_id or name)
    (user_dir / fusion_recents.USER_XML_NAME).write_bytes(xml.encode("utf-16"))
    return user_dir


def test_read_user_hub_options_parses_utf16(tmp_path: Path) -> None:
    """The real file is UTF-16 with a BOM; the declaration drives the decode."""
    user_dir = _write_user_dir(tmp_path, "200707241731883")

    assert fusion_recents.read_user_hub_options(str(user_dir)) == {
        "userId": "200707241731883",
        "hubUrlWip": "https://imallc.autodesk360.com",
        "hubName": "Industrial Machine Arts LLC",
        "edition": "business",
        "regionId": "us",
    }


def test_read_user_hub_options_missing_file_returns_empty(tmp_path: Path) -> None:
    """An unidentifiable directory yields {} rather than raising."""
    assert fusion_recents.read_user_hub_options(str(tmp_path)) == {}


def test_read_user_hub_options_bad_xml_returns_empty(tmp_path: Path) -> None:
    (tmp_path / fusion_recents.USER_XML_NAME).write_bytes(b"<not valid xml")

    assert fusion_recents.read_user_hub_options(str(tmp_path)) == {}


# ---------------------------------------------------------------------------
# resolve_recents_path
# ---------------------------------------------------------------------------


def _write_recents(
    user_dir: Path,
    prefix: str,
    *,
    site: str = "",
    mtime: float = 1_700_000_000.0,
    empty: bool = False,
) -> Path:
    """Write a minimal but realistically-shaped recents file with a fixed mtime."""
    site = site or prefix
    files = (
        []
        if empty
        else [
            {
                "name": "Doc",
                "id": "urn:adsk.wipprod:dm.lineage:abc",
                "fileType": "f3d",
                "qontextServer": f"https://{site}.autodesk360.com",
                "lastOpened": "1700000000000",
                "docstruct": '{"type":"part-design"}',
                "location": "Proj/Sub",
                "version": "3",
            }
        ]
    )
    path = user_dir / f"{prefix}_RecentsWithoutSearch_1.json"
    path.write_text(json.dumps({"files": files, "moreData": False}), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def options_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the module at an empty fake options tree."""
    root = tmp_path / "Options"
    root.mkdir()
    monkeypatch.setattr(fusion_recents, "OPTIONS_ROOT_CANDIDATES", (str(root),))
    return root


def test_resolve_prefers_newest_when_two_dirs_hold_the_same_hub(
    options_root: Path,
) -> None:
    """The real-world failure this guards: a stale copy of the active hub's file.

    Two user directories both hold ``imallc_…``; only the recently-written one is
    live. Ordering by mtime is what distinguishes them.
    """
    stale = _write_user_dir(options_root, "X6MHRWZ3VKGH")
    live = _write_user_dir(options_root, "200707241731883")
    _write_recents(stale, "imallc", mtime=1_600_000_000.0)
    expected = _write_recents(live, "imallc", mtime=1_800_000_000.0)

    chosen = fusion_recents.resolve_recents_path(
        hub_url="https://imallc.autodesk360.com"
    )

    assert chosen == str(expected)


def test_resolve_rejects_other_hubs(options_root: Path) -> None:
    """A sibling file for a different hub must never be selected, even if newer."""
    user_dir = _write_user_dir(options_root, "200707241731883")
    _write_recents(user_dir, "autodesk8083", mtime=1_900_000_000.0)
    expected = _write_recents(user_dir, "imallc", mtime=1_700_000_000.0)

    chosen = fusion_recents.resolve_recents_path(
        hub_url="https://imallc.autodesk360.com"
    )

    assert chosen == str(expected)


def test_resolve_validates_qontext_server_over_filename(options_root: Path) -> None:
    """A file named for our hub but holding another hub's entries is rejected."""
    user_dir = _write_user_dir(options_root, "200707241731883")
    _write_recents(user_dir, "imallc", site="someoneelse")

    assert (
        fusion_recents.resolve_recents_path(hub_url="https://imallc.autodesk360.com")
        == ""
    )


def test_resolve_prefers_recency_over_a_user_id_match(options_root: Path) -> None:
    """Recency must outrank a user-id match — the stale-sibling trap.

    On the machine this was built against, two directories' options files both
    name the same hub, so they are plausibly one person under two
    directory-keying schemes. ``Application.userId`` returns an internal account
    name that may match the *stale* one, so trusting it over the file Fusion is
    actively rewriting would serve a month-old list.
    """
    stale = _write_user_dir(options_root, "X6MHRWZ3VKGH")
    live = _write_user_dir(options_root, "200707241731883")
    _write_recents(stale, "imallc", mtime=1_600_000_000.0)
    expected = _write_recents(live, "imallc", mtime=1_800_000_000.0)

    chosen = fusion_recents.resolve_recents_path(
        hub_url="https://imallc.autodesk360.com", user_id="X6MHRWZ3VKGH"
    )

    assert chosen == str(expected)


def test_resolve_breaks_mtime_ties_with_the_user_dir(options_root: Path) -> None:
    """With nothing to choose on recency, the signed-in user decides."""
    other = _write_user_dir(options_root, "LGSXJ8PV4QPH")
    mine = _write_user_dir(options_root, "200707241731883")
    _write_recents(other, "imallc", mtime=1_700_000_000.0)
    expected = _write_recents(mine, "imallc", mtime=1_700_000_000.0)

    chosen = fusion_recents.resolve_recents_path(
        hub_url="https://imallc.autodesk360.com", user_id="200707241731883"
    )

    assert chosen == str(expected)


def test_resolve_matches_user_via_options_xml(options_root: Path) -> None:
    """``Application.userId`` may report an internal name, not the directory name.

    Equal mtimes, and the winning directory is named with a numeric id, so the
    match has to come from the directory's own options file.
    """
    other = _write_user_dir(options_root, "LGSXJ8PV4QPH", user_id="LGSXJ8PV4QPH")
    mine = _write_user_dir(options_root, "200707241731883", user_id="KEVINSINTERNAL")
    _write_recents(other, "imallc", mtime=1_700_000_000.0)
    expected = _write_recents(mine, "imallc", mtime=1_700_000_000.0)

    chosen = fusion_recents.resolve_recents_path(
        hub_url="https://imallc.autodesk360.com", user_id="KEVINSINTERNAL"
    )

    assert chosen == str(expected)


def test_resolve_falls_back_to_hub_id_when_url_missing(options_root: Path) -> None:
    """With no ``fusionWebURL``, the base64 hub id still yields the prefix."""
    user_dir = _write_user_dir(options_root, "200707241731883")
    expected = _write_recents(user_dir, "imallc")

    chosen = fusion_recents.resolve_recents_path(hub_id="a.YnVzaW5lc3M6aW1hbGxj")

    assert chosen == str(expected)


def test_resolve_skips_unknown_user_dir(options_root: Path) -> None:
    """The signed-out directory never holds a usable list."""
    signed_out = _write_user_dir(options_root, "UnknownUser")
    _write_recents(signed_out, "imallc", mtime=1_900_000_000.0)

    assert (
        fusion_recents.resolve_recents_path(hub_url="https://imallc.autodesk360.com")
        == ""
    )


def test_resolve_skips_empty_stub(options_root: Path) -> None:
    """An empty placeholder must not outrank a real list on mtime alone."""
    user_dir = _write_user_dir(options_root, "200707241731883")
    _write_recents(user_dir, "imallc", empty=True, mtime=1_900_000_000.0)
    other = _write_user_dir(options_root, "LGSXJ8PV4QPH")
    expected = _write_recents(other, "imallc", mtime=1_700_000_000.0)

    chosen = fusion_recents.resolve_recents_path(
        hub_url="https://imallc.autodesk360.com"
    )

    assert chosen == str(expected)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_resolve_skips_unreadable_file(options_root: Path) -> None:
    """One sibling file has been observed mode 0o400 owned by another context."""
    locked_dir = _write_user_dir(options_root, "LGSXJ8PV4QPH")
    locked = _write_recents(locked_dir, "imallc", mtime=1_900_000_000.0)
    os.chmod(locked, 0)
    readable_dir = _write_user_dir(options_root, "200707241731883")
    expected = _write_recents(readable_dir, "imallc", mtime=1_700_000_000.0)
    try:
        chosen = fusion_recents.resolve_recents_path(
            hub_url="https://imallc.autodesk360.com"
        )
    finally:
        os.chmod(locked, stat.S_IRUSR | stat.S_IWUSR)

    assert chosen == str(expected)


def test_resolve_returns_blank_when_root_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unverified platform layout degrades to "" so callers use their own cache."""
    monkeypatch.setattr(
        fusion_recents, "OPTIONS_ROOT_CANDIDATES", (str(tmp_path / "nope"),)
    )

    assert (
        fusion_recents.resolve_recents_path(hub_url="https://imallc.autodesk360.com")
        == ""
    )
    assert any("options root" in line for line in fusion_recents.resolution_trace())


def test_resolution_trace_records_the_choice(options_root: Path) -> None:
    """The trace is the diagnostic that pins down an unverified platform layout."""
    user_dir = _write_user_dir(options_root, "200707241731883")
    expected = _write_recents(user_dir, "imallc")

    fusion_recents.resolve_recents_path(hub_url="https://imallc.autodesk360.com")
    trace = fusion_recents.resolution_trace()

    assert any(str(expected) in line for line in trace)
    assert any("hub prefix: imallc" in line for line in trace)


# ---------------------------------------------------------------------------
# parse_recents / normalize_entry / list_native_recents
# ---------------------------------------------------------------------------


def test_parse_recents_reads_files_array(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    path.write_text(json.dumps({"files": [{"id": "a"}], "moreData": True}))

    assert fusion_recents.parse_recents(str(path)) == [{"id": "a"}]


@pytest.mark.parametrize(
    "payload", ['{"files": {}}', "[]", '{"nofiles": 1}', "not json", ""]
)
def test_parse_recents_malformed_returns_empty(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "r.json"
    path.write_text(payload)

    assert fusion_recents.parse_recents(str(path)) == []


def test_parse_recents_missing_path_returns_empty(tmp_path: Path) -> None:
    assert fusion_recents.parse_recents(str(tmp_path / "nope.json")) == []
    assert fusion_recents.parse_recents("") == []


def test_normalize_entry_maps_all_fields() -> None:
    """Field mapping, including the ``A/B`` -> ``A > B`` location re-punctuation."""
    entry = {
        "name": "voron_mobius_3.1",
        "id": "urn:adsk.wipprod:dm.lineage:Q1",
        "fileType": "f3d",
        "docstruct": '{"type":"hybrid-standard"}',
        "location": "3D Printers/Voron Family",
        "lastOpened": "1786636724000",
        "version": "8",
        "versionUrn": "urn:adsk.wipprod:fs.file:vf.Q1?version=8",
    }

    assert fusion_recents.normalize_entry(entry) == {
        "dataFileId": "urn:adsk.wipprod:dm.lineage:Q1",
        "name": "voron_mobius_3.1",
        "intent": "hybrid",
        "location": "3D Printers > Voron Family",
        "lastOpened": 1786636724000,
        "version": "8",
        "versionUrn": "urn:adsk.wipprod:fs.file:vf.Q1?version=8",
        "fileType": "f3d",
    }


def test_normalize_entry_tolerates_missing_keys() -> None:
    """Keys really are absent in the wild, so every field must use ``.get``."""
    out = fusion_recents.normalize_entry({"id": "urn:x", "fileType": "f3d"})

    assert out == {
        "dataFileId": "urn:x",
        "name": "",
        "intent": "",
        "location": "",
        "lastOpened": 0,
        "version": "",
        "versionUrn": "",
        "fileType": "f3d",
    }


@pytest.mark.parametrize(
    "entry",
    [
        {"id": "", "fileType": "f3d"},
        {"fileType": "f3d"},
        {"id": "urn:x", "fileType": "f2d"},
        {"id": "urn:x", "fileType": "f3d", "lastOpened": "not-a-number"},
        "not a dict",
    ],
)
def test_normalize_entry_skips_unusable(entry) -> None:
    assert fusion_recents.normalize_entry(entry) is None


def test_normalize_entry_accepts_all_types_when_unfiltered() -> None:
    """Open Recent lists drawings too, so ``file_types=None`` accepts everything."""
    entry = {"id": "urn:x", "fileType": "f2d"}

    assert fusion_recents.normalize_entry(entry, file_types=None)["fileType"] == "f2d"


def test_list_native_recents_sorts_by_last_opened_desc(tmp_path: Path) -> None:
    """The stored order is not reliably newest-first, so the sort is explicit.

    The fixture reproduces a real inversion pair observed in the live file (an
    entry at index 39 was older than the one after it).
    """
    path = tmp_path / "r.json"
    path.write_text(
        json.dumps(
            {
                "files": [
                    {"id": "urn:a", "fileType": "f3d", "lastOpened": "1786518000000"},
                    {"id": "urn:b", "fileType": "f3d", "lastOpened": "1786518120000"},
                    {"id": "urn:c", "fileType": "f3d", "lastOpened": "1786519000000"},
                ]
            }
        )
    )

    ids = [e["dataFileId"] for e in fusion_recents.list_native_recents(str(path))]

    assert ids == ["urn:c", "urn:b", "urn:a"]


def test_list_native_recents_filters_dedupes_and_limits(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    path.write_text(
        json.dumps(
            {
                "files": [
                    {"id": "urn:a", "fileType": "f3d", "lastOpened": "300"},
                    {"id": "urn:a", "fileType": "f3d", "lastOpened": "100"},
                    {"id": "urn:draw", "fileType": "f2d", "lastOpened": "400"},
                    {"id": "urn:b", "fileType": "f3d", "lastOpened": "200"},
                ]
            }
        )
    )

    assert [e["dataFileId"] for e in fusion_recents.list_native_recents(str(path))] == [
        "urn:a",
        "urn:b",
    ]
    assert [
        e["dataFileId"] for e in fusion_recents.list_native_recents(str(path), limit=1)
    ] == ["urn:a"]
    assert [
        e["dataFileId"]
        for e in fusion_recents.list_native_recents(str(path), file_types=None)
    ] == ["urn:draw", "urn:a", "urn:b"]
