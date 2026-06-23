// Copyright (C) Industrial Machine Arts LLC WA, USA - All Rights Reserved
// PowerTools Preferences palette logic. Renders the section nav + scrolling
// content from the state provided by entry.py (window.__ptInit / setState) and
// reports every change back to Python.

(function () {
    "use strict";

    var S = window.__ptInit || {
        groups: [], hub: {}, commandSettings: {}, theme: "dark", beta: false,
        settingsPath: "", restartNote: ""
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
        docopen: {
            label: "Show In Location",
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

    function groupByKey(key) {
        for (var i = 0; i < S.groups.length; i++) if (S.groups[i].key === key) return S.groups[i];
        return null;
    }

    function findCmd(key) {
        for (var i = 0; i < S.groups.length; i++) {
            var g = S.groups[i];
            for (var j = 0; j < g.commands.length; j++) {
                if (g.commands[j].key === key) return { group: g, cmd: g.commands[j] };
            }
        }
        return null;
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

    function sectionCommands() {
        var sec = el("section", { id: "sec-commands" }, [el("h2", { text: "Commands" })]);
        sec.appendChild(el("div", { class: "section-desc",
            text: "Enable or disable command groups and individual commands." }));
        S.groups.forEach(function (g) {
            var grp = el("div", { class: "group" + (g.enabled ? "" : " disabled") });
            var head = el("div", { class: "group-head" });
            head.appendChild(checkbox(g.enabled, function (v) {
                g.enabled = v; send("setGroup", { key: g.key, enabled: v }); render();
            }));
            head.appendChild(el("span", { class: "grow", text: g.label }));
            grp.appendChild(head);

            var body = el("div", { class: "group-body" });
            g.commands.filter(function (c) { return !c.beta || S.beta; }).forEach(function (c) {
                var row = el("div", { class: "row" });
                row.appendChild(checkbox(c.enabled, function (v) {
                    c.enabled = v; send("setCommand", { key: c.key, enabled: v }); render();
                }));
                var info = el("div", { class: "grow" });
                var name = el("div", { class: "name" });
                name.appendChild(document.createTextNode(c.name + " "));
                if (c.beta) name.appendChild(el("span", { class: "badge", text: "beta" }));
                info.appendChild(name);
                if (c.summary) info.appendChild(el("div", { class: "summary", title: c.summary, text: c.summary }));
                row.appendChild(info);
                row.appendChild(el("a", { class: "doc", href: "#", text: "docs ↗",
                    onclick: function (e) { e.preventDefault(); send("openDoc", { url: c.doc }); } }));
                body.appendChild(row);
            });
            grp.appendChild(body);
            sec.appendChild(grp);
        });
        return sec;
    }

    function sectionCmdSettings(key) {
        var def = CMD_SECTIONS[key];
        var cs = (S.commandSettings && S.commandSettings[key]) || {};
        var sec = el("section", { id: "sec-cmd-" + key }, [el("h2", { text: def.label + " settings" })]);
        var card = el("div", { class: "card" });
        def.render(cs).forEach(function (node) { card.appendChild(node); });
        sec.appendChild(card);
        return sec;
    }

    function sectionHub() {
        var h = S.hub || {};
        var sec = el("section", { id: "sec-hub" }, [el("h2", { text: "Hub Settings" })]);
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
        content.appendChild(sectionCommands()); nav.push(["sec-commands", "Commands"]);

        Object.keys(CMD_SECTIONS).forEach(function (key) {
            var fc = findCmd(key);
            if (fc && fc.group.enabled && fc.cmd.enabled) {
                content.appendChild(sectionCmdSettings(key));
                nav.push(["sec-cmd-" + key, CMD_SECTIONS[key].label]);
            }
        });

        var rel = groupByKey("related");
        if (rel && rel.enabled) {
            content.appendChild(sectionHub());
            nav.push(["sec-hub", "Hub Settings"]);
        }

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
