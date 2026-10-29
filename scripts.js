const API_BASE = window.API_BASE || "http://127.0.0.1:8000";
const API = `${API_BASE}/api/v1`;
const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws/telemetry";

const sectors = ["Sector_A1", "Sector_A2", "Sector_B1", "Sector_B2", "Sector_C1", "Sector_C2"];
let ws = null;
let wsRetry = 1000;
const liveSectorData = {};
const riskHistory = Object.fromEntries(sectors.map(s => [s, []]));
const lastSeverity = {};
const seenIncidents = new Set();
let firstState = true;
let simState = { running: true, speed: 1 };

let leafletMap = null;
const sectorMarkers = {};
const edgeLines = [];

const sectorCoords = {
    "Sector_A1": [34.0722, -118.2637],
    "Sector_A2": [34.0722, -118.2337],
    "Sector_B1": [34.0722, -118.2037],
    "Sector_B2": [34.0322, -118.2637],
    "Sector_C1": [34.0322, -118.2337],
    "Sector_C2": [34.0322, -118.2037]
};

const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = v => `${((v || 0) * 100).toFixed(0)}%`;
const sevColor = s => (s === "CRITICAL" ? "#ef4444" : s === "WARNING" ? "#f59e0b" : "#22c55e");

async function api(path, opts) {
    const res = await fetch(API + path, opts);
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json();
}
const post = (path, body) => api(path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined
});

function initLeafletMap() {
    if (leafletMap) return;
    const mapEl = document.getElementById('map');
    if (!mapEl) return;

    leafletMap = L.map('map', { zoomControl: false }).setView([34.0522, -118.2437], 12);

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        maxZoom: 19
    }).addTo(leafletMap);

    sectors.forEach((a, i) => sectors.slice(i + 1).forEach(b => {
        const dy = Math.round(Math.abs(sectorCoords[a][0] - sectorCoords[b][0]) / 0.04);
        const dx = Math.round(Math.abs(sectorCoords[a][1] - sectorCoords[b][1]) / 0.03);
        const w = dx + dy === 1 ? 0.4 : (dx === 1 && dy === 1 ? 0.2 : 0);
        if (!w) return;
        const line = L.polyline([sectorCoords[a], sectorCoords[b]],
            { color: "#38bdf8", weight: 1, opacity: 0.15, dashArray: "4 6" }).addTo(leafletMap);
        edgeLines.push({ line, a, b, w });
    }));

    Object.keys(sectorCoords).forEach(sec => {
        const coords = sectorCoords[sec];
        const circle = L.circleMarker(coords, {
            radius: 22,
            fillColor: '#22c55e',
            color: '#ffffff',
            weight: 2,
            opacity: 0.8,
            fillOpacity: 0.6
        }).addTo(leafletMap);

        circle.bindTooltip(`<b>${sec.replace('_', ' ')}</b><br>Awaiting telemetry...`, { direction: 'top' });
        circle.on('click', () => viewHistory(sec));

        sectorMarkers[sec] = circle;
    });
}

function updateEdges() {
    edgeLines.forEach(e => {
        const flow = Math.max(liveSectorData[e.a]?.composite_risk || 0, liveSectorData[e.b]?.composite_risk || 0) * e.w;
        e.line.setStyle({ opacity: 0.15 + flow * 2, weight: 1 + flow * 14, color: flow > 0.25 ? "#ef4444" : flow > 0.15 ? "#f59e0b" : "#38bdf8" });
    });
}

function initGrid() {
    const grid = document.getElementById('grid');
    if (!grid) return;
    grid.innerHTML = '';

    sectors.forEach(sec => {
        grid.innerHTML += `
          <div class="sector-card" id="card-${sec}">
            <div>
              <div class="sector-header">
                <div class="sector-title">${sec.replace('_', ' ')}</div>
                <button class="history-btn" onclick="viewHistory('${sec}')">History</button>
              </div>
              <div class="sector-status NORMAL" id="status-${sec}">AWAITING DATA</div>
            </div>

            <div class="eff-line" id="eff-${sec}">Effective risk: --</div>
            <div class="spark" id="spark-${sec}"></div>

            <div class="cascading-panel">
                <div class="cascading-title">Cascading Spillover Risk</div>
                <div class="spillover-list" id="cascading-${sec}">None</div>
            </div>
            
            <div class="risk-bars">
                <div class="risk-row">
                    <span>Grid Risk: <b id="val-grid-${sec}">0%</b></span>
                    <div class="progress-bg"><div class="progress-fill" id="bar-grid-${sec}"></div></div>
                </div>
                <div class="risk-row">
                    <span>Traffic Risk: <b id="val-traf-${sec}">0%</b></span>
                    <div class="progress-bg"><div class="progress-fill" id="bar-traf-${sec}"></div></div>
                </div>
                <div class="risk-row">
                    <span>AQI Risk: <b id="val-aqi-${sec}">0%</b></span>
                    <div class="progress-bg"><div class="progress-fill" id="bar-aqi-${sec}"></div></div>
                </div>
            </div>

            <div style="font-size:0.75rem; color:var(--accent-blue); font-weight: 500;" id="act-${sec}">Monitoring All Systems</div>
          </div>
        `;
    });
}

