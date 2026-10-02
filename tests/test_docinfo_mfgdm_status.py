"""MFGDM verdicts for Document Information.

``commands/docinfo/mfgdm_status.py`` turns ``mfgdm://v3`` answers into the
lines the dialog states as fact ("Available", "Not found", "links this drawing
to a different design"). The fixtures are the shapes the live endpoint returned
on ADSKMVG91G2F5W, pre-production channel, 2026-10-01, for a drawing whose
MFGDM link pointed at a different design from its local reference -- a Fusion
bug, and the case the mismatch warning exists to surface.
"""

from PowerTools.commands.docinfo import mfgdm_status as ms

DRAWING_LINEAGE = "urn:adsk.wipprod:dm.lineage:dRpT3b7ySrqDQ9PgV2XB5A"
LOCAL_SOURCE = "urn:adsk.wipprod:dm.lineage:TR3dxi4ZRpyXRa8FJ7EbqA"
CLOUD_SOURCE = "urn:adsk.wipprod:dm.lineage:o7KoITy6SmylfTRvLlCwLQ"
HUB = "urn:adsk.ace:prod.scope:b6bdc768-a837-49ac-a13d-2e20f8635382"

ITEM_DATA = {
    "item": {
        "__typename": "DrawingItem",
        "id": DRAWING_LINEAGE,
        "tipVersion": {"versionNumber": 4},
        "tipDrawing": {
            "id": "ZHJhd35QVll",
            "itemNumber": {"id": ""},
            "lifecycle": {"state": {"value": ""}, "revision": {"value": ""}},
            "model": {
                "id": "bW9kZWx-SkxpSW03",
                "designItem": {"id": CLOUD_SOURCE, "name": "Arm1 Copy"},
            },
        },
    }
}

MODEL_DATA = {
    "model": {
        "id": "bW9kZWx-ZHNuaDds",
        "component": {
            "id": "cHJvZHVjdH5Q",
            "hub": {"id": HUB},
            "partNumber": {"value": "PRT-000035"},
            "itemNumber": {"id": ""},
        },
        "designItem": {"id": LOCAL_SOURCE, "name": "Arm1"},
    }
}


class FakeGql:
    """Records calls; answers with *data* or raises *exc*."""

    def __init__(self, data=None, exc=None):
        self.data, self.exc, self.calls = data, exc, []

    def __call__(self, query, variables):
        self.calls.append((query, variables))
        if self.exc:
            raise self.exc
        return self.data


# --- summaries --------------------------------------------------------------


def test_summarize_item_flattens_a_drawing_item():
    s = ms.summarize_item(ITEM_DATA)
    assert s["status"] == ms.OK
    assert s["kind"] == "DrawingItem"
    assert s["version_number"] == "4"
    assert s["drawing_id"] == "ZHJhd35QVll"
    assert s["source_design_item_id"] == CLOUD_SOURCE
    assert s["source_design_item_name"] == "Arm1 Copy"
    assert s["item_number"] == ""


def test_summarize_item_null_item_is_missing():
    assert ms.summarize_item({"item": None}) == {"status": ms.MISSING}
    assert ms.summarize_item({}) == {"status": ms.MISSING}
    assert ms.summarize_item(None) == {"status": ms.MISSING}


def test_summarize_item_tolerates_null_levels():
    s = ms.summarize_item({"item": {"__typename": "DrawingItem", "tipDrawing": None}})
    assert s["status"] == ms.OK
    assert s["drawing_id"] == ""
    assert s["source_design_item_id"] == ""


def test_summarize_model_flattens_a_model():
    s = ms.summarize_model(MODEL_DATA)
    assert s["status"] == ms.OK
    assert s["model_id"] == "bW9kZWx-ZHNuaDds"
    assert s["component_id"] == "cHJvZHVjdH5Q"
    assert s["hub_id"] == HUB
    assert s["part_number"] == "PRT-000035"
    assert s["design_item_id"] == LOCAL_SOURCE


def test_summarize_model_null_model_is_missing():
    assert ms.summarize_model({"model": None}) == {"status": ms.MISSING}


# --- fetching ---------------------------------------------------------------


def test_model_summary_without_a_local_id_never_queries():
    gql = FakeGql(MODEL_DATA)
    assert ms.model_summary(gql, "") == {"status": ms.NO_LOCAL_ID}
    assert gql.calls == []


def test_model_summary_passes_the_model_id():
    gql = FakeGql(MODEL_DATA)
    assert ms.model_summary(gql, "m-1")["status"] == ms.OK
    assert gql.calls == [(ms.MODEL_QUERY, {"modelId": "m-1"})]


