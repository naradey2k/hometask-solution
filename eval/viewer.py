"""Trace viewer — generates a self-contained HTML file for a run report.

The viewer shows a message timeline with expandable tool-call I/O,
pass/fail badges, and highlighted failing steps. A human should find
the failing step in under 30 seconds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eval.models import RunReport


def generate_viewer(report: RunReport, output_path: Path) -> Path:
    """Generate a self-contained HTML trace viewer for a run."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report_json = json.dumps(report.to_dict(), indent=2, default=str)

    html = _VIEWER_TEMPLATE.replace("__REPORT_DATA__", report_json)

    with output_path.open("w") as f:
        f.write(html)

    return output_path


# ---------------------------------------------------------------------------
# HTML Template (self-contained, no external dependencies)
# ---------------------------------------------------------------------------

_VIEWER_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DRL Eval — Trace Viewer</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --surface2: #232733;
    --border: #2d3140;
    --text: #e1e4ed;
    --text-dim: #8b90a0;
    --accent: #6c8aff;
    --green: #3dd68c;
    --red: #ff6b7a;
    --yellow: #ffd666;
    --orange: #ff9f43;
    --pink: #ff6bcb;
    --font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    --mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  }

  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    line-height: 1.6;
    padding: 0;
  }

  .header {
    background: linear-gradient(135deg, #1a1d27 0%, #232733 100%);
    border-bottom: 1px solid var(--border);
    padding: 24px 32px;
    position: sticky;
    top: 0;
    z-index: 100;
    backdrop-filter: blur(12px);
  }

  .header h1 {
    font-size: 20px;
    font-weight: 700;
    color: var(--accent);
    margin-bottom: 8px;
  }

  .header-stats {
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
    font-size: 13px;
    color: var(--text-dim);
  }

  .header-stats .stat {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .header-stats .stat-value {
    color: var(--text);
    font-weight: 600;
  }

  .layout {
    display: flex;
    height: calc(100vh - 100px);
  }

  .sidebar {
    width: 340px;
    min-width: 340px;
    border-right: 1px solid var(--border);
    overflow-y: auto;
    background: var(--surface);
  }

  .sidebar-header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .case-item {
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    transition: background 0.15s;
  }

  .case-item:hover { background: var(--surface2); }
  .case-item.active { background: var(--surface2); border-left: 3px solid var(--accent); }

  .case-item .case-name {
    font-size: 14px;
    font-weight: 500;
    margin-bottom: 4px;
  }

  .case-item .case-meta {
    font-size: 12px;
    color: var(--text-dim);
    display: flex;
    gap: 12px;
    align-items: center;
  }

  .badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }

  .badge-pass { background: rgba(61,214,140,0.15); color: var(--green); }
  .badge-fail { background: rgba(255,107,122,0.15); color: var(--red); }
  .badge-flaky { background: rgba(255,214,102,0.15); color: var(--yellow); }

  .main {
    flex: 1;
    overflow-y: auto;
    padding: 24px 32px;
  }

  .case-detail-header {
    margin-bottom: 24px;
  }

  .case-detail-header h2 {
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 8px;
  }

  .case-detail-header .question {
    background: var(--surface);
    padding: 12px 16px;
    border-radius: 8px;
    border-left: 3px solid var(--accent);
    font-size: 14px;
    margin-bottom: 16px;
  }

  .metrics-grid {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 24px;
  }

  .metric-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px 16px;
    min-width: 180px;
    flex: 1;
  }

  .metric-card.metric-pass { border-left: 3px solid var(--green); }
  .metric-card.metric-fail { border-left: 3px solid var(--red); }
  .metric-card.metric-error { border-left: 3px solid var(--orange); }

  .metric-card .metric-name {
    font-size: 12px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-bottom: 4px;
  }

  .metric-card .metric-status {
    font-size: 14px;
    font-weight: 600;
  }

  .metric-card .metric-rationale {
    font-size: 12px;
    color: var(--text-dim);
    margin-top: 4px;
    line-height: 1.4;
  }

  .timeline {
    position: relative;
  }

  .timeline::before {
    content: '';
    position: absolute;
    left: 20px;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--border);
  }

  .timeline-item {
    position: relative;
    padding-left: 48px;
    margin-bottom: 16px;
  }

  .timeline-dot {
    position: absolute;
    left: 14px;
    top: 8px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: 2px solid var(--border);
    background: var(--bg);
  }

  .timeline-item[data-role="system"] .timeline-dot { background: var(--text-dim); border-color: var(--text-dim); }
  .timeline-item[data-role="user"] .timeline-dot { background: var(--accent); border-color: var(--accent); }
  .timeline-item[data-role="assistant"] .timeline-dot { background: var(--pink); border-color: var(--pink); }
  .timeline-item[data-role="tool"] .timeline-dot { background: var(--yellow); border-color: var(--yellow); }

  .timeline-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }

  .timeline-card.error-card {
    border-color: var(--red);
    background: rgba(255,107,122,0.05);
  }

  .timeline-card-header {
    padding: 10px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: pointer;
    user-select: none;
    border-bottom: 1px solid transparent;
    transition: border-color 0.15s;
  }

  .timeline-card-header:hover {
    border-bottom-color: var(--border);
  }

  .timeline-card-header .role-badge {
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .role-system { color: var(--text-dim); }
  .role-user { color: var(--accent); }
  .role-assistant { color: var(--pink); }
  .role-tool { color: var(--yellow); }

  .timeline-card-header .latency {
    font-size: 11px;
    color: var(--text-dim);
    font-family: var(--mono);
  }

  .timeline-card-body {
    padding: 12px 16px;
    font-size: 13px;
    line-height: 1.6;
    display: none;
    border-top: 1px solid var(--border);
  }

  .timeline-card-body.expanded { display: block; }

  .timeline-card-body pre {
    background: var(--bg);
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    font-family: var(--mono);
    font-size: 12px;
    line-height: 1.5;
    max-height: 400px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .tool-call-label {
    display: inline-block;
    background: rgba(108,138,255,0.1);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-family: var(--mono);
    margin-right: 8px;
  }

  .final-answer {
    background: var(--surface);
    border: 1px solid var(--green);
    border-radius: 8px;
    padding: 16px 20px;
    margin-top: 24px;
  }

  .final-answer h3 {
    color: var(--green);
    font-size: 14px;
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .final-answer .answer-text {
    font-size: 14px;
    line-height: 1.6;
  }

  .citations {
    margin-top: 12px;
    font-size: 12px;
    color: var(--text-dim);
  }

  .search-box {
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
  }

  .search-box input {
    width: 100%;
    padding: 8px 12px;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    font-family: var(--font);
    font-size: 13px;
    outline: none;
    transition: border-color 0.15s;
  }

  .search-box input:focus { border-color: var(--accent); }

  .expand-all-btn {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text-dim);
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 12px;
    cursor: pointer;
    margin-bottom: 16px;
    transition: all 0.15s;
  }

  .expand-all-btn:hover { background: var(--border); color: var(--text); }

  .summary-text {
    font-size: 13px;
    color: var(--text-dim);
    max-width: 400px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
</head>
<body>

<div class="header">
  <h1>🔬 Deep Research Lite — Trace Viewer</h1>
  <div class="header-stats" id="header-stats"></div>
</div>

<div class="layout">
  <div class="sidebar">
    <div class="search-box">
      <input type="text" id="search" placeholder="Filter cases..." />
    </div>
    <div class="sidebar-header">Test Cases</div>
    <div id="case-list"></div>
  </div>
  <div class="main" id="main-content">
    <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-dim)">
      Select a case from the sidebar to view its trace
    </div>
  </div>
</div>

<script>
const REPORT = __REPORT_DATA__;

// Render header stats
document.getElementById('header-stats').innerHTML = `
  <div class="stat">Pass Rate: <span class="stat-value">${REPORT.total_passed}/${REPORT.total_cases} (${(REPORT.pass_rate * 100).toFixed(1)}%)</span></div>
  <div class="stat">Cost: <span class="stat-value">$${REPORT.total_cost_usd.toFixed(4)}</span></div>
  <div class="stat">p50: <span class="stat-value">${REPORT.p50_latency_ms.toFixed(0)}ms</span></div>
  <div class="stat">p95: <span class="stat-value">${REPORT.p95_latency_ms.toFixed(0)}ms</span></div>
  <div class="stat">Run: <span class="stat-value">${REPORT.run_id}</span></div>
`;

// Render sidebar
function renderSidebar(filter = '') {
  const list = document.getElementById('case-list');
  list.innerHTML = '';
  REPORT.case_summaries.forEach((cs, idx) => {
    if (filter && !cs.case_name.toLowerCase().includes(filter.toLowerCase()) &&
        !cs.case_id.toLowerCase().includes(filter.toLowerCase())) return;

    const passed = cs.passed_count === cs.total_repeats;
    const flaky = cs.passed_count > 0 && cs.passed_count < cs.total_repeats;
    let badgeClass = passed ? 'badge-pass' : flaky ? 'badge-flaky' : 'badge-fail';
    let badgeText = passed ? 'PASS' : flaky ? `FLAKY ${cs.passed_count}/${cs.total_repeats}` : 'FAIL';

    const div = document.createElement('div');
    div.className = 'case-item';
    div.dataset.index = idx;
    div.innerHTML = `
      <div class="case-name">${cs.case_name}</div>
      <div class="case-meta">
        <span class="badge ${badgeClass}">${badgeText}</span>
        <span>$${cs.mean_cost_usd.toFixed(4)}</span>
        <span>${cs.mean_wall_time_ms.toFixed(0)}ms</span>
      </div>
    `;
    div.onclick = () => selectCase(idx);
    list.appendChild(div);
  });
}

document.getElementById('search').addEventListener('input', e => renderSidebar(e.target.value));
renderSidebar();

// Select & render a case
function selectCase(idx) {
  document.querySelectorAll('.case-item').forEach(el => el.classList.remove('active'));
  document.querySelector(`.case-item[data-index="${idx}"]`)?.classList.add('active');

  const cs = REPORT.case_summaries[idx];
  const result = cs.results[0]; // Show first repeat
  const trace = result.trace || {};
  const main = document.getElementById('main-content');

  let metricsHtml = '';
  (result.metric_results || []).forEach(m => {
    const cls = m.status === 'pass' ? 'metric-pass' : m.status === 'fail' ? 'metric-fail' : 'metric-error';
    const statusColor = m.status === 'pass' ? 'var(--green)' : m.status === 'fail' ? 'var(--red)' : 'var(--orange)';
    metricsHtml += `
      <div class="metric-card ${cls}">
        <div class="metric-name">${m.metric_name}</div>
        <div class="metric-status" style="color:${statusColor}">${m.status.toUpperCase()}${m.score !== null ? ' (' + m.score + ')' : ''}</div>
        <div class="metric-rationale">${escapeHtml(m.rationale || '')}</div>
      </div>
    `;
  });

  let timelineHtml = '';
  (trace.messages || []).forEach((msg, msgIdx) => {
    const role = msg.role || '?';
    const isError = msg.content && typeof msg.content === 'object' && msg.content.error;
    const errorClass = isError ? 'error-card' : '';

    let summary = '';
    let body = '';

    if (role === 'system') {
      summary = '<span class="summary-text">[System prompt]</span>';
      body = `<pre>${escapeHtml(msg.content || '')}</pre>`;
    } else if (role === 'user') {
      const content = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content);
      summary = `<span class="summary-text">${escapeHtml(content.substring(0, 100))}</span>`;
      body = `<pre>${escapeHtml(content)}</pre>`;
    } else if (role === 'assistant') {
      const text = msg.text || '';
      const toolCalls = msg.tool_calls || [];
      let parts = [];
      if (text) parts.push(text.substring(0, 60));
      toolCalls.forEach(tc => parts.push(`→ ${tc.name}()`));
      summary = `<span class="summary-text">${escapeHtml(parts.join(' | '))}</span>`;
      let bodyParts = [];
      if (text) bodyParts.push(`<p>${escapeHtml(text)}</p>`);
      toolCalls.forEach(tc => {
        bodyParts.push(`<div style="margin-top:8px"><span class="tool-call-label">${tc.name}</span></div>`);
        bodyParts.push(`<pre>${JSON.stringify(tc.args, null, 2)}</pre>`);
      });
      body = bodyParts.join('');
    } else if (role === 'tool') {
      const name = msg.name || '?';
      const content = msg.content;
      const contentStr = typeof content === 'string' ? content : JSON.stringify(content, null, 2);
      const preview = (typeof content === 'string' ? content : JSON.stringify(content)).substring(0, 80);
      summary = `<span class="tool-call-label">${name}</span><span class="summary-text">${escapeHtml(preview)}</span>`;
      body = `<pre>${escapeHtml(contentStr)}</pre>`;
    }

    const latency = msg.latency_ms !== undefined ? `${msg.latency_ms}ms` : '';

    timelineHtml += `
      <div class="timeline-item ${errorClass}" data-role="${role}">
        <div class="timeline-dot"></div>
        <div class="timeline-card ${errorClass}">
          <div class="timeline-card-header" onclick="toggleBody(this)">
            <div><span class="role-badge role-${role}">${role}</span> ${summary}</div>
            <span class="latency">${latency}</span>
          </div>
          <div class="timeline-card-body">${body}</div>
        </div>
      </div>
    `;
  });

  const answer = trace.final_answer || 'N/A';
  const citations = (trace.citations || []).map((c, i) => `[${i+1}] ${c}`).join('<br>');

  main.innerHTML = `
    <div class="case-detail-header">
      <h2>${escapeHtml(cs.case_name)}</h2>
      <div class="question">${escapeHtml(trace.question || '')}</div>
    </div>
    <div class="metrics-grid">${metricsHtml}</div>
    <button class="expand-all-btn" onclick="toggleAll()">Expand / Collapse All</button>
    <div class="timeline">${timelineHtml}</div>
    <div class="final-answer">
      <h3>Final Answer (${trace.stopped_reason || '?'})</h3>
      <div class="answer-text">${escapeHtml(answer)}</div>
      ${citations ? `<div class="citations">${citations}</div>` : ''}
    </div>
  `;
}

function toggleBody(header) {
  const body = header.nextElementSibling;
  body.classList.toggle('expanded');
}

function toggleAll() {
  const bodies = document.querySelectorAll('.timeline-card-body');
  const anyExpanded = Array.from(bodies).some(b => b.classList.contains('expanded'));
  bodies.forEach(b => {
    if (anyExpanded) b.classList.remove('expanded');
    else b.classList.add('expanded');
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Auto-select first case
if (REPORT.case_summaries.length > 0) selectCase(0);
</script>
</body>
</html>"""