function sparkline(values, color) {
    if (values.length < 2) return "";
    const w = 200, h = 30, y = r => h - 2 - Math.min(1, r) * (h - 4);
    const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${y(v)}`).join(" ");
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <line x1="0" x2="${w}" y1="${y(0.45)}" y2="${y(0.45)}" stroke="#f59e0b" stroke-opacity="0.35" stroke-dasharray="3 3"/>
      <line x1="0" x2="${w}" y1="${y(0.7)}" y2="${y(0.7)}" stroke="#ef4444" stroke-opacity="0.35" stroke-dasharray="3 3"/>
      <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8" vector-effect="non-scaling-stroke"/></svg>`;
}

function initWebSocket() {
    ws = new WebSocket(WS_URL);
    const wsBadge = document.getElementById('ws-status');

    ws.onopen = () => {
        wsRetry = 1000;
        if (!wsBadge) return;
        wsBadge.className = 'ws-badge ws-connected';
        wsBadge.textContent = '● WS Connected';
    };

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === 'TELEMETRY_UPDATE') {
            renderTelemetryData(message.data);
        } else if (message.type === 'STATE') {
            renderState(message.data);
        }
    };

    ws.onclose = () => {
        if (wsBadge) {
            wsBadge.className = 'ws-badge ws-disconnected';
            wsBadge.textContent = '● WS Disconnected';
        }
        setTimeout(initWebSocket, wsRetry);
        wsRetry = Math.min(wsRetry * 2, 15000);
    };
}

function renderState(s) {
    if (s.analytics) renderMetrics(s.analytics);
    if (s.incidents) renderIncidents(s.incidents);
    if (s.sim) renderSim(s.sim);
    (s.events || []).forEach(e => addLog(e.level, e.message));
    firstState = false;
}