def test_item_summary_needs_both_ids():
    gql = FakeGql(ITEM_DATA)
    assert ms.item_summary(gql, "", DRAWING_LINEAGE)["status"] == ms.NO_LOCAL_ID
    assert ms.item_summary(gql, HUB, "")["status"] == ms.NO_LOCAL_ID
    assert gql.calls == []
    assert ms.item_summary(gql, HUB, DRAWING_LINEAGE)["status"] == ms.OK
    assert gql.calls == [(ms.ITEM_QUERY, {"hubId": HUB, "itemId": DRAWING_LINEAGE})]


def test_a_failing_transport_becomes_an_error_summary():
    gql = FakeGql(exc=RuntimeError("MFGDM HTTP 500"))
    s = ms.model_summary(gql, "m-1")
    assert s == {"status": ms.ERROR, "error": "MFGDM HTTP 500"}


# --- mismatch ---------------------------------------------------------------


def test_source_mismatch_only_on_a_provable_disagreement():
    assert ms.source_mismatch(LOCAL_SOURCE, CLOUD_SOURCE) is True
    assert ms.source_mismatch(LOCAL_SOURCE, LOCAL_SOURCE) is False
    assert ms.source_mismatch("", CLOUD_SOURCE) is False
    assert ms.source_mismatch(LOCAL_SOURCE, "") is False


# --- rendering --------------------------------------------------------------


def test_render_design_ok_lists_the_ids_and_does_not_warn():
    html, warn = ms.render_design(ms.summarize_model(MODEL_DATA))
    assert warn is False
    assert "Available" in html
    assert "PRT-000035" in html
    assert HUB in html


def test_render_design_without_a_local_id_warns_and_says_why():
    html, warn = ms.render_design({"status": ms.NO_LOCAL_ID})
    assert warn is True
    assert "Not available yet" in html
    assert "Model ID" not in html


def test_render_design_error_shows_the_message_escaped():
    html, warn = ms.render_design({"status": ms.ERROR, "error": "bad <token>"})
    assert warn is True
    assert "bad &lt;token&gt;" in html


def test_render_drawing_flags_the_mfgdm_link_mismatch():
    item = ms.summarize_item(ITEM_DATA)
    model = ms.summarize_model(MODEL_DATA)
    html, warn = ms.render_drawing(item, "Arm1", LOCAL_SOURCE, model)
    assert warn is True
    assert "different design" in html
    assert "Arm1 Copy" in html


def test_render_drawing_matching_source_does_not_warn():
    data = {
        "item": {
            **ITEM_DATA["item"],
            "tipDrawing": {
                **ITEM_DATA["item"]["tipDrawing"],
                "model": {
                    "id": "m",
                    "designItem": {"id": LOCAL_SOURCE, "name": "Arm1"},
                },
            },
        }
    }
    html, warn = ms.render_drawing(
        ms.summarize_item(data), "Arm1", LOCAL_SOURCE, ms.summarize_model(MODEL_DATA)
    )
    assert warn is False
    assert "different design" not in html


def test_render_drawing_with_the_source_not_loaded_does_not_warn():
    item = ms.summarize_item(ITEM_DATA)
    html, warn = ms.render_drawing(
        item, "Arm1 Copy", CLOUD_SOURCE, {"status": ms.NOT_LOADED}
    )
    assert warn is False
    assert "not open in Fusion" in html


def test_render_drawing_missing_item_warns():
    html, warn = ms.render_drawing({"status": ms.MISSING}, "", "", None)
    assert warn is True
    assert "Not found" in html
    assert "Source Design:</b> (none)" in html


def test_render_escapes_names():
    item = ms.summarize_item(ITEM_DATA)
    html, _ = ms.render_drawing(
        item, "<script>", LOCAL_SOURCE, {"status": ms.NOT_LOADED}
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# --- electronics ------------------------------------------------------------

BASIC_ITEM_DATA = {
    "item": {
        "__typename": "BasicItem",
        "id": "urn:adsk.wipprod:dm.lineage:yKF7TfjGQ62L22fwrY4zsg",
        "extensionType": "fsch",
        "tipVersion": {"versionNumber": 1},
    }
}


def test_summarize_item_reads_a_basic_item():
    s = ms.summarize_item(BASIC_ITEM_DATA)
    assert s["status"] == ms.OK
    assert s["kind"] == "BasicItem"
    assert s["extension"] == "fsch"
    assert s["version_number"] == "1"
    assert s["drawing_id"] == ""


def test_render_file_ok_says_it_is_a_file_record_and_does_not_warn():
    html, warn = ms.render_file(ms.summarize_item(BASIC_ITEM_DATA))
    assert warn is False
    assert "BasicItem" in html and "fsch" in html
    assert "only a file record" in html


def test_render_file_missing_warns():
    html, warn = ms.render_file({"status": ms.MISSING})
    assert warn is True
    assert "Not found" in html
