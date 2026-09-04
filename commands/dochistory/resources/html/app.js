// Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
//
// Document History palette. Draws a design's version history as a stack of day
// rows, newest at the top.
//
// Each row is one calendar day, split into a track per author, with an identity
// avatar in a sticky left gutter. Alternating row bands and an elapsed-time
// label between rows ("Next day", "3 months and 2 days later") carry what a
// single strip cannot: the shape of a working day, and how long the design sat
// untouched.
//
// Two x mappings share that skeleton, behind one checkbox:
//   * off (default) - the row is a 00:00->24:00 clock fitted to the panel, so
//     noon is the same column in every row and nothing scrolls sideways.
//   * on - every save sits on one continuous chronological axis, COL_GAP apart,
//     with a polyline threading them in order. Empty time costs no width, so a
//     long history scrolls both ways inside a height-bounded box; that is the
//     trade the toggle makes. The author gutter freezes against the left edge
//     so a track never loses its face.
//
// The bucketing (which day, which track, how long a gap) is done in Python -
// commands/dochistory/history_model.py, which is unit-tested. What lives here
// is everything that needs the panel width the browser measures, plus the
// drawing itself.

(function () {
    "use strict";

    // ── geometry ─────────────────────────────────────────────────────────────
    // Spacing is this graph's own; the drawing weights (dot radius, rail width)
    // match the ones the web view shares between its two dot-on-rail charts, so
    // the two presentations of a history read as the same picture.

    var GUTTER_W = 46;   // avatar column, LEFT of the plot - never eats axis space
    var PAD_R = 14;
    var TRACK_H = 30;    // one author track
    var AXIS_H = 20;     // hour labels under the last track (day view only)
    var ROW_PAD_Y = 8;
    var HEADER_H = 22;   // the day's date line above its tracks

    // Gap bands between two day rows. Fixed heights per tier, so the whole
    // stack's vertical layout is arithmetic rather than a DOM measurement -
    // which is what lets the thread overlay place its polyline.
    var GAP_H_TIGHT = 18; // next day
    var GAP_H = 24;       // a few days
    var GAP_H_WIDE = 32;  // a week or more

    // Thread view: the pitch between consecutive saves.
    var COL_GAP = 38;

    var NODE_R = 7;
    var RING_W = 2;
    var RAIL_W = 3;
    var RAIL_ALPHA = 0.5;
    var CONNECTOR_W = 2;
    var CONNECTOR_OPACITY = 0.8;
    var TAG_FONT_SIZE = 9;

    var HALO_R = NODE_R + RING_W + 1.5;
    var SHARE_R = HALO_R + 3;
    var HIT_R = NODE_R + 5;
    var CHANGE_R = NODE_R - 2.5; // a non-save event, smaller than a save
    var DRIFT_VISIBLE = 3; // px a dot must be nudged before we mark its true time

    // Day view: the closest two dots may sit on one track before the declutter
    // pass pushes them apart.
    var MIN_DOT_GAP = NODE_R * 2 + 2;

    var DAY_ROWS_CAP = 60; // a render cap, not a data cap - see the "show all" row
    var DAY_MS = 86400000;
    var HOVER_DELAY_MS = 400;

    // ── state ────────────────────────────────────────────────────────────────

    var S = window.__ptInit || { theme: "dark", docName: "", status: "loading" };
    var thread = false;
    var showChanges = false;
    var showAll = false;
    var viewW = 720;         // measured; seeded so the first paint is not a flash
    var thumbs = {};         // versionId -> data: URL, or "" for "none available"
    var requested = {};      // versionId -> true once asked for
    var hoverTimer = null;
    var cardDot = null;      // the version the card is currently showing
    var cardTarget = null;   // the element it is anchored to

    var stackEl = document.getElementById("stack");
    var scroller = document.getElementById("scroller");
    var cardEl = document.getElementById("card");

    // ── plumbing ─────────────────────────────────────────────────────────────

    function send(action, payload) {
        try { adsk.fusionSendData(action, JSON.stringify(payload || {})); }
        catch (e) { console.log("[Document History] send failed:", action, e); }
    }

    function el(tag, attrs, kids) {
        var n = document.createElement(tag);
        apply(n, attrs, kids);
        return n;
    }

    function svgEl(tag, attrs, kids) {
        var n = document.createElementNS("http://www.w3.org/2000/svg", tag);
        apply(n, attrs, kids);
        return n;
    }

    function apply(n, attrs, kids) {
        attrs = attrs || {};
        for (var k in attrs) {
            if (!Object.prototype.hasOwnProperty.call(attrs, k)) continue;
            var v = attrs[k];
            if (v === null || v === undefined) continue;
            if (k === "class") n.setAttribute("class", v);
            else if (k === "text") n.textContent = v;
            else if (k === "style") { for (var s in v) n.style[s] = v[s]; }
            else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2), v);
            else if (n.namespaceURI === "http://www.w3.org/2000/svg") n.setAttribute(k, v);
            else n.setAttribute(k, v);
        }
        (kids || []).forEach(function (kid) { if (kid) n.appendChild(kid); });
    }

    function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); }

    // ── colour ───────────────────────────────────────────────────────────────
    //
    // Every colour but one comes from style.css, read back here so the palette
    // has a single source of truth. The exception is a person's identity
    // colour: it must be the same for the same author in every row, whatever
    // the theme, so it is a function of who rather than of the palette.

    var C = {};

    function readTheme() {
        var cs = getComputedStyle(document.documentElement);
        function get(name) { return (cs.getPropertyValue(name) || "").trim(); }
        C = {
            text: get("--text-primary"),
            secondary: get("--text-secondary"),
            muted: get("--text-muted"),
            accent: get("--accent"),
            share: get("--share"),
            divider: get("--border-color"),
            paper: get("--bg-panel")
        };
    }

    // hashKey is DJB2 - small, fast, and well spread for short strings.
    function hashKey(s) {
        var h = 5381;
        for (var i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
        return h >>> 0;
    }

    // Saturation and lightness are fixed: only the hue carries identity, so
    // every avatar has the same visual weight and none dominates the row.
    var SAT = 68;
    var LIGHT = 48;

    function userColor(key) {
        return "hsl(" + (hashKey(key) % 360) + ", " + SAT + "%, " + LIGHT + "%)";
    }

    function userColorAlpha(key, a) {
        return "hsla(" + (hashKey(key) % 360) + ", " + SAT + "%, " + LIGHT + "%, " + a + ")";
    }

    // HSL lightness is not perceptual - white on yellow at L=48% fails contrast
    // while white on blue at the same lightness is fine - so the initials are
    // solved against the disc rather than hardcoded white.
    function contrastText(hue) {
        var h = hue / 360, s = SAT / 100, l = LIGHT / 100;
        var q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        var p = 2 * l - q;
        function ch(t) {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1 / 6) return p + (q - p) * 6 * t;
            if (t < 1 / 2) return q;
            if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
            return p;
        }
        var lum = 0.2126 * ch(h + 1 / 3) + 0.7152 * ch(h) + 0.0722 * ch(h - 1 / 3);
        return lum > 0.5 ? "#1a1a1a" : "#ffffff";
    }

    // The theme colours arrive as hex; the chart needs a few of them faded.
    function fade(color, a) {
        var m = /^#([0-9a-f]{6})$/i.exec(color || "");
        if (!m) return color;
        var n = parseInt(m[1], 16);
        return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")";
    }

    // ── formatting ───────────────────────────────────────────────────────────

    function fmt(kind, opts) {
        try { return new Intl[kind](undefined, opts); }
        catch (e) { return null; }
    }

    // parseDay reads YYYY-MM-DD as LOCAL midnight. new Date('YYYY-MM-DD') parses
    // UTC midnight and renders a day early in negative-offset zones.
    function parseDay(s) {
        var p = (s || "").split("-").map(Number);
        if (p.length !== 3 || !p[0]) return null;
        return new Date(p[0], p[1] - 1, p[2]);
    }

    function sameDay(a, b) {
        return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()
            && a.getDate() === b.getDate();
    }

    function dayLabel(day) {
        var d = parseDay(day);
        if (!d) return "Date unknown";
        var now = new Date();
        var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        if (sameDay(d, today)) return "Today";
        var yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
        if (sameDay(d, yesterday)) return "Yesterday";
        var f = fmt("DateTimeFormat", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
        return f ? f.format(d) : day;
    }

    function hourLabel(hour) {
        // Formatted, not concatenated, so 6 reads "6 AM" in English and "06" in
        // German. 24 is midnight of the following day, drawn at the right edge.
        var f = fmt("DateTimeFormat", { hour: "numeric" });
        var d = new Date(2000, 0, 1, hour % 24);
        return f ? f.format(d) : String(hour % 24);
    }

    function fmtStamp(ms) {
        if (!ms) return "—";
        var f = fmt("DateTimeFormat", { dateStyle: "medium", timeStyle: "short" });
        return f ? f.format(new Date(ms)) : new Date(ms).toLocaleString();
    }

    // fmtDuration renders a calendar breakdown as a localized phrase - "3 months
    // and 2 days" - without a per-unit catalog: each part goes through
    // Intl.NumberFormat's unit style, which already knows every locale's plural
    // forms, and Intl.ListFormat joins them.
    function fmtDuration(b) {
        function part(n, unit) {
            var f = fmt("NumberFormat", { style: "unit", unit: unit, unitDisplay: "long" });
            return f ? f.format(n) : n + " " + unit + (n === 1 ? "" : "s");
        }
        var parts = [];
        if (b.years) parts.push(part(b.years, "year"));
        if (b.months) parts.push(part(b.months, "month"));
        if (b.days) {
            // Weeks only below a month, where "2 weeks" beats "14 days". Above
            // one, "1 month, 1 week and 3 days" reads worse than "1 month and
            // 10 days".
            if (!b.years && !b.months && b.days >= 7) {
                parts.push(part(Math.floor(b.days / 7), "week"));
                if (b.days % 7) parts.push(part(b.days % 7, "day"));
            } else {
                parts.push(part(b.days, "day"));
            }
        }
        if (parts.length < 2) return parts.join("");
        var lf = fmt("ListFormat", {});
        return lf ? lf.format(parts) : parts.join(", ");
    }

    function plural(n, one, many) {
        return n + " " + (n === 1 ? one : many);
    }

    // avatarInitials takes up to two words, splitting on '@' as well as
    // whitespace so a bare email address still yields more than one letter.
    function avatarInitials(name) {
        var s = (name || "").trim();
        if (!s) return "?";
        var out = s.split(/[\s@]+/).filter(Boolean).slice(0, 2)
            .map(function (w) { return Array.from(w)[0] || ""; })
            .join("").toUpperCase();
        return out || "?";
    }

    // ── layout maths ─────────────────────────────────────────────────────────

    /** Usable plot width inside a row, excluding the sticky avatar gutter. */
    function plotWidth(w) { return Math.max(80, w - GUTTER_W - PAD_R); }

    /** Day view: milliseconds since local midnight -> x inside the plot. */
    function xOfMs(ms, w) {
        return Math.max(0, Math.min(1, ms / DAY_MS)) * plotWidth(w);
    }

    /** Thread view: position in the whole history -> x inside the plot. */
    function xOfIndex(index) { return COL_GAP / 2 + index * COL_GAP; }

    /** Thread view: total plot width for a rendered history of `count` saves. */
    function threadWidth(count) { return Math.max(COL_GAP, count * COL_GAP) + PAD_R; }

    function rowHeight(trackCount, withAxis) {
        return ROW_PAD_Y * 2 + Math.max(1, trackCount) * TRACK_H + (withAxis ? AXIS_H : 0);
    }

    function trackY(i) { return ROW_PAD_Y + i * TRACK_H + TRACK_H / 2; }

    function gapHeight(tier) {
        return tier === "nextDay" ? GAP_H_TIGHT : tier === "days" ? GAP_H : GAP_H_WIDE;
    }

    /**
     * indexBase is the lowest version index among the rendered rows - what
     * xOfIndex must be offset by.
     *
     * The day-row cap drops the OLDEST days, so a capped history keeps a suffix
     * of the index range. Without rebasing, the thread axis would open with
     * sixty days' worth of blank width before the first dot.
     */
    function indexBase(rows) {
        var min = Infinity;
        rows.forEach(function (row) {
            row.tracks.forEach(function (track) {
                track.dots.forEach(function (d) { if (d.index < min) min = d.index; });
            });
        });
        return isFinite(min) ? min : 0;
    }

    /**
     * layoutStack walks the rendered rows top to bottom and returns each row's y
     * offset within the stack, plus the total height. Header and gap heights are
     * constants precisely so this can be arithmetic instead of a DOM
     * measurement - the thread overlay needs a row's y before the browser has
     * laid anything out.
     */
    function layoutStack(rows, withAxis) {
        var tops = [];
        var y = 0;
        rows.forEach(function (row, i) {
            if (i > 0 && row.gap) y += gapHeight(row.gap.tier);
            tops.push(y);
            y += HEADER_H + rowHeight(row.tracks.length, withAxis);
        });
        return { tops: tops, total: y };
    }

    /**
     * declutter nudges same-track dots apart so a burst of saves a minute apart
     * does not stack into one blob, while preserving order and staying as close
     * to true clock position as it can. Day view only - the thread axis already
     * guarantees a full COL_GAP between saves.
     *
     * The forward pass pushes right; the back pass pulls the run off the right
     * wall, so a cluster at 23:59 spreads leftward instead of being clipped.
     */
    function declutter(rawX, left, right, minGap) {
        minGap = minGap || MIN_DOT_GAP;
        var n = rawX.length;
        if (n === 0) return [];
        var x = rawX.map(function (v) { return Math.min(right, Math.max(left, v)); });

        // More dots than the axis can ever separate: space them evenly and let
        // the hover card carry the exact time. Interpolated rather than stepped,
        // because i * step drifts past `right` on the last dot for most widths.
        if ((n - 1) * minGap > right - left) {
            if (n === 1) return [left];
            return x.map(function (_, i) { return left + ((right - left) * i) / (n - 1); });
        }

        for (var i = 1; i < n; i++) if (x[i] - x[i - 1] < minGap) x[i] = x[i - 1] + minGap;
        for (var j = n - 2; j >= 0; j--) if (x[j + 1] - x[j] < minGap) x[j] = x[j + 1] - minGap;
        if (x[n - 1] > right) {
            var d = x[n - 1] - right;
            for (var k = 0; k < n; k++) x[k] -= d;
        }
        return x;
    }

    /**
     * hourTicks picks the hour gridlines for a plot of the given width, thinning
     * them as the palette narrows so the labels never collide. `label` marks the
     * ticks that get a printed hour.
     */
    function hourTicks(plotW) {
        if (plotW < 200) return [];
        var every = plotW >= 420 ? 1 : plotW >= 260 ? 3 : 6;
        var labelEvery = plotW >= 420 ? 6 : plotW >= 260 ? 12 : 24;
        var ticks = [];
        for (var h = 0; h <= 24; h += every) {
            ticks.push({ hour: h, label: h % labelEvery === 0 });
        }
        // Below 260 px only noon is labelled - the edges are implied by the row.
        if (plotW < 260) {
            return ticks.map(function (t) { return { hour: t.hour, label: t.hour === 12 }; });
        }
        return ticks;
    }

    // ── the hover card ───────────────────────────────────────────────────────

    function hideCard() {
        if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null; }
        cardEl.hidden = true;
        cardDot = null;
        cardTarget = null;
    }

    function placeCard(target) {
        // Measured after the content is in, then clamped to the palette so a
        // card on the first row or the right edge is never half off-screen.
        cardEl.hidden = false;
        var r = target.getBoundingClientRect();
        var c = cardEl.getBoundingClientRect();
        var left = Math.min(
            Math.max(6, r.left + r.width / 2 - c.width / 2),
            window.innerWidth - c.width - 6
        );
        var top = r.top - c.height - 8;
        if (top < 6) top = r.bottom + 8;
        cardEl.style.left = left + "px";
        cardEl.style.top = top + "px";
    }

    function showTip(target, text) {
        cardDot = null;
        cardTarget = null;
        clear(cardEl);
        cardEl.appendChild(el("div", { text: text }));
        placeCard(target);
    }

    /**
     * The hover card for one save: its thumbnail, version number,
     * milestone/release/share markers, the description the author typed, the
     * exact local timestamp, and who saved it.
     *
     * The thumbnail is an ungated per-version cloud call, which is why it is
     * only asked for once the pointer has actually rested on a dot for
     * HOVER_DELAY_MS. Brushing the cursor across a busy day would otherwise
     * start one download per dot passed over.
     */
    function showVersionCard(target, v) {
        cardDot = v;
        cardTarget = target;
        clear(cardEl);

        var isChange = v.kind === "change";
        var thumb = !isChange && v.versionId ? thumbs[v.versionId] : "";
        if (thumb) {
            cardEl.appendChild(el("img", { src: thumb, alt: "" }));
        } else if (!isChange && v.versionId && thumbs[v.versionId] === "") {
            cardEl.appendChild(el("div", { class: "muted", text: "No preview for this version" }));
        }

        var marks;
        if (v.kind === "change") {
            // No version number, because no version was made.
            marks = v.changeLabel || "Change";
        } else {
            marks = "v" + v.number;
            if (v.isMilestone) marks += " · Milestone";
            if (v.revision) marks += " · Release " + v.revision;
        }
        cardEl.appendChild(el("div", { class: "title", text: marks }));
        if (v.publicShare) {
            cardEl.appendChild(el("div", { class: "share", text: "Public share" }));
        }

        // Shown even when empty, so "this save has no description" is
        // distinguishable from "the description did not render".
        cardEl.appendChild(el("div", {
            class: v.comment ? "comment" : "comment muted",
            text: v.comment || (isChange ? "No detail recorded" : "No description")
        }));
        cardEl.appendChild(el("div", { class: "when", text: fmtStamp(v.createdOnMs) }));

        var key = v.createdById || v.createdBy || "";
        cardEl.appendChild(el("div", { class: "who" }, [
            avatarNode(key, v.createdBy, 18, null),
            el("span", { text: v.createdBy || "Unknown author" })
        ]));

        placeCard(target);
        if (!isChange) requestThumb(v);
    }

    function requestThumb(v) {
        if (!v.versionId || requested[v.versionId]) return;
        requested[v.versionId] = true;
        send("requestThumbs", { ids: [v.versionId] });
    }

    // ── drawing ──────────────────────────────────────────────────────────────

    function avatarNode(key, name, size, text) {
        var hue = hashKey(key) % 360;
        return el("div", {
            class: "avatar",
            style: {
                width: size + "px",
                height: size + "px",
                fontSize: Math.max(9, Math.round(size * 0.45)) + "px",
                background: text ? "var(--text-muted)" : userColor(key),
                color: text ? "var(--bg-panel)" : contrastText(hue)
            },
            text: text || avatarInitials(name)
        });
    }

    function gapNode(gap) {
        var h = gapHeight(gap.tier);
        var tier = gap.tier === "nextDay" ? "tight" : gap.tier === "wide" ? "wide" : "";
        var label = gap.tier === "nextDay"
            ? "Next day"
            : fmtDuration(gap.breakdown) + " later";
        return el("div", { class: "gap " + tier, style: { height: h + "px" } }, [
            el("div", { class: "gap-inner", style: { width: viewW + "px", height: h + "px" } }, [
                el("div", { class: "gap-rule" }),
                el("div", { class: "gap-label", text: label }),
                el("div", { class: "gap-rule" })
            ])
        ]);
    }

    // A save. The transparent circle comes first and is the hover target - it is
    // wider than the dot so the card is reachable without pixel-hunting, and
    // fill="transparent" rather than "none" because "none" is not hit-testable.
    // Milestones and releases decorate the dot in place; vertical space belongs
    // to days and people, so they get no lane of their own.
    // An edit that produced no version: a property changed, a milestone marked,
    // a part number set. Drawn as a small open ring in the author's own colour
    // so it reads as a lighter event on the same track - a save is a filled
    // dot, and a property tweak must never be mistaken for one.
    function changeNode(v, cx, cy, railColor) {
        var g = svgEl("g", {}, [
            svgEl("circle", { class: "hit", cx: cx, cy: cy, r: HIT_R, fill: "transparent" }),
            svgEl("circle", {
                cx: cx, cy: cy, r: CHANGE_R, fill: C.paper,
                stroke: railColor, "stroke-width": RING_W
            })
        ]);
        g.addEventListener("mouseenter", function () {
            if (hoverTimer) clearTimeout(hoverTimer);
            hoverTimer = setTimeout(function () { showVersionCard(g, v); }, HOVER_DELAY_MS);
        });
        g.addEventListener("mouseleave", hideCard);
        return g;
    }

    function dotNode(v, cx, cy) {
        // A milestone keeps a save's grey dot and gains the accent ring; a
        // release fills that same ring in. So the ring means "marked" and the
        // fill means "released", which is one step rather than two hues to
        // learn, and a release still reads as the heavier of the two.
        var fill = v.revision ? C.accent : C.secondary;
        var halo = C.accent;
        var kids = [svgEl("circle", { class: "hit", cx: cx, cy: cy, r: HIT_R, fill: "transparent" })];

        if (v.publicShare) {
            kids.push(svgEl("circle", {
                cx: cx, cy: cy, r: SHARE_R, fill: "none",
                stroke: C.share, "stroke-width": RING_W, "stroke-opacity": CONNECTOR_OPACITY
            }));
        }
        if (v.isMilestone || v.revision) {
            kids.push(svgEl("circle", {
                cx: cx, cy: cy, r: HALO_R, fill: "none",
                stroke: halo, "stroke-width": RING_W, "stroke-opacity": CONNECTOR_OPACITY
            }));
        }
        var core = svgEl("circle", {
            cx: cx, cy: cy, r: NODE_R, fill: fill,
            stroke: C.paper, "stroke-width": 0
        });
        kids.push(core);

        var g = svgEl("g", {}, kids);
        // The hover ring is set on the circle rather than re-rendered: a repaint
        // of the stack under the pointer would drop the element the card is
        // anchored to, and with it the hover that opened it.
        g.addEventListener("mouseenter", function () {
            core.setAttribute("stroke-width", RING_W);
            if (hoverTimer) clearTimeout(hoverTimer);
            hoverTimer = setTimeout(function () { showVersionCard(g, v); }, HOVER_DELAY_MS);
        });
        g.addEventListener("mouseleave", function () {
            core.setAttribute("stroke-width", 0);
            hideCard();
        });
        return g;
    }

    // "5 saves" is a lie once the row also holds property edits, so the header
    // counts what is actually on it.
    function rowTally(row) {
        var changes = 0;
        row.tracks.forEach(function (track) {
            track.dots.forEach(function (d) { if (d.v.kind === "change") changes++; });
        });
        var saves = row.count - changes;
        if (!changes) return plural(saves, "save", "saves");
        if (!saves) return plural(changes, "change", "changes");
        return plural(saves, "save", "saves") + " · " + plural(changes, "change", "changes");
    }

    function rowNode(row, band, plotW, base) {
        var withAxis = !thread;
        var ticks = withAxis ? hourTicks(plotW) : [];
        var h = rowHeight(row.tracks.length, withAxis && ticks.length > 0);

        var header = el("div", {
            class: "row-header",
            style: { width: viewW + "px", height: HEADER_H + "px" }
        }, [
            el("span", { class: "day", text: dayLabel(row.day) }),
            el("span", { class: "saves", text: rowTally(row) })
        ]);

        var gutter = el("div", {
            class: "gutter" + (band ? " band" : "") + (thread ? " ruled" : ""),
            // Each avatar cell is TRACK_H tall and centres its disc, so one
            // ROW_PAD_Y of lead-in lines them up with trackY().
            style: { width: GUTTER_W + "px", height: h + "px", paddingTop: ROW_PAD_Y + "px" }
        }, row.tracks.map(function (track) {
            var label = track.overflow
                ? plural(track.authorCount, "more person", "more people")
                : track.name ? "Saved by " + track.name : "Unknown author";
            var cell = el("div", { class: "avatar-cell", style: { height: TRACK_H + "px" } }, [
                avatarNode(track.key, track.name, 22, track.overflow ? "+" + track.authorCount : null)
            ]);
            cell.addEventListener("mouseenter", function () { showTip(cell, label); });
            cell.addEventListener("mouseleave", hideCard);
            return cell;
        }));

        var kids = [];

        // Hour grid - day view only; in thread view x is sequence, not clock.
        ticks.forEach(function (tick) {
            var x = xOfMs(tick.hour * 3600000, viewW);
            kids.push(svgEl("line", {
                x1: x, y1: 4, x2: x, y2: h - AXIS_H,
                stroke: C.divider, "stroke-opacity": tick.hour % 6 === 0 ? 0.7 : 0.35
            }));
        });

        row.tracks.forEach(function (track, ti) {
            var y = trackY(ti);
            var raw = track.dots.map(function (d) {
                return thread ? xOfIndex(d.index - base) : xOfMs(d.ms, viewW);
            });
            var xs = thread ? raw : declutter(raw, 0, plotWidth(viewW));
            var rail = track.overflow ? fade(C.secondary, RAIL_ALPHA)
                : userColorAlpha(track.key, RAIL_ALPHA);
            var group = [svgEl("line", {
                x1: 0, y1: y, x2: plotW, y2: y,
                stroke: rail, "stroke-width": RAIL_W, "stroke-linecap": "round"
            })];

            // Where a dot had to be nudged to stay legible, a hairline marks the
            // time it actually happened.
            xs.forEach(function (cx, i) {
                if (Math.abs(cx - raw[i]) <= DRIFT_VISIBLE) return;
                group.push(svgEl("line", {
                    x1: raw[i], y1: y - NODE_R, x2: raw[i], y2: y + NODE_R,
                    stroke: fade(C.secondary, 0.3), "stroke-width": 1
                }));
            });

            track.dots.forEach(function (d, i) {
                group.push(
                    d.v.kind === "change"
                        ? changeNode(d.v, xs[i], y, track.overflow ? C.secondary : userColor(track.key))
                        : dotNode(d.v, xs[i], y)
                );
            });
            kids.push(svgEl("g", {}, group));
        });

        // Hour labels under the last track.
        ticks.filter(function (t) { return t.label; }).forEach(function (tick) {
            var x = xOfMs(tick.hour * 3600000, viewW);
            kids.push(svgEl("text", {
                x: x, y: h - 6,
                "text-anchor": tick.hour === 0 ? "start" : tick.hour === 24 ? "end" : "middle",
                "font-size": TAG_FONT_SIZE, fill: C.secondary,
                text: hourLabel(tick.hour)
            }));
        });

        var plot = svgEl("svg", {
            class: "plot", width: plotW, height: h, role: "img",
            "aria-label": dayLabel(row.day) + " - " + rowTally(row)
        }, kids);

        return el("div", { class: "row" + (band ? " band" : "") }, [
            header,
            el("div", { class: "row-body" }, [gutter, plot])
        ]);
    }

    /**
     * Thread mode's connecting line: one polyline through every save in
     * chronological order, plus a seam wherever the axis crosses from one day
     * into the next.
     *
     * It lives in its own SVG stretched over the whole stack, because the line
     * crosses rows and a per-row SVG cannot draw outside itself. That is only
     * possible because the stack's vertical layout is arithmetic (layoutStack),
     * so a row's y is known without measuring the DOM.
     *
     * Decorative and pointer-transparent: it repeats what the rows already say,
     * and must never steal a dot's hover.
     */
    function threadOverlay(rows, width, base) {
        var stack = layoutStack(rows, false);
        var points = [];
        var dayRanges = [];

        // Rows are newest-first; the thread is drawn oldest -> newest.
        for (var r = rows.length - 1; r >= 0; r--) {
            var row = rows[r];
            if (!row.day) continue; // the undated bucket has no place on a time axis
            var first = Infinity, last = -Infinity;
            row.tracks.forEach(function (track, ti) {
                track.dots.forEach(function (d) {
                    points.push({
                        index: d.index,
                        x: GUTTER_W + xOfIndex(d.index - base),
                        y: stack.tops[r] + HEADER_H + trackY(ti)
                    });
                    if (d.index < first) first = d.index;
                    if (d.index > last) last = d.index;
                });
            });
            if (first <= last) dayRanges.push({ first: first, last: last });
        }
        if (points.length === 0) return null;
        points.sort(function (a, b) { return a.index - b.index; });

        var kids = [];
        // A seam sits midway between the last save of one day and the first of
        // the next - the only cue that the axis has crossed a date boundary,
        // since empty time consumes no width.
        for (var i = 1; i < dayRanges.length; i++) {
            var mid = (xOfIndex(dayRanges[i - 1].last - base) + xOfIndex(dayRanges[i].first - base)) / 2;
            kids.push(svgEl("line", {
                x1: GUTTER_W + mid, y1: 0, x2: GUTTER_W + mid, y2: stack.total,
                stroke: C.divider, "stroke-opacity": 0.6, "stroke-dasharray": "2 4"
            }));
        }
        if (points.length > 1) {
            kids.push(svgEl("polyline", {
                points: points.map(function (p) { return p.x + "," + p.y; }).join(" "),
                fill: "none", stroke: fade(C.secondary, 0.6), "stroke-width": CONNECTOR_W,
                "stroke-opacity": CONNECTOR_OPACITY, "stroke-linejoin": "round",
                "stroke-linecap": "round"
            }));
        }

        var svg = svgEl("svg", {
            width: width, height: stack.total, "aria-hidden": "true",
            style: { position: "absolute", top: 0, left: 0, pointerEvents: "none", overflow: "visible" }
        }, kids);
        return svg;
    }

    // Legend swatches draw the decoration, not just a colour chip, because the
    // markers differ by shape (halo, outer ring) as well as hue. Only the
    // markers that occur in this history are listed.
    function legendItem(color, label, halo, ring) {
        // halo and ring are colours, not flags: a milestone's ring is the
        // accent while its dot stays grey, so the two cannot be derived from
        // one another.
        var size = (NODE_R + RING_W + 3) * 2;
        var c = size / 2;
        var kids = [];
        if (ring) {
            kids.push(svgEl("circle", {
                cx: c, cy: c, r: NODE_R + RING_W + 1.5, fill: "none",
                stroke: ring, "stroke-width": RING_W
            }));
        }
        if (halo) {
            kids.push(svgEl("circle", {
                cx: c, cy: c, r: NODE_R + RING_W + 1.5, fill: "none",
                stroke: fade(halo, 0.8), "stroke-width": RING_W
            }));
        }
        kids.push(svgEl("circle", { cx: c, cy: c, r: NODE_R - 1, fill: color }));
        return el("span", { class: "legend-item" }, [
            svgEl("svg", { width: size, height: size, "aria-hidden": "true" }, kids),
            el("span", { text: label })
        ]);
    }

    function changeLegendItem() {
        var size = (NODE_R + RING_W + 3) * 2;
        var c = size / 2;
        return el("span", { class: "legend-item" }, [
            svgEl("svg", { width: size, height: size, "aria-hidden": "true" }, [
                svgEl("circle", {
                    cx: c, cy: c, r: CHANGE_R, fill: C.paper,
                    stroke: C.secondary, "stroke-width": RING_W
                })
            ]),
            el("span", { text: "Other changes" })
        ]);
    }

    // ── render ───────────────────────────────────────────────────────────────

    function render() {
        readTheme();
        document.documentElement.classList.toggle("light", S.theme === "light");
        hideCard();

        document.getElementById("doc-name").textContent = S.docName || "Document History";

        var banner = document.getElementById("banner");
        var more = document.getElementById("more");
        var legend = document.getElementById("legend");
        var countEl = document.getElementById("version-count");
        var toggle = document.getElementById("thread-toggle");
        clear(stackEl);
        clear(more);
        clear(legend);

        if (S.status !== "ok") {
            banner.className = S.status === "loading" ? "banner" : "banner error";
            banner.textContent = S.status === "loading"
                ? "Reading version history..."
                : (S.message || "The version history is not available.");
            countEl.textContent = "";
            toggle.style.visibility = "hidden";
            scroller.classList.remove("wide");
            return;
        }

        banner.textContent = "";
        banner.className = "banner";
        toggle.style.visibility = "visible";

        var changeCount = S.changeCount || 0;
        var changeToggle = document.getElementById("change-toggle");
        // Hidden rather than disabled when there is nothing to show: the
        // DataFile fallback cannot see these events at all, and a dead
        // checkbox would imply the history has none.
        changeToggle.hidden = changeCount === 0;
        if (changeCount === 0) showChanges = false;
        document.getElementById("change-check").checked = showChanges;

        var allRows = (showChanges ? S.rowsWithChanges : S.rows) || S.rows || [];
        var capped = !showAll && allRows.length > DAY_ROWS_CAP;
        var rows = capped ? allRows.slice(0, DAY_ROWS_CAP) : allRows;
        var shown = rows.reduce(function (n, r) { return n + r.count; }, 0);
        var base = indexBase(rows);
        var plotW = thread ? threadWidth(shown) : plotWidth(viewW);
        var stackW = thread ? GUTTER_W + threadWidth(shown) : viewW;

        countEl.textContent =
            plural(S.versionCount || 0, "version", "versions")
            + (showChanges ? " · " + plural(changeCount, "other change", "other changes") : "");
        scroller.classList.toggle("wide", thread);
        stackEl.style.width = stackW + "px";
        stackEl.style.minWidth = "100%";

        rows.forEach(function (row, i) {
            if (i > 0 && row.gap) stackEl.appendChild(gapNode(row.gap));
            stackEl.appendChild(rowNode(row, i % 2 === 1, plotW, base));
        });
        if (thread) {
            var overlay = threadOverlay(rows, stackW, base);
            if (overlay) stackEl.appendChild(overlay);
        }

        if (capped) {
            more.appendChild(el("span", { text: "Showing the most recent " + DAY_ROWS_CAP + " days" }));
            more.appendChild(el("button", {
                type: "button",
                text: "Show all " + allRows.length + " days",
                onclick: function () { showAll = true; render(); }
            }));
        }

        var versions = [];
        allRows.forEach(function (row) {
            row.tracks.forEach(function (t) {
                t.dots.forEach(function (d) { versions.push(d.v); });
            });
        });
        legend.appendChild(legendItem(C.secondary, "Saves", null, null));
        if (versions.some(function (v) { return v.isMilestone; })) {
            legend.appendChild(legendItem(C.secondary, "Milestones", C.accent, null));
        }
        if (versions.some(function (v) { return !!v.revision; })) {
            legend.appendChild(legendItem(C.accent, "Releases", C.accent, null));
        }
        if (versions.some(function (v) { return v.publicShare; })) {
            legend.appendChild(legendItem(C.secondary, "Public shares", null, C.share));
        }
        if (showChanges && versions.some(function (v) { return v.kind === "change"; })) {
            legend.appendChild(changeLegendItem());
        }
    }

    // ── wiring ───────────────────────────────────────────────────────────────

    var threadCheck = document.getElementById("thread-check");
    threadCheck.addEventListener("change", function () {
        thread = threadCheck.checked;
        render();
    });
    var changeCheck = document.getElementById("change-check");
    changeCheck.addEventListener("change", function () {
        showChanges = changeCheck.checked;
        render();
    });
    var changeToggleEl = document.getElementById("change-toggle");
    changeToggleEl.addEventListener("mouseenter", function () {
        showTip(
            changeToggleEl,
            "Include edits that made no new version - property changes, milestones, part numbers - and the people who made them"
        );
    });
    changeToggleEl.addEventListener("mouseleave", hideCard);

    var toggleEl = document.getElementById("thread-toggle");
    toggleEl.addEventListener("mouseenter", function () {
        showTip(toggleEl, "Line up every save on one continuous axis and thread them in order");
    });
    toggleEl.addEventListener("mouseleave", hideCard);

    // One observer for the whole stack: every row draws at the same measured
    // width, which is what keeps the clock axis aligned from row to row.
    if (window.ResizeObserver) {
        var ro = new ResizeObserver(function (entries) {
            var w = entries[0] && entries[0].contentRect ? entries[0].contentRect.width : 0;
            if (w > 0 && Math.abs(viewW - w) > 0.5) { viewW = w; render(); }
        });
        ro.observe(scroller);
    } else {
        window.addEventListener("resize", function () {
            viewW = scroller.clientWidth || viewW;
            render();
        });
    }

    window.fusionJavaScriptHandler = {
        handle: function (action, data) {
            try {
                if (action === "setHistory") {
                    S = JSON.parse(data);
                    thumbs = {};
                    requested = {};
                    render();
                } else if (action === "setThumbs") {
                    var mapping = JSON.parse(data);
                    for (var id in mapping) {
                        if (Object.prototype.hasOwnProperty.call(mapping, id)) {
                            thumbs[id] = mapping[id];
                        }
                    }
                    // Repaint only the open card, and only if it is the one that
                    // was waiting - a full render would tear the stack down
                    // under the pointer.
                    if (cardDot && cardTarget && mapping[cardDot.versionId] !== undefined) {
                        showVersionCard(cardTarget, cardDot);
                    }
                }
            } catch (e) {
                console.log("[Document History] handler error:", e);
            }
            return "OK";
        }
    };

    viewW = scroller.clientWidth || viewW;
    render();

    // The paint above came from init.js, which entry.py writes before the
    // palette is created - the page never waits on Python to show a history.
    // This only asks for a repaint from the state that open already gathered,
    // because Fusion's embedded browser caches init.js by URL across palette
    // recreations on Windows and can serve a stale copy.
    send("htmlReady", {});
})();
