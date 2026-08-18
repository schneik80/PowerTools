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

    // Design intents the icon set covers. Anything else — including the ~25% of
    // documents Fusion records no intent for — gets no badge rather than a
    // guessed one.
    var INTENTS = ['part', 'hybrid', 'assembly'];

    // Recent cards rendered at once. The backend sends the whole list so the
    // filter can search all of it; only this many are in the DOM at a time,
    // because a few hundred cards is a long scroll in a narrow palette.
    var RECENT_RENDER_CAP = 40;

    // Full unfiltered Recent list, kept so filtering never round-trips.
    var recentAll = [];

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
            console.log('[Assembly Palette] not in Fusion palette:', action, payload);
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

    function renderGallery(rootId, emptyId, docs, opts) {
        opts = opts || {};
        var all = docs || [];
        // Update the corresponding tab count badge alongside the gallery so
        // the user sees how many items each tab holds without switching. The
        // Recent badge counts the whole list, not the filtered subset.
        if (rootId === 'openGallery') setTabCount('openCount', all.length);
        if (rootId === 'recentGallery') {
            setTabCount('recentCount', opts.total != null ? opts.total : all.length);
        }

        var root = document.getElementById(rootId);
        if (!root) return;
        // Wipe and rebuild.
        root.innerHTML = '';
        if (all.length === 0) {
            var empty = document.createElement('div');
            empty.className = 'empty';
            empty.id = emptyId;
            empty.textContent = opts.emptyText || ((emptyId === 'openEmpty')
                ? 'No other open documents.'
                : 'No recent documents yet.');
            root.appendChild(empty);
            return;
        }
        var shown = opts.cap ? all.slice(0, opts.cap) : all;
        shown.forEach(function (doc) {
            var card = document.createElement('div');
            card.className = 'doc-card';
            card.title = 'Insert ' + (doc.name || '');

            // Narrowed to the known set, so it is safe to drop straight into a
            // class name. Blank means Fusion never recorded an intent for this
            // document and never will, so no badge is shown rather than guessing
            // one — coercing to 'part' would mislabel a quarter of the list.
            var intent = INTENTS.indexOf(doc.intent) >= 0 ? doc.intent : '';
            var intentLabel = intent
                ? intent.charAt(0).toUpperCase() + intent.slice(1)
                : '';

            // The intent class rides on the thumb too: with no thumbnail (or one
            // that fails to load) `.broken` swaps in this type's 32px icon.
            var thumbClass = 'doc-thumb' + (intent ? ' ' + intent : '');
            var thumbHtml;
            if (doc.thumbUrl) {
                thumbHtml = '<div class="' + thumbClass + '">' +
                    '<img src="' + escapeHtml(doc.thumbUrl) + '" alt="" ' +
                    'onerror="this.parentNode.classList.add(\'broken\');this.remove();" />' +
                    '</div>';
            } else {
                thumbHtml = '<div class="' + thumbClass + ' broken"></div>';
            }

            var iconHtml = intent
                ? '<span class="intent-icon ' + intent + '" role="img" ' +
                  'title="' + intentLabel + '" aria-label="' + intentLabel + '"></span>'
                : '';

            card.innerHTML =
                thumbHtml +
                '<div class="doc-card-meta">' +
                iconHtml +
                '<div class="doc-card-name">' + escapeHtml(doc.name || '') + '</div>' +
                '</div>';
            card.addEventListener('click', function () {
                send('insertDoc', {
                    dataFileId: doc.dataFileId,
                    name: doc.name,
                    intent: doc.intent
                });
            });
            root.appendChild(card);
        });
        if (all.length > shown.length) {
            var note = document.createElement('div');
            note.className = 'gallery-note';
            note.textContent = 'Showing ' + shown.length + ' of ' + all.length +
                ' — filter by name to reach the rest.';
            root.appendChild(note);
        }
    }

    // Repaint the Recent gallery from the full list through the filter box.
    // Client-side so typing never round-trips to the backend.
    function renderRecent() {
        var input = document.getElementById('recentFilter');
        var query = input ? input.value.trim().toLowerCase() : '';
        var matches = recentAll;
        if (query) {
            matches = recentAll.filter(function (doc) {
                return (doc.name || '').toLowerCase().indexOf(query) >= 0;
            });
        }
        renderGallery('recentGallery', 'recentEmpty', matches, {
            cap: RECENT_RENDER_CAP,
            total: recentAll.length,
            emptyText: query ? 'No recent document matches that name.' : ''
        });
    }

    function setRecentDocs(docs) {
        recentAll = docs || [];
        renderRecent();
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
    setRecentDocs(ptInit.recentDocs);
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

    // Filtering a few hundred names is instant, so this repaints on each
    // keystroke with no debounce. 'search' also fires on the clear affordance.
    var recentFilter = document.getElementById('recentFilter');
    if (recentFilter) {
        recentFilter.addEventListener('input', renderRecent);
        recentFilter.addEventListener('search', renderRecent);
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
                    setRecentDocs(recent);
                } else if (action === 'setTargetProject') {
                    applyTargetProject(data);
                }
            } catch (e) {
                console.log('[Assembly Palette] handler error:', e);
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