function renderTelemetryData(data) {
    const sec = data.sector_id;
    liveSectorData[sec] = data;

    const card = document.getElementById(`card-${sec}`);
    const statusEl = document.getElementById(`status-${sec}`);
    const eff = data.effective_risk ?? data.composite_risk;

    const marker = sectorMarkers[sec];
    if (marker) {
        const color = sevColor(data.severity);
        marker.setStyle({ fillColor: color, color: color });
        marker.setRadius(18 + eff * 14);

        const b = data.breakdown || {};
        marker.bindTooltip(`
            <strong style="color:${color};">${sec.replace('_', ' ')}</strong><br>
            Status: <b>${esc(data.status)}</b><br>
            Direct: <b>${pct(data.composite_risk)}</b> | Effective: <b>${pct(eff)}</b><br>
            Grid: ${pct(b.grid_risk)} | Traf: ${pct(b.traffic_risk)} | AQI: ${pct(b.aqi_risk)}
        `, { direction: 'top' });
    }
    updateEdges();

    if (!card) return;

    if (statusEl) {
        statusEl.innerText = data.status;
        statusEl.className = `sector-status ${data.severity}`;
    }

    const actEl = document.getElementById(`act-${sec}`);
    if (actEl) actEl.innerText = data.primary_action;

    const effEl = $(`eff-${sec}`);
    if (effEl) effEl.innerHTML = `Direct ${pct(data.composite_risk)} → Effective <b>${pct(eff)}</b>` +
        (data.cascade_induced ? ` <span class="cascade-tag">⚡ cascade</span>` : "");

    const hist = riskHistory[sec];
    hist.push(eff);
    if (hist.length > 40) hist.shift();
    const sparkEl = $(`spark-${sec}`);
    if (sparkEl) sparkEl.innerHTML = sparkline(hist, sevColor(data.severity));

    const b = data.breakdown || {};

    const valGrid = document.getElementById(`val-grid-${sec}`);
    if (valGrid) valGrid.innerText = pct(b.grid_risk);
    const barGrid = document.getElementById(`bar-grid-${sec}`);
    if (barGrid) {
        barGrid.style.width = `${(b.grid_risk || 0) * 100}%`;
        barGrid.style.backgroundColor = getBarColor(b.grid_risk || 0);
    }

    const valTraf = document.getElementById(`val-traf-${sec}`);
    if (valTraf) valTraf.innerText = pct(b.traffic_risk);
    const barTraf = document.getElementById(`bar-traf-${sec}`);
    if (barTraf) {
        barTraf.style.width = `${(b.traffic_risk || 0) * 100}%`;
        barTraf.style.backgroundColor = getBarColor(b.traffic_risk || 0);
    }

    const valAqi = document.getElementById(`val-aqi-${sec}`);
    if (valAqi) valAqi.innerText = pct(b.aqi_risk);
    const barAqi = document.getElementById(`bar-aqi-${sec}`);
    if (barAqi) {
        barAqi.style.width = `${(b.aqi_risk || 0) * 100}%`;
        barAqi.style.backgroundColor = getBarColor(b.aqi_risk || 0);
    }

    const casContainer = document.getElementById(`cascading-${sec}`);
    const spillovers = data.cascading_threat?.adjacent_spillover_risks || {};
    if (casContainer) {
        casContainer.innerHTML = Object.keys(spillovers).length > 0
            ? Object.entries(spillovers)
                .map(([s, val]) => `<span class="spill-item">${esc(s.replace('Sector_', ''))}: +${pct(val)}</span>`)
                .join('')
            : 'None';
    }

    if (data.severity === "CRITICAL") {
        card.style.borderColor = "var(--status-critical)";
        card.style.boxShadow = "0 0 15px rgba(239, 68, 68, 0.25)";
    } else if (data.severity === "WARNING") {
        card.style.borderColor = "var(--status-warning)";
        card.style.boxShadow = "0 0 15px rgba(245, 158, 11, 0.25)";
    } else {
        card.style.borderColor = "var(--border-color)";
        card.style.boxShadow = "none";
    }

    if (lastSeverity[sec] !== data.severity) {
        if (lastSeverity[sec] !== undefined) addLog(data.severity, `${sec}: ${data.severity} (risk ${pct(eff)})`);
        lastSeverity[sec] = data.severity;
    }
}

function addLog(level, message) {
    const box = document.getElementById('logs');
    if (!box) return;
    const d = document.createElement('div');
    d.className = level;
    d.textContent = `[${level}] ${message}`;
    box.appendChild(d);
    while (box.children.length > 200) box.removeChild(box.firstChild);
    box.scrollTop = box.scrollHeight;
}

function updateSliders() {
    const setVal = (id, valId) => {
        const el = document.getElementById(id);
        const valEl = document.getElementById(valId);
        if (el && valEl) valEl.innerText = el.value;
    };
    setVal('input-temp', 'val-temp');
    setVal('input-occ', 'val-occ');
    setVal('input-traffic', 'val-traffic');
    setVal('input-aqi', 'val-aqi');
    setVal('input-hour', 'val-hour');
}

function getBarColor(score) {
    if (score >= 0.7) return "var(--status-critical)";
    if (score >= 0.45) return "var(--status-warning)";
    return "var(--status-normal)";
}

async function sendScan(sec, hour, temp, occ, traffic, aqi) {
    try {
        await post('/predict', {
            sector_id: sec,
            hour: parseInt(hour),
            is_weekend: 0,
            temperature: parseFloat(temp),
            occupancy: parseInt(occ),
            traffic_density: parseInt(traffic),
            aqi: parseInt(aqi)
        });
    } catch (e) { console.error("Scan error:", e); notify("Injection failed: " + e.message); }
}

async function injectManualTelemetry() {
    const sec = document.getElementById('val-sector')?.value || sectors[0];
    const temp = document.getElementById('input-temp')?.value || 30;
    const occ = document.getElementById('input-occ')?.value || 200;
    const traffic = document.getElementById('input-traffic')?.value || 45;
    const aqi = document.getElementById('input-aqi')?.value || 85;
    const hour = document.getElementById('input-hour')?.value || 14;

    addLog("INFO", `[MANUAL TEST] ${sec}`);
    await sendScan(sec, hour, temp, occ, traffic, aqi);
}

