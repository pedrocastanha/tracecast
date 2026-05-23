(function() {
  const API = './api';
  let currentPage = 'overview';
  let currentPeriod = '7d';
  let chartInstances = {};
  let tracePage = 1;
  let traceSort = 'date';
  let traceOrder = 'desc';

  // ── Navigation ──────────────────────────────────────────
  document.querySelectorAll('nav button').forEach(btn => {
    btn.addEventListener('click', () => {
      currentPage = btn.dataset.page;
      document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      document.getElementById('page-' + currentPage).classList.add('active');
      if (currentPage === 'overview') loadOverview();
      if (currentPage === 'traces') loadTraces();
      if (currentPage === 'models') loadModels();
    });
  });

  document.getElementById('period').addEventListener('change', e => {
    currentPeriod = e.target.value;
    if (currentPage === 'overview') loadOverview();
  });

  document.getElementById('btn-filter').addEventListener('click', () => {
    tracePage = 1;
    loadTraces();
  });
  document.getElementById('btn-clear-filters').addEventListener('click', () => {
    document.getElementById('filter-project').value = '';
    document.getElementById('filter-user').value = '';
    document.getElementById('filter-from').value = '';
    document.getElementById('filter-to').value = '';
    tracePage = 1;
    loadTraces();
  });

  document.querySelectorAll('#traces-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      if (traceSort === th.dataset.sort) {
        traceOrder = traceOrder === 'desc' ? 'asc' : 'desc';
      } else {
        traceSort = th.dataset.sort;
        traceOrder = 'desc';
      }
      tracePage = 1;
      loadTraces();
    });
  });

  document.querySelector('.modal-close').addEventListener('click', () => {
    document.getElementById('modal').classList.add('hidden');
  });
  document.getElementById('modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
  });

  // ── API helpers ─────────────────────────────────────────
  async function fetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.json();
  }

  function formatCost(usd) { return '$' + Number(usd).toFixed(4); }
  function formatMs(ms) { return ms == null ? '—' : ms < 1000 ? ms + 'ms' : (ms / 1000).toFixed(2) + 's'; }
  function formatNum(n) { return n == null ? '—' : n.toLocaleString(); }
  function formatPct(n) { return (n * 100).toFixed(1) + '%'; }

  // ── Charts ──────────────────────────────────────────────
  function destroyChart(key) {
    if (chartInstances[key]) { chartInstances[key].destroy(); delete chartInstances[key]; }
  }

  function chartColors() {
    return ['#6366f1','#22c55e','#f59e0b','#ef4444','#06b6d4','#a855f7','#ec4899','#84cc16'];
  }

  function makeLineChart(canvasId, labels, datasets) {
    destroyChart(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    chartInstances[canvasId] = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets: datasets.map((ds, i) => ({ ...ds, borderColor: chartColors()[i % 8], backgroundColor: chartColors()[i % 8] + '20', fill: true, tension: 0.3 })) },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#8b8fa6', font: { size: 11 } } } },
        scales: {
          x: { ticks: { color: '#8b8fa6', font: { size: 10 } }, grid: { color: '#2a2d37' } },
          y: { ticks: { color: '#8b8fa6', font: { size: 10 } }, grid: { color: '#2a2d37' }, beginAtZero: true },
        },
      },
    });
  }

  function makeDoughnutChart(canvasId, labels, data) {
    destroyChart(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    chartInstances[canvasId] = new Chart(ctx, {
      type: 'doughnut',
      data: { labels, datasets: [{ data, backgroundColor: chartColors() }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: 'right', labels: { color: '#8b8fa6', font: { size: 10 }, padding: 12 } } },
      },
    });
  }

  function makeBarChart(canvasId, labels, datasets) {
    destroyChart(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    chartInstances[canvasId] = new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets: datasets.map((ds, i) => ({ ...ds, backgroundColor: chartColors()[i % 8] })) },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#8b8fa6', font: { size: 11 } } } },
        scales: {
          x: { ticks: { color: '#8b8fa6', font: { size: 10 } }, grid: { color: '#2a2d37' } },
          y: { ticks: { color: '#8b8fa6', font: { size: 10 } }, grid: { color: '#2a2d37' }, beginAtZero: true },
        },
      },
    });
  }

  // ── Overview Page ───────────────────────────────────────
  async function loadOverview() {
    try {
      const m = await fetchJSON(API + '/metrics?period=' + currentPeriod);
      document.getElementById('stat-traces').textContent = formatNum(m.total_traces);
      document.getElementById('stat-cost').textContent = formatCost(m.total_cost_usd);
      document.getElementById('stat-latency').textContent = formatMs(m.avg_latency_ms);
      document.getElementById('stat-cache').textContent = formatPct(m.cache_hit_rate);
      document.getElementById('stat-tokens-in').textContent = formatNum(m.total_tokens_in);
      document.getElementById('stat-tokens-out').textContent = formatNum(m.total_tokens_out);

      if (m.traces_over_time && m.traces_over_time.length) {
        makeLineChart('chart-cost-time', m.traces_over_time.map(d => d.date), [
          { label: 'Cost USD', data: m.traces_over_time.map(d => d.cost_usd) },
        ]);
      }

      if (m.cost_by_model) {
        const keys = Object.keys(m.cost_by_model);
        makeDoughnutChart('chart-cost-model', keys, keys.map(k => m.cost_by_model[k]));
      }

      if (m.cost_by_project) {
        const keys = Object.keys(m.cost_by_project);
        makeBarChart('chart-cost-project', keys, [{ label: 'Cost USD', data: keys.map(k => m.cost_by_project[k]) }]);
      }
    } catch (err) { console.error('Metrics error:', err); }
  }

  // ── Traces Page ─────────────────────────────────────────
  async function loadTraces() {
    const projectId = document.getElementById('filter-project').value;
    const userId = document.getElementById('filter-user').value;
    const from = document.getElementById('filter-from').value;
    const to = document.getElementById('filter-to').value;

    let url = API + '/traces?page=' + tracePage + '&page_size=50&sort_by=' + traceSort + '&order=' + traceOrder;
    if (projectId) url += '&project_id=' + encodeURIComponent(projectId);
    if (userId) url += '&user_id=' + encodeURIComponent(userId);
    if (from) url += '&from=' + from;
    if (to) url += '&to=' + to;

    try {
      const data = await fetchJSON(url);
      document.getElementById('trace-count').textContent = data.total + ' traces';
      const tbody = document.querySelector('#traces-table tbody');
      tbody.innerHTML = '';
      data.traces.forEach(t => {
        const tr = document.createElement('tr');
        tr.className = 'clickable';
        tr.innerHTML = [
          '<td>' + h(t.name) + '</td>',
          '<td>' + (t.started_at ? new Date(t.started_at).toLocaleString() : '—') + '</td>',
          '<td>' + formatMs(t.latency_ms) + '</td>',
          '<td>' + formatNum(t.total_tokens_in) + ' / ' + formatNum(t.total_tokens_out) + '</td>',
          '<td>' + formatCost(t.cost_usd) + '</td>',
          '<td>' + (t.span_count || 0) + '</td>',
        ].join('');
        tr.addEventListener('click', () => showTraceDetail(t.trace_id));
        tbody.appendChild(tr);
      });
      renderPagination(data.total);
    } catch (err) { console.error('Traces error:', err); }
  }

  function renderPagination(total) {
    const totalPages = Math.ceil(total / 50);
    const el = document.getElementById('pagination');
    el.innerHTML = '';
    const prev = document.createElement('button');
    prev.textContent = 'Prev';
    prev.disabled = tracePage <= 1;
    prev.addEventListener('click', () => { if (tracePage > 1) { tracePage--; loadTraces(); } });
    el.appendChild(prev);

    const info = document.createElement('span');
    info.style.cssText = 'color:#8b8fa6;font-size:13px;padding:0 12px';
    info.textContent = tracePage + ' / ' + totalPages;
    el.appendChild(info);

    const next = document.createElement('button');
    next.textContent = 'Next';
    next.disabled = tracePage >= totalPages;
    next.addEventListener('click', () => { if (tracePage < totalPages) { tracePage++; loadTraces(); } });
    el.appendChild(next);
  }

  async function showTraceDetail(traceId) {
    try {
      const t = await fetchJSON(API + '/traces/' + traceId);
      let html = '<h2>' + h(t.name) + '</h2>';
      html += '<p style="color:#8b8fa6;font-size:13px">Trace ID: <code>' + h(t.trace_id) + '</code></p>';
      html += '<p style="color:#8b8fa6;font-size:13px">Model: ' + (t.model || '—') + ' | Total Cost: ' + formatCost(t.cost_usd) + ' | Latency: ' + formatMs(t.latency_ms) + '</p>';

      if (t.spans && t.spans.length) {
        html += '<h3 style="margin-top:16px">Spans</h3>';
        t.spans.forEach(s => {
          const cls = 'span-item ' + (s.type || '');
          html += '<div class="' + cls + '">';
          html += '<div class="span-name">' + h(s.name) + ' <span style="color:#8b8fa6;font-size:11px">' + h(s.type) + '</span></div>';
          html += '<div class="span-details">';
          if (s.model) html += '<span>Model: ' + h(s.model) + '</span>';
          html += '<span>Tokens: ' + formatNum(s.tokens_in) + ' in / ' + formatNum(s.tokens_out) + ' out</span>';
          html += '<span>Cost: ' + formatCost(s.cost_usd) + '</span>';
          html += '<span>Latency: ' + formatMs(s.latency_ms) + '</span>';
          html += '</div>';
          if (s.input) {
            html += '<div class="span-io"><strong>Input:</strong> <pre>' + h(truncate(s.input, 500)) + '</pre></div>';
          }
          if (s.output) {
            html += '<div class="span-io"><strong>Output:</strong> <pre>' + h(truncate(s.output, 500)) + '</pre></div>';
          }
          html += '</div>';
        });
      }
      document.getElementById('modal-body').innerHTML = html;
      document.getElementById('modal').classList.remove('hidden');
    } catch (err) { console.error('Trace detail error:', err); }
  }

  // ── Models Page ─────────────────────────────────────────
  async function loadModels() {
    try {
      const m = await fetchJSON(API + '/metrics?period=' + currentPeriod);
      if (m.cost_by_model) {
        const keys = Object.keys(m.cost_by_model);
        makeBarChart('chart-models-cost', keys, [{ label: 'Cost USD', data: keys.map(k => m.cost_by_model[k]) }]);
      }

      const data = await fetchJSON(API + '/traces?page=1&page_size=200');
      const modelTokens = {};
      const modelCount = {};
      data.traces.forEach(t => {
        if (!t.model) return;
        modelTokens[t.model] = (modelTokens[t.model] || 0) + t.total_tokens;
        modelCount[t.model] = (modelCount[t.model] || 0) + 1;
      });
      let html = '<table style="margin-top:24px"><thead><tr><th>Model</th><th>Traces</th><th>Total Tokens</th></tr></thead><tbody>';
      Object.entries(modelCount).sort((a, b) => b[1] - a[1]).forEach(([model, count]) => {
        html += '<tr><td>' + h(model) + '</td><td>' + count + '</td><td>' + formatNum(modelTokens[model]) + '</td></tr>';
      });
      html += '</tbody></table>';
      document.getElementById('models-table-wrap').innerHTML = html;
    } catch (err) { console.error('Models error:', err); }
  }

  function h(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function truncate(s, max) { return s && s.length > max ? s.slice(0, max) + '…' : s; }

  loadOverview();
})();
