"""Which MFGDM model id a design reports.

``mfgdm_props.design_model_id`` is how Assign Drawing Number and Document
Information find the model id they query MFGDM with. On a design opened as a
drawing's source reference, ``rootDataComponent`` was None while
``rootComponent.mfgdmModelId`` held the right id (ADSKMVG91G2F5W,
pre-production, 2026-10-01). Reading only the first made Assign Drawing Number
report "source design has no MFGDM model id yet" for a design that had one.
"""

from types import SimpleNamespace as NS

from PowerTools.commands.partnumber_shared import mfgdm_props


def design(data_component=None, root_id=""):
    return NS(rootDataComponent=data_component, rootComponent=NS(mfgdmModelId=root_id))


class Raises:
    def __getattr__(self, name):
        raise RuntimeError("InternalValidationError")


def test_prefers_root_data_component():
    d = design(NS(mfgdmModelId="from-data"), root_id="from-root")
    assert mfgdm_props.design_model_id(d) == "from-data"


def test_falls_back_when_root_data_component_is_none():
    assert mfgdm_props.design_model_id(design(None, "from-root")) == "from-root"


def test_falls_back_when_root_data_component_id_is_empty():
    assert mfgdm_props.design_model_id(design(NS(mfgdmModelId=""), "from-root")) == (
        "from-root"
    )


def test_empty_when_neither_has_one():
    assert mfgdm_props.design_model_id(design(None, "")) == ""


def test_never_raises():
    assert mfgdm_props.design_model_id(Raises()) == ""
