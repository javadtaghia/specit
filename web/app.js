/* SPECiT — Full-Viewport Open Canvas · MS Word · Hand-Drawn Diagram Studio */

const state = {
  project: localStorage.getItem('ae_project') || 'clep-test-project',
  step: 1,
  data: null,
  catalogueDraft: null,
  selectedProcessIdx: 0,
  selectedWorkflowIds: new Set(),
  activeArtProcessId: null,
  activeArtField: 'workflow_md',
  activeArtKind: 'workflow',
  canvasMode: 'word', // 'map' | 'word' | 'split' | 'diagram'
  activeFoundField: 'constitution_md',
  foundView: 'word', // 'word' | 'split'
  activePlanMode: 'plan_md', // 'plan_md' | 'tasks_md' | 'code'
  planView: 'word', // 'word' | 'split'
  activeCodeFile: null,
  qaSelectedIds: new Set(),
  qaBatchStop: false,
  step3BatchStop: false,
  nativeEditor: null,
  providers: [],
  cfg: JSON.parse(localStorage.getItem('ae_cfg_v2') || 'null') || {
    provider: 'copilot_cli',
    url: '',
    model: 'auto',
    api_key: '',
    drawio_url: 'https://embed.diagrams.net',
  },
};

const SKETCH_FONT = '"Virgil", "Patrick Hand", "Architects Daughter", "Segoe Print", cursive';

if (window.mermaid) {
  mermaid.initialize({
    startOnLoad: false,
    suppressErrorRendering: true,
    look: 'handDrawn',
    theme: 'base',
    securityLevel: 'loose',
    themeVariables: {
      fontFamily: SKETCH_FONT,
      fontSize: '16px',
      background: '#ffffff',
      primaryColor: '#fef9d7',
      primaryTextColor: '#1e1e1e',
      primaryBorderColor: '#1e1e1e',
      secondaryColor: '#eaf4fe',
      secondaryTextColor: '#1e1e1e',
      secondaryBorderColor: '#1e1e1e',
      tertiaryColor: '#f0edfe',
      tertiaryTextColor: '#1e1e1e',
      tertiaryBorderColor: '#1e1e1e',
      lineColor: '#1e1e1e',
      textColor: '#1e1e1e',
      mainBkg: '#fef9d7',
      nodeBorder: '#1e1e1e',
      clusterBkg: '#ffffff',
      clusterBorder: '#1e1e1e',
      edgeLabelBackground: '#ffffff',
    },
  });
}

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ==================== COLOR-FORMATTED DIFF RENDERER ==================== */
function renderColoredDiff(diffText, targetEl, statsEl = null) {
  if (!targetEl) return;
  if (!diffText || !diffText.trim()) {
    targetEl.innerHTML = '<div class="diff-empty">(No differences between selected revisions)</div>';
    if (statsEl) statsEl.innerHTML = '';
    return;
  }
  let added = 0;
  let removed = 0;
  const rows = diffText.split('\n').map((line) => {
    if (line.startsWith('+++') || line.startsWith('---')) {
      return `<div class="diff-line diff-meta"><span class="diff-gutter"></span><span class="diff-text">${escapeHtml(line)}</span></div>`;
    }
    if (line.startsWith('@@')) {
      return `<div class="diff-line diff-hunk"><span class="diff-gutter">⋯</span><span class="diff-text">${escapeHtml(line)}</span></div>`;
    }
    if (line.startsWith('+')) {
      added++;
      return `<div class="diff-line diff-add"><span class="diff-gutter">+</span><span class="diff-text">${escapeHtml(line.slice(1))}</span></div>`;
    }
    if (line.startsWith('-')) {
      removed++;
      return `<div class="diff-line diff-del"><span class="diff-gutter">−</span><span class="diff-text">${escapeHtml(line.slice(1))}</span></div>`;
    }
    return `<div class="diff-line diff-ctx"><span class="diff-gutter"> </span><span class="diff-text">${escapeHtml(line.startsWith(' ') ? line.slice(1) : line)}</span></div>`;
  });
  targetEl.innerHTML = rows.join('');
  if (statsEl) {
    statsEl.innerHTML = `<span class="diff-stat-add">+${added}</span><span class="diff-stat-del">−${removed}</span>`;
  }
}

/* ==================== RIGHT-CLICK CONTEXT MENU ==================== */
function closeContextMenu() {
  const menu = $('item-context-menu');
  if (menu) menu.classList.add('hidden');
}

window.openItemContextMenu = function (evt, pid, pname = '', originStep = 3) {
  evt.preventDefault();
  evt.stopPropagation();
  const menu = $('item-context-menu');
  const title = pname ? `${pid} — ${pname}` : pid;
  const items = [
    { label: '📄 Word View', fn: () => { goStep(3); openFlowInCanvas(pid, 'word'); } },
    { label: '✏️ Edit Markdown', fn: () => { goStep(3); openFlowInCanvas(pid, 'split'); } },
    { label: '📐 Diagram Editor', fn: () => { goStep(3); openFlowInCanvas(pid, 'diagram'); } },
    { label: '🗺️ Flows Map', fn: () => { goStep(3); state.activeArtProcessId = pid; setCanvasMode('map'); } },
    { sep: true },
    {
      label: '💬 Comments',
      fn: () => {
        if (originStep === 2) {
          const idx = ((state.catalogueDraft && state.catalogueDraft.processes) || []).findIndex((p) => p.id === pid);
          if (idx >= 0) selectCatProcess(idx);
          openCommentsForScope(getScopeForStep(2));
        } else {
          state.activeArtProcessId = pid;
          renderArtifactStudio();
          openCommentsForScope(getScopeForStep(3));
        }
      },
    },
    {
      label: '🤖 Review by AI',
      fn: () => {
        if (originStep === 2) {
          const idx = ((state.catalogueDraft && state.catalogueDraft.processes) || []).findIndex((p) => p.id === pid);
          if (idx >= 0) selectCatProcess(idx);
          openCommentsForScope(getScopeForStep(2));
        } else {
          state.activeArtProcessId = pid;
          renderArtifactStudio();
          openCommentsForScope(getScopeForStep(3));
        }
        $('btn-cd-ai-review').click();
      },
    },
    { sep: true },
    {
      label: '↻ Regenerate This Workflow',
      fn: async () => {
        state.activeArtProcessId = pid;
        goStep(3);
        $('regen-popover').classList.remove('hidden');
        $('art-regen-feedback').focus();
      },
    },
    {
      label: '↻ Batch Regen All Selected',
      fn: () => {
        goStep(3);
        $('regen-popover').classList.remove('hidden');
        $('art-regen-feedback').focus();
      },
    },
    { sep: true },
    {
      label: '📄 Export .docx',
      fn: () => {
        const art = (state.data.artifacts || {})[pid];
        if (!art) return toast(`Generate ${pid} first before exporting.`, 'err');
        downloadSingleDocx(`${pid}-${state.activeArtKind}`, art[state.activeArtField] || '', `Project: ${state.project}`);
      },
    },
    {
      label: '⬇ Download .drawio',
      fn: () => {
        window.location.href = `/api/projects/${encodeURIComponent(state.project)}/diagrams/${encodeURIComponent(pid)}/${state.activeArtKind}/download`;
      },
    },
  ];

  menu.innerHTML = `<div class="ctx-header">${escapeHtml(title)}</div>` + items.map((it, idx) =>
    it.sep ? '<div class="ctx-sep"></div>' : `<button class="ctx-item" data-ctx-idx="${idx}">${it.label}</button>`
  ).join('');

  menu.querySelectorAll('[data-ctx-idx]').forEach((btn) => {
    btn.onclick = () => {
      const idx = Number(btn.dataset.ctxIdx);
      closeContextMenu();
      items[idx].fn();
    };
  });

  menu.classList.remove('hidden');
  const mw = menu.offsetWidth || 230;
  const mh = menu.offsetHeight || 360;
  const left = Math.min(evt.clientX, window.innerWidth - mw - 12);
  const top = Math.min(evt.clientY, window.innerHeight - mh - 12);
  menu.style.left = `${Math.max(8, left)}px`;
  menu.style.top = `${Math.max(8, top)}px`;
};

window.addEventListener('click', closeContextMenu);
window.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeContextMenu(); });

function toast(msg, kind = '') {
  const el = $('toast');
  el.textContent = msg;
  el.className = `toast ${kind}`;
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => el.classList.add('hidden'), 4500);
}

function setBusy(active, msg = 'Working...', sub = '') {
  $('busy-message').textContent = msg;
  $('busy-sub').textContent = sub;
  $('busy-overlay').classList.toggle('hidden', !active);
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || JSON.stringify(j);
    } catch (_) {}
    throw new Error(detail);
  }
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res;
}

/* ==================== PAN & ZOOM ENGINE (OPEN CANVAS) ==================== */
class PanZoom {
  constructor(viewportId, contentId) {
    this.vp = $(viewportId);
    this.content = $(contentId);
    this.scale = 1;
    this.x = 0;
    this.y = 0;
    this.dragging = false;
    this.startX = 0;
    this.startY = 0;
    if (this.vp) this._bind();
  }
  _bind() {
    this.vp.addEventListener('mousedown', (e) => {
      if (e.target.closest('button, a, input, select')) return;
      this.dragging = true;
      this.startX = e.clientX - this.x;
      this.startY = e.clientY - this.y;
      this.vp.classList.add('grabbing');
    });
    window.addEventListener('mousemove', (e) => {
      if (!this.dragging) return;
      this.x = e.clientX - this.startX;
      this.y = e.clientY - this.startY;
      this.apply();
    });
    window.addEventListener('mouseup', () => {
      if (!this.dragging) return;
      this.dragging = false;
      this.vp.classList.remove('grabbing');
    });
    this.vp.addEventListener('wheel', (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 0.91;
      const rect = this.vp.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const next = Math.min(2.6, Math.max(0.25, this.scale * factor));
      const ratio = next / this.scale;
      this.x = mx - (mx - this.x) * ratio;
      this.y = my - (my - this.y) * ratio;
      this.scale = next;
      this.apply();
    }, { passive: false });
  }
  apply() {
    if (this.content) {
      this.content.style.transform = `translate(${this.x}px, ${this.y}px) scale(${this.scale})`;
    }
  }
  zoomBy(factor) {
    const rect = this.vp.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const next = Math.min(2.6, Math.max(0.25, this.scale * factor));
    const ratio = next / this.scale;
    this.x = cx - (cx - this.x) * ratio;
    this.y = cy - (cy - this.y) * ratio;
    this.scale = next;
    this.apply();
  }
  reset() {
    this.scale = 1; this.x = 0; this.y = 0; this.apply();
  }
  fit() {
    if (!this.vp || !this.content) return;
    const vr = this.vp.getBoundingClientRect();
    const cw = this.content.scrollWidth || 800;
    const ch = this.content.scrollHeight || 600;
    const s = Math.min(1.1, Math.max(0.3, Math.min((vr.width - 40) / cw, (vr.height - 80) / ch)));
    this.scale = s;
    this.x = Math.max(12, (vr.width - cw * s) / 2);
    this.y = 12;
    this.apply();
  }
}

let mapPanZoom;

/* ==================== AI PROVIDERS ==================== */
function llmPayload() {
  return {
    provider: state.cfg.provider,
    url: state.cfg.url || '',
    model: state.cfg.model || 'auto',
    api_key: state.cfg.api_key || '',
  };
}

function getProviderMeta(id) {
  return (state.providers || []).find((p) => p.id === id) || null;
}

const PROVIDER_LOGOS = {
  openai: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22.28 9.82a5.98 5.98 0 0 0-.51-4.91 6.05 6.05 0 0 0-6.51-2.9A6.07 6.07 0 0 0 4.98 4.18a5.98 5.98 0 0 0-4 2.9 6.05 6.05 0 0 0 .74 7.1 5.98 5.98 0 0 0 .51 4.91 6.05 6.05 0 0 0 6.51 2.9 5.98 5.98 0 0 0 4.5 2.01 6.06 6.06 0 0 0 5.77-4.21 5.99 5.99 0 0 0 4-2.9 6.06 6.06 0 0 0-.73-7.07zM13.24 22.43a4.48 4.48 0 0 1-2.88-1.04l.14-.08 4.78-2.76a.8.8 0 0 0 .39-.68v-6.74l2.02 1.17a.07.07 0 0 1 .04.05v5.58a4.5 4.5 0 0 1-4.49 4.5zM3.6 18.3a4.47 4.47 0 0 1-.54-3.01l.14.09 4.78 2.76a.77.77 0 0 0 .78 0l5.84-3.37v2.33a.08.08 0 0 1-.03.06L9.74 19.95a4.5 4.5 0 0 1-6.14-1.65zM2.34 7.9a4.49 4.49 0 0 1 2.37-1.97V11.6a.77.77 0 0 0 .39.68l5.81 3.35-2.02 1.17a.08.08 0 0 1-.07 0l-4.83-2.79A4.5 4.5 0 0 1 2.34 7.9zm16.6 3.86-5.83-3.37 2.02-1.16a.08.08 0 0 1 .07 0l4.83 2.79a4.49 4.49 0 0 1-.68 8.1v-5.68a.79.79 0 0 0-.41-.68zm2.01-3.02-.14-.09-4.77-2.78a.78.78 0 0 0-.79 0L9.41 9.23V6.9a.07.07 0 0 1 .03-.06l4.83-2.79a4.5 4.5 0 0 1 6.68 4.66zM8.31 12.86 6.29 11.7a.08.08 0 0 1-.04-.06V6.07a4.5 4.5 0 0 1 7.38-3.45l-.14.08-4.78 2.76a.8.8 0 0 0-.39.68zm1.1-2.37 2.6-1.5 2.6 1.5v3l-2.6 1.5-2.6-1.5z"/></svg>',
  claude: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.1 6.7L20.5 6l-4.2 5.4L22 14.5l-6.8.7L17 22l-5-4.7L7 22l1.8-6.8L2 14.5l5.7-3.1L3.5 6l6.4 2.7z"/></svg>',
  copilot: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.58 2 12.26c0 4.54 2.87 8.39 6.84 9.75.5.09.68-.22.68-.49 0-.24-.01-.88-.01-1.73-2.78.62-3.37-1.37-3.37-1.37-.45-1.18-1.11-1.5-1.11-1.5-.91-.64.07-.63.07-.63 1 .07 1.53 1.06 1.53 1.06.89 1.57 2.34 1.12 2.91.85.09-.66.35-1.12.63-1.37-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05a9.3 9.3 0 0 1 5 0c1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.94-2.34 4.81-4.57 5.06.36.32.68.94.68 1.9 0 1.37-.01 2.48-.01 2.82 0 .27.18.59.69.49A10.27 10.27 0 0 0 22 12.26C22 6.58 17.52 2 12 2z"/></svg>',
  gemini: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c.6 5.2 4.8 9.4 10 10-5.2.6-9.4 4.8-10 10-.6-5.2-4.8-9.4-10-10 5.2-.6 9.4-4.8 10-10z"/></svg>',
};

