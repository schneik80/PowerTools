# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.
#
# Report generation for the Flatten Surface command: a Markdown summary and an
# SVG of the flattened pattern shaded by strain. Like flatten.py this imports no
# `adsk` module, so both documents can be produced and checked outside Fusion.
#
# SVG is the whole toolchain here on purpose. It is text, so it needs no imaging
# library that Fusion's Python does not have; it prints and scales without
# resampling; and every browser can open it.

import xml.sax.saxutils as saxutils

# Rendered pattern width in SVG user units. The viewBox carries the real
# centimetre extents, so this only sets the default on-screen size.
_CANVAS = 900.0
_MARGIN = 24.0
_LEGEND_HEIGHT = 46.0
_LEGEND_STOPS = 9


def _escape(text: str) -> str:
    """Escape text for inclusion in XML content."""
    return saxutils.escape(str(text))


def _format_area(value_cm2: float, units: str) -> str:
    """Format a square-centimetre area for display in *units*."""
    if units == "mm":
        return f"{value_cm2 * 100.0:.1f} mm^2"
    if units == "in":
        return f"{value_cm2 / 6.4516:.3f} in^2"
    return f"{value_cm2:.3f} cm^2"


def svg_strain_map(
    uvs: list,
    tris: list,
    colors: list,
    boundary: list,
    limit: float,
    ramp,
    title: str = "",
) -> str:
    """Render the flattened pattern as an SVG shaded by strain.

    Each triangle is filled with the average of its corner colours and stroked in
    the same colour, because leaving the triangles unstroked lets the renderer's
    anti-aliasing show hairline cracks along every shared edge.

    Args:
        uvs: Flattened coordinates in centimetres.
        tris: Triangles as (i, j, k) index tuples into *uvs*.
        colors: Per-vertex (r, g, b, a) tuples, parallel to *uvs*.
        boundary: Boundary loops as vertex index lists, outer loop first.
        limit: Symmetric strain limit the colours were mapped through, used to
            label the legend.
        ramp: The colour ramp the caller used, called as ``ramp(value, limit)``
            and returning (r, g, b, a). Passed in rather than imported so this
            module stays free of any dependency of its own.
        title: Optional heading drawn above the pattern.

    Returns:
        A complete SVG document.
    """
    if not uvs or not tris:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="60">'
            '<text x="12" y="34" font-family="sans-serif" font-size="14">'
            "No flattened geometry to show.</text></svg>"
        )

    xs = [uv[0] for uv in uvs]
    ys = [uv[1] for uv in uvs]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max(max_x - min_x, 1e-9)
    height = max(max_y - min_y, 1e-9)
    scale = _CANVAS / width
    view_w = _CANVAS + 2 * _MARGIN
    view_h = height * scale + 2 * _MARGIN + _LEGEND_HEIGHT

    def place(index: int) -> tuple[float, float]:
        """Map a flattened point into SVG space, flipping Y to point up."""
        x = (uvs[index][0] - min_x) * scale + _MARGIN
        y = (max_y - uvs[index][1]) * scale + _MARGIN
        return x, y

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{view_w:.1f}" '
        f'height="{view_h:.1f}" viewBox="0 0 {view_w:.1f} {view_h:.1f}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]

    for a, b, c in tris:
        red = (colors[a][0] + colors[b][0] + colors[c][0]) // 3
        green = (colors[a][1] + colors[b][1] + colors[c][1]) // 3
        blue = (colors[a][2] + colors[b][2] + colors[c][2]) // 3
        fill = f"#{red:02x}{green:02x}{blue:02x}"
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in (place(i) for i in (a, b, c)))
        parts.append(
            f'<polygon points="{points}" fill="{fill}" stroke="{fill}" '
            'stroke-width="0.6"/>'
        )

    for loop in boundary:
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in (place(i) for i in loop))
        parts.append(
            f'<polygon points="{points}" fill="none" stroke="#111111" '
            'stroke-width="1.4"/>'
        )

    parts.append(_legend(view_h, limit, ramp))
    if title:
        parts.append(
            f'<text x="{_MARGIN:.1f}" y="{_MARGIN - 8:.1f}" '
            'font-family="sans-serif" font-size="13" fill="#111111">'
            f"{_escape(title)}</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _legend(view_h: float, limit: float, ramp) -> str:
    """Draw the colour bar and its percent ticks along the bottom."""
    top = view_h - _LEGEND_HEIGHT + 6.0
    bar_h = 12.0
    bar_w = _CANVAS
    swatch = bar_w / _LEGEND_STOPS
    parts = []
    for step in range(_LEGEND_STOPS):
        position = (step + 0.5) / _LEGEND_STOPS
        value = (position * 2.0 - 1.0) * limit
        red, green, blue, _alpha = ramp(value, limit)
        parts.append(
            f'<rect x="{_MARGIN + step * swatch:.2f}" y="{top:.2f}" '
            f'width="{swatch:.2f}" height="{bar_h:.2f}" '
            f'fill="#{red:02x}{green:02x}{blue:02x}"/>'
        )
    parts.append(
        f'<rect x="{_MARGIN:.2f}" y="{top:.2f}" width="{bar_w:.2f}" '
        f'height="{bar_h:.2f}" fill="none" stroke="#666666" stroke-width="0.6"/>'
    )
    for fraction, anchor in ((0.0, "start"), (0.5, "middle"), (1.0, "end")):
        value = (fraction * 2.0 - 1.0) * limit * 100.0
        parts.append(
            f'<text x="{_MARGIN + fraction * bar_w:.2f}" '
            f'y="{top + bar_h + 14.0:.2f}" font-family="sans-serif" '
            f'font-size="11" fill="#333333" text-anchor="{anchor}">'
            f"{value:+.2f}%</text>"
        )
    parts.append(
        f'<text x="{_MARGIN + bar_w / 2:.2f}" y="{top - 4.0:.2f}" '
        'font-family="sans-serif" font-size="11" fill="#333333" '
        'text-anchor="middle">compression - no distortion - stretch</text>'
    )
    return "\n".join(parts)


def markdown_report(
    stats,
    document_name: str,
    face_count: int,
    quality: str,
    relaxed: bool,
    svg_name: str,
    units: str = "cm",
    timestamp: str = "",
) -> str:
    """Summarise a flattening run as Markdown.

    Args:
        stats: The run's :class:`flatten.FlattenStats`.
        document_name: Fusion document the faces came from.
        face_count: Number of faces selected.
        quality: Tessellation quality label used.
        relaxed: Whether the ARAP relaxation ran.
        svg_name: File name of the companion strain map.
        units: Display units, one of "cm", "mm" or "in".
        timestamp: Optional creation time, already formatted.

    Returns:
        The report as Markdown text.
    """
    growth = 0.0
    if stats.area_3d > 0.0:
        growth = (stats.area_2d / stats.area_3d - 1.0) * 100.0

    lines = [
        f"# Flattened pattern - {document_name}",
        "",
    ]
    if timestamp:
        lines.append(f"Generated {timestamp}")
        lines.append("")
    lines += [
        f"![Strain map]({svg_name})",
        "",
        "## Distortion",
        "",
        "The strain below is the change in local size between the surface and",
        "the flat pattern. Negative values are compression, positive values are",
        "stretch. A developable surface flattens at zero; anything else has to",
        "move material somewhere.",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Maximum stretch | {stats.max_strain * 100.0:+.2f}% |",
        f"| Maximum compression | {stats.min_strain * 100.0:+.2f}% |",
        f"| Mean absolute strain | {stats.mean_abs_strain * 100.0:.2f}% |",
        "",
        "## Pattern",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Surface area | {_format_area(stats.area_3d, units)} |",
        f"| Flattened area | {_format_area(stats.area_2d, units)} |",
        f"| Area change | {growth:+.2f}% |",
        f"| Faces selected | {face_count} |",
        f"| Separate pieces | {stats.islands} |",
        "",
        "## How it was made",
        "",
        "| Setting | Value |",
        "| --- | --- |",
        f"| Method | {'LSCM then ARAP relaxation' if relaxed else 'LSCM only'} |",
        f"| Mesh quality | {quality} |",
        f"| Triangles | {stats.triangles} |",
        f"| Vertices | {stats.vertices} |",
    ]

    warnings = []
    if stats.flipped:
        warnings.append(
            f"{stats.flipped} triangles folded over in the layout. The pattern "
            "is not trustworthy: try a finer mesh, or flatten fewer faces at "
            "once."
        )
    if stats.degenerate:
        warnings.append(
            f"{stats.degenerate} triangles were too small to measure and were skipped."
        )
    if warnings:
        lines += ["", "## Warnings", ""]
        lines += [f"- {warning}" for warning in warnings]

    lines.append("")
    return "\n".join(lines)
