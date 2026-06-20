#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Generate version diff branch/timeline icons using Pillow.

Concept A: Split timeline - a common root splits into two branches with
version nodes, connected by a dashed comparison arrow.

Produces: 16x16, 32x32, 64x64 in both light and dark variants.
"""

from PIL import Image, ImageDraw
import os
import math

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def draw_icon_small(size, stroke_color):
    """Simplified icon for 16x16: bold Y-fork with 3 nodes, no dashes or intermediates."""
    ss = 4
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = big / 64.0
    color = stroke_color

    sw = max(3, int(3.5 * s))
    r_node = max(3, int(4.5 * s))

    # Three key points: root bottom-center, two branch tips top-left / top-right
    root = (int(32 * s), int(54 * s))
    fork = (int(32 * s), int(30 * s))
    l_tip = (int(12 * s), int(12 * s))
    r_tip = (int(52 * s), int(12 * s))

    # Trunk
    draw.line([root, fork], fill=color, width=sw)

    # Left branch (straight)
    draw.line([fork, l_tip], fill=color, width=sw)
    # Right branch (straight)
    draw.line([fork, r_tip], fill=color, width=sw)

    # Root node (filled)
    draw.ellipse([root[0] - r_node, root[1] - r_node,
                  root[0] + r_node, root[1] + r_node],
                 fill=color, outline=color)

    # Tip nodes (hollow)
    draw.ellipse([l_tip[0] - r_node, l_tip[1] - r_node,
                  l_tip[0] + r_node, l_tip[1] + r_node],
                 fill=None, outline=color, width=sw)
    draw.ellipse([r_tip[0] - r_node, r_tip[1] - r_node,
                  r_tip[0] + r_node, r_tip[1] + r_node],
                 fill=None, outline=color, width=sw)

    img = img.resize((size, size), Image.LANCZOS)
    return img


def draw_icon(size, stroke_color):
    """Draw the branch-comparison icon at the given size."""
    # Use 4x supersampling for anti-aliasing
    ss = 4
    big = size * ss
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    s = big / 64.0  # scale factor relative to 64px base

    # Stroke widths (scaled for supersampled canvas)
    sw = max(2, int(2.5 * s))
    sw_thin = max(1, int(1.8 * s))

    # Node radii
    r_big = max(3, int(3.5 * s))
    r_small = max(2, int(2.0 * s))

    # Key coordinates
    root = (int(32 * s), int(55 * s))
    bp = (int(32 * s), int(37 * s))
    l_mid = (int(21 * s), int(23 * s))
    r_mid = (int(43 * s), int(23 * s))
    l_end = (int(13 * s), int(13 * s))
    r_end = (int(51 * s), int(13 * s))

    color = stroke_color

    # --- Draw branches using line segments to approximate curves ---

    # Trunk: root to branch point
    draw.line([root, bp], fill=color, width=sw)

    # Left branch: bp -> curve -> l_mid -> l_end
    # Approximate cubic bezier with segments
    steps = 12
    prev = bp
    for i in range(1, steps + 1):
        t = i / steps
        # Simple quadratic bezier: bp -> control -> l_mid
        ctrl = (int(32 * s), int(28 * s))
        x = (1-t)**2 * bp[0] + 2*(1-t)*t * ctrl[0] + t**2 * l_mid[0]
        y = (1-t)**2 * bp[1] + 2*(1-t)*t * ctrl[1] + t**2 * l_mid[1]
        pt = (int(x), int(y))
        draw.line([prev, pt], fill=color, width=sw)
        prev = pt
    draw.line([l_mid, l_end], fill=color, width=sw)

    # Right branch: bp -> curve -> r_mid -> r_end
    prev = bp
    for i in range(1, steps + 1):
        t = i / steps
        ctrl = (int(32 * s), int(28 * s))
        x = (1-t)**2 * bp[0] + 2*(1-t)*t * ctrl[0] + t**2 * r_mid[0]
        y = (1-t)**2 * bp[1] + 2*(1-t)*t * ctrl[1] + t**2 * r_mid[1]
        pt = (int(x), int(y))
        draw.line([prev, pt], fill=color, width=sw)
        prev = pt
    draw.line([r_mid, r_end], fill=color, width=sw)

    # --- Nodes ---
    def filled_circle(center, radius):
        x, y = center
        draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                      fill=color, outline=color, width=sw)

    def hollow_circle(center, radius):
        x, y = center
        draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                      fill=None, outline=color, width=sw)

    # Root and branch point (filled)
    filled_circle(root, r_big)
    filled_circle(bp, r_big)

    # Intermediate nodes (filled, smaller)
    filled_circle(l_mid, r_small)
    filled_circle(r_mid, r_small)

    # End version nodes (hollow)
    hollow_circle(l_end, r_big)
    hollow_circle(r_end, r_big)

    # --- Dashed comparison arrow between end nodes ---
    arrow_y = l_end[1]
    arrow_left = l_end[0] + r_big + int(3 * s)
    arrow_right = r_end[0] - r_big - int(3 * s)

    # Draw dashed line
    dash_len = max(3, int(3 * s))
    gap_len = max(2, int(2.5 * s))
    x = arrow_left
    drawing = True
    while x < arrow_right:
        seg_end = min(x + (dash_len if drawing else gap_len), arrow_right)
        if drawing:
            draw.line([(x, arrow_y), (seg_end, arrow_y)], fill=color, width=sw_thin)
        x = seg_end
        drawing = not drawing

    # Arrowheads
    ah = max(3, int(3 * s))
    # Left arrowhead (pointing left)
    draw.line([(arrow_left + ah, arrow_y - ah), (arrow_left, arrow_y)], fill=color, width=sw_thin)
    draw.line([(arrow_left + ah, arrow_y + ah), (arrow_left, arrow_y)], fill=color, width=sw_thin)
    # Right arrowhead (pointing right)
    draw.line([(arrow_right - ah, arrow_y - ah), (arrow_right, arrow_y)], fill=color, width=sw_thin)
    draw.line([(arrow_right - ah, arrow_y + ah), (arrow_right, arrow_y)], fill=color, width=sw_thin)

    # Downsample with high-quality resampling
    img = img.resize((size, size), Image.LANCZOS)
    return img


def main():
    sizes = [16, 32, 64]

    # Light theme: dark charcoal
    light_color = (74, 74, 74, 255)     # #4A4A4A
    # Dark theme: silver-gray
    dark_color = (160, 160, 173, 255)   # #A0A0AD

    for size in sizes:
        # Use simplified icon for 16x16
        draw_fn = draw_icon_small if size == 16 else draw_icon

        # Light
        img = draw_fn(size, light_color)
        path = os.path.join(SCRIPT_DIR, f"{size}x{size}.png")
        img.save(path, "PNG")
        print(f"Created {path} ({os.path.getsize(path)} bytes)")

        # Dark
        img = draw_fn(size, dark_color)
        path = os.path.join(SCRIPT_DIR, f"{size}x{size}-dark.png")
        img.save(path, "PNG")
        print(f"Created {path} ({os.path.getsize(path)} bytes)")


if __name__ == "__main__":
    main()
