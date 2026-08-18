// Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
// Team Add-ins report palette. Renders one static report handed over by
// entry.py in window.__ptTeamAddins (written to init.js just before the palette
// is created). There is no polling and no live state: the palette is opened
// fresh for each check, so a stale report can never be on screen.

(function () {
    "use strict";

    var S = window.__ptTeamAddins || {
        status: "up_to_date", headline: "", detail: "", rows: [], errors: [],
        orphans: [], restartRequired: false, folderName: "", projectName: "",
        checkedAt: "", trigger: "manual"
    };

    var GLYPH = { loaded: "✓", restart: "↻", failed: "✕" };

    function el(tag, attrs, children) {
        var node = document.createElement(tag);
        attrs = attrs || {};
        Object.keys(attrs).forEach(function (key) {
            if (key === "class") node.className = attrs[key];
            else if (key === "text") node.textContent = attrs[key];
            else node.setAttribute(key, attrs[key]);
        });
        (children || []).forEach(function (child) { node.appendChild(child); });
        return node;
    }

    function send(action, data) {
        try {
            adsk.fusionSendData(action, JSON.stringify(data || {}));
        } catch (e) { /* palette closing */ }
    }

    // Plenty of add-ins never bump the version in their own manifest, so an
    // update would otherwise render as "1.0.0 → 1.0.0" and read as a no-op.
    // The hub's file revision always moves, so it is the fallback whenever the
    // declared version fails to say anything.
    function versionText(row) {
        var declaredMoved = row.from_version && row.version &&
                            row.from_version !== row.version;
        if (declaredMoved) return row.from_version + " → " + row.version;

        if (row.action === "update") {
            var rev = row.from_revision && row.revision
                ? "rev " + row.from_revision + " → " + row.revision
                : (row.revision ? "rev " + row.revision : "updated");
            return row.version ? row.version + " · " + rev : rev;
        }

        if (row.version) return row.version;
        return row.revision ? "rev " + row.revision : "";
    }

    function rowNode(row) {
        var state = row.state || "loaded";
        var title = el("div", { class: "name", text: row.name || row.addin_id });

        var text = versionText(row);
        if (text) {
            title.appendChild(el("span", { class: "version", text: text }));
        }

        var body = [title];
        if (row.message) body.push(el("div", { class: "message", text: row.message }));

        return el("div", { class: "row " + state }, [
            el("span", { class: "glyph", text: GLYPH[state] || "•" }),
            el("div", { class: "body" }, body)
        ]);
    }

    function render() {
        var headline = document.getElementById("headline");
        var detail = document.getElementById("detail");
        var banner = document.getElementById("banner");
        var content = document.getElementById("content");
        var meta = document.getElementById("meta");
        var configure = document.getElementById("configure");

        headline.textContent = S.headline || "Team Add-ins";
        if (S.detail) detail.textContent = S.detail;
        else detail.remove();

        // One banner, and only when it earns its place: a restart notice
        // outranks an error notice because it is the one thing the user has to
        // act on.
        if (S.restartRequired) {
            var n = S.rows.filter(function (r) { return r.state === "restart"; }).length;
            banner.className = "banner warn";
            banner.textContent = "Restart Fusion to finish updating " + n +
                (n === 1 ? " add-in." : " add-ins.");
            banner.hidden = false;
        } else if (S.status === "error" || S.errors.length) {
            banner.className = "banner error";
            banner.textContent = "Some team add-ins could not be installed.";
            banner.hidden = false;
        }

        var failed = S.rows.filter(function (r) { return r.state === "failed"; });
        var ok = S.rows.filter(function (r) { return r.state !== "failed"; });

        if (!S.rows.length && !S.errors.length && !(S.orphans || []).length) {
            var message = S.status === "not_configured"
                ? "This hub has no Shared Addins folder yet. PowerTools can create it for you."
                : "Everything is up to date. Nothing was downloaded.";
            content.appendChild(el("div", { class: "empty", text: message }));
        } else {
            if (ok.length) {
                content.appendChild(el("div", { class: "section-label", text: "Installed" }));
                ok.forEach(function (r) { content.appendChild(rowNode(r)); });
            }
            if (failed.length) {
                content.appendChild(el("div", { class: "section-label", text: "Not installed" }));
                failed.forEach(function (r) { content.appendChild(rowNode(r)); });
            }
            if (S.errors.length) {
                content.appendChild(el("div", { class: "section-label", text: "Folder problems" }));
                S.errors.forEach(function (text) {
                    content.appendChild(el("div", { class: "note", text: text }));
                });
            }
        }

        // Orphans are informational only — Team Add-ins never uninstalls
        // anything on its own — so they sit at the bottom, unstyled as a
        // problem.
        if (S.orphans && S.orphans.length) {
            content.appendChild(el("div", { class: "section-label", text: "No longer published" }));
            content.appendChild(el("div", {
                class: "note",
                text: S.orphans.join(", ") +
                    " — still installed locally. Remove with Utilities → Scripts and Add-Ins if you no longer want them."
            }));
        }

        var where = [S.projectName, S.folderName].filter(Boolean).join(" / ");
        meta.textContent = [where, S.checkedAt ? "Checked " + S.checkedAt : ""]
            .filter(Boolean).join("  ·  ");

        if (S.status === "not_configured") {
            configure.hidden = false;
            configure.addEventListener("click", function () { send("configure", {}); });
        }
        document.getElementById("close").addEventListener("click", function () {
            send("close", {});
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", render);
    } else {
        render();
    }
})();
