# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Read a design's version history from MFGDM over GraphQL.

The desktop Data API cannot attribute versions. ``DataFile.createdBy`` returns
the file's creator and ``DataFile.lastUpdatedBy`` its last editor, and both
answer the same for every version in the collection: on a 27-version design
saved by nine people they reported one name each, and different names from each
other. There is no third ``User`` property and no per-version type. Fusion's own
history panel shows all nine, so the data exists - just not there.

It is in MFGDM, in two halves, which is why this module fetches both:

* ``designItem.versions`` -> ``DesignItemVersion``: ``versionNumber``,
  ``createdOn`` and ``createdBy``. The only per-version author Fusion exposes.
* ``model.history`` -> ``ModelWrittenHistoryChange``: the ``description`` the
  author typed at save time. ``DesignItemVersion.description`` exists but comes
  back empty, so the comment has to come from here.

Both arrive in one request. Measured on the 27-version design: 1.4s against 21s
for the DataFile walk it replaces, which was ~160 cloud round trips because
every property read is one.

Thumbnails are deliberately NOT requested. ``DesignItemVersion.thumbnail``
carries a ``signedUrl``, but asking for it costs about 1.4s per row - five rows
took 8.3s and thirty aborted the transport at 30s. They stay lazy, one per
hover, over the route entry.py already has.

Timing: ``mfgdmModelId`` must not be read from ``commandCreated``. Doing so and
then showing a modal crashed Fusion (234b043, commands/partnumber_shared/
intent.py). entry.py calls this from a timer-fired custom event, a later
main-loop turn.

Shape verified against the live schema on ADSKMVG91G2F5W, pre-production
channel, 2026-09-03.
"""

from __future__ import annotations

from ...lib import ptAddInUtils as ptutil
from ..partnumber_shared import mfgdm_props
from . import history_model as model

# Page sizes. The two lists have different server-side ceilings, found the hard
# way: a shared limit of 100 was rejected outright with "Pagination limit 100
# exceeds maximum allowed value of 50" against ``model.history``, which cost
# the whole cloud read and fell back to the slow path. ``designItem.versions``
# does accept 100 - the ladder probe returned a full page at that size - so the
# two are set independently rather than both dropped to the lower cap.
VERSIONS_PAGE_LIMIT = 100
HISTORY_PAGE_LIMIT = 50

# A history is not allowed to page forever. Sixty pages is far past any real
# design and bounds a server that keeps handing back a cursor.
MAX_PAGES = 60

# The two lists are paginated independently, so they take separate cursors even
# though they travel in one document.
#
# The history is fetched UNFILTERED rather than with
# ``input: { filterTypes: MODEL_WRITTEN }``: the unfiltered form is the one that
# was actually exercised against the live endpoint, and the rows a filter would
# have excluded are wanted anyway - they are the property edits and milestones
# the palette shows behind its own toggle.
_QUERY = """
query($m: ID!, $vLimit: Int!, $hLimit: Int!, $vCursor: String, $hCursor: String) {
  model(modelId: $m) {
    designItem {
      versions(pagination: { limit: $vLimit, cursor: $vCursor }) {
        pagination { cursor }
        results {
          versionNumber
          createdOn
          createdBy { id userName firstName lastName }
        }
      }
    }
    history(pagination: { limit: $hLimit, cursor: $hCursor }) {
      pagination { cursor }
      results {
        __typename
        timestamp
        description
        author { id userName firstName lastName }
      }
    }
  }
}
"""

# The history entry that corresponds to a save. Confirmed by count: a
# 27-version design produced exactly 27 of these, against 11
# PropertiesUpdatedHistoryChange, 3 ComponentPrimaryHistoryChange and 1
# VersionCreatedHistoryChange (which is a milestone, not a file version - its
# id decodes to "...~milestone").
_SAVE_CHANGE = "ModelWrittenHistoryChange"


class HistoryUnavailable(Exception):
    """MFGDM could not answer, so the caller should fall back."""


def fetch_records(model_id: str) -> tuple[list[dict], list[dict]]:
    """Return *model_id*'s history as ``(versions, other changes)``.

    Both come out of the one request. The second list is everything the history
    holds that did not produce a version - property edits, milestones, part
    number changes - which the palette shows behind its own toggle. They are
    worth keeping: on the test design two of the nine people who touched it
    never saved a version, so saves alone credit it to eight.

    Args:
        model_id: The design's timeless ``mfgdmModelId``. Must have been read
            outside ``commandCreated`` - see the module docstring.

    Returns:
        Two lists of records in the shape :func:`history_model.bucket_by_day`
        consumes, each newest first.

    Raises:
        HistoryUnavailable: No model id, or the endpoint failed or returned
            nothing usable. Always this type, so the caller has one thing to
            catch before falling back to the desktop API.
    """
    if not model_id:
        raise HistoryUnavailable("the design has no MFGDM model id")

    versions: list[dict] = []
    writes: list[dict] = []
    others: list[dict] = []
    v_cursor = h_cursor = None
    # The two lists page independently and one usually finishes first. Once a
    # list has handed back a null cursor its rows are ignored on later turns:
    # the query always asks for both, and a finished list would otherwise
    # answer from the start again and duplicate every row it already gave.
    v_done = h_done = False
    pages = 0

    while pages < MAX_PAGES:
        pages += 1
        try:
            data = mfgdm_props.gql(
                _QUERY,
                {
                    "m": model_id,
                    "vLimit": VERSIONS_PAGE_LIMIT,
                    "hLimit": HISTORY_PAGE_LIMIT,
                    "vCursor": v_cursor,
                    "hCursor": h_cursor,
                },
            )
        except Exception as exc:
            raise HistoryUnavailable(str(exc)) from exc

        model_node = (data or {}).get("model") or {}
        v_page = ((model_node.get("designItem") or {}).get("versions")) or {}
        h_page = model_node.get("history") or {}

        if not v_done:
            versions.extend(v_page.get("results") or [])
            v_cursor = (v_page.get("pagination") or {}).get("cursor")
            v_done = not v_cursor
        if not h_done:
            for row in h_page.get("results") or []:
                if row.get("__typename") == _SAVE_CHANGE:
                    writes.append(row)
                else:
                    others.append(row)
            h_cursor = (h_page.get("pagination") or {}).get("cursor")
            h_done = not h_cursor
        if v_done and h_done:
            break

    if pages >= MAX_PAGES:
        ptutil.log(
            f"Document History: stopped paging MFGDM at {MAX_PAGES} pages "
            f"({len(versions)} versions so far)."
        )
    if not versions:
        raise HistoryUnavailable("MFGDM returned no versions for this design")

    return model.merge_cloud_history(versions, writes), model.change_records(others)