function getProviderBrand(id) {
  if (id.includes('codex') || id.includes('openai')) return 'openai';
  if (id.includes('claude') || id.includes('anthropic')) return 'claude';
  if (id.includes('gemini')) return 'gemini';
  return 'copilot';
}

function updateLLMPill() {
  const btn = $('llm-pill');
  const meta = getProviderMeta(state.cfg.provider);
  const label = meta ? meta.label : state.cfg.provider;
  const brand = getProviderBrand(state.cfg.provider || '');
  const ok = !!(meta && meta.available);
  btn.innerHTML = `${PROVIDER_LOGOS[brand]}<span class="provider-logo-dot ${ok ? 'ok' : ''}"></span>`;
  btn.title = `${label} · Model: ${state.cfg.model || 'auto'} (click to change)`;
}

async function loadProviders() {
  try {
    const res = await api('/api/llm/providers');
    state.providers = res.providers || [];
    if (!localStorage.getItem('ae_cfg_v2')) {
      const firstReady = state.providers.find((p) => p.kind === 'subscription' && p.available);
      if (firstReady) {
        state.cfg.provider = firstReady.id;
        state.cfg.model = firstReady.default_model;
      }
    } else {
      // Upgrade stale "default" placeholder to real discovered model
      const meta = getProviderMeta(state.cfg.provider);
      if (meta && (!state.cfg.model || state.cfg.model === 'default') && meta.default_model && meta.default_model !== 'default') {
        state.cfg.model = meta.default_model;
        localStorage.setItem('ae_cfg_v2', JSON.stringify(state.cfg));
      }
    }
    populateProviderDropdown();
    updateLLMPill();
  } catch (_) {}
}

function populateProviderDropdown() {
  const sel = $('cfg-provider');
  const subs = state.providers.filter((p) => p.kind === 'subscription');
  const apis = state.providers.filter((p) => p.kind === 'api');
  const opt = (p) => `<option value="${escapeHtml(p.id)}" ${p.id === state.cfg.provider ? 'selected' : ''}>${p.available ? '✓ ' : '○ '}${escapeHtml(p.label)}</option>`;
  sel.innerHTML =
    `<optgroup label="Use Your Subscription (No API Key Needed)">${subs.map(opt).join('')}</optgroup>` +
    `<optgroup label="Direct API Key / GitHub Token">${apis.map(opt).join('')}</optgroup>`;
  syncSettingsUIForProvider(sel.value, false);
}

function syncSettingsUIForProvider(providerId, resetDefaults = true) {
  const meta = getProviderMeta(providerId);
  if (!meta) return;
  $('provider-help').innerHTML = `<strong>${meta.available ? '✓ Detected:' : 'ℹ Status:'}</strong> ${escapeHtml(meta.detected_detail)}<br><small>${escapeHtml(meta.help)}</small>`;
  $('cfg-api-fields').classList.toggle('hidden', meta.kind === 'subscription');
  const mlist = $('cfg-model-list');
  mlist.innerHTML = '<option value="">(preset models)</option>' + (meta.models || []).map((m) => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
  if (resetDefaults) {
    $('cfg-model').value = meta.default_model || 'auto';
    $('cfg-url').value = meta.default_url || '';
  }
}

function currentPrefix() {
  return (state.data && state.data.prefix) || 'PRJ';
}

function wfCode(processId) {
  const px = currentPrefix();
  const m = String(processId || '').match(/(\d+)$/);
  return m ? `${px}-WF-${String(Number(m[1])).padStart(3, '0')}` : `${px}-WF-${processId}`;
}

function syncPrefixInputs() {
  const px = currentPrefix();
  if ($('prefix-input-step1')) $('prefix-input-step1').value = px;
  if ($('prefix-input-step2')) $('prefix-input-step2').value = px;
  if ($('prefix-preview-step1')) {
    $('prefix-preview-step1').textContent = `IDs: ${px}-CA-001 (Catalogue) · ${px}-WF-001 (Work Flows) · ${px}-SC-001 (SC)`;
  }
  if ($('code-task-input')) {
    $('code-task-input').placeholder = `Task ID or slice (e.g. ${px}-SC-001: Implement core domain entity with unit tests)`;
  }
}

async function applyProjectPrefix(rawVal) {
  const clean = String(rawVal || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10);
  if (clean.length < 2) return toast('Prefix must be at least 2 letters/numbers (e.g. PRJ, CLEP, LSKD).', 'err');
  try {
    const res = await api(`/api/projects/${encodeURIComponent(state.project)}/prefix`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prefix: clean, renumber_existing: true }),
    });
    state.selectedWorkflowIds.clear();
    state.activeArtProcessId = null;
    toast(`Prefix set to ${res.prefix} (${res.prefix}-CA-001 · ${res.prefix}-WF-001 · ${res.prefix}-SC-001)`, 'ok');
    await refreshState();
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ==================== WIZARD NAVIGATION ==================== */
window.goStep = function (n) {
  state.step = n;
  document.querySelectorAll('.wstep').forEach((b) => {
    b.classList.toggle('active', Number(b.dataset.step) === n);
  });
  document.querySelectorAll('.step-panel').forEach((p) => {
    p.classList.toggle('active', p.id === `step-${n}`);
  });
  if (n === 3) renderArtifactStudio();
  if (n === 4) renderQualityStep();
  if (n === 5) renderFoundationStep();
  if (n === 6) renderPlanningStep();
};

/* ==================== PROJECT LOADING ==================== */
async function loadProjects() {
  const res = await api('/api/projects');
  const sel = $('project-select');
  const list = Array.from(new Set([state.project, ...res.projects]));
  sel.innerHTML = list.map((p) => `<option value="${escapeHtml(p)}" ${p === state.project ? 'selected' : ''}>${escapeHtml(p)}</option>`).join('');
}

async function refreshState() {
  const data = await api(`/api/projects/${encodeURIComponent(state.project)}/state`);
  state.data = data;
  state.catalogueDraft = data.catalogue ? structuredClone(data.catalogue) : null;

  const procs = (data.catalogue && data.catalogue.processes) || [];
  if (procs.length && state.selectedWorkflowIds.size === 0) {
    procs.forEach((p) => state.selectedWorkflowIds.add(p.id));
  } else {
    const valid = new Set(procs.map((p) => p.id));
    for (const id of Array.from(state.selectedWorkflowIds)) {
      if (!valid.has(id)) state.selectedWorkflowIds.delete(id);
    }
    if (procs.length && state.selectedWorkflowIds.size === 0) {
      procs.forEach((p) => state.selectedWorkflowIds.add(p.id));
    }
  }

  // Pick a generated artifact first if activeArtProcessId isn't set yet
  const artIds = Object.keys(data.artifacts || {});
  if (!state.activeArtProcessId || !procs.some((p) => p.id === state.activeArtProcessId)) {
    state.activeArtProcessId = artIds[0] || (procs[0] && procs[0].id) || null;
  }

  syncPrefixInputs();
  updateWizardBadges();
  renderStep1();
  renderStep2();
  renderArtifactStudio();
  renderQualityStep();
  renderFoundationStep();
  renderPlanningStep();
  updateCommentBadges();
  renderCommentsDrawer();
  refreshGitBadge();
}

function updateWizardBadges() {
  const d = state.data;
  if (!d) return;
  const procs = (d.catalogue && d.catalogue.processes) || [];
  const artCount = Object.keys(d.artifacts || {}).length;

  setStepBadge(1, d.sources.length ? `${d.sources.length}` : '', d.sources.length > 0);
  setStepBadge(2, d.approvals.catalogue ? '✓' : procs.length ? `${procs.length}` : '', d.approvals.catalogue);
  setStepBadge(3, procs.length ? `${artCount}/${procs.length}` : '', procs.length > 0 && artCount === procs.length);
  setStepBadge(4, d.approvals.artifacts ? '✓' : d.quality ? `${d.quality.score}` : '', d.approvals.artifacts);
  setStepBadge(5, d.approvals.foundation ? '✓' : d.foundation ? '•' : '', d.approvals.foundation);
  setStepBadge(6, d.approvals.planning ? '✓' : d.planning ? '•' : '', d.approvals.planning);
}

function setStepBadge(stepNum, text, done) {
  const b = $(`badge-step-${stepNum}`);
  if (b) b.textContent = text;
  const btn = document.querySelector(`.wstep[data-step="${stepNum}"]`);
  if (btn) btn.classList.toggle('done', !!done);
}

/* ==================== MARKDOWN + SEAMLESS INLINE DIAGRAM RENDERER ==================== */
let mermaidCounter = 0;

function slugKey(s) {
  return String(s || '').toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '');
}

