/**
 * LHC Data Pipeline — Dashboard Client
 * Real-time charts and WebSocket updates using Chart.js + Socket.IO
 */

// ── Chart.js Global Config ──────────────────────────────────
Chart.defaults.color = '#8892b0';
Chart.defaults.borderColor = 'rgba(42, 48, 80, 0.6)';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.animation.duration = 600;
Chart.defaults.elements.point.radius = 0;
Chart.defaults.elements.point.hoverRadius = 4;

// ── Utility ─────────────────────────────────────────────────
function formatNumber(n) {
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toLocaleString();
}

function formatUptime(sec) {
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = Math.floor(sec % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

// ── Initialize Charts ───────────────────────────────────────

// Rate Chart (line)
const rateCtx = document.getElementById('rate-chart').getContext('2d');
const rateChart = new Chart(rateCtx, {
    type: 'line',
    data: {
        labels: Array(30).fill(''),
        datasets: [{
            data: Array(30).fill(0),
            fill: true,
            backgroundColor: 'rgba(99, 102, 241, 0.1)',
            borderColor: '#6366f1',
            borderWidth: 2,
            tension: 0.4,
            pointBackgroundColor: '#6366f1',
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: { display: false },
            y: {
                beginAtZero: true,
                grid: { color: 'rgba(42, 48, 80, 0.4)' },
                ticks: { callback: v => v + ' /s' },
            }
        },
        plugins: {
            tooltip: {
                backgroundColor: '#1a1f35',
                borderColor: '#2a3050',
                borderWidth: 1,
                callbacks: { label: ctx => ctx.raw + ' events/s' }
            }
        }
    }
});

// Event Type Doughnut
const typeCtx = document.getElementById('type-chart').getContext('2d');
const typeChart = new Chart(typeCtx, {
    type: 'doughnut',
    data: {
        labels: ['Z→μμ', 'tt̄', 'QCD'],
        datasets: [{
            data: [0, 0, 0],
            backgroundColor: ['#6366f1', '#f59e0b', '#06b6d4'],
            borderColor: '#1a1f35',
            borderWidth: 3,
            hoverOffset: 8,
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '65%',
        plugins: {
            legend: {
                display: true,
                position: 'bottom',
                labels: {
                    padding: 16,
                    usePointStyle: true,
                    pointStyle: 'circle',
                    font: { size: 12 },
                }
            },
            tooltip: {
                backgroundColor: '#1a1f35',
                borderColor: '#2a3050',
                borderWidth: 1,
                callbacks: {
                    label: ctx => {
                        const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                        const pct = total > 0 ? (ctx.raw / total * 100).toFixed(1) : 0;
                        return ` ${ctx.label}: ${formatNumber(ctx.raw)} (${pct}%)`;
                    }
                }
            }
        }
    }
});

// Dimuon Mass Histogram
const massCtx = document.getElementById('mass-chart').getContext('2d');
const massChart = new Chart(massCtx, {
    type: 'bar',
    data: {
        labels: [],
        datasets: [{
            data: [],
            backgroundColor: 'rgba(99, 102, 241, 0.6)',
            borderColor: '#6366f1',
            borderWidth: 1,
            borderRadius: 2,
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: {
                grid: { display: false },
                title: { display: true, text: 'M(μ⁺μ⁻) [GeV]', color: '#5a6380' },
            },
            y: {
                beginAtZero: true,
                grid: { color: 'rgba(42, 48, 80, 0.4)' },
                title: { display: true, text: 'Events', color: '#5a6380' },
            }
        },
        plugins: {
            tooltip: {
                backgroundColor: '#1a1f35',
                borderColor: '#2a3050',
                borderWidth: 1,
            }
        }
    }
});

// MET Histogram
const metCtx = document.getElementById('met-chart').getContext('2d');
const metChart = new Chart(metCtx, {
    type: 'bar',
    data: {
        labels: [],
        datasets: [{
            data: [],
            backgroundColor: 'rgba(239, 68, 68, 0.5)',
            borderColor: '#ef4444',
            borderWidth: 1,
            borderRadius: 2,
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            x: {
                grid: { display: false },
                title: { display: true, text: 'E_T^miss [GeV]', color: '#5a6380' },
            },
            y: {
                beginAtZero: true,
                grid: { color: 'rgba(42, 48, 80, 0.4)' },
                title: { display: true, text: 'Events', color: '#5a6380' },
            }
        },
        plugins: {
            tooltip: {
                backgroundColor: '#1a1f35',
                borderColor: '#2a3050',
                borderWidth: 1,
            }
        }
    }
});

// ── Histogram Helper ────────────────────────────────────────
function buildHistogram(values, nBins, xmin, xmax) {
    const binWidth = (xmax - xmin) / nBins;
    const labels = [];
    const counts = new Array(nBins).fill(0);

    for (let i = 0; i < nBins; i++) {
        const lo = xmin + i * binWidth;
        labels.push(Math.round(lo));
    }

    for (const v of values) {
        if (v < xmin || v >= xmax) continue;
        const bin = Math.floor((v - xmin) / binWidth);
        if (bin >= 0 && bin < nBins) counts[bin]++;
    }

    return { labels, counts };
}

// ── Update Functions ────────────────────────────────────────

function updateKPIs(data) {
    document.getElementById('total-events').textContent = formatNumber(data.total_events || 0);
    document.getElementById('triggered-events').textContent = formatNumber(data.triggered_events || 0);
    document.getElementById('trigger-rate').textContent = (data.trigger_rate || data.overall_trigger_rate || 0).toFixed(1) + '%';

    const rate = data.event_rate || data.avg_event_rate || 0;
    document.getElementById('event-rate').textContent = typeof rate === 'number' ? rate.toFixed(0) : rate;

    if (data.uptime_seconds) {
        document.getElementById('uptime').textContent = formatUptime(data.uptime_seconds);
    }
    if (data.avg_latency_ms !== undefined) {
        document.getElementById('avg-latency').textContent = data.avg_latency_ms.toFixed(2) + ' ms';
    }

    document.getElementById('last-update').textContent = 'Last update: ' + new Date().toLocaleTimeString();
}

function updateRateChart(rates) {
    if (!rates || rates.length === 0) return;
    const padded = Array(30).fill(0);
    rates.slice(-30).forEach((v, i) => padded[30 - rates.slice(-30).length + i] = v);
    rateChart.data.datasets[0].data = padded;
    rateChart.update('none');
}

function updateTypeChart(byType) {
    if (!byType) return;
    typeChart.data.datasets[0].data = [
        byType['z_mumu'] || 0,
        byType['ttbar'] || 0,
        byType['qcd'] || 0,
    ];
    typeChart.update('none');
}

function updateMassChart(masses) {
    if (!masses || masses.length === 0) return;
    const hist = buildHistogram(masses, 40, 40, 140);
    massChart.data.labels = hist.labels;
    massChart.data.datasets[0].data = hist.counts;
    massChart.update('none');
}

function updateMETChart(mets) {
    if (!mets || mets.length === 0) return;
    const hist = buildHistogram(mets, 30, 0, 150);
    metChart.data.labels = hist.labels;
    metChart.data.datasets[0].data = hist.counts;
    metChart.update('none');
}

function updateTriggerBars(data) {
    const counts = data.trigger_counts || data.triggers_fired || {};
    const total = data.total_events || 1;

    const triggers = [
        { key: 'single_muon', bar: 'trig-muon-bar', count: 'trig-muon-count' },
        { key: 'dimuon_z', bar: 'trig-dimuon-bar', count: 'trig-dimuon-count' },
        { key: 'multi_jet', bar: 'trig-jet-bar', count: 'trig-jet-count' },
        { key: 'high_met', bar: 'trig-met-bar', count: 'trig-met-count' },
    ];

    for (const t of triggers) {
        const c = counts[t.key] || 0;
        const pct = Math.min((c / total) * 100, 100);
        document.getElementById(t.bar).style.width = pct.toFixed(1) + '%';
        document.getElementById(t.count).textContent = formatNumber(c) + ` (${pct.toFixed(1)}%)`;
    }
}

// ── Full Stats Fetch (initial + fallback) ───────────────────

async function fetchStats() {
    try {
        const res = await fetch('/api/stats');
        if (!res.ok) return;
        const data = await res.json();

        updateKPIs(data);
        updateRateChart(data.recent_rates);
        updateTypeChart(data.events_by_type);
        updateMassChart(data.dimuon_masses);
        updateMETChart(data.met_values);
        updateTriggerBars(data);
    } catch (e) {
        console.warn('Failed to fetch stats:', e);
    }
}

// ── WebSocket (real-time updates) ───────────────────────────

const socket = io({ transports: ['websocket', 'polling'] });

socket.on('connect', () => {
    console.log('✓ WebSocket connected');
    document.getElementById('status-badge').classList.add('badge-live');
});

socket.on('disconnect', () => {
    console.log('✗ WebSocket disconnected');
    document.getElementById('status-badge').classList.remove('badge-live');
});

socket.on('stats_update', (data) => {
    updateKPIs(data);
    if (data.recent_rates) updateRateChart(data.recent_rates);
    if (data.events_by_type) updateTypeChart(data.events_by_type);
    if (data.recent_masses) updateMassChart(data.recent_masses);
    if (data.recent_mets) updateMETChart(data.recent_mets);
    if (data.trigger_counts || data.triggers_fired) updateTriggerBars(data);
});

// ── Initialization ──────────────────────────────────────────

fetchStats();
setInterval(fetchStats, 3000);  // Poll every 3s as fallback
