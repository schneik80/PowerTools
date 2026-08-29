"""Tests for the Flatten Surface report writer.

Both documents are plain text built with f-strings, so the risks are structural
rather than numerical: malformed XML that no browser will open, a legend that
mislabels which end is compression, or a run with folded triangles that reports
a clean pattern anyway. These check exactly those.
"""

import importlib.util
import xml.etree.ElementTree as ElementTree
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name, filename):
    path = REPO_ROOT / "commands" / "flattensurface" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


flatten = _load("fs_flatten_for_report", "flatten.py")
report = _load("fs_report", "report.py")


def sample():
    """A two-triangle square with a mild strain gradient across it."""
    uvs = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    tris = [(0, 1, 2), (0, 2, 3)]
    strain = [-0.02, 0.0, 0.03, 0.0]
    limit = flatten.strain_limit(strain, percentile=0.0)
    colors = [flatten.strain_to_rgba(value, limit) for value in strain]
    boundary = [[0, 1, 2, 3]]
    return uvs, tris, colors, boundary, limit


def test_svg_is_well_formed_xml():
    uvs, tris, colors, boundary, limit = sample()

    svg = report.svg_strain_map(
        uvs, tris, colors, boundary, limit, flatten.strain_to_rgba
    )
    root = ElementTree.fromstring(svg)

    assert root.tag.endswith("svg")


def test_svg_draws_one_polygon_per_triangle_plus_the_outline():
    uvs, tris, colors, boundary, limit = sample()

    svg = report.svg_strain_map(
        uvs, tris, colors, boundary, limit, flatten.strain_to_rgba
    )
    root = ElementTree.fromstring(svg)
    polygons = root.findall(".//{http://www.w3.org/2000/svg}polygon")

    assert len(polygons) == len(tris) + len(boundary)


def test_svg_labels_the_legend_with_signed_percentages():
    uvs, tris, colors, boundary, limit = sample()

    svg = report.svg_strain_map(
        uvs, tris, colors, boundary, limit, flatten.strain_to_rgba
    )

    assert f"{limit * 100.0:+.2f}%" in svg
    assert f"{-limit * 100.0:+.2f}%" in svg
    assert "compression" in svg and "stretch" in svg


def test_svg_escapes_a_title_that_looks_like_markup():
    uvs, tris, colors, boundary, limit = sample()

    svg = report.svg_strain_map(
        uvs,
        tris,
        colors,
        boundary,
        limit,
        flatten.strain_to_rgba,
        title="<not a tag> & co",
    )
    root = ElementTree.fromstring(svg)
    texts = [node.text for node in root.findall(".//{http://www.w3.org/2000/svg}text")]

    assert "<not a tag> & co" in texts


def test_svg_flips_the_y_axis_so_the_pattern_is_not_mirrored():
    # SVG's Y axis points down while the pattern's points up. Getting this
    # wrong produces a vertically mirrored - and unusable - cut file.
    uvs = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    tris = [(0, 1, 2)]
    colors = [(0, 0, 0, 255)] * 3

    svg = report.svg_strain_map(uvs, tris, colors, [], 0.01, flatten.strain_to_rgba)
    root = ElementTree.fromstring(svg)
    polygon = root.find(".//{http://www.w3.org/2000/svg}polygon")
    points = [
        tuple(float(v) for v in pair.split(","))
        for pair in polygon.get("points").split()
    ]

    # Vertex 2 is highest in pattern space, so it must have the smallest y here.
    assert points[2][1] < points[0][1]


def test_svg_handles_an_empty_pattern():
    svg = report.svg_strain_map([], [], [], [], 0.0, flatten.strain_to_rgba)

    root = ElementTree.fromstring(svg)
    assert root.tag.endswith("svg")


def test_markdown_reports_the_headline_numbers():
    stats = flatten.FlattenStats(
        vertices=120,
        triangles=200,
        islands=1,
        area_3d=10.0,
        area_2d=10.5,
        min_strain=-0.021,
        max_strain=0.034,
        mean_abs_strain=0.012,
    )

    text = report.markdown_report(
        stats,
        document_name="Bracket",
        face_count=3,
        quality="Medium",
        relaxed=True,
        svg_name="Bracket-strain.svg",
    )

    assert "# Flattened pattern - Bracket" in text
    assert "+3.40%" in text
    assert "-2.10%" in text
    assert "1.20%" in text
    assert "![Strain map](Bracket-strain.svg)" in text
    assert "LSCM then ARAP relaxation" in text
    assert "| Faces selected | 3 |" in text


def test_markdown_notes_the_method_when_relaxation_is_off():
    stats = flatten.FlattenStats(triangles=10)

    text = report.markdown_report(stats, "Doc", 1, "Coarse", False, "map.svg")

    assert "LSCM only" in text


def test_markdown_warns_about_folded_triangles():
    stats = flatten.FlattenStats(triangles=10, flipped=4, degenerate=2)

    text = report.markdown_report(stats, "Doc", 1, "Fine", True, "map.svg")

    assert "## Warnings" in text
    assert "4 triangles folded over" in text
    assert "2 triangles were too small" in text


def test_markdown_stays_quiet_when_nothing_is_wrong():
    stats = flatten.FlattenStats(triangles=10)

    text = report.markdown_report(stats, "Doc", 1, "Fine", True, "map.svg")

    assert "## Warnings" not in text


def test_markdown_converts_areas_to_the_requested_units():
    stats = flatten.FlattenStats(area_3d=6.4516, area_2d=6.4516)

    text = report.markdown_report(stats, "Doc", 1, "Fine", True, "map.svg", units="in")

    assert "1.000 in^2" in text