async function renderMarkdownToPaper(markdownText, targetEl, diagramCtx = null) {
  if (!targetEl) return;
  if (!markdownText || !markdownText.trim()) {
    targetEl.innerHTML = '<p class="muted">No document generated yet for this selection.</p>';
    return;
  }
  const html = window.marked ? marked.parse(markdownText) : `<pre>${escapeHtml(markdownText)}</pre>`;
  targetEl.innerHTML = html;

  const codeBlocks = Array.from(targetEl.querySelectorAll('pre code.language-mermaid'));
  for (let idx = 0; idx < codeBlocks.length; idx++) {
    const codeEl = codeBlocks[idx];
    const code = codeEl.textContent.trim();
    const pre = codeEl.parentElement;

    // For the primary diagram in an architecture artifact, render a seamless interactive figure
    if (diagramCtx && idx === 0) {
      const dkey = slugKey(`${diagramCtx.processId}_${diagramCtx.kind}`);
      const savedSvg = state.data && state.data.diagram_svgs && state.data.diagram_svgs[dkey];

      const fig = document.createElement('div');
      fig.className = 'doc-diagram-figure';
      fig.setAttribute('contenteditable', 'false');
      fig.dataset.mermaidCode = code;
      fig.innerHTML = `
        <div class="doc-diagram-bar">
          <div>
            <strong>${escapeHtml(diagramCtx.processId)} — ${escapeHtml(diagramCtx.kind.toUpperCase())} Diagram</strong>
            <span class="status-pill ${savedSvg ? 'pill-ok' : 'pill-warn'}" style="margin-left:6px;">${savedSvg ? 'Custom Edited' : 'Auto-Generated'}</span>
          </div>
          <div class="row-actions">
            <button class="btn btn-2xs btn-primary" data-inline-edit="1">✎ Edit Diagram Inline</button>
            <button class="btn btn-2xs" data-full-edit="1">⛶ Full Canvas</button>
          </div>
        </div>
        <div class="doc-diagram-body"></div>
        <div class="doc-diagram-inline-editor hidden"></div>
      `;

      const body = fig.querySelector('.doc-diagram-body');
      const inlineHost = fig.querySelector('.doc-diagram-inline-editor');

      if (savedSvg) {
        body.innerHTML = savedSvg;
      } else {
        // Render directly from the EXACT same .drawio XML that the editor opens so View === Edit!
        try {
          const res = await api(`/api/projects/${encodeURIComponent(state.project)}/diagrams/${encodeURIComponent(diagramCtx.processId)}/${diagramCtx.kind}`);
          if (res.svg) {
            body.innerHTML = res.svg;
          } else if (res.xml && window.NativeDiagramEditor) {
            body.innerHTML = NativeDiagramEditor.renderXmlToSvg(res.xml, `${diagramCtx.processId} ${diagramCtx.kind}`, true);
          }
        } catch (err) {
          body.innerHTML = `<div class="alert-box err">Diagram load issue: ${escapeHtml(err.message || err)}</div><pre>${escapeHtml(code)}</pre>`;
        }
      }

      fig.querySelector('[data-full-edit]').onclick = () => setCanvasMode('diagram');
      fig.querySelector('[data-inline-edit]').onclick = async () => {
        if (!inlineHost.classList.contains('hidden')) {
          inlineHost.classList.add('hidden');
          body.classList.remove('hidden');
          return;
        }
        try {
          const res = await api(`/api/projects/${encodeURIComponent(state.project)}/diagrams/${encodeURIComponent(diagramCtx.processId)}/${diagramCtx.kind}`);
          body.classList.add('hidden');
          inlineHost.classList.remove('hidden');
          const ed = new NativeDiagramEditor(inlineHost, {
            onSave: async (xml, svg) => {
              await api(`/api/projects/${encodeURIComponent(state.project)}/diagrams/${encodeURIComponent(diagramCtx.processId)}/${diagramCtx.kind}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ xml, svg, note: 'edited inline inside Word document' }),
              });
              toast('Diagram saved into Word document!', 'ok');
              await refreshState();
            },
            onClose: () => {
              inlineHost.classList.add('hidden');
              body.classList.remove('hidden');
            },
          });
          ed.loadDrawioXml(res.xml, `${diagramCtx.processId} ${diagramCtx.kind}`);
        } catch (e) {
          toast(e.message, 'err');
        }
      };

      pre.replaceWith(fig);
      continue;
    }

    const box = document.createElement('div');
    box.className = 'mermaid-render-box';
    box.setAttribute('contenteditable', 'false');
    box.dataset.mermaidCode = code;
    try {
      if (window.mermaid) {
        const id = `mmd_${++mermaidCounter}`;
        const { svg } = await mermaid.render(id, code);
        box.innerHTML = svg;
      } else {
        box.innerHTML = `<pre>${escapeHtml(code)}</pre>`;
      }
    } catch (err) {
      // Remove any stray Mermaid error SVG appended to document.body
      document.querySelectorAll('body > [id^="d"], body > svg[aria-roledescription="error"]').forEach((el) => {
        if ((el.textContent || '').includes('Syntax error in text')) el.remove();
      });
      box.innerHTML = `<pre>${escapeHtml(code)}</pre>`;
    }
    pre.replaceWith(box);
  }
}

async function openFullCanvasDiagramEditor() {
  if (!state.activeArtProcessId) return;
  const pid = state.activeArtProcessId;
  const kind = state.activeArtKind;
  const host = $('native-diagram-host');
  if (!host) return;
  const titleEl = $('full-diagram-title');
  if (titleEl) titleEl.textContent = `${pid} — ${kind.toUpperCase()} Diagram Canvas`;
  try {
    const res = await api(`/api/projects/${encodeURIComponent(state.project)}/diagrams/${encodeURIComponent(pid)}/${kind}`);
    state.nativeEditor = new NativeDiagramEditor(host, {
      onSave: async (xml, svg) => {
        await api(`/api/projects/${encodeURIComponent(state.project)}/diagrams/${encodeURIComponent(pid)}/${kind}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ xml, svg, note: 'edited in full-canvas diagram studio' }),
        });
        toast(`Saved diagram for ${pid} (${kind}) — updated in Word View!`, 'ok');
        await refreshState();
      },
      onClose: () => setCanvasMode('word'),
    });
    state.nativeEditor.loadDrawioXml(res.xml, `${pid} ${kind.toUpperCase()}`);
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ==================== DIRECT WORD EDITING (HTML -> MARKDOWN) ==================== */
window.fmtWord = function (cmd, val = null) {
  document.execCommand(cmd, false, val);
  $('word-dirty-indicator').textContent = 'Unsaved edits — click 💾 Save Text Edits';
};

function _inlineToMd(node) {
  if (node.nodeType === Node.TEXT_NODE) return node.nodeValue || '';
  if (node.nodeType !== Node.ELEMENT_NODE) return '';
  const tag = node.tagName.toUpperCase();
  const inner = Array.from(node.childNodes).map(_inlineToMd).join('');
  if (tag === 'STRONG' || tag === 'B') return inner.trim() ? `**${inner}**` : '';
  if (tag === 'EM' || tag === 'I') return inner.trim() ? `*${inner}*` : '';
  if (tag === 'CODE') return inner ? `\`${inner}\`` : '';
  if (tag === 'BR') return '\n';
  if (tag === 'IMG') return `![${node.getAttribute('alt') || 'Image'}](${node.getAttribute('src') || ''})`;
  if (tag === 'A') return `[${inner}](${node.getAttribute('href') || ''})`;
  return inner;
}

function wordPaperToMarkdown(rootEl) {
  const blocks = [];
  for (const node of Array.from(rootEl.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE) {
      const t = (node.nodeValue || '').trim();
      if (t) blocks.push(t);
      continue;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) continue;
    if (node.dataset && node.dataset.mermaidCode) {
      blocks.push('```mermaid\n' + node.dataset.mermaidCode + '\n```');
      continue;
    }
    const tag = node.tagName.toUpperCase();
    if (tag === 'IMG') {
      blocks.push(`![${node.getAttribute('alt') || 'Image'}](${node.getAttribute('src') || ''})`);
      continue;
    }
    if (tag === 'FIGURE') {
      const img = node.querySelector('img');
      if (img) {
        const cap = (node.querySelector('figcaption')?.textContent || img.getAttribute('alt') || 'Image').trim();
        blocks.push(`![${cap}](${img.getAttribute('src') || ''})`);
        continue;
      }
    }
    if (/^H[1-6]$/.test(tag)) {
      const lvl = Number(tag[1]);
      blocks.push('#'.repeat(lvl) + ' ' + _inlineToMd(node).trim());
    } else if (tag === 'UL') {
      const items = Array.from(node.children).map((li) => '- ' + _inlineToMd(li).trim()).filter((x) => x !== '- ');
      if (items.length) blocks.push(items.join('\n'));
    } else if (tag === 'OL') {
      const items = Array.from(node.children).map((li, i) => `${i + 1}. ` + _inlineToMd(li).trim());
      if (items.length) blocks.push(items.join('\n'));
    } else if (tag === 'BLOCKQUOTE') {
      blocks.push(
        _inlineToMd(node).trim().split('\n').map((l) => '> ' + l).join('\n')
      );
    } else if (tag === 'PRE') {
      blocks.push('```\n' + (node.textContent || '').trim() + '\n```');
    } else if (tag === 'TABLE') {
      const rows = Array.from(node.querySelectorAll('tr')).map((tr) =>
        Array.from(tr.children).map((td) => _inlineToMd(td).replace(/\s+/g, ' ').trim())
      );
      if (rows.length) {
        const hdr = '| ' + rows[0].join(' | ') + ' |';
        const sep = '| ' + rows[0].map(() => '---').join(' | ') + ' |';
        const body = rows.slice(1).map((r) => '| ' + r.join(' | ') + ' |');
        blocks.push([hdr, sep, ...body].join('\n'));
      }
    } else {
      const t = _inlineToMd(node).trim();
      if (t) blocks.push(t);
    }
  }
  return blocks.join('\n\n');
}

/* ==================== COMMENTS & SCOPED AI REVIEW DRAWER ==================== */
let activeCommentScope = { key: '', label: '' };
let pendingCommentQuote = '';

function getScopeForStep(stepNum) {
  const d = state.data;
  if (!d) return { key: '', label: '' };
  if (stepNum === 2) {
    const p = (state.catalogueDraft && state.catalogueDraft.processes || [])[state.selectedProcessIdx];
    return p ? { key: `catalogue::process::${p.id}`, label: `Catalogue Process · ${p.id} — ${p.name}` } : { key: '', label: '' };
  }
  if (stepNum === 3) {
    return state.activeArtProcessId
      ? { key: `artifact::${state.activeArtProcessId}::${state.activeArtField}`, label: `Artifact · ${state.activeArtProcessId} (${state.activeArtKind})` }
      : { key: '', label: '' };
  }
  if (stepNum === 5) {
    return { key: `foundation::${state.activeFoundField}`, label: `Foundation · ${state.activeFoundField.replace('_md', '')}` };
  }
  if (stepNum === 6 && state.activePlanMode !== 'code') {
    return { key: `planning::${state.activePlanMode}`, label: `Planning · ${state.activePlanMode.replace('_md', '')}` };
  }
  return { key: '', label: '' };
}

function openCommentsForScope(scope, quote = '') {
  if (!scope || !scope.key) return toast('Select an item first to comment on it.', 'err');
  activeCommentScope = scope;
  pendingCommentQuote = (quote || '').trim();
  $('comments-drawer').classList.remove('hidden');
  renderCommentsDrawer();
  $('cd-input').focus();
}

function updateCommentBadges() {
  const all = (state.data && state.data.comments) || [];
  const countOpen = (key) => all.filter((c) => c.target_key === key && c.status === 'open').length;
  const pairs = [
    ['btn-cat-comments', getScopeForStep(2).key],
    ['btn-art-comments', getScopeForStep(3).key],
    ['btn-found-comments', getScopeForStep(5).key],
    ['btn-plan-comments', getScopeForStep(6).key],
  ];
  for (const [btnId, key] of pairs) {
    const el = $(btnId);
    if (!el) continue;
    const n = key ? countOpen(key) : 0;
    el.textContent = n ? `💬 Comments (${n})` : '💬 Comments';
  }
}

function renderCommentsDrawer() {
  if ($('comments-drawer').classList.contains('hidden')) return;
  $('cd-target-label').textContent = `Scope: ${activeCommentScope.label}`;
  const qp = $('cd-quote-preview');
  if (pendingCommentQuote) {
    qp.textContent = `"${pendingCommentQuote}"`;
    qp.classList.remove('hidden');
    $('btn-cd-clear-quote').classList.remove('hidden');
  } else {
    qp.classList.add('hidden');
    $('btn-cd-clear-quote').classList.add('hidden');
  }

  const all = (state.data && state.data.comments) || [];
  const list = all.filter((c) => c.target_key === activeCommentScope.key);
  const el = $('cd-list');
  if (!list.length) {
    el.innerHTML = '<p class="muted">No comments on this item yet. Add a note below or click <b>🤖 Review by AI</b>.</p>';
    return;
  }
  el.innerHTML = list.map((c) => {
    const isAi = c.author === 'AI Review';
    const isRes = c.status === 'resolved';
    return `
      <div class="comment-card ${isAi ? 'ai' : ''} ${isRes ? 'resolved' : ''}">
        <div class="row-between">
          <strong>${isAi ? '🤖 AI Review' : '👤 ' + escapeHtml(c.author || 'Reviewer')}</strong>
          <small class="muted">${escapeHtml(c.created_at || '')}</small>
        </div>
        ${c.quote ? `<div class="comment-quote">"${escapeHtml(c.quote)}"</div>` : ''}
        <div class="comment-body">${escapeHtml(c.text)}</div>
        <div class="row-actions">
          <button class="btn btn-2xs" onclick="toggleCommentStatus('${escapeHtml(c.id)}','${isRes ? 'open' : 'resolved'}')">${isRes ? 'Reopen' : '✓ Resolve'}</button>
          <button class="btn btn-2xs btn-danger-outline" onclick="removeComment('${escapeHtml(c.id)}')">Delete</button>
        </div>
      </div>
    `;
  }).join('');
}

window.toggleCommentStatus = async function (cid, status) {
  await api(`/api/projects/${encodeURIComponent(state.project)}/comments/${encodeURIComponent(cid)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
  });
  await refreshState();
  renderCommentsDrawer();
};

window.removeComment = async function (cid) {
  await api(`/api/projects/${encodeURIComponent(state.project)}/comments/${encodeURIComponent(cid)}`, { method: 'DELETE' });
  await refreshState();
  renderCommentsDrawer();
};

/* ==================== STEP 1: SOURCES ==================== */
function renderStep1() {
  const sources = state.data.sources || [];
  const listEl = $('source-list');
  if (!sources.length) {
    listEl.innerHTML = '<p class="muted">No documents uploaded yet. Drop a file above or click <b>Load Sample (sample_document.pdf)</b>.</p>';
  } else {
    listEl.innerHTML = sources.map((s) => `
      <div class="source-row">
        <div>
          <strong>${escapeHtml(s.filename)}</strong>
          <div class="muted">ID: <code>${escapeHtml(s.source_id)}</code> · ${s.chunks.length} sections · ${(s.size / 1024).toFixed(1)} KB</div>
        </div>
        <button class="btn btn-xs btn-danger-outline" onclick="deleteSourceFile('${escapeHtml(s.filename)}')">Remove</button>
      </div>
    `).join('');
  }
  $('btn-extract').disabled = sources.filter((s) => !s.error).length === 0;
}

async function uploadFiles(fileList) {
  if (!fileList || !fileList.length) return;
  const fd = new FormData();
  for (const f of fileList) fd.append('files', f);
  setBusy(true, 'Parsing uploaded documents...', 'Extracting pages, headings, and tables');
  try {
    const res = await api(`/api/projects/${encodeURIComponent(state.project)}/sources/upload`, { method: 'POST', body: fd });
    toast(`Uploaded ${res.saved.join(', ')}`, 'ok');
    await refreshState();
  } catch (e) {
    toast(e.message, 'err');
  } finally {
    setBusy(false);
  }
}

window.deleteSourceFile = async function (filename) {
  try {
    await api(`/api/projects/${encodeURIComponent(state.project)}/sources/${encodeURIComponent(filename)}`, { method: 'DELETE' });
    toast(`Removed ${filename}`, 'ok');
    await refreshState();
  } catch (e) {
    toast(e.message, 'err');
  }
};

/* ==================== STEP 2: CATALOGUE ==================== */
function renderStep2() {
  const cat = state.catalogueDraft;
  const approved = state.data.approvals.catalogue;
  $('cat-empty').classList.toggle('hidden', !!cat);
  $('cat-workspace').classList.toggle('hidden', !cat);

  const badge = $('cat-approval-badge');
  badge.textContent = approved ? '✓ Approved' : 'Not Approved';
  badge.className = `status-pill ${approved ? 'pill-ok' : 'pill-warn'}`;
  $('btn-approve-cat').disabled = !cat || approved;
  $('btn-revoke-cat').classList.toggle('hidden', !approved);

  if (!cat) {
    $('cat-metrics-inline').textContent = '';
    $('cat-static-warnings').classList.add('hidden');
    return;
  }

  const procs = cat.processes || [];
  const totalRules = procs.reduce((acc, p) => acc + (p.rules || []).length, 0);
  $('cat-metrics-inline').textContent = `${procs.length} processes · ${(cat.systems || []).length} systems · ${totalRules} rules · ${(cat.open_questions || []).length} open items`;

  const checks = state.data.static_checks || [];
  const warnBox = $('cat-static-warnings');
  if (checks.length) {
    warnBox.classList.remove('hidden');
    warnBox.innerHTML = `<strong>Static checks (${checks.length}):</strong> ${checks.slice(0, 4).map(escapeHtml).join(' · ')}${checks.length > 4 ? ` (+${checks.length - 4} more in Step 4)` : ''}`;
  } else {
    warnBox.classList.add('hidden');
  }

  if (state.selectedProcessIdx >= procs.length) state.selectedProcessIdx = Math.max(0, procs.length - 1);
  $('process-list').innerHTML = procs.map((p, i) => `
    <div class="list-item ${i === state.selectedProcessIdx ? 'active' : ''}" onclick="selectCatProcess(${i})" oncontextmenu="openItemContextMenu(event,'${escapeHtml(p.id)}','${escapeHtml(p.name)}',2)">
      <strong>${escapeHtml(p.id)} — ${escapeHtml(p.name)}</strong>
      <small>${(p.steps || []).length} steps · ${(p.rules || []).length} rules · ${escapeHtml(p.confidence)}</small>
    </div>
  `).join('');

  renderProcessEditorForm();
  renderCatContextEditor();
  $('cat-raw-json').value = JSON.stringify(cat, null, 2);
}

window.selectCatProcess = function (idx) {
  syncActiveProcessFormToDraft();
  state.selectedProcessIdx = idx;
  renderStep2();
  updateCommentBadges();
  if (!$('comments-drawer').classList.contains('hidden') && state.step === 2) {
    activeCommentScope = getScopeForStep(2);
    renderCommentsDrawer();
  }
};

function renderProcessEditorForm() {
  const pane = $('process-editor-pane');
  const procs = state.catalogueDraft.processes || [];
  const p = procs[state.selectedProcessIdx];
  if (!p) {
    pane.innerHTML = '<p class="muted">Click + Add to create a process.</p>';
    return;
  }

  const rulesHtml = (p.rules || []).map((r, ri) => `
    <div class="rule-row">
      <input type="text" data-rule-id="${ri}" value="${escapeHtml(r.id)}" placeholder="R-01" />
      <select data-rule-cls="${ri}">
        <option value="source_defined" ${r.classification === 'source_defined' ? 'selected' : ''}>source_defined</option>
        <option value="design_proposed" ${r.classification === 'design_proposed' ? 'selected' : ''}>design_proposed</option>
        <option value="unresolved" ${r.classification === 'unresolved' ? 'selected' : ''}>unresolved</option>
      </select>
      <input type="text" data-rule-stmt="${ri}" value="${escapeHtml(r.statement)}" placeholder="Rule statement..." />
      <button class="btn btn-xs btn-danger-outline" onclick="removeProcessRule(${ri})">✕</button>
    </div>
  `).join('');

  const evHtml = (p.evidence || []).map((e) =>
    `<div class="muted"><code>${escapeHtml(e.source_id)}</code> · <b>${escapeHtml(e.locator)}</b> — "${escapeHtml(e.quote)}"</div>`
  ).join('') || '<div class="muted">No source citations attached.</div>';

  pane.innerHTML = `
    <div style="max-width:980px;">
      <div class="row-between">
        <h3 style="margin:0;">${escapeHtml(p.id)} — ${escapeHtml(p.name)}</h3>
        <button class="btn btn-xs btn-danger-outline" onclick="deleteCurrentProcess()">Delete Process</button>
      </div>
      <div class="grid-2">
        <div><label class="field-label">Process ID</label><input id="pf-id" type="text" value="${escapeHtml(p.id)}" /></div>
        <div><label class="field-label">Confidence</label>
          <select id="pf-confidence">
            <option value="high" ${p.confidence === 'high' ? 'selected' : ''}>high</option>
            <option value="medium" ${p.confidence === 'medium' ? 'selected' : ''}>medium</option>
            <option value="low" ${p.confidence === 'low' ? 'selected' : ''}>low</option>
          </select>
        </div>
      </div>
      <label class="field-label">Name</label>
      <input id="pf-name" type="text" value="${escapeHtml(p.name)}" />
      <label class="field-label">Description</label>
      <textarea id="pf-desc" rows="2">${escapeHtml(p.description)}</textarea>
      <div class="grid-2">
        <div><label class="field-label">Trigger</label><input id="pf-trigger" type="text" value="${escapeHtml(p.trigger)}" /></div>
        <div><label class="field-label">Actors (comma separated)</label><input id="pf-actors" type="text" value="${escapeHtml((p.actors || []).join(', '))}" /></div>
      </div>
      <div class="grid-2">
        <div><label class="field-label">Ordered Steps (one per line)</label><textarea id="pf-steps" rows="6">${escapeHtml((p.steps || []).join('\n'))}</textarea></div>
        <div><label class="field-label">Exceptions (one per line)</label><textarea id="pf-exceptions" rows="6">${escapeHtml((p.exceptions || []).join('\n'))}</textarea></div>
      </div>
      <div class="grid-2">
        <div><label class="field-label">Messages / Touchpoints (one per line)</label><textarea id="pf-messages" rows="4">${escapeHtml((p.messages || []).join('\n'))}</textarea></div>
        <div><label class="field-label">Entities (one per line)</label><textarea id="pf-entities" rows="4">${escapeHtml((p.entities || []).join('\n'))}</textarea></div>
      </div>
      <div class="row-between" style="margin-top:10px;">
        <label class="field-label" style="margin:0;">Business Rules</label>
        <button class="btn btn-xs" onclick="addProcessRule()">+ Add Rule</button>
      </div>
      <div id="pf-rules-list" style="margin-top:6px;">${rulesHtml}</div>
      <label class="field-label">Open Questions (one per line)</label>
      <textarea id="pf-openq" rows="3">${escapeHtml((p.open_questions || []).join('\n'))}</textarea>
      <label class="field-label">Source Evidence Citations</label>
      <div class="alert-box">${evHtml}</div>
    </div>
  `;
}

function splitLines(v) {
  return v.split('\n').map((x) => x.trim()).filter(Boolean);
}

function syncActiveProcessFormToDraft() {
  if (!state.catalogueDraft) return;
  const p = (state.catalogueDraft.processes || [])[state.selectedProcessIdx];
  if (!p || !$('pf-id')) return;
  p.id = $('pf-id').value.trim() || p.id;
  p.name = $('pf-name').value.trim();
  p.confidence = $('pf-confidence').value;
  p.description = $('pf-desc').value.trim();
  p.trigger = $('pf-trigger').value.trim();
  p.actors = $('pf-actors').value.split(',').map((x) => x.trim()).filter(Boolean);
  p.steps = splitLines($('pf-steps').value);
  p.exceptions = splitLines($('pf-exceptions').value);
  p.messages = splitLines($('pf-messages').value);
  p.entities = splitLines($('pf-entities').value);
  p.open_questions = splitLines($('pf-openq').value);
  p.rules = (p.rules || []).map((r, ri) => ({
    ...r,
    id: document.querySelector(`[data-rule-id="${ri}"]`)?.value.trim() || r.id,
    classification: document.querySelector(`[data-rule-cls="${ri}"]`)?.value || r.classification,
    statement: document.querySelector(`[data-rule-stmt="${ri}"]`)?.value.trim() || '',
  })).filter((r) => r.statement);
}

window.addProcessRule = function () {
  syncActiveProcessFormToDraft();
  const p = state.catalogueDraft.processes[state.selectedProcessIdx];
  p.rules = p.rules || [];
  p.rules.push({ id: `R-${p.rules.length + 1}`, statement: '', classification: 'source_defined', evidence: [] });
  renderProcessEditorForm();
};

window.removeProcessRule = function (ri) {
  syncActiveProcessFormToDraft();
  state.catalogueDraft.processes[state.selectedProcessIdx].rules.splice(ri, 1);
  renderProcessEditorForm();
};

window.deleteCurrentProcess = function () {
  state.catalogueDraft.processes.splice(state.selectedProcessIdx, 1);
  state.selectedProcessIdx = Math.max(0, state.selectedProcessIdx - 1);
  renderStep2();
};

function renderCatContextEditor() {
  const cat = state.catalogueDraft;
  const box = $('cat-context-editor');
  const sysText = (cat.systems || []).map((s) => `${s.name} | ${s.responsibility} | ${s.ownership || ''}`).join('\n');
  const glossText = (cat.glossary || []).map((g) => `${g.term} : ${g.definition}`).join('\n');

  box.innerHTML = `
    <div class="card">
      <label class="field-label">Project Name</label>
      <input id="ctx-name" type="text" value="${escapeHtml(cat.project_name || '')}" />
      <label class="field-label">Project Summary</label>
      <textarea id="ctx-summary" rows="3">${escapeHtml(cat.project_summary || '')}</textarea>
      <label class="field-label">Shared Actors / Roles (one per line)</label>
      <textarea id="ctx-actors" rows="5">${escapeHtml((cat.shared_actors || []).join('\n'))}</textarea>
      <label class="field-label">Systems &amp; Ownership (Name | Responsibility | Ownership)</label>
      <textarea id="ctx-systems" rows="7">${escapeHtml(sysText)}</textarea>
    </div>
    <div class="card">
      <label class="field-label">Glossary / Abbreviations (Term : Definition)</label>
      <textarea id="ctx-glossary" rows="6">${escapeHtml(glossText)}</textarea>
      <label class="field-label">Non-Functional Requirements (one per line)</label>
      <textarea id="ctx-nfrs" rows="5">${escapeHtml((cat.nfrs || []).join('\n'))}</textarea>
      <label class="field-label">Out of Scope / Exclusions (one per line)</label>
      <textarea id="ctx-exclusions" rows="4">${escapeHtml((cat.exclusions || []).join('\n'))}</textarea>
      <label class="field-label">Project-Level Open Questions (one per line)</label>
      <textarea id="ctx-openq" rows="6">${escapeHtml((cat.open_questions || []).join('\n'))}</textarea>
    </div>
  `;
}

function syncContextFormToDraft() {
  const cat = state.catalogueDraft;
  if (!cat || !$('ctx-name')) return;
  cat.project_name = $('ctx-name').value.trim();
  cat.project_summary = $('ctx-summary').value.trim();
  cat.shared_actors = splitLines($('ctx-actors').value);
  cat.systems = splitLines($('ctx-systems').value).map((ln) => {
    const [name = '', responsibility = '', ownership = ''] = ln.split('|').map((x) => x.trim());
    return { name, responsibility, ownership };
  }).filter((s) => s.name);
  cat.glossary = splitLines($('ctx-glossary').value).map((ln) => {
    const [term, ...rest] = ln.split(':');
    return { term: (term || '').trim(), definition: rest.join(':').trim() };
  }).filter((g) => g.term);
  cat.nfrs = splitLines($('ctx-nfrs').value);
  cat.exclusions = splitLines($('ctx-exclusions').value);
  cat.open_questions = splitLines($('ctx-openq').value);
}

/* ==================== STEP 3: OPEN CANVAS STUDIO ==================== */
window.setCanvasMode = function (mode) {
  window.scrollTo(0, 0);
  state.canvasMode = mode;
  document.querySelectorAll('#canvas-mode-tabs .seg-btn').forEach((b) => {
    b.classList.toggle('active', b.dataset.cmode === mode);
  });
  ['map', 'word', 'split', 'diagram'].forEach((m) => {
    $(`cmode-${m}`).classList.toggle('hidden', m !== mode);
  });
  if (mode === 'map') {
    renderFlowsMapCanvas();
    setTimeout(() => mapPanZoom && mapPanZoom.fit(), 30);
  } else if (mode === 'diagram') {
    openFullCanvasDiagramEditor();
  }
};

function renderFlowsMapCanvas() {
  const board = $('flows-map-board');
  const procs = (state.data && state.data.catalogue && state.data.catalogue.processes) || [];
  const arts = (state.data && state.data.artifacts) || {};
  if (!procs.length) {
    board.innerHTML = '<div class="card">No processes extracted yet. Go to Step 1 to upload and extract a specification.</div>';
    return;
  }

  board.innerHTML = `<div class="flows-board-grid">${procs.map((p) => {
    const hasArt = !!arts[p.id];
    const active = p.id === state.activeArtProcessId;
    const steps = (p.steps || []).slice(0, 5);
    const stepsHtml = steps.map((s, idx) =>
      `<div class="fnc-step"><b>${idx + 1}.</b> ${escapeHtml(s.length > 78 ? s.slice(0, 78) + '…' : s)}</div>${idx < steps.length - 1 ? '<div class="fnc-arrow">↓</div>' : ''}`
    ).join('');
    return `
      <div class="flow-node-card ${hasArt ? 'has-art' : ''} ${active ? 'active' : ''}" oncontextmenu="openItemContextMenu(event,'${escapeHtml(p.id)}','${escapeHtml(p.name)}',3)">
        <div class="fnc-head">
          <span class="fnc-id">${escapeHtml(wfCode(p.id))}</span>
          <span class="fnc-status ${hasArt ? 'ok' : 'todo'}">${hasArt ? '✓ 4 Docs Ready' : 'Not Generated'}</span>
        </div>
        <div class="fnc-body">
          <div class="fnc-title">${escapeHtml(p.name)}</div>
          <div class="fnc-actors">${(p.actors || []).slice(0, 4).map((a) => `<span class="fnc-tag">${escapeHtml(a)}</span>`).join('')}</div>
          <div class="fnc-steps">${stepsHtml || '<div class="muted">No steps listed</div>'}</div>
          ${(p.steps || []).length > 5 ? `<small class="muted">+${p.steps.length - 5} more steps</small>` : ''}
        </div>
        <div class="fnc-foot">
          <button class="btn btn-xs btn-primary" onclick="openFlowInCanvas('${escapeHtml(p.id)}','word')">📄 Word</button>
          <button class="btn btn-xs btn-drawio" onclick="openFlowInCanvas('${escapeHtml(p.id)}','diagram')">📐 Edit Diagram</button>
        </div>
      </div>
    `;
  }).join('')}</div>`;
}

window.openFlowInCanvas = function (pid, mode) {
  state.activeArtProcessId = pid;
  renderArtifactStudio();
  setCanvasMode(mode);
};

function renderArtifactStudio() {
  const d = state.data;
  if (!d) return;
  const procs = (d.catalogue && d.catalogue.processes) || [];
  const arts = d.artifacts || {};
  const allowed = d.approvals.catalogue;

  $('step3-gate').classList.toggle('hidden', allowed);
  $('btn-generate-selected').disabled = !allowed || state.selectedWorkflowIds.size === 0;
  $('btn-regen-single-art').disabled = !allowed || !state.activeArtProcessId;
  if ($('btn-regen-batch-art')) $('btn-regen-batch-art').disabled = !allowed || state.selectedWorkflowIds.size === 0;
  if ($('regen-sel-count')) $('regen-sel-count').textContent = String(state.selectedWorkflowIds.size);
  $('selected-count-label').textContent = `(${state.selectedWorkflowIds.size}/${procs.length})`;

  const activeProc = procs.find((p) => p.id === state.activeArtProcessId);
  $('active-proc-chip').textContent = activeProc ? `${wfCode(activeProc.id)} · ${activeProc.name}` : 'Select a flow';

  // Left collapsible rail: checkboxes + flow selection + right-click context menu
  $('art-process-rail').innerHTML = procs.map((p) => {
    const hasArt = !!arts[p.id];
    const checked = state.selectedWorkflowIds.has(p.id);
    const active = p.id === state.activeArtProcessId;
    return `
      <div class="flow-item ${active ? 'active' : ''}" onclick="selectArtProcess('${escapeHtml(p.id)}')" oncontextmenu="openItemContextMenu(event,'${escapeHtml(p.id)}','${escapeHtml(p.name)}',3)">
        <input type="checkbox" ${checked ? 'checked' : ''} onclick="event.stopPropagation()" onchange="toggleWorkflowSelection('${escapeHtml(p.id)}', this.checked)" />
        <div class="flow-item-meta">
          <strong>${escapeHtml(wfCode(p.id))}</strong>
          <small>${escapeHtml(p.name)}</small>
        </div>
        <span class="flow-dot ${hasArt ? 'ready' : ''}" title="${hasArt ? '4 artifacts generated' : 'Not generated yet'}"></span>
      </div>
    `;
  }).join('');

  const art = arts[state.activeArtProcessId];
  const md = art ? (art[state.activeArtField] || '') : '';
  $('art-md-editor').value = md;
  const diagCtx = state.activeArtProcessId ? { processId: state.activeArtProcessId, kind: state.activeArtKind } : null;
  renderMarkdownToPaper(md, $('art-word-preview-full'), diagCtx);
  renderMarkdownToPaper(md, $('art-word-preview'), diagCtx);
  if ($('word-dirty-indicator')) $('word-dirty-indicator').textContent = 'Click anywhere in text to edit directly';
  updateCommentBadges();
  if (!$('comments-drawer').classList.contains('hidden') && state.step === 3) {
    activeCommentScope = getScopeForStep(3);
    renderCommentsDrawer();
  }
  if (state.canvasMode === 'map') renderFlowsMapCanvas();
  if (state.canvasMode === 'diagram') openFullCanvasDiagramEditor();
}

window.toggleWorkflowSelection = function (pid, checked) {
  if (checked) state.selectedWorkflowIds.add(pid);
  else state.selectedWorkflowIds.delete(pid);
  renderArtifactStudio();
};

window.selectArtProcess = function (pid) {
  state.activeArtProcessId = pid;
  renderArtifactStudio();
};

function applyMarkdownToolbar(textarea, action) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  const sel = textarea.value.slice(start, end) || 'Text';
  const templates = {
    h1: `\n# ${sel}\n`,
    h2: `\n## ${sel}\n`,
    h3: `\n### ${sel}\n`,
    bold: `**${sel}**`,
    italic: `*${sel}*`,
    ul: `\n- ${sel}\n- Item 2\n`,
    ol: `\n1. ${sel}\n2. Step 2\n`,
    table: `\n| Column 1 | Column 2 | Classification |\n| --- | --- | --- |\n| Value A | Value B | source_defined |\n`,
    callout: `\n> **Architectural Note:** ${sel}\n`,
    mermaid: `\n\`\`\`mermaid\nflowchart TD\n  A[Start] --> B[Validate]\n  B --> C[Complete]\n\`\`\`\n`,
  };
  textarea.setRangeText(templates[action] || sel, start, end, 'end');
  textarea.focus();
  textarea.dispatchEvent(new Event('input'));
}

/* ==================== STEP 4: QUALITY, BATCH RUNS & COMPARE ==================== */
function _processDefectSet(d) {
  const defective = new Set();
  const lines = [
    ...(d.static_checks || []),
    ...((d.quality && d.quality.critical) || []),
    ...((d.quality && d.quality.warnings) || []),
  ];
  const procs = (d.catalogue && d.catalogue.processes) || [];
  for (const p of procs) {
    if (lines.some((ln) => ln.includes(p.id))) defective.add(p.id);
  }
  return defective;
}

window.toggleQaSelection = function (pid, checked) {
  if (checked) state.qaSelectedIds.add(pid);
  else state.qaSelectedIds.delete(pid);
  renderQaBatchChips();
};

function renderQaBatchChips() {
  const d = state.data;
  if (!d) return;
  const procs = (d.catalogue && d.catalogue.processes) || [];
  const arts = d.artifacts || {};
  const defects = _processDefectSet(d);

  // Initialize default selection to all generated processes (or all processes if none generated)
  const validIds = new Set(procs.map((p) => p.id));
  for (const id of Array.from(state.qaSelectedIds)) {
    if (!validIds.has(id)) state.qaSelectedIds.delete(id);
  }
  if (state.qaSelectedIds.size === 0 && procs.length) {
    const genIds = procs.filter((p) => arts[p.id]).map((p) => p.id);
    (genIds.length ? genIds : procs.map((p) => p.id)).forEach((id) => state.qaSelectedIds.add(id));
  }

  $('qa-batch-count').textContent = `(${state.qaSelectedIds.size} of ${procs.length} selected)`;
  $('qa-batch-chips').innerHTML = procs.map((p) => {
    const hasArt = !!arts[p.id];
    const hasDef = defects.has(p.id);
    const checked = state.qaSelectedIds.has(p.id);
    const cls = hasDef ? 'warn' : hasArt ? 'ok' : '';
    const icon = hasDef ? '⚠' : hasArt ? '✓' : '○';
    return `
      <label class="qa-chip ${cls}" title="${escapeHtml(p.name)}">
        <input type="checkbox" ${checked ? 'checked' : ''} onchange="toggleQaSelection('${escapeHtml(p.id)}', this.checked)" />
        <span><b>${escapeHtml(p.id)}</b> ${icon}</span>
      </label>
    `;
  }).join('');
}

function renderQualityStep() {
  const d = state.data;
  if (!d) return;
  const procs = (d.catalogue && d.catalogue.processes) || [];
  const arts = d.artifacts || {};
  const artIds = Object.keys(arts);
  const approved = d.approvals.artifacts;

  renderQaBatchChips();

  const badge = $('art-approval-badge');
  badge.textContent = approved ? '✓ Approved' : 'Not Approved';
  badge.className = `status-pill ${approved ? 'pill-ok' : 'pill-warn'}`;
  $('btn-revoke-arts').classList.toggle('hidden', !approved);
  $('btn-run-qa').disabled = artIds.length === 0;
  $('qa-coverage-summary').textContent = `(${artIds.length} of ${procs.length} workflows generated)`;

  const checks = d.static_checks || [];
  const sbox = $('qa-static-box');
  if (checks.length) {
    sbox.className = 'alert-box warn';
    sbox.innerHTML = `<strong>Deterministic Checks (${checks.length}):</strong><ul>${checks.map((c) => `<li>${escapeHtml(c)}</li>`).join('')}</ul>`;
  } else {
    sbox.className = 'alert-box hidden';
  }

  const q = d.quality;
  const view = $('qa-report-view');
  if (!q) {
    view.innerHTML = '<p class="muted">Click <b>🔍 Run AI + Deterministic QA</b> to check cross-artifact consistency, exceptions, and coverage.</p>';
  } else {
    const listBlock = (title, arr) => arr && arr.length
      ? `<h4>${title} (${arr.length})</h4><ul>${arr.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`
      : '';
    view.innerHTML = `
      <div class="qa-score">
        <div class="qa-score-num">${q.score}/100</div>
        <div><strong>Quality Assessment</strong><div class="muted">${escapeHtml(q.summary || '')}</div></div>
      </div>
      ${listBlock('Critical Defects', q.critical)}
      ${listBlock('Warnings', q.warnings)}
      ${listBlock('Coverage Gaps', q.coverage_gaps)}
      ${listBlock('Model Discrepancies', q.model_issues)}
      ${listBlock('Recommendations', q.recommendations)}
    `;
  }

  const keySel = $('compare-key-select');
  const prevKey = keySel.value;
  keySel.innerHTML = (d.revision_keys || []).map((k) => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
  if (prevKey && (d.revision_keys || []).includes(prevKey)) keySel.value = prevKey;

  const artSel = $('compare-art-select');
  const artOpts = [];
  artIds.forEach((pid) => {
    ['workflow_md', 'boundaries_md', 'domain_md', 'states_md'].forEach((f) => {
      artOpts.push({ id: `${pid}::${f}`, label: `${pid} — ${f.replace('_md', '')}` });
    });
  });
  artSel.innerHTML = artOpts.map((o) => `<option value="${escapeHtml(o.id)}">${escapeHtml(o.label)}</option>`).join('');

  const srcSel = $('compare-src-select');
  const srcOpts = [];
  (d.sources || []).forEach((s, si) => {
    (s.chunks || []).forEach((ch, ci) => {
      srcOpts.push({ id: `${si}:${ci}`, label: `${s.filename} — ${ch.locator}`, text: ch.text });
    });
  });
  srcSel.innerHTML = srcOpts.map((o) => `<option value="${o.id}">${escapeHtml(o.label)}</option>`).join('');

  const updateCompareSource = () => {
    const [pid, field] = (artSel.value || '').split('::');
    const md = (arts[pid] && arts[pid][field]) || '';
    const ctx = pid && field ? { processId: pid, kind: field.replace('_md', '') } : null;
    renderMarkdownToPaper(md, $('compare-art-pane'), ctx);
    const chosen = srcOpts.find((o) => o.id === srcSel.value);
    $('compare-src-pane').textContent = chosen ? chosen.text : '';
  };
  artSel.onchange = updateCompareSource;
  srcSel.onchange = updateCompareSource;
  if (artOpts.length || srcOpts.length) updateCompareSource();
  updateApproveArtsButton();
}

function updateApproveArtsButton() {
  const d = state.data;
  if (!d) return;
  const hasArts = Object.keys(d.artifacts || {}).length > 0;
  $('btn-approve-arts').disabled = !(hasArts && d.approvals.catalogue && $('chk-human-ack').checked);
}

async function loadCompareRevisions() {
  const key = $('compare-key-select').value;
  if (!key) return;
  const res = await api(`/api/projects/${encodeURIComponent(state.project)}/revisions/${encodeURIComponent(key)}`);
  const revs = res.revisions || [];
  const opts = revs.map((r) => `<option value="${escapeHtml(r.id)}">${escapeHtml(r.id.slice(0, 15))} (${escapeHtml(r.reason.slice(0, 28))})</option>`).join('');
  $('compare-rev-a').innerHTML = opts;
  $('compare-rev-b').innerHTML = opts;
  if (revs.length >= 2) {
    $('compare-rev-a').value = revs[1].id;
    $('compare-rev-b').value = revs[0].id;
    await loadDiffOutput();
  } else {
    $('compare-diff-output').textContent = `Only ${revs.length} revision exists for "${key}".`;
  }
}

async function loadDiffOutput() {
  const key = $('compare-key-select').value;
  const revA = $('compare-rev-a').value;
  const revB = $('compare-rev-b').value;
  if (!key || !revA || !revB) return;
  const res = await api(`/api/projects/${encodeURIComponent(state.project)}/diff/${encodeURIComponent(key)}?rev_a=${encodeURIComponent(revA)}&rev_b=${encodeURIComponent(revB)}`);
  renderColoredDiff(res.diff, $('compare-diff-output'));
}

/* ==================== STEP 5: FOUNDATION ==================== */
function renderFoundationStep() {
  const d = state.data;
  if (!d) return;
  const allowed = d.approvals.artifacts;
  const approved = d.approvals.foundation;
  $('step5-gate').classList.toggle('hidden', allowed);
  $('btn-gen-foundation').disabled = !allowed;
  $('btn-approve-found').disabled = !d.foundation || approved;
  const badge = $('found-approval-badge');
  badge.textContent = approved ? '✓ Approved' : 'Not Approved';
  badge.className = `status-pill ${approved ? 'pill-ok' : 'pill-warn'}`;

  const md = (d.foundation && d.foundation[state.activeFoundField]) || '';
  $('found-md-editor').value = md;
  renderMarkdownToPaper(md, $('found-word-preview-full'));
  renderMarkdownToPaper(md, $('found-word-preview'));
  $('found-word-stage').classList.toggle('hidden', state.foundView !== 'word');
  $('found-split-stage').classList.toggle('hidden', state.foundView !== 'split');
}

/* ==================== STEP 6: PLAN & IMPLEMENT ==================== */
function renderPlanningStep() {
  const d = state.data;
  if (!d) return;
  const approved = d.approvals.planning;
  $('btn-gen-planning').disabled = !d.approvals.foundation;
  $('btn-approve-plan').disabled = !d.planning || approved;
  $('btn-export-speckit').disabled = !d.foundation;
  $('btn-gen-code').disabled = !approved;
  const badge = $('plan-approval-badge');
  badge.textContent = approved ? '✓ Approved' : 'Not Approved';
  badge.className = `status-pill ${approved ? 'pill-ok' : 'pill-warn'}`;

  const isCode = state.activePlanMode === 'code';
  $('plan-view-toggle').classList.toggle('hidden', isCode);
  $('tech-pref-bar').classList.toggle('hidden', isCode);
  $('plan-code-stage').classList.toggle('hidden', !isCode);
  $('plan-word-stage').classList.toggle('hidden', isCode || state.planView !== 'word');
  $('plan-split-stage').classList.toggle('hidden', isCode || state.planView !== 'split');

  if (!isCode) {
    const md = (d.planning && d.planning[state.activePlanMode]) || '';
    $('plan-md-editor').value = md;
    renderMarkdownToPaper(md, $('plan-word-preview-full'));
    renderMarkdownToPaper(md, $('plan-word-preview'));
  }

  const cp = d.code_proposal;
  $('code-proposal-viewer').classList.toggle('hidden', !cp);
  if (cp) {
    $('code-notes').textContent = cp.notes || 'Proposed files ready for review.';
    const files = Object.keys(cp.files || {});
    if (!state.activeCodeFile || !cp.files[state.activeCodeFile]) state.activeCodeFile = files[0] || null;
    $('code-file-list').innerHTML = files.map((f) => `
      <div class="list-item ${f === state.activeCodeFile ? 'active' : ''}" onclick="selectCodeFile('${escapeHtml(f)}')">
        <strong>${escapeHtml(f)}</strong>
      </div>
    `).join('');
    $('code-active-path').textContent = state.activeCodeFile || 'No files';
    $('code-active-content').textContent = state.activeCodeFile ? cp.files[state.activeCodeFile] : '';
  }
}

window.selectCodeFile = function (path) {
  state.activeCodeFile = path;
  renderPlanningStep();
};

/* ==================== WORD (.DOCX) DOWNLOAD ==================== */
async function downloadSingleDocx(title, markdown, subtitle = '') {
  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(state.project)}/export/docx-single`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, subtitle, markdown }),
    });
    if (!res.ok) throw new Error('Export failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${title.replace(/[^a-z0-9_-]+/gi, '-')}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    toast(e.message, 'err');
  }
}

/* ==================== GIT REPOSITORY SYNC MODAL ==================== */
async function refreshGitBadge() {
  try {
    const st = await api(`/api/projects/${encodeURIComponent(state.project)}/git/status`);
    const dot = $('git-badge');
    if (!dot) return;
    if (!st.initialized) {
      dot.classList.add('hidden');
      $('btn-git').title = 'Connect project to a Git repository';
    } else {
      dot.classList.remove('hidden');
      const dirty = (st.changed_files || []).length > 0;
      dot.classList.toggle('dirty', dirty);
      $('btn-git').title = `Git (${st.branch}${st.remote_url ? ' · ' + st.remote_url : ' · local only'})${dirty ? ` — ${st.changed_files.length} uncommitted change(s)` : ' — clean'}`;
    }
    return st;
  } catch (_) {
    return null;
  }
}

async function openGitModal() {
  $('git-modal').classList.remove('hidden');
  $('git-action-output').classList.add('hidden');
  await refreshGitModal();
}

async function refreshGitModal() {
  const st = await refreshGitBadge();
  if (!st) return;
  $('git-local-path').innerHTML = `Local workspace copy: <code>${escapeHtml(st.local_path)}</code> · Status: <b>${st.initialized ? `Git initialized on branch "${escapeHtml(st.branch)}"` : 'Not initialized yet'}</b>`;
  if (st.remote_url) $('git-remote-url').value = st.remote_url;
  $('git-branch').value = st.branch || 'main';

  const changed = st.changed_files || [];
  $('git-changed-count').textContent = `(${changed.length})`;
  $('git-changed-list').innerHTML = changed.length
    ? changed.map((f) => `<div class="list-item" style="padding:5px 8px;"><code>${escapeHtml(f.status)}</code> ${escapeHtml(f.path)}</div>`).join('')
    : '<p class="muted" style="padding:6px;">Working tree clean — no uncommitted changes.</p>';

  const commits = st.recent_commits || [];
  $('git-commits-list').innerHTML = commits.length
    ? commits.map((c) => `<div class="list-item" style="padding:6px 8px;"><strong><code>${escapeHtml(c.hash)}</code> ${escapeHtml(c.message)}</strong><small>${escapeHtml(c.author)} · ${escapeHtml(c.date)}</small></div>`).join('')
    : '<p class="muted" style="padding:6px;">No commits yet.</p>';
}

/* ==================== VERSION HISTORY MODAL ==================== */
async function openHistoryModal() {
  const sel = $('history-key-select');
  sel.innerHTML = (state.data.revision_keys || []).map((k) => `<option value="${escapeHtml(k)}">${escapeHtml(k)}</option>`).join('');
  $('history-modal').classList.remove('hidden');
  await refreshHistoryModal();
}

async function refreshHistoryModal() {
  const key = $('history-key-select').value;
  if (!key) return;
  const [revsRes, diffRes] = await Promise.all([
    api(`/api/projects/${encodeURIComponent(state.project)}/revisions/${encodeURIComponent(key)}`),
    api(`/api/projects/${encodeURIComponent(state.project)}/diff/${encodeURIComponent(key)}`),
  ]);
  const revs = revsRes.revisions || [];
  $('history-rev-list').innerHTML = revs.length
    ? revs.map((r) => `
      <div class="list-item">
        <div class="row-between">
          <strong>${escapeHtml(r.id)}</strong>
          <button class="btn btn-xs" onclick="restoreHistoricalRevision('${escapeHtml(key)}','${escapeHtml(r.id)}')">Restore</button>
        </div>
        <small>${escapeHtml(r.reason)}</small>
      </div>
    `).join('')
    : '<p class="muted" style="padding:12px;">No revisions yet.</p>';
  renderColoredDiff(diffRes.diff, $('history-diff-view'), $('history-diff-stats'));
}

window.restoreHistoricalRevision = async function (key, revId) {
  try {
    await api(`/api/projects/${encodeURIComponent(state.project)}/revisions/${encodeURIComponent(key)}/restore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ revision_id: revId }),
    });
    toast(`Restored ${key} to ${revId}`, 'ok');
    await refreshState();
    await refreshHistoryModal();
  } catch (e) {
    toast(e.message, 'err');
  }
};

