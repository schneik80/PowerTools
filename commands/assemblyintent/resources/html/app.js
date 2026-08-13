(function () {
    'use strict';

    var ptInit = window.__ptInit || {
        docName: '',
        theme: 'dark',
        openDocs: [],
        recentDocs: [],
        showChildren: false,
        hasTargetProject: true,
        targetProject: ''
    };

    function applyTheme(theme) {
        document.body.classList.remove('dark', 'light');
        document.body.classList.add(theme === 'light' ? 'light' : 'dark');
    }

    function setDocName(name) {
        var el = document.getElementById('docName');
        if (el) el.textContent = name || '';
    }

    function send(action, payload) {
        try {
            adsk.fusionSendData(action, JSON.stringify(payload || {}));
        } catch (e) {
            console.log('[New Assembly] not in Fusion palette:', action, payload);
        }
    }

    function escapeHtml(text) {
        var d = document.createElement('div');
        d.textContent = text == null ? '' : String(text);
        return d.innerHTML;
    }

    function setTabCount(id, n) {
        var el = document.getElementById(id);
        if (el) el.textContent = n > 0 ? ' (' + n + ')' : '';
    }

    function renderGallery(rootId, emptyId, docs) {
        // Update the corresponding tab count badge alongside the gallery so
        // the user sees how many items each tab holds without switching.
        if (rootId === 'openGallery') setTabCount('openCount', (docs || []).length);
        if (rootId === 'recentGallery') setTabCount('recentCount', (docs || []).length);

        var root = document.getElementById(rootId);
        if (!root) return;
        // Wipe and rebuild.
        root.innerHTML = '';
        if (!docs || docs.length === 0) {
            var empty = document.createElement('div');
            empty.className = 'empty';
            empty.id = emptyId;
            empty.textContent = (emptyId === 'openEmpty')
                ? 'No other open documents.'
                : 'No recent documents yet.';
            root.appendChild(empty);
            return;
        }
        docs.forEach(function (doc) {
            var card = document.createElement('div');
            card.className = 'doc-card';
            card.title = 'Insert ' + (doc.name || '');

            var thumbHtml;
            if (doc.thumbUrl) {
                thumbHtml = '<div class="doc-thumb">' +
                    '<img src="' + escapeHtml(doc.thumbUrl) + '" alt="" ' +
                    'onerror="this.parentNode.classList.add(\'broken\');this.remove();" />' +
                    '</div>';
            } else {
                thumbHtml = '<div class="doc-thumb broken"></div>';
            }

            card.innerHTML =
                thumbHtml +
                '<span class="badge ' + escapeHtml(doc.intent || 'part') + '">' +
                escapeHtml(doc.intent || 'part') +
                '</span>' +
                '<div class="doc-card-name">' + escapeHtml(doc.name || '') + '</div>';
            card.addEventListener('click', function () {
                send('insertDoc', {
                    dataFileId: doc.dataFileId,
                    name: doc.name,
                    intent: doc.intent
                });
            });
            root.appendChild(card);
        });
    }

    function updateIntentLabel() {
        var sel = document.getElementById('newCompIntent');
        var lbl = document.getElementById('intentLabel');
        if (sel && lbl) lbl.textContent = sel.value;
    }

    // Toggle the "no target project" banner and enable/disable New Component
    // accordingly. Accepts either the backend's {hasProject, name} object or a
    // JSON string form of it. When no project is available, creating a
    // component would fail (nowhere to save it), so the button is disabled.
    function applyTargetProject(state) {
        if (typeof state === 'string') {
            try { state = JSON.parse(state); } catch (e) { state = {}; }
        }
        var hasProject = !!(state && state.hasProject);
        var banner = document.getElementById('noProjectBanner');
        if (banner) banner.hidden = hasProject;
        var btn = document.getElementById('btnCreateComp');
        if (btn) {
            btn.disabled = !hasProject;
            btn.title = hasProject
                ? ''
                : 'No target project — select one in the Data Panel, then Re-check.';
        }
        // Restore the Re-check button from any transient "Checking…" state now
        // that a fresh answer has arrived.
        var recheck = document.getElementById('btnRecheckProject');
        if (recheck) {
            recheck.textContent = 'Re-check';
            recheck.classList.remove('checking');
        }
    }

    // Ask the backend to re-resolve the target project. Fusion has no
    // active-project-changed event, so this is how we learn the user picked a
    // project in the Data Panel — via an explicit re-check.
    function recheckProject() {
        var btn = document.getElementById('btnRecheckProject');
        if (btn) {
            btn.textContent = 'Checking…';
            btn.classList.add('checking');
        }
        send('recheckProject', {});
    }

    // Auto re-check when the palette regains focus, but only while the banner
    // is showing — no point polling when a project is already set. This makes
    // returning from the Data Panel clear the banner without a manual click.
    function autoRecheckIfNeeded() {
        var banner = document.getElementById('noProjectBanner');
        if (banner && !banner.hidden) send('recheckProject', {});
    }

    // --- Initial paint from ptInit ---
    applyTheme(ptInit.theme);
    setDocName(ptInit.docName);
    renderGallery('openGallery', 'openEmpty', ptInit.openDocs);
    renderGallery('recentGallery', 'recentEmpty', ptInit.recentDocs);
    updateIntentLabel();
    applyTargetProject({
        hasProject: ptInit.hasTargetProject,
        name: ptInit.targetProject
    });

    // "Show referenced children" toggles whether reference-loaded sub-assemblies
    // / parts of open assemblies appear in the Open tab. Off by default → only
    // top-level docs. Filtering is backend-side (an instant in-memory check),
    // so a change just re-requests the open-docs list.
    var showChildren = document.getElementById('openShowChildren');
    if (showChildren) {
        showChildren.checked = !!ptInit.showChildren;
        showChildren.addEventListener('change', function () {
            send('setShowChildren', { showChildren: showChildren.checked });
        });
    }

    // --- Wire actions ---
    document.getElementById('btnCreateComp').addEventListener('click', function () {
        var name = document.getElementById('newCompName').value.trim();
        var intent = document.getElementById('newCompIntent').value;
        if (!name) {
            document.getElementById('newCompName').focus();
            return;
        }
        send('createComponent', { name: name, intent: intent });
        document.getElementById('newCompName').value = '';
        document.getElementById('newCompName').focus();
    });

    document.getElementById('newCompName').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.getElementById('btnCreateComp').click();
        }
    });

    document.getElementById('newCompIntent').addEventListener('change', updateIntentLabel);

    document.getElementById('btnAssemblyBuilder').addEventListener('click', function () {
        send('launchAssemblyBuilder', {});
    });
    document.getElementById('btnGlobalParameters').addEventListener('click', function () {
        send('launchGlobalParameters', {});
    });
    document.getElementById('btnRefresh').addEventListener('click', function () {
        send('refresh', {});
    });

    // Hands off to Fusion's own Fasteners dialog. href="#" would navigate the
    // palette page, so the default is always suppressed.
    var fastenersLink = document.getElementById('linkFasteners');
    if (fastenersLink) {
        fastenersLink.addEventListener('click', function (e) {
            e.preventDefault();
            send('launchFasteners', {});
        });
    }

    var recheckBtn = document.getElementById('btnRecheckProject');
    if (recheckBtn) recheckBtn.addEventListener('click', recheckProject);

    // Fusion emits no active-project event, so approximate one: when the user
    // returns to the palette after using the Data Panel, re-check.
    window.addEventListener('focus', autoRecheckIfNeeded);
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden) autoRecheckIfNeeded();
    });

    // --- Tab switching (Open / Recent) ---
    function activateTab(which) {
        var tabs = document.querySelectorAll('.tab');
        for (var i = 0; i < tabs.length; i++) {
            var t = tabs[i];
            var active = t.dataset.tab === which;
            t.classList.toggle('active', active);
            t.setAttribute('aria-selected', active ? 'true' : 'false');
        }
        var panes = document.querySelectorAll('.tab-pane');
        for (var j = 0; j < panes.length; j++) {
            panes[j].classList.toggle('active', panes[j].dataset.tab === which);
        }
        // Reset scroll so a switch always starts at the top, regardless of
        // where the previous tab was scrolled to.
        var container = document.querySelector('.tab-panes');
        if (container) container.scrollTop = 0;
    }

    document.querySelectorAll('.tab').forEach(function (t) {
        t.addEventListener('click', function () { activateTab(t.dataset.tab); });
    });

    // --- Fusion → page bridge ---
    window.fusionJavaScriptHandler = {
        handle: function (action, data) {
            try {
                if (action === 'setDocumentName') {
                    setDocName(data);
                } else if (action === 'setTheme') {
                    applyTheme(data);
                } else if (action === 'setOpenDocs') {
                    var open = [];
                    try { open = JSON.parse(data) || []; } catch (e) { open = []; }
                    renderGallery('openGallery', 'openEmpty', open);
                } else if (action === 'setRecentDocs') {
                    var recent = [];
                    try { recent = JSON.parse(data) || []; } catch (e) { recent = []; }
                    renderGallery('recentGallery', 'recentEmpty', recent);
                } else if (action === 'setTargetProject') {
                    applyTargetProject(data);
                }
            } catch (e) {
                console.log('[New Assembly] handler error:', e);
            }
            return 'OK';
        }
    };

    // Tell the backend the page is loaded so it can push fresh state via
    // sendInfoToHTML. The initial paint above uses window.__ptInit from
    // init.js, but on Windows Fusion's embedded browser caches init.js by URL
    // across palette recreations and may serve a stale/empty copy — so we
    // never rely on init.js alone for the live doc lists. This handshake
    // guarantees the galleries are repainted from current data on every open.
    send('htmlReady', {});
})();
