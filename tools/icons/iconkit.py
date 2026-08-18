# Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
#
# This source code is protected under international copyright law.  All rights
# reserved and protected by the copyright holders.
#
# This file is confidential and only available to authorized individuals with the
# permission of the copyright holders.  If you encounter this file and do not have
# permission, please contact the copyright holders and delete this file.

"""Shared drawing kit for the committed command-icon generators.

This is a developer tool, not add-in code: nothing here is imported at runtime
and Fusion never loads it.  Each command family keeps its own
``resources/generate_icons.py`` holding only that family's geometry, and loads
this module by path (see any of those scripts for the two-line loader).

Shapes are signed distance fields on a 64-unit design grid, so one set of
coordinates drives every output size.  Masks combine those fields into what
actually gets painted, and the rasterizer supersamples the mask for
anti-aliasing.  PNGs are written with zlib/struct: Fusion's embedded Python has
no Pillow, and the add-in carries no third-party dependencies, so the tooling
that produces its assets stays stdlib-only too.

Fusion picks the ``-dark`` and ``-disabled`` variant out of the resource folder
itself, so a generator only has to write the files under the right names.
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from collections.abc import Callable, Sequence

# A signed distance, in design-grid units, from a point to a shape's edge.
Field = Callable[[float, float], float]
# Whether a point on the design grid is painted.
Mask = Callable[[float, float], bool]
# A glyph: shapes to union, and sockets to subtract from that union.
Shape = tuple[list[Field], list[Field]]

GRID = 64.0
SIZES = (16, 32, 64)

# Subsamples per axis, per output size.  Small icons get more because each
# pixel carries more of the glyph.
SUBSAMPLES = {16: 16, 32: 12, 64: 8}

# Fusion has only one "-disabled" slot per size -- no dark counterpart -- so
# that grey has to stay legible against both the light and the dark theme.
LIGHT_COLOR = (0x4A, 0x4A, 0x4A)
DARK_COLOR = (0xA0, 0xA0, 0xAD)
DISABLED_COLOR = (0x96, 0x96, 0x9C)

THEME_VARIANTS = (("", LIGHT_COLOR), ("-dark", DARK_COLOR))
ALL_VARIANTS = (*THEME_VARIANTS, ("-disabled", DISABLED_COLOR))


# --------------------------------------------------------------------------
# Signed distance fields
# --------------------------------------------------------------------------


def round_box(cx: float, cy: float, hx: float, hy: float, radius: float) -> Field:
    """Build the signed distance field of a rounded rectangle.

    Args:
        cx: Centre x on the design grid.
        cy: Centre y on the design grid.
        hx: Half width, corner radius included.
        hy: Half height, corner radius included.
        radius: Corner radius.

    Returns:
        A field that is negative inside the rectangle and positive outside.
    """

    def field(x: float, y: float) -> float:
        qx = abs(x - cx) - (hx - radius)
        qy = abs(y - cy) - (hy - radius)
        outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
        inside = min(max(qx, qy), 0.0)
        return outside + inside - radius

    return field


def round_disc(cx: float, cy: float, radius: float) -> Field:
    """Build the signed distance field of a circle.

    Args:
        cx: Centre x on the design grid.
        cy: Centre y on the design grid.
        radius: Circle radius.

    Returns:
        A field that is negative inside the circle and positive outside.
    """

    def field(x: float, y: float) -> float:
        return math.hypot(x - cx, y - cy) - radius

    return field


def capsule(x1: float, y1: float, x2: float, y2: float, radius: float) -> Field:
    """Build the signed distance field of a round-capped bar.

    Args:
        x1: Start x on the design grid.
        y1: Start y on the design grid.
        x2: End x on the design grid.
        y2: End y on the design grid.
        radius: Half the bar's thickness; the caps extend this far past the ends.

    Returns:
        A field that is negative inside the bar and positive outside.
    """
    dx = x2 - x1
    dy = y2 - y1
    length_squared = dx * dx + dy * dy

    def field(x: float, y: float) -> float:
        px = x - x1
        py = y - y1
        along = 0.0
        if length_squared > 0.0:
            along = max(0.0, min(1.0, (px * dx + py * dy) / length_squared))
        return math.hypot(px - along * dx, py - along * dy) - radius

    return field


def scaled(field: Field, factor: float, dx: float, dy: float) -> Field:
    """Scale a field about the grid origin and translate it.

    Distances are rescaled with the shape, so a stroke width stated in design
    units stays the same thickness whatever the shape is scaled to.

    Args:
        field: The field to transform.
        factor: Uniform scale factor.
        dx: Translation along x, applied after scaling.
        dy: Translation along y, applied after scaling.

    Returns:
        The transformed field.
    """

    def moved(x: float, y: float) -> float:
        return field((x - dx) / factor, (y - dy) / factor) * factor

    return moved


def scale_shape(shape: Shape, factor: float, dx: float, dy: float) -> Shape:
    """Scale and translate every shape of a glyph together.

    Args:
        shape: The glyph's parts and holes.
        factor: Uniform scale factor.
        dx: Translation along x, applied after scaling.
        dy: Translation along y, applied after scaling.

    Returns:
        The transformed parts and holes.
    """
    parts, holes = shape
    return (
        [scaled(part, factor, dx, dy) for part in parts],
        [scaled(hole, factor, dx, dy) for hole in holes],
    )


# --------------------------------------------------------------------------
# Masks
# --------------------------------------------------------------------------


def _on_union_edge(parts: Sequence[Field], x: float, y: float, half: float) -> bool:
    """Test whether a point sits on the outline of a union of shapes.

    A point counts when it is within half a stroke of some shape's edge and is
    not buried deep inside any other shape.  That second test is what removes
    the seams: without it a body's edge would be drawn straight across every
    tab that overlaps it.

    Args:
        parts: The shapes to union.
        x: Point x on the design grid.
        y: Point y on the design grid.
        half: Half the stroke width.

    Returns:
        True when the point is on the union's outline.
    """
    on_edge = False
    for part in parts:
        distance = part(x, y)
        if distance < -half:
            return False
        if distance <= half:
            on_edge = True
    return on_edge


def _union_distance(parts: Sequence[Field], x: float, y: float) -> float:
    """Measure how far a point is from a union of shapes.

    The magnitude is only a lower bound inside the union, but the sign is
    exact, which is all the callers need.

    Args:
        parts: The shapes to union.
        x: Point x on the design grid.
        y: Point y on the design grid.

    Returns:
        A distance that is negative inside the union.
    """
    return min(part(x, y) for part in parts)


def filled(parts: Sequence[Field], holes: Sequence[Field] = ()) -> Mask:
    """Paint the solid union of several shapes, less any sockets.

    Args:
        parts: The shapes to union.
        holes: Shapes to subtract from that union.

    Returns:
        A mask that is true inside the union and outside every hole.
    """

    def mask(x: float, y: float) -> bool:
        if not any(part(x, y) <= 0.0 for part in parts):
            return False
        return not any(hole(x, y) <= 0.0 for hole in holes)

    return mask


def outlined(parts: Sequence[Field], width: float, holes: Sequence[Field] = ()) -> Mask:
    """Stroke the outline of a union of shapes, less any sockets.

    The outline has two halves.  Stretches of the union's own edge survive
    wherever a socket has not eaten them, and each socket wall is drawn only
    over the stretch where it cuts through the union.

    Args:
        parts: The shapes to union.
        width: Stroke width in design units.
        holes: Shapes to subtract from that union.

    Returns:
        A mask that is true on the resulting outline.
    """
    half = width / 2.0

    def mask(x: float, y: float) -> bool:
        if _on_union_edge(parts, x, y, half):
            return not holes or _union_distance(holes, x, y) >= 0.0
        if holes and _on_union_edge(holes, x, y, half):
            return _union_distance(parts, x, y) <= 0.0
        return False

    return mask


def combined(*masks: Mask) -> Mask:
    """Paint wherever any of the given masks paints.

    Args:
        masks: The masks to overlay.

    Returns:
        A mask that is true where any input is true.
    """

    def mask(x: float, y: float) -> bool:
        return any(each(x, y) for each in masks)

    return mask


def knocked_out(mask: Mask, hole: Mask) -> Mask:
    """Erase one mask from another.

    Args:
        mask: The mask to paint.
        hole: The region to leave transparent.

    Returns:
        A mask that is true where mask is true and hole is not.
    """

    def result(x: float, y: float) -> bool:
        return mask(x, y) and not hole(x, y)

    return result


def triangle(ax: float, ay: float, bx: float, by: float, cx: float, cy: float) -> Mask:
    """Paint a solid triangle.

    Args:
        ax: First corner x.
        ay: First corner y.
        bx: Second corner x.
        by: Second corner y.
        cx: Third corner x.
        cy: Third corner y.

    Returns:
        A mask that is true inside the triangle.
    """

    def side(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        return (px - x2) * (y1 - y2) - (x1 - x2) * (py - y2)

    def mask(x: float, y: float) -> bool:
        d1 = side(x, y, ax, ay, bx, by)
        d2 = side(x, y, bx, by, cx, cy)
        d3 = side(x, y, cx, cy, ax, ay)
        has_negative = d1 < 0.0 or d2 < 0.0 or d3 < 0.0
        has_positive = d1 > 0.0 or d2 > 0.0 or d3 > 0.0
        return not (has_negative and has_positive)

    return mask


def arc(
    cx: float,
    cy: float,
    radius: float,
    width: float,
    start_degrees: float,
    sweep_degrees: float,
) -> Mask:
    """Stroke a circular arc.

    Args:
        cx: Centre x on the design grid.
        cy: Centre y on the design grid.
        radius: Arc radius to the centre of the stroke.
        width: Stroke width in design units.
        start_degrees: Where the arc starts; 0 points right, 90 points down.
        sweep_degrees: How far it runs, in the direction of increasing angle.

    Returns:
        A mask that is true on the arc.
    """
    half = width / 2.0

    def mask(x: float, y: float) -> bool:
        dx = x - cx
        dy = y - cy
        if abs(math.hypot(dx, dy) - radius) > half:
            return False
        offset = (math.degrees(math.atan2(dy, dx)) - start_degrees) % 360.0
        return offset <= sweep_degrees

    return mask


def sync_badge(
    center: float, radius: float, width: float, start_degrees: float = -48.0
) -> Mask:
    """Build a circular sync arrow: an arc with a gap, closed by an arrowhead.

    Shared by every command whose job is "bring this up to date", so the mark
    means the same thing wherever it is badged onto a glyph.

    Args:
        center: Both coordinates of the badge centre on the design grid.
        radius: Arc radius to the centre of the stroke.
        width: Stroke width in design units.
        start_degrees: Where the arc starts and the arrowhead sits.

    Returns:
        A mask covering the arc and its arrowhead.
    """
    ring = arc(center, center, radius, width, start_degrees, 276.0)

    angle = math.radians(start_degrees)
    end_x = center + radius * math.cos(angle)
    end_y = center + radius * math.sin(angle)
    # Radial spans the arrowhead's base; the tangent points it into the gap.
    radial_x, radial_y = math.cos(angle), math.sin(angle)
    tangent_x, tangent_y = -math.sin(angle), math.cos(angle)
    head_length = radius * 0.70
    head_half = radius * 0.52

    head = triangle(
        end_x - tangent_x * head_length,
        end_y - tangent_y * head_length,
        end_x + radial_x * head_half,
        end_y + radial_y * head_half,
        end_x - radial_x * head_half,
        end_y - radial_y * head_half,
    )
    return combined(ring, head)


# --------------------------------------------------------------------------
# Rasterizing and writing
# --------------------------------------------------------------------------


def rasterize(mask: Mask, size: int) -> list[int]:
    """Sample a mask into one alpha byte per pixel.

    Args:
        mask: The glyph to sample, in design-grid coordinates.
        size: Output size in pixels.

    Returns:
        size * size alpha values in row-major order.

    Raises:
        KeyError: If no subsample count is configured for the size.
    """
    steps = SUBSAMPLES[size]
    unit = GRID / size
    offsets = [((index + 0.5) / steps) * unit for index in range(steps)]
    total = steps * steps

    alpha: list[int] = []
    for pixel_y in range(size):
        rows = [pixel_y * unit + offset for offset in offsets]
        for pixel_x in range(size):
            columns = [pixel_x * unit + offset for offset in offsets]
            hits = 0
            for grid_y in rows:
                for grid_x in columns:
                    if mask(grid_x, grid_y):
                        hits += 1
            alpha.append(255 * hits // total)
    return alpha


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    """Frame one PNG chunk with its length and CRC.

    Args:
        tag: Four-byte chunk type.
        data: Chunk payload.

    Returns:
        The encoded chunk.
    """
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def write_png(
    path: str, size: int, alpha: Sequence[int], color: tuple[int, int, int]
) -> None:
    """Write an 8-bit RGBA PNG of one flat colour with the given coverage.

    Args:
        path: Destination file.
        size: Image width and height in pixels.
        alpha: One alpha value per pixel, row-major.
        color: The red, green and blue channels to paint.

    Raises:
        OSError: If the file cannot be written.
    """
    red, green, blue = color
    raw = bytearray()
    index = 0
    for _ in range(size):
        raw.append(0)  # Filter type 0: none.
        for _ in range(size):
            raw += bytes((red, green, blue, alpha[index]))
            index += 1

    # Width, height, 8-bit depth, colour type 6 (RGBA), default everything else.
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _png_chunk(b"IEND", b"")
    )
    with open(path, "wb") as handle:
        handle.write(png)


def render_set(
    folder_path: str,
    build_mask: Callable[[int], Mask],
    variants: Sequence[tuple[str, tuple[int, int, int]]] = ALL_VARIANTS,
) -> None:
    """Render every size and theme variant of one glyph into a resource folder.

    The geometry is sampled once per size and then painted in each colour, so
    the variants of a size differ only in their RGB channels.

    Args:
        folder_path: The command's resources folder.
        build_mask: Builds the glyph's mask for a given output size.
        variants: The filename suffixes and colours to write.

    Raises:
        OSError: If a file cannot be written.
    """
    for size in SIZES:
        alpha = rasterize(build_mask(size), size)
        for suffix, color in variants:
            path = os.path.join(folder_path, f"{size}x{size}{suffix}.png")
            write_png(path, size, alpha, color)
            print(f"Created {path} ({os.path.getsize(path)} bytes)")
