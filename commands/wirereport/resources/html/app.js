/* Wire & Cable Report palette page.
   State arrives from Python as one JSON blob ("setState" message, with
   init.js providing the first paint). The page renders it and can ask the
   backend to re-measure via the Refresh button ("refresh" action). */

'use strict';

function send(action, payload) {
    try { adsk.fusionSendData(action, JSON.stringify(payload || {})); }
    catch (e) { console.log('[Wire Report] not in Fusion palette:', action); }
}

function applyTheme(theme) {
    document.body.classList.remove('dark', 'light');
    document.body.classList.add(theme === 'light' ? 'light' : 'dark');
}

function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text !== undefined) { node.textContent = text; }
    return node;
}

function renderTotals(totals, skipped) {
    var host = document.getElementById('totals');
    host.textContent = '';
    if (!totals) { return; }
    var stats = [
        [String(totals.wires), 'wires'],
        [String(totals.cables), 'cables'],
        [totals.conductor, 'total conductor']
    ];
    if (skipped) { stats.push([String(skipped), 'unsupported routes']); }
    stats.forEach(function (pair) {
        var stat = el('div', 'stat');
        stat.appendChild(el('div', 'value', pair[0]));
        stat.appendChild(el('div', 'label', pair[1]));
        host.appendChild(stat);
    });
}

function renderAssembly(assembly) {
    var card = el('div', 'assembly');
    var title = el('h2', null, assembly.title);
    title.appendChild(el('span', 'kind', assembly.kind));
    card.appendChild(title);
    if (assembly.ends) { card.appendChild(el('p', 'ends', assembly.ends)); }
    if (assembly.spec) { card.appendChild(el('p', 'spec', assembly.spec)); }

    var table = document.createElement('table');
    (assembly.rows || []).forEach(function (row) {
        var tr = document.createElement('tr');
        if (row.highlight) { tr.className = 'highlight'; }
        tr.appendChild(el('td', null, row.label));
        tr.appendChild(el('td', null, row.value));
        table.appendChild(tr);
    });
    if (assembly.total) {
        var totalRow = document.createElement('tr');
        totalRow.className = 'total';
        totalRow.appendChild(el('td', null, assembly.total.label));
        totalRow.appendChild(el('td', null, assembly.total.value));
        table.appendChild(totalRow);
    }
    card.appendChild(table);
    return card;
}

function renderState(state) {
    if (!state) { return; }
    if (state.theme) { applyTheme(state.theme); }
    document.getElementById('docName').textContent = state.docName || '';
    document.getElementById('generated').textContent =
        state.generated ? ('Generated ' + state.generated) : '';
    renderTotals(state.totals, state.skipped);

    var host = document.getElementById('assemblies');
    host.textContent = '';
    var assemblies = state.assemblies || [];
    document.getElementById('empty').hidden = assemblies.length > 0;
    assemblies.forEach(function (assembly) {
        host.appendChild(renderAssembly(assembly));
    });
}

window.fusionJavaScriptHandler = {
    handle: function (action, data) {
        try {
            if (action === 'setTheme') {
                applyTheme(data);
            } else if (action === 'setState') {
                var state = null;
                try { state = JSON.parse(data); } catch (e) { state = null; }
                renderState(state);
            }
        } catch (e) {
            console.log('[Wire Report] handler error:', e);
        }
        return 'OK';
    }
};

document.getElementById('refreshBtn').addEventListener('click', function () {
    send('refresh', {});
});

/* First paint from the init.js sidecar (trusted for theme/initial data),
   then ask the backend for fresh state - Windows CEF caches init.js by
   URL across palette recreations. */
if (window.__ptInit) { renderState(window.__ptInit); }
send('htmlReady', {});