/* ==================== EVENT WIRING ==================== */
function wireEvents() {
  document.querySelectorAll('.wstep').forEach((btn) => {
    btn.onclick = () => goStep(Number(btn.dataset.step));
  });

  $('project-select').onchange = async (e) => {
    state.project = e.target.value;
    localStorage.setItem('ae_project', state.project);
    state.selectedWorkflowIds.clear();
    state.activeArtProcessId = null;
    await refreshState();
  };
  $('btn-new-project-prompt').onclick = async () => {
    const name = window.prompt('Enter new or existing project workspace name:');
    if (!name || !name.trim()) return;
    state.project = name.trim();
    localStorage.setItem('ae_project', state.project);
    state.selectedWorkflowIds.clear();
    state.activeArtProcessId = null;
    await loadProjects();
    await refreshState();
    toast(`Opened workspace "${state.project}"`, 'ok');
  };

  $('import-project-zip-input').onchange = async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    setBusy(true, 'Opening project ZIP...', file.name);
    try {
      const res = await api('/api/projects/import-zip', { method: 'POST', body: fd });
      state.project = res.project_slug;
      localStorage.setItem('ae_project', state.project);
      state.selectedWorkflowIds.clear();
      state.activeArtProcessId = null;
      await loadProjects();
      await refreshState();
      toast(`Loaded project "${res.project_slug}" (${res.files_imported} files)`, 'ok');
    } catch (err) {
      toast(`Import failed: ${err.message}`, 'err');
    } finally {
      setBusy(false);
    }
  };

  $('btn-export-project-zip').onclick = () => {
    window.location.href = `/api/projects/${encodeURIComponent(state.project)}/export/zip`;
  };

  // Step 1
  const dz = $('dropzone');
  $('file-input').onchange = (e) => uploadFiles(e.target.files);
  dz.ondragover = (e) => { e.preventDefault(); dz.classList.add('dragover'); };
  dz.ondragleave = () => dz.classList.remove('dragover');
  dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove('dragover'); uploadFiles(e.dataTransfer.files); };

  $('btn-load-sample').onclick = async () => {
    setBusy(true, 'Loading sample_document.pdf...', 'Parsing CLEP OCD with table-aware extractor');
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/sources/load-example`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: 'sample_document.pdf' }),
      });
      toast('Loaded examples/sample_document.pdf (CLEP OCD)', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };

  $('btn-extract').onclick = async () => {
    setBusy(true, 'Extracting process catalogue...', `Using ${state.cfg.provider} (${state.cfg.model})`);
    try {
      const out = await api(`/api/projects/${encodeURIComponent(state.project)}/extract`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llmPayload(), feedback: $('extract-feedback').value }),
      });
      toast(`Extracted ${out.processes.length} processes!`, 'ok');
      await refreshState();
      goStep(2);
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };

  // Step 2
  document.querySelectorAll('[data-cattab]').forEach((btn) => {
    btn.onclick = () => {
      syncActiveProcessFormToDraft();
      syncContextFormToDraft();
      document.querySelectorAll('[data-cattab]').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.cat-subpanel').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      $(`cattab-${btn.dataset.cattab}`).classList.add('active');
      if (btn.dataset.cattab === 'json') $('cat-raw-json').value = JSON.stringify(state.catalogueDraft, null, 2);
    };
  });

  $('btn-save-prefix-step1').onclick = () => applyProjectPrefix($('prefix-input-step1').value);
  $('btn-save-prefix-step2').onclick = () => applyProjectPrefix($('prefix-input-step2').value);
  $('prefix-input-step1').addEventListener('input', (e) => {
    const px = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '') || 'PRJ';
    $('prefix-preview-step1').textContent = `IDs: ${px}-CA-001 (Catalogue) · ${px}-WF-001 (Work Flows) · ${px}-SC-001 (SC)`;
  });

  $('btn-add-process').onclick = () => {
    syncActiveProcessFormToDraft();
    const procs = state.catalogueDraft.processes;
    procs.push({
      id: `${currentPrefix()}-CA-${String(procs.length + 1).padStart(3, '0')}`,
      name: 'New Process', description: '', actors: [], trigger: '', inputs: [], outputs: [],
      steps: [], exceptions: [], messages: [], entities: [], rules: [],
      open_questions: [], evidence: [], confidence: 'medium',
    });
    state.selectedProcessIdx = procs.length - 1;
    renderStep2();
  };

  $('btn-save-catalogue').onclick = async () => {
    try {
      const activeTab = document.querySelector('[data-cattab].active')?.dataset.cattab;
      let payload;
      if (activeTab === 'json') payload = JSON.parse($('cat-raw-json').value);
      else { syncActiveProcessFormToDraft(); syncContextFormToDraft(); payload = state.catalogueDraft; }
      await api(`/api/projects/${encodeURIComponent(state.project)}/catalogue`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ catalogue: payload, note: $('cat-save-note').value || 'catalogue edited' }),
      });
      $('cat-save-note').value = '';
      toast('Catalogue revision saved', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); }
  };

  $('btn-approve-cat').onclick = async () => {
    await api(`/api/projects/${encodeURIComponent(state.project)}/approve/catalogue`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: true }),
    });
    toast('Catalogue approved!', 'ok');
    await refreshState();
  };
  $('btn-revoke-cat').onclick = async () => {
    await api(`/api/projects/${encodeURIComponent(state.project)}/approve/catalogue`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: false }),
    });
    toast('Catalogue approval revoked', 'ok');
    await refreshState();
  };

  // Step 3: Open Canvas Studio
  $('btn-toggle-rail').onclick = () => {
    $('studio-canvas-shell').classList.toggle('rail-collapsed');
  };
  $('btn-toggle-regen-pop').onclick = () => $('regen-popover').classList.toggle('hidden');
  $('btn-close-regen').onclick = () => $('regen-popover').classList.add('hidden');

  document.querySelectorAll('#art-doc-tabs .seg-btn').forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll('#art-doc-tabs .seg-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeArtField = btn.dataset.artfield;
      state.activeArtKind = btn.dataset.kind;
      renderArtifactStudio();
    };
  });

  document.querySelectorAll('#canvas-mode-tabs .seg-btn').forEach((btn) => {
    btn.onclick = () => setCanvasMode(btn.dataset.cmode);
  });

  $('btn-select-all-wf').onclick = () => {
    ((state.data.catalogue && state.data.catalogue.processes) || []).forEach((p) => state.selectedWorkflowIds.add(p.id));
    renderArtifactStudio();
  };
  $('btn-select-missing-wf').onclick = () => {
    state.selectedWorkflowIds.clear();
    const arts = state.data.artifacts || {};
    ((state.data.catalogue && state.data.catalogue.processes) || []).forEach((p) => {
      if (!arts[p.id]) state.selectedWorkflowIds.add(p.id);
    });
    renderArtifactStudio();
  };

  async function runStep3Batch(ids, feedbackText = '', verb = 'Generating') {
    if (!ids.length) return;
    state.step3BatchStop = false;
    $('batch-progress').classList.remove('hidden');
    $('btn-regen-stop').classList.remove('hidden');
    let okCount = 0;
    for (let i = 0; i < ids.length; i++) {
      if (state.step3BatchStop) break;
      const pid = ids[i];
      $('batch-progress-bar').style.width = `${Math.round((i / ids.length) * 100)}%`;
      $('batch-progress-text').textContent = `${verb} ${pid} (${i + 1}/${ids.length})...`;
      try {
        await api(`/api/projects/${encodeURIComponent(state.project)}/artifacts/generate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ llm: llmPayload(), process_id: pid, feedback: feedbackText }),
        });
        okCount++;
        state.activeArtProcessId = pid;
        await refreshState();
      } catch (e) {
        toast(`Failed on ${pid}: ${e.message}`, 'err');
        break;
      }
    }
    $('btn-regen-stop').classList.add('hidden');
    $('batch-progress-bar').style.width = '100%';
    $('batch-progress-text').textContent = state.step3BatchStop ? `Stopped (${okCount}/${ids.length})` : `Done: ${okCount}/${ids.length}`;
    if (okCount) toast(`${verb} finished for ${okCount} workflow(s)`, 'ok');
  }

  $('btn-regen-stop').onclick = () => {
    state.step3BatchStop = true;
    toast('Stopping after current workflow completes...');
  };

  $('btn-generate-selected').onclick = () => runStep3Batch(Array.from(state.selectedWorkflowIds), '', 'Generating');

  $('btn-regen-batch-art').onclick = async () => {
    const ids = Array.from(state.selectedWorkflowIds);
    const fb = $('art-regen-feedback').value.trim();
    await runStep3Batch(ids, fb, 'Regenerating');
    $('art-regen-feedback').value = '';
  };

  $('btn-regen-single-art').onclick = async () => {
    if (!state.activeArtProcessId) return;
    setBusy(true, `Regenerating ${state.activeArtProcessId}...`);
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/artifacts/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llmPayload(), process_id: state.activeArtProcessId, feedback: $('art-regen-feedback').value }),
      });
      $('art-regen-feedback').value = '';
      $('regen-popover').classList.add('hidden');
      toast(`Regenerated ${state.activeArtProcessId}`, 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };

  document.querySelectorAll('.ribbon-btn[data-md]').forEach((btn) => {
    btn.onclick = () => applyMarkdownToolbar($('art-md-editor'), btn.dataset.md);
  });

  let previewTimer;
  $('art-md-editor').addEventListener('input', () => {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(() => {
      renderMarkdownToPaper($('art-md-editor').value, $('art-word-preview'));
      renderMarkdownToPaper($('art-md-editor').value, $('art-word-preview-full'));
    }, 200);
  });

  $('art-word-preview-full').addEventListener('input', () => {
    $('word-dirty-indicator').textContent = 'Unsaved edits — click 💾 Save Text Edits';
  });

  async function uploadAndInsertImage(file, mode = 'word') {
    if (!file || !file.type.startsWith('image/')) return;
    const fd = new FormData();
    fd.append('file', file, file.name || 'pasted-image.png');
    try {
      const res = await api(`/api/projects/${encodeURIComponent(state.project)}/assets/upload`, {
        method: 'POST',
        body: fd,
      });
      const caption = (file.name || 'Image').replace(/\.[^.]+$/, '');
      if (mode === 'split') {
        const ta = $('art-md-editor');
        const snippet = `\n![${caption}](${res.url})\n`;
        ta.setRangeText(snippet, ta.selectionStart, ta.selectionEnd, 'end');
        ta.dispatchEvent(new Event('input'));
      } else {
        const paper = $('art-word-preview-full');
        const imgHtml = `<p><img src="${escapeHtml(res.url)}" alt="${escapeHtml(caption)}" /></p>`;
        paper.focus();
        if (!document.execCommand('insertHTML', false, imgHtml)) {
          paper.insertAdjacentHTML('beforeend', imgHtml);
        }
        $('word-dirty-indicator').textContent = 'Image inserted — click 💾 Save Text Edits';
      }
      toast(`Inserted image "${caption}" — click Save to persist in document`, 'ok');
    } catch (e) {
      toast(`Image upload failed: ${e.message}`, 'err');
    }
  }

  $('word-insert-img-input').onchange = (e) => {
    if (e.target.files[0]) uploadAndInsertImage(e.target.files[0], 'word');
    e.target.value = '';
  };
  $('split-insert-img-input').onchange = (e) => {
    if (e.target.files[0]) uploadAndInsertImage(e.target.files[0], 'split');
    e.target.value = '';
  };
  // Paste image directly (Cmd+V) or drag-drop image onto the Word paper!
  $('art-word-preview-full').addEventListener('paste', (e) => {
    const items = (e.clipboardData && e.clipboardData.items) || [];
    for (const item of items) {
      if (item.type && item.type.startsWith('image/')) {
        e.preventDefault();
        uploadAndInsertImage(item.getAsFile(), 'word');
        return;
      }
    }
  });
  $('art-word-preview-full').addEventListener('dragover', (e) => {
    if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) e.preventDefault();
  });
  $('art-word-preview-full').addEventListener('drop', (e) => {
    const files = (e.dataTransfer && e.dataTransfer.files) || [];
    const img = Array.from(files).find((f) => f.type && f.type.startsWith('image/'));
    if (img) {
      e.preventDefault();
      uploadAndInsertImage(img, 'word');
    }
  });

  $('btn-save-word-direct').onclick = async () => {
    if (!state.activeArtProcessId) return;
    const md = wordPaperToMarkdown($('art-word-preview-full'));
    $('art-md-editor').value = md;
    const cur = structuredClone((state.data.artifacts || {})[state.activeArtProcessId] || {
      process_id: state.activeArtProcessId, workflow_md: '', boundaries_md: '', domain_md: '', states_md: '', findings: [],
    });
    cur[state.activeArtField] = md;
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/artifacts/${encodeURIComponent(state.activeArtProcessId)}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artifact: cur, note: `direct Word edit on ${state.activeArtKind}` }),
      });
      $('word-dirty-indicator').textContent = '✓ Saved!';
      toast('Saved Word text edits as new revision', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); }
  };

  $('btn-word-comment-sel').onclick = () => {
    const sel = (window.getSelection() ? window.getSelection().toString() : '').trim();
    openCommentsForScope(getScopeForStep(3), sel);
  };
  $('btn-word-ai-review').onclick = () => {
    openCommentsForScope(getScopeForStep(3));
    $('btn-cd-ai-review').click();
  };

  $('btn-cat-comments').onclick = () => openCommentsForScope(getScopeForStep(2));
  $('btn-art-comments').onclick = () => openCommentsForScope(getScopeForStep(3));
  $('btn-found-comments').onclick = () => openCommentsForScope(getScopeForStep(5));
  $('btn-plan-comments').onclick = () => openCommentsForScope(getScopeForStep(6));
  $('btn-comments-close').onclick = () => $('comments-drawer').classList.add('hidden');
  $('btn-cd-clear-quote').onclick = () => { pendingCommentQuote = ''; renderCommentsDrawer(); };

  $('btn-cd-add').onclick = async () => {
    const text = $('cd-input').value.trim();
    if (!text) return toast('Write a comment first.', 'err');
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/comments`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_key: activeCommentScope.key, text, quote: pendingCommentQuote }),
      });
      $('cd-input').value = '';
      pendingCommentQuote = '';
      toast('Comment added', 'ok');
      await refreshState();
      renderCommentsDrawer();
    } catch (e) { toast(e.message, 'err'); }
  };

  $('btn-cd-ai-review').onclick = async () => {
    if (!activeCommentScope.key) return;
    setBusy(true, 'AI reviewing this item...', activeCommentScope.label);
    try {
      const res = await api(`/api/projects/${encodeURIComponent(state.project)}/review-item`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llmPayload(), target_key: activeCommentScope.key, extra_feedback: $('cd-input').value.trim() }),
      });
      toast(`AI Review posted (${res.review.verdict})`, 'ok');
      await refreshState();
      renderCommentsDrawer();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };

  $('btn-cd-ai-rerun').onclick = async () => {
    if (!activeCommentScope.key) return;
    setBusy(true, 'Rerunning small scope with open comments...', activeCommentScope.label);
    try {
      const res = await api(`/api/projects/${encodeURIComponent(state.project)}/rerun-item`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llmPayload(), target_key: activeCommentScope.key, extra_feedback: $('cd-input').value.trim() }),
      });
      $('cd-input').value = '';
      toast(res.summary || 'Scope updated with comments!', 'ok');
      await refreshState();
      renderCommentsDrawer();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };

  $('btn-save-art').onclick = async () => {
    if (!state.activeArtProcessId) return;
    const cur = structuredClone((state.data.artifacts || {})[state.activeArtProcessId] || {
      process_id: state.activeArtProcessId, workflow_md: '', boundaries_md: '', domain_md: '', states_md: '', findings: [],
    });
    cur[state.activeArtField] = $('art-md-editor').value;
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/artifacts/${encodeURIComponent(state.activeArtProcessId)}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artifact: cur, note: $('art-save-note').value || `edited ${state.activeArtField}` }),
      });
      $('art-save-note').value = '';
      toast('Saved document revision', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); }
  };

  $('btn-download-drawio').onclick = () => {
    if (!state.activeArtProcessId) return;
    window.location.href = `/api/projects/${encodeURIComponent(state.project)}/diagrams/${encodeURIComponent(state.activeArtProcessId)}/${state.activeArtKind}/download`;
  };
  $('btn-reset-drawio').onclick = async () => {
    if (!state.activeArtProcessId) return;
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/diagrams/${encodeURIComponent(state.activeArtProcessId)}/${state.activeArtKind}/reset`, { method: 'POST' });
      toast('Diagram reset from Mermaid source', 'ok');
      await refreshState();
      if (state.canvasMode === 'diagram') await openFullCanvasDiagramEditor();
    } catch (e) { toast(e.message, 'err'); }
  };
  $('upload-drawio-input').onchange = async (e) => {
    const file = e.target.files[0];
    if (!file || !state.activeArtProcessId) return;
    const xml = await file.text();
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/diagrams/${encodeURIComponent(state.activeArtProcessId)}/${state.activeArtKind}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ xml, note: `imported ${file.name}` }),
      });
      toast(`Imported ${file.name}`, 'ok');
      await refreshState();
      if (state.canvasMode === 'diagram') await openFullCanvasDiagramEditor();
    } catch (err) { toast(err.message, 'err'); }
  };
  $('btn-download-art-docx').onclick = () => {
    const title = `${state.activeArtProcessId || 'Artifact'}-${state.activeArtKind}`;
    downloadSingleDocx(title, $('art-md-editor').value, `Project: ${state.project}`);
  };

  // Step 4: QA & Batch Runs
  $('btn-qa-sel-all').onclick = () => {
    ((state.data.catalogue && state.data.catalogue.processes) || []).forEach((p) => state.qaSelectedIds.add(p.id));
    renderQaBatchChips();
  };
  $('btn-qa-sel-gen').onclick = () => {
    state.qaSelectedIds.clear();
    const arts = state.data.artifacts || {};
    ((state.data.catalogue && state.data.catalogue.processes) || []).forEach((p) => { if (arts[p.id]) state.qaSelectedIds.add(p.id); });
    renderQaBatchChips();
  };
  $('btn-qa-sel-defects').onclick = () => {
    state.qaSelectedIds.clear();
    for (const id of _processDefectSet(state.data)) state.qaSelectedIds.add(id);
    renderQaBatchChips();
  };
  $('btn-qa-sel-missing').onclick = () => {
    state.qaSelectedIds.clear();
    const arts = state.data.artifacts || {};
    ((state.data.catalogue && state.data.catalogue.processes) || []).forEach((p) => { if (!arts[p.id]) state.qaSelectedIds.add(p.id); });
    renderQaBatchChips();
  };
  $('btn-batch-stop').onclick = () => {
    state.qaBatchStop = true;
    toast('Stopping after current workflow finishes...');
  };

  function setQaBatchProgress(active, pct = 0, text = '') {
    $('qa-batch-progress').classList.toggle('hidden', !active && !text);
    $('btn-batch-stop').classList.toggle('hidden', !active);
    $('qa-batch-progress-bar').style.width = `${pct}%`;
    $('qa-batch-progress-text').textContent = text;
  }

  $('btn-batch-qa').onclick = async () => {
    const arts = state.data.artifacts || {};
    const ids = Array.from(state.qaSelectedIds).filter((id) => arts[id]);
    if (!ids.length) return toast('Select at least one generated workflow for Batch Deep QA.', 'err');
    state.qaBatchStop = false;
    const reports = [];
    for (let i = 0; i < ids.length; i++) {
      if (state.qaBatchStop) break;
      const pid = ids[i];
      setQaBatchProgress(true, Math.round((i / ids.length) * 100), `Deep QA on ${pid} (${i + 1}/${ids.length})...`);
      try {
        const rep = await api(`/api/projects/${encodeURIComponent(state.project)}/assess`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ llm: llmPayload(), feedback: $('qa-feedback').value, process_ids: [pid] }),
        });
        reports.push({ pid, rep });
      } catch (e) {
        toast(`Deep QA failed on ${pid}: ${e.message}`, 'err');
        break;
      }
    }
    if (reports.length) {
      const avgScore = Math.round(reports.reduce((a, r) => a + (r.rep.score || 0), 0) / reports.length);
      const uniq = (arr) => Array.from(new Set(arr));
      const merged = {
        score: avgScore,
        summary: `Batch Deep QA completed across ${reports.length} workflow(s): ` + reports.map((r) => `${r.pid}=${r.rep.score}`).join(', '),
        critical: uniq(reports.flatMap((r) => r.rep.critical || [])),
        warnings: uniq(reports.flatMap((r) => r.rep.warnings || [])),
        coverage_gaps: uniq(reports.flatMap((r) => r.rep.coverage_gaps || [])),
        model_issues: uniq(reports.flatMap((r) => r.rep.model_issues || [])),
        recommendations: uniq(reports.flatMap((r) => r.rep.recommendations || [])),
      };
      await api(`/api/projects/${encodeURIComponent(state.project)}/quality`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ report: merged, note: `batch deep QA (${reports.length} workflows)` }),
      });
      setQaBatchProgress(false, 100, `Batch Deep QA complete: ${reports.length}/${ids.length} workflows (avg ${avgScore}/100)`);
      toast(`Merged Batch QA report saved (${avgScore}/100)`, 'ok');
      await refreshState();
    } else {
      setQaBatchProgress(false, 0, '');
    }
  };

  $('btn-batch-revise').onclick = async () => {
    if (!state.data.approvals.catalogue) return toast('Approve catalogue in Step 2 first.', 'err');
    const ids = Array.from(state.qaSelectedIds);
    if (!ids.length) return toast('Select workflows to revise.', 'err');
    const baseFeedback = $('qa-feedback').value.trim();
    const q = state.data.quality || {};
    state.qaBatchStop = false;
    let done = 0;
    for (let i = 0; i < ids.length; i++) {
      if (state.qaBatchStop) break;
      const pid = ids[i];
      const procFindings = [
        ...(state.data.static_checks || []),
        ...(q.critical || []),
        ...(q.warnings || []),
        ...(q.model_issues || []),
        ...(q.recommendations || []),
      ].filter((ln) => ln.includes(pid) || ln.toLowerCase().includes('all'));
      const combinedFb = [baseFeedback, procFindings.length ? 'Address QA findings:\n- ' + procFindings.join('\n- ') : ''].filter(Boolean).join('\n\n');
      setQaBatchProgress(true, Math.round((i / ids.length) * 100), `Revising ${pid} (${i + 1}/${ids.length})...`);
      try {
        await api(`/api/projects/${encodeURIComponent(state.project)}/artifacts/generate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ llm: llmPayload(), process_id: pid, feedback: combinedFb }),
        });
        done++;
        await refreshState();
      } catch (e) {
        toast(`Revise failed on ${pid}: ${e.message}`, 'err');
        break;
      }
    }
    setQaBatchProgress(false, 100, `Revised ${done}/${ids.length} workflow(s).`);
    if (done) toast(`Batch revised ${done} workflow(s)!`, 'ok');
  };

  $('btn-batch-gen-missing').onclick = async () => {
    if (!state.data.approvals.catalogue) return toast('Approve catalogue in Step 2 first.', 'err');
    const arts = state.data.artifacts || {};
    const ids = Array.from(state.qaSelectedIds).filter((id) => !arts[id]);
    if (!ids.length) return toast('All selected workflows already have generated artifacts.', 'ok');
    state.qaBatchStop = false;
    let done = 0;
    for (let i = 0; i < ids.length; i++) {
      if (state.qaBatchStop) break;
      const pid = ids[i];
      setQaBatchProgress(true, Math.round((i / ids.length) * 100), `Generating missing ${pid} (${i + 1}/${ids.length})...`);
      try {
        await api(`/api/projects/${encodeURIComponent(state.project)}/artifacts/generate`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ llm: llmPayload(), process_id: pid, feedback: $('qa-feedback').value }),
        });
        done++;
        await refreshState();
      } catch (e) {
        toast(`Generate failed on ${pid}: ${e.message}`, 'err');
        break;
      }
    }
    setQaBatchProgress(false, 100, `Generated ${done}/${ids.length} missing workflow(s).`);
    if (done) toast(`Generated ${done} missing workflow(s)!`, 'ok');
  };

  $('btn-run-qa').onclick = async () => {
    setBusy(true, 'Running adversarial quality assessment...');
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/assess`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llmPayload(), feedback: $('qa-feedback').value }),
      });
      toast('Quality report generated', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  $('chk-human-ack').onchange = updateApproveArtsButton;
  $('btn-approve-arts').onclick = async () => {
    await api(`/api/projects/${encodeURIComponent(state.project)}/approve/artifacts`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: true }),
    });
    toast('Architecture approved!', 'ok');
    await refreshState();
  };
  $('btn-revoke-arts').onclick = async () => {
    await api(`/api/projects/${encodeURIComponent(state.project)}/approve/artifacts`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: false }),
    });
    toast('Approval revoked', 'ok');
    await refreshState();
  };
  $('btn-restart-extract').onclick = async () => {
    setBusy(true, 'Restarting extraction with feedback...');
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/extract`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llmPayload(), feedback: $('qa-feedback').value }),
      });
      toast('Catalogue re-extracted', 'ok');
      await refreshState();
      goStep(2);
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  $('compare-mode').onchange = (e) => {
    const isDiff = e.target.value === 'diff';
    $('compare-diff-controls').classList.toggle('hidden', !isDiff);
    $('compare-diff-output').classList.toggle('hidden', !isDiff);
    $('compare-source-view').classList.toggle('hidden', isDiff);
    if (isDiff) loadCompareRevisions();
  };
  $('compare-key-select').onchange = loadCompareRevisions;
  $('btn-load-diff').onclick = loadDiffOutput;

  // Step 5
  document.querySelectorAll('[data-foundfield]').forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll('[data-foundfield]').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.activeFoundField = btn.dataset.foundfield;
      renderFoundationStep();
    };
  });
  document.querySelectorAll('[data-fview]').forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll('[data-fview]').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.foundView = btn.dataset.fview;
      renderFoundationStep();
    };
  });
  $('found-md-editor').addEventListener('input', () => {
    renderMarkdownToPaper($('found-md-editor').value, $('found-word-preview'));
    renderMarkdownToPaper($('found-md-editor').value, $('found-word-preview-full'));
  });
  $('btn-gen-foundation').onclick = async () => {
    setBusy(true, 'Generating Spec Kit Foundation...');
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/foundation/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llmPayload(), feedback: '' }),
      });
      toast('Foundation drafted!', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  $('btn-save-found').onclick = async () => {
    const f = structuredClone(state.data.foundation || { constitution_md: '', specification_md: '', clarification_md: '' });
    f[state.activeFoundField] = $('found-md-editor').value;
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/foundation`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ foundation: f, note: $('found-save-note').value || 'edited foundation' }),
      });
      toast('Foundation saved', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); }
  };
  $('btn-approve-found').onclick = async () => {
    await api(`/api/projects/${encodeURIComponent(state.project)}/approve/foundation`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: true }),
    });
    toast('Foundation approved!', 'ok');
    await refreshState();
  };
  $('btn-download-found-docx').onclick = () => downloadSingleDocx(`${state.project}-${state.activeFoundField}`, $('found-md-editor').value);

  // Step 6
  document.querySelectorAll('[data-planmode]').forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll('[data-planmode]').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.activePlanMode = btn.dataset.planmode;
      renderPlanningStep();
    };
  });
  document.querySelectorAll('[data-pview]').forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll('[data-pview]').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.planView = btn.dataset.pview;
      renderPlanningStep();
    };
  });
  $('plan-md-editor').addEventListener('input', () => {
    renderMarkdownToPaper($('plan-md-editor').value, $('plan-word-preview'));
    renderMarkdownToPaper($('plan-md-editor').value, $('plan-word-preview-full'));
  });
  $('btn-gen-planning').onclick = async () => {
    setBusy(true, 'Generating Technology Plan & Tasks...');
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/planning/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llmPayload(), tech_preferences: $('tech-preferences').value }),
      });
      toast('Plan & Tasks generated!', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  $('btn-save-plan').onclick = async () => {
    const p = structuredClone(state.data.planning || { plan_md: '', tasks_md: '' });
    if (state.activePlanMode !== 'code') p[state.activePlanMode] = $('plan-md-editor').value;
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/planning`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ planning: p, note: $('plan-save-note').value || 'edited planning' }),
      });
      toast('Plan saved', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); }
  };
  $('btn-approve-plan').onclick = async () => {
    await api(`/api/projects/${encodeURIComponent(state.project)}/approve/planning`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ approved: true }),
    });
    toast('Plan approved!', 'ok');
    await refreshState();
  };
  $('btn-download-plan-docx').onclick = () => downloadSingleDocx(`${state.project}-${state.activePlanMode}`, $('plan-md-editor').value);
  $('btn-export-docx').onclick = () => { window.location.href = `/api/projects/${encodeURIComponent(state.project)}/export/docx`; };
  $('btn-export-full-docx-2').onclick = () => { window.location.href = `/api/projects/${encodeURIComponent(state.project)}/export/docx`; };
  $('btn-export-speckit').onclick = () => { window.location.href = `/api/projects/${encodeURIComponent(state.project)}/export/speckit`; };

  $('btn-gen-code').onclick = async () => {
    const task = $('code-task-input').value.trim();
    if (!task) return toast('Enter a task or slice first.', 'err');
    setBusy(true, 'Generating code proposal...');
    try {
      await api(`/api/projects/${encodeURIComponent(state.project)}/implementation/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ llm: llmPayload(), task_selection: task }),
      });
      toast('Code proposal ready', 'ok');
      await refreshState();
    } catch (e) { toast(e.message, 'err'); } finally { setBusy(false); }
  };
  $('btn-save-code').onclick = async () => {
    if (!$('chk-code-reviewed').checked) return toast('Confirm review first.', 'err');
    try {
      const res = await api(`/api/projects/${encodeURIComponent(state.project)}/implementation/save`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: state.data.code_proposal.files, reviewed: true, overwrite: $('chk-code-overwrite').checked }),
      });
      toast(`Saved ${res.count} file(s) to ${res.saved_dir}`, 'ok');
    } catch (e) { toast(e.message, 'err'); }
  };

  // Settings Modal
  $('btn-settings').onclick = async () => {
    await loadProviders();
    $('cfg-provider').value = state.cfg.provider;
    syncSettingsUIForProvider(state.cfg.provider, false);
    const meta = getProviderMeta(state.cfg.provider);
    $('cfg-url').value = state.cfg.url || (meta?.default_url || '');
    const curModel = (!state.cfg.model || state.cfg.model === 'default') ? (meta?.default_model || 'auto') : state.cfg.model;
    $('cfg-model').value = curModel;
    $('cfg-api-key').value = state.cfg.api_key || '';
    $('llm-check-status').textContent = '';
    $('settings-modal').classList.remove('hidden');
  };
  $('llm-pill').onclick = () => $('btn-settings').click();
  $('btn-settings-close').onclick = () => $('settings-modal').classList.add('hidden');
  $('cfg-provider').onchange = (e) => syncSettingsUIForProvider(e.target.value, true);
  $('cfg-model-list').onchange = (e) => { if (e.target.value) $('cfg-model').value = e.target.value; };
  $('btn-check-llm').onclick = async () => {
    $('llm-check-status').textContent = 'Checking subscription & discovering current models...';
    const res = await api('/api/llm/test', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: $('cfg-provider').value, url: $('cfg-url').value, model: $('cfg-model').value, api_key: $('cfg-api-key').value }),
    });
    if (res.models && res.models.length) {
      $('cfg-model-list').innerHTML = '<option value="">(detected models)</option>' + res.models.map((m) => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
      if (res.default_model && (!$('cfg-model').value || $('cfg-model').value === 'default')) {
        $('cfg-model').value = res.default_model;
      }
    }
    $('llm-check-status').textContent = res.ok ? `✓ ${res.message}` : `✕ ${res.message}`;
  };
  $('btn-settings-save').onclick = () => {
    state.cfg = {
      provider: $('cfg-provider').value,
      url: $('cfg-url').value.trim(),
      model: $('cfg-model').value.trim() || 'auto',
      api_key: $('cfg-api-key').value,
    };
    localStorage.setItem('ae_cfg_v2', JSON.stringify(state.cfg));
    updateLLMPill();
    $('settings-modal').classList.add('hidden');
    toast('AI provider settings saved', 'ok');
  };

  // Global Escape exits full-canvas Diagram Editor back to Word View
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.step === 3 && state.canvasMode === 'diagram') {
      setCanvasMode('word');
    }
  });

  // Git Sync Modal
  $('btn-git').onclick = openGitModal;
  $('btn-git-close').onclick = () => $('git-modal').classList.add('hidden');
  $('btn-git-refresh').onclick = refreshGitModal;

  $('btn-git-connect').onclick = async () => {
    const out = $('git-action-output');
    try {
      const res = await api(`/api/projects/${encodeURIComponent(state.project)}/git/connect`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ remote_url: $('git-remote-url').value.trim(), branch: $('git-branch').value.trim() || 'main' }),
      });
      out.className = 'alert-box';
      out.textContent = res.remote_url
        ? `Connected local repo to ${res.remote_url} (branch: ${res.branch}).`
        : `Initialized local Git repository on branch ${res.branch}.`;
      toast('Git repository connected!', 'ok');
      await refreshGitModal();
    } catch (e) {
      out.className = 'alert-box err';
      out.textContent = e.message;
      toast(e.message, 'err');
    }
  };

  async function doGitCommit(push) {
    const out = $('git-action-output');
    setBusy(true, push ? 'Committing & pushing to Git...' : 'Committing changes locally...');
    try {
      const res = await api(`/api/projects/${encodeURIComponent(state.project)}/git/commit`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: $('git-commit-msg').value.trim() || 'Update architecture artifacts',
          push,
          branch: $('git-branch').value.trim() || 'main',
        }),
      });
      $('git-commit-msg').value = '';
      out.className = 'alert-box';
      out.textContent = push
        ? (res.committed ? `Committed & pushed to Git! ${res.push_output}` : `Already committed — pushed to Git! ${res.push_output}`)
        : (res.committed ? 'Committed locally!' : 'Nothing new to commit.');
      toast(push ? 'Changes pushed to Git!' : 'Committed locally!', 'ok');
      await refreshGitModal();
    } catch (e) {
      out.className = 'alert-box err';
      out.textContent = e.message;
      toast(e.message, 'err');
    } finally {
      setBusy(false);
    }
  }

  $('btn-git-commit-local').onclick = () => doGitCommit(false);
  $('btn-git-push').onclick = () => doGitCommit(true);

  $('btn-git-pull').onclick = async () => {
    const out = $('git-action-output');
    setBusy(true, 'Pulling latest changes from Git...');
    try {
      const res = await api(`/api/projects/${encodeURIComponent(state.project)}/git/pull`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ branch: $('git-branch').value.trim() || 'main' }),
      });
      out.className = 'alert-box';
      out.textContent = res.output || 'Pulled latest from remote.';
      toast('Pulled latest from Git!', 'ok');
      await refreshState();
      await refreshGitModal();
    } catch (e) {
      out.className = 'alert-box err';
      out.textContent = e.message;
      toast(e.message, 'err');
    } finally {
      setBusy(false);
    }
  };

  // History Modal
  $('btn-history').onclick = openHistoryModal;
  $('btn-history-close').onclick = () => $('history-modal').classList.add('hidden');
  $('history-key-select').onchange = refreshHistoryModal;
  $('btn-history-refresh').onclick = refreshHistoryModal;

  // About Modal
  const closeAbout = () => $('about-modal').classList.add('hidden');
  $('btn-about-brand').onclick = openAboutModal;
  $('btn-about').onclick = openAboutModal;
  $('btn-about-close').onclick = closeAbout;
  $('btn-about-ok').onclick = closeAbout;
  $('about-modal').onclick = (e) => { if (e.target === $('about-modal')) closeAbout(); };
}

