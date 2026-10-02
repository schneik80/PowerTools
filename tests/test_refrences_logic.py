"""Document References: merging a drawing's two sources of Uses.

A drawing's Uses list comes from ``DataFile.childReferences`` and, as a
backstop, the open drawing's ``documentReferences``. Both can name the same
source design; ``unique_by_id`` must list it once.
"""

from types import SimpleNamespace as NS

from PowerTools.commands.refrences import logic


class NoId:
    @property
    def id(self):
        raise RuntimeError("InternalValidationError")


def test_keeps_the_first_of_each_id_in_order():
    a1, b, a2 = NS(id="a", n=1), NS(id="b"), NS(id="a", n=2)
    assert logic.unique_by_id([a1, b], [a2]) == [a1, b]


def test_second_group_fills_in_what_the_first_lacks():
    design = NS(id="arm1")
    assert logic.unique_by_id([], [design]) == [design]


def test_none_groups_are_empty():
    assert logic.unique_by_id(None, None) == []


def test_unreadable_or_empty_ids_are_dropped():
    good = NS(id="x")
    assert logic.unique_by_id([NoId(), NS(id=""), NS(id=None), good]) == [good]