async function runWhatIf() {
    const out = $('whatif-result');
    const body = {
        sector_id: $('val-sector').value, hour: +$('input-hour').value, is_weekend: 0,
        temperature: +$('input-temp').value, occupancy: +$('input-occ').value,
        traffic_density: +$('input-traffic').value, aqi: +$('input-aqi').value
    };
    try {
        const r = await post('/whatif', body);
        out.innerHTML = `<table class="whatif-table"><tr><th>Sector</th><th>Now</th><th>Scenario</th><th>Δ</th></tr>` +
            r.sectors.map(s => {
                const d = s.scenario_risk - s.baseline_risk;
                const col = d > 0.02 ? "var(--status-critical)" : d < -0.02 ? "var(--status-normal)" : "var(--text-muted)";
                return `<tr><td>${esc(s.sector_id.replace('Sector_', ''))}</td><td>${pct(s.baseline_risk)}</td>` +
                    `<td style="color:${sevColor(s.scenario_severity)}">${pct(s.scenario_risk)}</td>` +
                    `<td style="color:${col}">${d >= 0 ? '+' : ''}${(d * 100).toFixed(0)}%</td></tr>`;
            }).join('') + `</table>`;
    } catch (e) { out.textContent = "What-if failed: " + e.message; }
}

function renderSim(s) {
    simState = s;
    if ($('sim-clock')) $('sim-clock').textContent = s.clock;
    if ($('btn-pause')) $('btn-pause').textContent = s.running ? "Pause" : "Resume";
    if ($('sim-speed')) $('sim-speed').value = String(s.speed);
    if ($('sim-active')) $('sim-active').textContent = s.scenarios.length
        ? "Active: " + s.scenarios.map(x => `${x.name}${x.sector_id ? " @" + x.sector_id.replace("Sector_", "") : ""} (${x.remaining})`).join(", ")
        : "";
}
const toggleSim = () => post('/simulation/control', { running: !simState.running }).then(renderSim);
const setSpeed = v => post('/simulation/control', { speed: Number(v) }).then(renderSim);
async function runScenario(name) {
    const cityWide = ["heatwave", "wildfire_smoke", "clear"].includes(name);
    const r = await post('/simulation/scenario', {
        name, sector_id: cityWide ? null : $('val-sector').value, duration_ticks: 20
    });
    if (name !== "clear") addLog("WARNING", `Scenario "${name}" started (${r.sector_id})`);
    renderSim(r);
}

const NEXT = {
    OPEN: [["ACKNOWLEDGED", "Acknowledge"], ["MITIGATING", "Mitigate"], ["RESOLVED", "Resolve"]],
    ACKNOWLEDGED: [["MITIGATING", "Mitigate"], ["RESOLVED", "Resolve"]],
    MITIGATING: [["RESOLVED", "Resolve"]]
};

function renderIncidents(list) {
    const container = document.getElementById('incidents-container');
    if (!container) return;

    list.forEach(i => {
        if (!seenIncidents.has(i.incident_id)) {
            seenIncidents.add(i.incident_id);
            if (!firstState && i.severity === "CRITICAL")
                notify(`CRITICAL: ${i.sector_id.replace('_', ' ')} ${i.domain} — ${i.primary_action}`);
        }
    });

    if (!list.length) {
        container.innerHTML = `<div style="font-size:0.75rem; color:var(--text-muted);">No open critical incidents.</div>`;
        return;
    }
    container.innerHTML = list.map(inc => `
        <div class="incident-item state-${esc(inc.state)}">
            <div class="incident-header">
                <span>${esc(inc.incident_id)}</span>
                <span>${esc(inc.sector_id)} · ${esc(inc.domain)}</span>
            </div>
            <div class="incident-state">${esc(inc.severity)} · ${esc(inc.state)} · peak ${pct(inc.peak_risk)}</div>
            <div style="color:var(--text-secondary); margin:4px 0;">${esc(inc.primary_action)}</div>
            <div class="incident-actions">${(NEXT[inc.state] || []).map(([st, txt]) =>
                `<button class="resolve-btn" onclick="transitionIncident('${esc(inc.incident_id)}','${st}')">${txt}</button>`).join('')}</div>
        </div>`).join('');
}

async function transitionIncident(id, state) {
    try { await post(`/incidents/${id}/transition`, { state }); }
    catch (e) { console.error("Incident error:", e); notify("Incident update failed"); }
}

function notify(text) {
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = text;
    $('toasts').appendChild(t);
    setTimeout(() => t.remove(), 6000);
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.connect(g); g.connect(ctx.destination);
        o.frequency.value = 880; g.gain.value = 0.05;
        o.start(); o.stop(ctx.currentTime + 0.18);
    } catch{}
}