async function loadAbout() {
  try {
    state.about = await api('/api/about');
    if (state.about) {
      const ver = state.about.version || '0.1.0-beta';
      const stage = state.about.stage || 'Beta';
      if ($('topbar-beta-pill')) {
        $('topbar-beta-pill').textContent = stage.toUpperCase();
        $('topbar-beta-pill').classList.toggle('hidden', !state.about.is_beta);
      }
      if ($('btn-about-brand')) {
        $('btn-about-brand').title = `About ${state.about.name} v${ver} (${stage})`;
      }
    }
  } catch (_) {
    // non-fatal
  }
}

async function openAboutModal() {
  if (!state.about) await loadAbout();
  const info = state.about || {
    name: 'SPECiT',
    version: '0.1.0-beta',
    stage: 'Beta',
    is_beta: true,
    workspace_root: 'workspace',
    frozen: false,
    repo_url: 'https://github.com/javadtaghia/specit',
    python_version: '',
    platform: '',
  };
  $('about-version').textContent = `v${info.version}`;
  $('about-stage').textContent = (info.stage || 'Beta').toUpperCase();
  $('about-meta-version').textContent = info.version;
  $('about-meta-stage').textContent = info.stage || 'Beta';
  $('about-meta-workspace').textContent = info.workspace_root || 'workspace';
  const runtimeParts = [info.frozen ? 'Standalone Desktop App' : 'Local Python'];
  if (info.python_version) runtimeParts.push(`Python ${info.python_version}`);
  if (info.platform) runtimeParts.push(info.platform);
  $('about-meta-runtime').textContent = runtimeParts.join(' · ');
  const repoEl = $('about-meta-repo');
  repoEl.href = info.repo_url || 'https://github.com/javadtaghia/specit';
  repoEl.textContent = (info.repo_url || 'https://github.com/javadtaghia/specit').replace(/^https?:\/\//, '');
  $('about-modal').classList.remove('hidden');
}

/* ==================== BOOTSTRAP ==================== */
(async function init() {
  mapPanZoom = new PanZoom('flows-map-viewport', 'flows-map-board');
  wireEvents();
  await Promise.all([loadAbout(), loadProviders(), loadProjects()]);
  await refreshState();
})();
