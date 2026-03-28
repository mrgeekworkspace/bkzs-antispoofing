// Main dashboard controller
class BKZSDashboard {
    constructor() {
        this.ws = null;
        this.cn0History = new Array(120).fill(42);
        this.atkHistory = new Array(120).fill('NOMINAL');
        this.alerts = [];
        this.detections = [];
        this.connected = false;
        this._lastDetType = 'NOMINAL';

        this.init();
    }

    init() {
        this.connectWebSocket();
        this.bindControls();
        this.updateClock();
        setInterval(() => this.updateClock(), 1000);
    }

    connectWebSocket() {
        const host = window.location.host;
        this.ws = new WebSocket(`ws://${host}/ws`);

        this.ws.onopen = () => {
            this.connected = true;
            this.setConnectionStatus(true);
            console.log('WebSocket connected');
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'gnss_update') {
                    this.handleUpdate(data);
                }
            } catch (e) {
                console.error('Parse error:', e);
            }
        };

        this.ws.onclose = () => {
            this.connected = false;
            this.setConnectionStatus(false);
            setTimeout(() => this.connectWebSocket(), 2000);
        };

        this.ws.onerror = (err) => {
            console.error('WebSocket error:', err);
        };
    }

    handleUpdate(data) {
        this.updateStatusBar(data);
        this.updateSatList(data.satellites);
        this.updateReceiverMetrics(data.receiver);
        this.updateAnomalyPanel(data.detection);
        this.updateSignalHistory(data);
        this.updateAttackStatus(data.attack_state);
        this.drawSignalChart();
        this.handleDetectionEvent(data.detection, data.attack_state);

        if (window.globeController) {
            window.globeController.update(data);
        }
    }

    updateStatusBar(data) {
        const det = data.detection;
        const badge = document.getElementById('status-badge');
        const thrType = document.getElementById('threat-type');
        const visCount = document.getElementById('vis-count');
        const methodBadge = document.getElementById('method-badge');

        if (visCount) visCount.textContent = data.receiver.visible_count;
        if (methodBadge) methodBadge.textContent = det.method || 'RULE';

        if (det.type === 'JAMMING') {
            badge.textContent = 'JAMMING'; badge.className = 'status-badge critical';
            thrType.textContent = 'JAMMING'; thrType.className = 'threat-value critical';
        } else if (det.type === 'SPOOFING') {
            badge.textContent = 'SPOOFING'; badge.className = 'status-badge critical';
            thrType.textContent = 'SPOOFING'; thrType.className = 'threat-value critical';
        } else if (det.type === 'ANOMALY') {
            badge.textContent = 'ANOMALY'; badge.className = 'status-badge warning';
            thrType.textContent = 'ANOMALY'; thrType.className = 'threat-value warning';
        } else {
            badge.textContent = 'NOMINAL'; badge.className = 'status-badge nominal';
            thrType.textContent = 'NOMINAL'; thrType.className = 'threat-value nominal';
        }
    }

    updateSatList(satellites) {
        const list = document.getElementById('sat-list');
        if (!list) return;
        const html = satellites.slice(0, 14).map(sat => {
            const cnoCls = sat.cn0 > 34 ? 'good' : sat.cn0 > 24 ? 'warn' : 'bad';
            const vis = sat.visible ? '' : 'dim';
            return `
                <div class="sat-row ${vis}">
                    <span class="sat-dot ${sat.is_bkzs ? 'bkzs' : 'gps'} ${cnoCls}"></span>
                    <span class="sat-id">${sat.prn}</span>
                    <span class="sat-el">${sat.elevation.toFixed(0)}&deg;</span>
                    <span class="sat-cn0 ${cnoCls}">${sat.cn0.toFixed(1)}</span>
                </div>`;
        }).join('');
        list.innerHTML = html;
    }

    updateReceiverMetrics(rx) {
        const setMetric = (id, val, cls) => {
            const el = document.getElementById(id);
            if (el) { el.textContent = val; el.className = `metric-value ${cls}`; }
        };
        const fixNames = { 0: 'NO FIX', 1: '1D FIX', 2: '2D FIX', 3: '3D FIX' };
        const fixCls = rx.fix_type >= 3 ? 'good' : rx.fix_type >= 2 ? 'warn' : 'bad';

        setMetric('m-hdop', rx.hdop.toFixed(2), rx.hdop < 1.5 ? 'good' : rx.hdop < 3 ? 'warn' : 'bad');
        setMetric('m-fix', fixNames[rx.fix_type] || 'UNKNOWN', fixCls);
        setMetric('m-pos', `\u00B1${rx.position_error_m.toFixed(1)} m`, rx.position_error_m < 10 ? 'good' : 'bad');
        setMetric('m-clock', `${rx.clock_bias_ns > 0 ? '+' : ''}${rx.clock_bias_ns.toFixed(1)} ns`,
                  Math.abs(rx.clock_bias_ns) < 20 ? 'good' : 'bad');
        setMetric('m-agc', rx.agc_level.toFixed(3), rx.agc_level > 0.5 ? 'good' : rx.agc_level > 0.3 ? 'warn' : 'bad');
        setMetric('m-pdop', rx.pdop.toFixed(2), rx.pdop < 2 ? 'good' : 'warn');
    }

    updateAnomalyPanel(det) {
        const setBar = (id, valId, val, warnTh, critTh) => {
            const fill = document.getElementById(id);
            const valEl = document.getElementById(valId);
            if (!fill || !valEl) return;
            fill.style.width = Math.min(100, Math.max(0, val)) + '%';
            fill.className = 'score-fill' + (val >= critTh ? ' bad' : val >= warnTh ? ' warn' : '');
            valEl.textContent = val;
        };

        if (det.rf_probs && det.rf_probs.NOMINAL !== null) {
            const p = det.rf_probs;
            const j = Math.round((p.JAMMING || 0) * 100);
            const s = Math.round((p.SPOOFING || 0) * 100);
            const n = Math.round((p.NOMINAL || 1) * 100);
            setBar('bar-jamming', 'val-jamming', j, 40, 70);
            setBar('bar-spoofing', 'val-spoofing', s, 40, 70);
            setBar('bar-integrity', 'val-integrity', n, 50, 80);
        } else {
            // Rule-based fallback: show confidence as bar based on detection type
            const conf = Math.round((det.confidence || 0) * 100);
            if (det.type === 'JAMMING') {
                setBar('bar-jamming', 'val-jamming', conf, 40, 70);
                setBar('bar-spoofing', 'val-spoofing', 0, 40, 70);
                setBar('bar-integrity', 'val-integrity', 100 - conf, 50, 80);
            } else if (det.type === 'SPOOFING') {
                setBar('bar-jamming', 'val-jamming', 0, 40, 70);
                setBar('bar-spoofing', 'val-spoofing', conf, 40, 70);
                setBar('bar-integrity', 'val-integrity', 100 - conf, 50, 80);
            } else {
                setBar('bar-jamming', 'val-jamming', 0, 40, 70);
                setBar('bar-spoofing', 'val-spoofing', 0, 40, 70);
                setBar('bar-integrity', 'val-integrity', conf, 50, 80);
            }
        }

        if (det.iso_score !== null && det.iso_score !== undefined) {
            setBar('bar-iso', 'val-iso', Math.round(det.iso_score * 100), 50, 70);
        }

        const confEl = document.getElementById('detection-confidence');
        if (confEl) confEl.textContent = `${Math.round((det.confidence || 0) * 100)}%`;

        // Also update the large confidence display
        const confLg = document.getElementById('detection-confidence-lg');
        if (confLg) {
            const pct = Math.round((det.confidence || 0) * 100);
            confLg.textContent = `${pct}%`;
            confLg.style.color = det.type === 'NOMINAL' ? '#22c55e' : det.type === 'JAMMING' ? '#f59e0b' : '#ef4444';
        }
    }

    updateSignalHistory(data) {
        this.cn0History.push(data.features.avg_cn0);
        this.cn0History.shift();
        this.atkHistory.push(data.detection.type);
        this.atkHistory.shift();
    }

    drawSignalChart() {
        const canvas = document.getElementById('signal-chart');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const w = canvas.width = canvas.offsetWidth;
        const h = canvas.height = 90;

        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = 'rgba(0,0,0,0.4)';
        ctx.fillRect(0, 0, w, h);

        ctx.strokeStyle = 'rgba(0,140,190,0.12)'; ctx.lineWidth = 0.6;
        [20, 30, 40, 50].forEach(db => {
            const y = h - (db - 15) / 40 * h;
            ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
            ctx.fillStyle = 'rgba(0,140,190,0.45)'; ctx.font = '7px JetBrains Mono';
            ctx.fillText(db, 2, y - 2);
        });

        for (let i = 0; i < 120; i++) {
            const x = i / 120 * w, bw = w / 120;
            if (this.atkHistory[i] === 'JAMMING') { ctx.fillStyle = 'rgba(255,170,0,0.06)'; ctx.fillRect(x, 0, bw, h); }
            if (this.atkHistory[i] === 'SPOOFING') { ctx.fillStyle = 'rgba(255,45,64,0.07)'; ctx.fillRect(x, 0, bw, h); }
        }

        ctx.lineWidth = 1.8; ctx.shadowBlur = 5;
        for (let i = 1; i < 120; i++) {
            const x0 = (i-1)/119 * w, x1 = i/119 * w;
            const y0 = h - (this.cn0History[i-1] - 15) / 40 * h;
            const y1 = h - (this.cn0History[i] - 15) / 40 * h;
            ctx.strokeStyle = this.atkHistory[i] === 'JAMMING' ? '#f59e0b' :
                              this.atkHistory[i] === 'SPOOFING' ? '#ef4444' : '#22c55e';
            ctx.shadowColor = ctx.strokeStyle;
            ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
        }
        ctx.shadowBlur = 0;

        const threshY = h - (24 - 15) / 40 * h;
        ctx.strokeStyle = 'rgba(255,170,0,0.3)'; ctx.lineWidth = 0.8;
        ctx.setLineDash([4, 4]);
        ctx.beginPath(); ctx.moveTo(0, threshY); ctx.lineTo(w, threshY); ctx.stroke();
        ctx.setLineDash([]);

        ctx.fillStyle = 'rgba(0,190,220,0.45)'; ctx.font = '7px JetBrains Mono';
        ctx.fillText('dB-Hz', w - 34, 10);
    }

    updateAttackStatus(state) {
        if (!state) return;
        const indicator = document.getElementById('attack-indicator');
        if (!indicator) return;
        indicator.style.display = state.is_active ? 'flex' : 'none';
        indicator.className = `attack-indicator ${state.attack_type.toLowerCase()}`;
        const typeEl = document.getElementById('attack-type-display');
        const intEl = document.getElementById('attack-intensity-display');
        if (typeEl) typeEl.textContent = state.attack_type;
        if (intEl) intEl.textContent = `${Math.round(state.current_intensity * 100)}%`;
    }

    handleDetectionEvent(det, attackState) {
        const type = det.type;
        if (type !== this._lastDetType) {
            if (type === 'JAMMING') {
                this.addAlert('CRIT', 'JAMMING', 'Signal jamming detected -- C/N0 dropped below threshold');
                this.addDetection('crit', 'ALARM', `Jam conf: ${Math.round((det.confidence||0)*100)}% via ${det.method}`);
            } else if (type === 'SPOOFING') {
                this.addAlert('CRIT', 'SPOOFING', 'Spoofing attack -- Doppler inconsistency detected');
                this.addDetection('crit', 'SPOOF', `Spoof conf: ${Math.round((det.confidence||0)*100)}% via ${det.method}`);
            } else if (type === 'ANOMALY') {
                this.addAlert('WARN', 'ANOMALY', `Isolation forest anomaly detected -- score: ${det.iso_score}`);
                this.addDetection('warn', 'ISO', `Unknown anomaly, iso_score=${det.iso_score}`);
            } else if (this._lastDetType && this._lastDetType !== 'NOMINAL') {
                this.addAlert('CLEAR', 'CLEAR', 'Threat cleared -- system back to nominal');
                this.addDetection('ok', 'OK', 'All metrics within nominal bounds');
            }
            this._lastDetType = type;
        }
    }

    addAlert(level, badge, msg) {
        const now = new Date(Date.now() + 3 * 60 * 60 * 1000);
        const t = `${String(now.getUTCHours()).padStart(2,'0')}:${String(now.getUTCMinutes()).padStart(2,'0')}:${String(now.getUTCSeconds()).padStart(2,'0')}`;
        this.alerts.unshift({ t, level, badge, msg });
        if (this.alerts.length > 50) this.alerts.pop();
        this.renderAlerts();
    }

    renderAlerts() {
        const feed = document.getElementById('alert-feed');
        if (!feed) return;
        feed.innerHTML = this.alerts.slice(0, 5).map(a =>
            `<div class="alert-line">
                <span class="al-time">${a.t}</span>
                <span class="al-badge ${a.level}">${a.badge}</span>
                <span class="al-msg">${a.msg}</span>
            </div>`
        ).join('');
    }

    addDetection(cls, badge, msg) {
        const now2 = new Date(Date.now() + 3 * 60 * 60 * 1000);
        const t = `${String(now2.getUTCHours()).padStart(2,'0')}:${String(now2.getUTCMinutes()).padStart(2,'0')}:${String(now2.getUTCSeconds()).padStart(2,'0')}`;
        this.detections.unshift({ t, cls, badge, msg });
        if (this.detections.length > 20) this.detections.pop();
        const log = document.getElementById('det-log');
        if (!log) return;
        log.innerHTML = this.detections.slice(0, 6).map(d =>
            `<div class="det-row">
                <span class="det-time">${d.t}</span>
                <span class="det-badge ${d.cls}">${d.badge}</span>
                <span class="det-msg">${d.msg}</span>
            </div>`
        ).join('');
    }

    bindControls() {
        document.getElementById('btn-jam-start')?.addEventListener('click', () => this.startJamming());
        document.getElementById('btn-stop-all')?.addEventListener('click', () => this.stopAllAttacks());
        document.getElementById('btn-spoof-start')?.addEventListener('click', () => this.startSpoofing());

        ['jamming-intensity', 'spoofing-intensity', 'spoofing-offset', 'jamming-ramp', 'spoofing-ramp'].forEach(id => {
            const el = document.getElementById(id);
            const valEl = document.getElementById(id + '-val');
            if (el && valEl) {
                el.addEventListener('input', () => {
                    if (id === 'spoofing-offset') valEl.textContent = el.value + 'm';
                    else if (id.includes('ramp')) valEl.textContent = el.value + 's';
                    else valEl.textContent = el.value + '%';
                });
            }
        });

        document.getElementById('btn-auto-demo')?.addEventListener('change', (e) => {
            fetch(`/api/attack/auto-demo?enable=${e.target.checked}`, { method: 'POST' })
                .catch(err => console.error('Auto-demo toggle error:', err));
        });

        document.getElementById('btn-train-sim')?.addEventListener('click', () => this.trainModel('simulate'));
        document.getElementById('btn-train-data')?.addEventListener('click', () => this.trainModel('mendeley'));

        document.getElementById('btn-apply-thresh')?.addEventListener('click', () => this.applyThresholds());
        document.getElementById('btn-reset-thresh')?.addEventListener('click', () => this.resetThresholds());

        document.querySelector('.thresh-toggle')?.addEventListener('click', () => {
            document.querySelector('.thresh-section')?.classList.toggle('collapsed');
        });
    }

    startJamming() {
        const intensity = parseFloat(document.getElementById('jamming-intensity')?.value || '80') / 100;
        const subtype = document.querySelector('input[name="jamming-subtype"]:checked')?.value || 'WIDEBAND';
        const ramp = parseFloat(document.getElementById('jamming-ramp')?.value || '3');

        const payload = {
            attack_type: 'JAMMING',
            intensity: intensity,
            jamming_subtype: subtype,
            spoofing_subtype: 'POSITION_PUSH',
            spoofing_offset_m: 500.0,
            ramp_duration_s: ramp
        };
        console.log('Sending JAMMING:', payload);

        fetch('/api/attack/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
          .then(d => { console.log('Attack response:', d); this.addAlert('WARN', 'INJECT', `Jamming injection started: ${subtype} @ ${Math.round(intensity*100)}%`); })
          .catch(err => { console.error('Attack start error:', err); this.addAlert('CRIT', 'ERROR', `Failed to start attack: ${err.message}`); });

        const btn = document.getElementById('btn-jam-start');
        if (btn) { btn.textContent = 'JAMMING ACTIVE'; btn.classList.add('active-jam'); }
    }

    startSpoofing() {
        const intensity = parseFloat(document.getElementById('spoofing-intensity')?.value || '80') / 100;
        const subtype = document.querySelector('input[name="spoofing-subtype"]:checked')?.value || 'POSITION_PUSH';
        const offset = parseFloat(document.getElementById('spoofing-offset')?.value || '500');
        const ramp = parseFloat(document.getElementById('spoofing-ramp')?.value || '3');

        const payload = {
            attack_type: 'SPOOFING',
            intensity: intensity,
            jamming_subtype: 'WIDEBAND',
            spoofing_subtype: subtype,
            spoofing_offset_m: offset,
            ramp_duration_s: ramp
        };
        console.log('Sending SPOOFING:', payload);

        fetch('/api/attack/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
          .then(d => { console.log('Spoof response:', d); this.addAlert('WARN', 'INJECT', `Spoofing injection started: ${subtype} @ ${Math.round(intensity*100)}%`); })
          .catch(err => { console.error('Spoof start error:', err); this.addAlert('CRIT', 'ERROR', `Failed to start attack: ${err.message}`); });

        const btn = document.getElementById('btn-spoof-start');
        if (btn) { btn.textContent = 'SPOOFING ACTIVE'; btn.classList.add('active-spoof'); }
    }

    stopAllAttacks() {
        fetch('/api/attack/stop', { method: 'POST' })
            .catch(err => console.error('Stop error:', err));
        const jBtn = document.getElementById('btn-jam-start');
        const sBtn = document.getElementById('btn-spoof-start');
        if (jBtn) { jBtn.textContent = 'START JAMMING'; jBtn.classList.remove('active-jam'); }
        if (sBtn) { sBtn.textContent = 'START SPOOFING'; sBtn.classList.remove('active-spoof'); }
    }

    trainModel(type) {
        const statusEl = document.getElementById('train-status');
        if (statusEl) statusEl.textContent = 'Training... this may take 30-60 seconds';

        const dataPath = document.getElementById('data-path')?.value || '';

        fetch('/api/train', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dataset_type: type, n_estimators: 150, data_path: dataPath || null })
        }).catch(err => { if (statusEl) statusEl.textContent = `Error: ${err}`; });

        const poll = setInterval(() => {
            fetch('/api/train/status').then(r => r.json()).then(d => {
                if (!d.running) {
                    clearInterval(poll);
                    if (d.result) {
                        if (statusEl) statusEl.innerHTML =
                            `Training complete! Accuracy: ${(d.result.accuracy * 100).toFixed(1)}% | ` +
                            `CV F1: ${(d.result.cv_f1_mean * 100).toFixed(1)}%`;
                        const ms = document.getElementById('models-status');
                        if (ms) { ms.textContent = 'MODELS LOADED'; ms.className = 'models-status loaded'; }
                    } else if (d.error) {
                        if (statusEl) statusEl.textContent = `Error: ${d.error}`;
                    }
                }
            }).catch(() => {});
        }, 2000);
    }

    applyThresholds() {
        const body = {
            jamming_cn0_threshold: parseFloat(document.getElementById('thresh-cn0')?.value),
            agc_drop_threshold: parseFloat(document.getElementById('thresh-agc')?.value),
            spoofing_doppler_threshold: parseFloat(document.getElementById('thresh-doppler')?.value),
            spoofing_position_jump_m: parseFloat(document.getElementById('thresh-pos')?.value),
            spoofing_clock_jump_ns: parseFloat(document.getElementById('thresh-clock')?.value),
        };
        Object.keys(body).forEach(k => isNaN(body[k]) && delete body[k]);

        fetch('/api/thresholds', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(r => r.json()).then(() => {
            const s = document.getElementById('thresh-status');
            if (s) { s.textContent = 'Thresholds updated'; setTimeout(() => s.textContent = '', 2000); }
        }).catch(err => console.error('Threshold error:', err));
    }

    resetThresholds() {
        document.getElementById('thresh-cn0').value = 24;
        document.getElementById('thresh-agc').value = 0.35;
        document.getElementById('thresh-doppler').value = 6;
        document.getElementById('thresh-pos').value = 120;
        document.getElementById('thresh-clock').value = 12;
        this.applyThresholds();
    }

    setConnectionStatus(connected) {
        const el = document.getElementById('ws-status');
        if (el) {
            el.textContent = connected ? 'LIVE' : 'DISCONNECTED';
            el.className = connected ? 'ws-status connected' : 'ws-status disconnected';
        }
    }

    updateClock() {
        const el = document.getElementById('clock');
        if (el) {
            const n = new Date();
            // Istanbul time = UTC+3
            const istanbul = new Date(n.getTime() + 3 * 60 * 60 * 1000);
            el.textContent = `${String(istanbul.getUTCHours()).padStart(2,'0')}:${String(istanbul.getUTCMinutes()).padStart(2,'0')}:${String(istanbul.getUTCSeconds()).padStart(2,'0')} IST`;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new BKZSDashboard();
    console.log('BKZS Dashboard initialized');
});