function historyChart(rows) {
    if (rows.length < 2) return "";
    const w = 560, h = 140, y = v => h - 8 - Math.min(1, v || 0) * (h - 16), x = i => (i / (rows.length - 1)) * w;
    const line = k => rows.map((r, i) => `${x(i)},${y(r[k])}`).join(" ");
    return `<svg class="history-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <line x1="0" x2="${w}" y1="${y(0.45)}" y2="${y(0.45)}" stroke="#f59e0b" stroke-opacity=".4" stroke-dasharray="4 4"/>
      <line x1="0" x2="${w}" y1="${y(0.7)}" y2="${y(0.7)}" stroke="#ef4444" stroke-opacity=".4" stroke-dasharray="4 4"/>
      <polyline points="${line('composite_risk')}" fill="none" stroke="#38bdf8" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
      <polyline points="${line('effective_risk')}" fill="none" stroke="#f59e0b" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>
      <div style="color:var(--text-muted); margin-bottom:8px;">Blue = direct risk · Amber = effective (after cascade)</div>`;
}

async function viewHistory(sectorId) {
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    const historyModal = document.getElementById('history-modal');

    if (modalTitle) modalTitle.innerText = `${sectorId.replace('_', ' ')} Telemetry Log History`;
    if (modalBody) modalBody.innerText = 'Loading...';
    if (historyModal) historyModal.style.display = 'flex';

    try {
        const data = await api(`/history/${sectorId}?limit=100`);
        let html = `<div style="margin-bottom:10px; color:var(--text-secondary);">Avg Temp: ${esc(data.average_temperature)}°C | Total Log Entries: ${esc(data.logs_count)}</div>`;
        html += historyChart(data.history);

        [...data.history].reverse().slice(0, 40).forEach(entry => {
            html += `
                <div style="padding:6px 0; border-bottom:1px dashed rgba(255,255,255,0.1);">
                    <span style="color:var(--text-muted);">${esc(entry.timestamp ? entry.timestamp.split('T')[1].split('.')[0] : '')}</span> - 
                    <span class="${esc(entry.severity)}">${esc(entry.severity)}</span> - 
                    Risk: ${pct(entry.composite_risk)} → ${pct(entry.effective_risk)} | Temp: ${esc(entry.temperature)}°C | AQI: ${esc(entry.aqi)}
                </div>
            `;
        });
        if (modalBody) modalBody.innerHTML = html;
    } catch (e) {
        if (modalBody) modalBody.innerText = 'Failed to load sector history.';
    }
}

function closeModal() {
    const historyModal = document.getElementById('history-modal');
    if (historyModal) historyModal.style.display = 'none';
}

async function fetchModelDiagnostics() {
    try {
        const data = await api('/model-info');
        const container = document.getElementById('importance-list');
        if (!container) return;

        container.innerHTML = '';

        const renderGroup = (title, features) => {
            const rows = Object.entries(features || {});
            if (!rows.length) return `<div style="font-size:0.7rem; color:var(--text-muted);">${title}: no importances available</div>`;
            let html = `<div class="imp-group" style="font-size:0.75rem; margin-bottom:8px;"><div style="color:var(--accent-blue); font-weight:600; font-size:0.7rem; text-transform:uppercase;">${title}</div>`;
            for (const [feat, imp] of rows) {
                html += `<div style="display:flex; justify-content:space-between; color:var(--text-secondary);"><span>${esc(feat)}</span><b style="font-family:'JetBrains Mono', monospace; color:var(--text-primary);">${(imp * 100).toFixed(1)}%</b></div>`;
            }
            return html + `</div>`;
        };

        container.innerHTML += renderGroup('1. Grid Power Model', data.grid_features);
        container.innerHTML += renderGroup('2. Traffic Model', data.traffic_features);
        container.innerHTML += renderGroup('3. AQI Hazard Model', data.aqi_features);
    } catch (e) { console.error("Diagnostics error:", e); }
}

function renderMetrics(data) {
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val;
    };
    setVal('stat-scans', data.total_scans ?? 0);
    setVal('stat-anomalies', data.total_anomalies ?? 0);
    setVal('stat-rate', `${data.anomaly_rate_percent ?? 0.0}%`);
    setVal('stat-risk', data.highest_risk_sector ?? "N/A");
    setVal('stat-incidents', data.open_incidents_count ?? 0);
}

document.addEventListener("DOMContentLoaded", () => {
    initGrid();
    initLeafletMap();
    initWebSocket();
    fetchModelDiagnostics();
    api('/simulation').then(renderSim).catch(() => { });
});