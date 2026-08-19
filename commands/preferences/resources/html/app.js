// Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
// PowerTools Preferences palette logic. Renders the section nav + scrolling
// content from the state provided by entry.py (window.__ptInit / setState) and
// reports every change back to Python.

(function () {
    "use strict";

    var S = window.__ptInit || {
        groups: [], hub: {}, teamAddins: {}, commandSettings: {}, theme: "dark",
        beta: false, settingsPath: "", restartNote: ""
    };

    // Per-command settings sections. Keyed by command module name.
    var CMD_SECTIONS = {
        componentwarn: {
            label: "Component Warning",
            render: function (cs) {
                return [
                    labelCheck(
                        "Also warn when creating a feature in a non-leaf component",
                        cs.warn_non_leaf === true,
                        function (v) { setCmdSetting("componentwarn", "warn_non_leaf", v); }
                    )
                ];
            }
        },
        changecyclecolor: {
            label: "Change Cycle Color",
            render: function (cs) {
                return [
                    labelCheck(
                        "Show in the right-click context menu",
                        cs.show_in_context_menu !== false,
                        function (v) { setCmdSetting("changecyclecolor", "show_in_context_menu", v); }
                    )
                ];
            }
        },
        docopen: {
            label: "Show In Location",
            // Rendered nested under its own row in the Commands list rather
            // than as a top-level section. This command has no button - it
            // only reacts to documentOpened/documentActivated - so a separate
            // section made the enable checkbox and these two toggles look like
            // three controls for two real states.
            inline: true,
            render: function (cs) {
                return [
                    labelCheck(
                        "Reveal location when a document is opened",
                        cs.run_on_open !== false,
                        function (v) { setCmdSetting("docopen", "run_on_open", v); }
                    ),
                    labelCheck(
                        "Reveal location when a document is activated",
                        cs.run_on_activate !== false,
                        function (v) { setCmdSetting("docopen", "run_on_activate", v); }
                    )
                ];
            }
        },
        defaultfolders: {
            label: "Add Project Folders",
            render: function (cs) {
                return [
                    foldersEditor("Basic folder set", cs.basic || [],
                        function (list) { setCmdSetting("defaultfolders", "basic", list); }),
                    foldersEditor("Advanced folder set", cs.advanced || [],
                        function (list) { setCmdSetting("defaultfolders", "advanced", list); })
                ];
            }
        }
        // NOTE: Team Add-ins deliberately has no entry here. Its settings are
        // rendered by teamAddinsSubsection() alongside the shared-folder status
        // card; a CMD_SECTIONS entry as well would render its settings twice
        // inside the Team Add-ins group section.
    };

    // ── helpers ──────────────────────────────────────────────────────────────
    function send(action, payload) {
        try { adsk.fusionSendData(action, JSON.stringify(payload || {})); }
        catch (e) { console.log("[Preferences] send failed:", action, e); }
    }

    function el(tag, attrs, kids) {
        var n = document.createElement(tag);
        attrs = attrs || {};
        for (var k in attrs) {
            if (k === "class") n.className = attrs[k];
            else if (k === "text") n.textContent = attrs[k];
            else if (k === "title") n.title = attrs[k];
            else if (k.slice(0, 2) === "on") n.addEventListener(k.slice(2).toLowerCase(), attrs[k]);
            else n.setAttribute(k, attrs[k]);
        }
        (kids || []).forEach(function (c) {
            if (c == null) return;
            n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
        });
        return n;
    }

    function checkbox(checked, onchange) {
        var c = el("input", { type: "checkbox" });
        c.checked = !!checked;
        c.addEventListener("change", function () { onchange(c.checked); });
        return c;
    }

    function labelCheck(text, checked, onchange) {
        var lbl = el("label", { class: "inline" });
        lbl.appendChild(checkbox(checked, onchange));
        lbl.appendChild(el("span", { text: text }));
        return lbl;
    }

    // Bounded integer field. Clamps out-of-range input rather than rejecting
    // it, so a mistyped value can never leave a setting unsaved.
    function labelNumber(text, value, min, max, onchange) {
        var lbl = el("label", { class: "inline" });
        var input = el("input", { type: "number", min: String(min), max: String(max) });
        input.value = String(value);
        input.style.width = "70px";
        input.addEventListener("change", function () {
            var n = parseInt(input.value, 10);
            if (isNaN(n)) n = value;
            n = Math.max(min, Math.min(max, n));
            input.value = String(n);
            onchange(n);
        });
        lbl.appendChild(input);
        lbl.appendChild(el("span", { text: text }));
        return lbl;
    }

    // Editable list of names (one per line). Saves on blur/change.
    function foldersEditor(title, list, onsave) {
        var wrap = el("div", { class: "folders-edit" });
        wrap.appendChild(el("div", { class: "fe-title", text: title }));
        wrap.appendChild(el("div", { class: "summary",
            text: "One folder name per line. Saved when you click away." }));
        var ta = el("textarea", { rows: "8", spellcheck: "false" });
        ta.value = (list || []).join("\n");
        ta.addEventListener("change", function () {
            var lines = ta.value.split("\n")
                .map(function (s) { return s.trim(); })
                .filter(function (s) { return s.length; });
            onsave(lines);
        });
        wrap.appendChild(ta);
        return wrap;
    }

    function kv(k, v) {
        return el("div", { class: "kv" }, [
            el("div", { class: "k", text: k }),
            el("div", { class: "v", text: v })
        ]);
    }

    function setCmdSetting(key, sub, value) {
        S.commandSettings = S.commandSettings || {};
        S.commandSettings[key] = S.commandSettings[key] || {};
        S.commandSettings[key][sub] = value;
        send("setCommandSetting", { key: key, sub: sub, value: value });
    }

    function applyTheme(t) {
        document.body.classList.remove("light");
        if (t === "light") document.body.classList.add("light");
    }

    // ── sections ─────────────────────────────────────────────────────────────
    function sectionGeneral() {
        var sec = el("section", { id: "sec-general" }, [el("h2", { text: "General" })]);
        var card = el("div", { class: "card" });
        card.appendChild(labelCheck(
            "Enable beta mode (show beta commands)",
            S.beta === true,
            function (v) { S.beta = v; send("setBeta", { value: v }); render(); }
        ));
        var btns = el("div", { class: "btn-row" });
        btns.appendChild(el("button", { class: "secondary", text: "Open settings file",
            onclick: function () { send("openSettingsFile", {}); } }));
        btns.appendChild(el("button", { class: "secondary", text: "Import settings…",
            onclick: function () { send("importSettings", {}); } }));
        card.appendChild(btns);
        card.appendChild(el("div", { class: "summary", text: "Settings file: " + (S.settingsPath || "") }));
        sec.appendChild(card);
        return sec;
    }

    // One section per registry group rather than a single "Commands" section.
    // With ~50 commands, one entry gave the nav nothing to aim at: every group
    // was the same long scroll. The group's own name is the heading, so the
    // toggle below it says what it does instead of repeating the name.
    function sectionGroup(g) {
        var sec = el("section", { id: groupSectionId(g.key) }, [el("h2", { text: g.label })]);

        var grp = el("div", { class: "group" + (g.enabled ? "" : " disabled") });
        var head = el("div", { class: "group-head" });
        head.appendChild(checkbox(g.enabled, function (v) {
            g.enabled = v; send("setGroup", { key: g.key, enabled: v }); render();
        }));
        head.appendChild(el("span", { class: "grow", text: "Enable " + g.label + " commands" }));
        grp.appendChild(head);

        var body = el("div", { class: "group-body" });
        var visible = g.commands.filter(function (c) { return !c.beta || S.beta; });
        if (!visible.length) {
            body.appendChild(el("div", { class: "muted",
                text: "No commands in this group are available." }));
        }
        visible.forEach(function (c) {
            var row = el("div", { class: "row" });
            row.appendChild(checkbox(c.enabled, function (v) {
                c.enabled = v; send("setCommand", { key: c.key, enabled: v }); render();
            }));
            var info = el("div", { class: "grow" });
            var name = el("div", { class: "name" });
            name.appendChild(document.createTextNode(c.name + " "));
            if (c.beta) name.appendChild(el("span", { class: "badge", text: "beta" }));
            info.appendChild(name);
            // No title attribute: the summary already wraps and is fully
            // visible, so a native tooltip only repeated it in an
            // unthemed, unbounded-width browser popup.
            if (c.summary) info.appendChild(el("div", { class: "summary", text: c.summary }));

            // Settings flagged inline sit under their own command, gated
            // on the enable checkbox above them, instead of repeating the
            // command as a separate section further down.
            var inlineDef = CMD_SECTIONS[c.key];
            if (inlineDef && inlineDef.inline && c.enabled) {
                var nested = el("div", { class: "row-settings" });
                var cs = (S.commandSettings && S.commandSettings[c.key]) || {};
                inlineDef.render(cs).forEach(function (node) { nested.appendChild(node); });
                info.appendChild(nested);
            }
            row.appendChild(info);
            row.appendChild(el("a", { class: "doc", href: "#", text: "docs ↗",
                onclick: function (e) { e.preventDefault(); send("openDoc", { url: c.doc }); } }));
            body.appendChild(row);
        });
        grp.appendChild(body);
        sec.appendChild(grp);
        groupExtras(g).forEach(function (node) { sec.appendChild(node); });
        return sec;
    }

    function groupSectionId(key) {
        return "sec-group-" + key;
    }

    // A titled block nested inside a group's section. Deliberately a div and
    // not a <section>: the scroll-spy tracks every section to highlight the
    // nav, and a nested one would keep clearing the highlight as it scrolled
    // past, since it has no nav entry of its own.
    function subsection(title) {
        return el("div", { class: "subsection" }, [el("h3", { text: title })]);
    }

    // Extra settings a group owns, rendered inside it. Anything belonging to a
    // group or one of its commands lives in that group's section, so nothing
    // appears in the nav twice.
    function groupExtras(g) {
        var out = [];
        g.commands.forEach(function (c) {
            var def = CMD_SECTIONS[c.key];
            if (!def || def.inline) return;   // inline settings sit under the row
            if (!g.enabled || !c.enabled) return;
            out.push(cmdSettingsSubsection(c.key));
        });
        if (g.key === "related" && g.enabled) out.push(hubSubsection());
        if (g.key === "teamaddins" && g.enabled) out.push(teamAddinsSubsection());
        return out;
    }

    function cmdSettingsSubsection(key) {
        var def = CMD_SECTIONS[key];
        var cs = (S.commandSettings && S.commandSettings[key]) || {};
        var sec = subsection(def.label + " settings");
        var card = el("div", { class: "card" });
        def.render(cs).forEach(function (node) { card.appendChild(node); });
        sec.appendChild(card);
        return sec;
    }

    function hubSubsection() {
        var h = S.hub || {};
        var sec = subsection("Hub Settings");
        var card = el("div", { class: "card" });
        if (h.hubId) {
            card.appendChild(kv("Active hub", h.hubName || "(unnamed)"));
            card.appendChild(kv("Hub id", h.hubId));
            var status = el("span", {
                class: h.configured ? "status-ok" : "status-no",
                text: h.configured ? "Configured" : "Not configured"
            });
            var s = el("div", { class: "kv" }, [el("div", { class: "k", text: "Related Data" })]);
            s.appendChild(el("div", { class: "v" }, [status]));
            card.appendChild(s);
            if (h.configured) {
                card.appendChild(kv("Project", h.projectName || ""));
                card.appendChild(kv("Templates folder", h.folderName || ""));
            }
        } else {
            card.appendChild(el("div", { class: "muted",
                text: "No active hub. Sign in to a Fusion Team hub and open a document." }));
        }
        var btns = el("div", { class: "btn-row" });
        btns.appendChild(el("button", { text: "Select Related Data Folder…",
            onclick: function () { send("browseHubFolder", {}); } }));
        card.appendChild(btns);
        sec.appendChild(card);
        return sec;
    }

    // Status labels for the shared folder. There is nothing to configure: the
    // location is a fixed convention, so this reports whether it is there.
    var TEAM_STATE = {
        ready:   { label: "Ready",       cls: "status-ok" },
        missing: { label: "Not created", cls: "status-no" },
        no_hub:  { label: "No hub",      cls: "status-no" },
        error:   { label: "Unavailable", cls: "status-no" }
    };

    function teamAddinsSubsection() {
        var t = S.teamAddins || {};
        var st = TEAM_STATE[t.state] || TEAM_STATE.error;
        var project = t.projectName || "Assets";
        var folder = t.folderName || "Shared Addins";

        var sec = subsection("Shared folder");
        sec.appendChild(el("div", { class: "section-desc",
            text: "Add-ins dropped into a shared hub folder are installed automatically " +
                  "shortly after Fusion starts. The folder is always " +
                  project + " / " + folder + " in the active hub, so there is nothing " +
                  "to configure." }));

        var card = el("div", { class: "card" });
        var s = el("div", { class: "kv" }, [el("div", { class: "k", text: folder })]);
        s.appendChild(el("div", { class: "v" }, [el("span", { class: st.cls, text: st.label })]));
        card.appendChild(s);

        if (t.hubName) card.appendChild(kv("Hub", t.hubName));
        card.appendChild(kv("Location", project + " / " + folder));

        if (t.state === "ready") {
            card.appendChild(kv("Packages in folder", String(t.packageCount || 0)));
            card.appendChild(kv("Installed on this machine", String(t.installedCount || 0)));
            if (t.checkedAt) card.appendChild(kv("Last checked", t.checkedAt));
        } else if (t.message) {
            card.appendChild(el("div", { class: "muted", text: t.message }));
        }

        var btns = el("div", { class: "btn-row" });
        btns.appendChild(el("button", {
            text: t.state === "ready" ? "Check folder…" : "Create shared folder…",
            onclick: function () { send("setUpTeamAddinsFolder", {}); }
        }));
        card.appendChild(btns);
        sec.appendChild(card);

        // Settings live in this same section rather than in CMD_SECTIONS, so
        // there is one "Team Add-ins" entry in the nav instead of two.
        var cs = (S.commandSettings && S.commandSettings.teamaddins) || {};
        var opts = el("div", { class: "card" });
        opts.appendChild(labelCheck(
            "Check the shared folder shortly after Fusion starts",
            cs.auto_check_on_launch !== false,
            function (v) { setCmdSetting("teamaddins", "auto_check_on_launch", v); }
        ));
        opts.appendChild(labelNumber(
            "Wait this many seconds after launch before checking",
            cs.startup_delay_seconds == null ? 25 : cs.startup_delay_seconds,
            5, 600,
            function (v) { setCmdSetting("teamaddins", "startup_delay_seconds", v); }
        ));
        opts.appendChild(labelCheck(
            "Load updates immediately (otherwise they wait for a Fusion restart)",
            cs.auto_reload !== false,
            function (v) { setCmdSetting("teamaddins", "auto_reload", v); }
        ));
        opts.appendChild(el("div", { class: "summary",
            text: "The check never blocks Fusion's launch: it runs on a later turn, " +
                  "and stays silent unless something actually changed." }));
        sec.appendChild(opts);
        return sec;
    }

    // ── nav + render ─────────────────────────────────────────────────────────
    function setActive(id) {
        document.querySelectorAll("#nav .nav-item").forEach(function (n) {
            n.classList.toggle("active", n.getAttribute("data-target") === id);
        });
    }

    function buildNav(items) {
        var nav = document.getElementById("nav");
        nav.innerHTML = "";
        items.forEach(function (it) {
            nav.appendChild(el("div", {
                class: "nav-item", "data-target": it[0], text: it[1],
                onclick: function () {
                    var t = document.getElementById(it[0]);
                    if (t) t.scrollIntoView({ behavior: "smooth", block: "start" });
                    setActive(it[0]);
                }
            }));
        });
        if (items.length) setActive(items[0][0]);
    }

    function render() {
        applyTheme(S.theme);
        document.getElementById("banner").textContent = S.restartNote || "";
        var content = document.getElementById("content");
        content.innerHTML = "";
        var nav = [];

        content.appendChild(sectionGeneral()); nav.push(["sec-general", "General"]);

        S.groups.forEach(function (g) {
            content.appendChild(sectionGroup(g));
            nav.push([groupSectionId(g.key), g.label]);
        });

        // Nothing else is appended here. Per-command settings, Hub Settings and
        // the Team Add-ins shared folder are all rendered by groupExtras()
        // inside the group that owns them, so the nav is General plus one entry
        // per group and no group appears in it twice.
        buildNav(nav);
    }

    // Highlight the nav entry for the section currently in view.
    function wireScrollSpy() {
        var content = document.getElementById("content");
        content.addEventListener("scroll", function () {
            var top = content.scrollTop, best = null;
            content.querySelectorAll("section").forEach(function (sec) {
                if (sec.offsetTop - 24 <= top) best = sec.id;
            });
            if (best) setActive(best);
        });
    }

    // Messages from Python.
    window.fusionJavaScriptHandler = {
        handle: function (action, data) {
            try {
                if (action === "setState") { S = JSON.parse(data); render(); }
            } catch (e) { console.log("[Preferences] handler error:", e); }
            return "OK";
        }
    };

    render();
    wireScrollSpy();
    send("ready", {});
})();
