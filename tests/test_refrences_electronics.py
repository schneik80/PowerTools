"""Document References: resolving the electronics design a file belongs to.

The fixture is the Air_Quality_Sensor design as the cloud reported it on
ADSKMVG91G2F5W, pre-production 2706.0.116, 2026-10-02: a project whose
children are a schematic and a 2D board, a board whose child is the 3D PCB,
and a drawing of the 3D PCB whose child is -- as Fusion records it -- the
project. The electronics files share one name, so identity is the id alone.
"""

from PowerTools.commands.refrences import electronics as el


class File:
    def __init__(self, id, ext, name="Air_Quality_Sensor"):
        self.id, self.fileExtension, self.name = id, ext, name
        self.parentReferences, self.childReferences = [], []


class Broken(File):
    @property
    def parentReferences(self):
        raise RuntimeError("cloud")

    @parentReferences.setter
    def parentReferences(self, value):
        pass

    @property
    def childReferences(self):
        raise RuntimeError("cloud")

    @childReferences.setter
    def childReferences(self, value):
        pass


def air_quality():
    prj, sch, brd, pcb, dwg = (
        File("prj", "fprj"),
        File("sch", "fsch"),
        File("brd", "fbrd"),
        File("pcb", "f3d"),
        File("dwg", "f2d", "Air_Quality_Sensor Drawing"),
    )
    prj.childReferences = [sch, brd]
    prj.parentReferences = [dwg]
    sch.parentReferences = [prj]
    brd.parentReferences = [prj]
    brd.childReferences = [pcb]
    pcb.parentReferences = [brd]
    dwg.childReferences = [prj]
    return prj, sch, brd, pcb, dwg


def ids(group):
    return [f.id for f in group]


def assert_whole_set(s):
    assert ids(s.projects) == ["prj"]
    assert ids(s.schematics) == ["sch"]
    assert ids(s.boards) == ["brd"]
    assert ids(s.pcb3ds) == ["pcb"]
    assert ids(s.drawings) == ["dwg"]


def test_every_member_resolves_the_whole_set():
    for start in air_quality():
        assert_whole_set(el.electronics_set(start))


def test_ids_covers_all_five():
    prj, *_ = air_quality()
    assert el.electronics_set(prj).ids() == {"prj", "sch", "brd", "pcb", "dwg"}


def test_an_ordinary_design_is_not_electronics():
    part = File("part", "f3d")
    part.parentReferences = [File("asm", "f3d")]
    assert el.electronics_set(part) is None
    assert el.boards_of_design(part) == []


def test_a_drawing_of_an_ordinary_design_is_not_electronics():
    dwg = File("dwg", "f2d")
    dwg.childReferences = [File("part", "f3d")]
    assert el.electronics_set(dwg) is None
    assert el.electronics_set(File("empty", "f2d")) is None


def test_a_drawing_that_references_the_3d_pcb_directly():
    _, _, brd, pcb, _ = air_quality()
    direct = File("dwg2", "f2d")
    direct.childReferences = [pcb]
    pcb.parentReferences = [brd, direct]
    s = el.electronics_set(direct)
    assert_ids = {k: ids(getattr(s, k)) for k in ("projects", "boards", "pcb3ds")}
    assert assert_ids == {"projects": ["prj"], "boards": ["brd"], "pcb3ds": ["pcb"]}
    assert ids(s.drawings) == ["dwg2", "dwg"]


def test_a_board_without_its_project_still_lists_itself_and_its_3d_pcb():
    brd, pcb = File("brd", "fbrd"), File("pcb", "f3d")
    brd.childReferences = [pcb]
    s = el.electronics_set(brd)
    assert ids(s.projects) == []
    assert ids(s.boards) == ["brd"]
    assert ids(s.pcb3ds) == ["pcb"]


def test_a_3d_pcb_whose_board_lost_its_project():
    brd, pcb = File("brd", "fbrd"), File("pcb", "f3d")
    brd.childReferences = [pcb]
    pcb.parentReferences = [brd]
    s = el.electronics_set(pcb)
    assert ids(s.boards) == ["brd"]
    assert ids(s.pcb3ds) == ["pcb"]


def test_reference_reads_that_raise_read_as_none():
    s = el.electronics_set(Broken("sch", "fsch"))
    assert ids(s.schematics) == ["sch"]
    assert ids(s.projects) == ids(s.boards) == ids(s.pcb3ds) == []


def test_extension_is_case_insensitive_and_classifies():
    assert el.is_electronics_file(File("x", "FBRD"))
    assert not el.is_electronics_file(File("x", "f3d"))
