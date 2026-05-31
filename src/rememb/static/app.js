const state = {
  view: 'memories',
  workstreamSurfaceFocus: 'overview',
  section: null,
  config: null,
  entries: [],
  workstreams: [],
  reviewItems: [],
  dashboardSwitchPackage: null,
  skills: null,
  total: 0,
  offset: 0,
  limit: 24,
  sort_by: 'recent',
  descending: true,
  hasMore: false,
  searchMode: false,
  searchQuery: '',
  includeDeleted: false,
  workstreamsIncludeDeleted: false,
  reviewFilterWorkstreamId: '',
  reviewFilterSessionId: '',
  reviewFilterActorType: '',
  reviewFilterActorId: '',
  reviewFilterEntryKind: '',
  reviewAvailableSessions: [],
  reviewWorkstreamSummary: null,
  reviewSessionSummary: null,
  workstreamQueueItems: [],
  selectedWorkstreamId: null,
  workstreamDetail: null,
  selectedReviewId: null,
  loading: false,
  systemInfo: null,
};

async function apiFetch(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

const api = {
  config: () => apiFetch('/api/config'),
  models: () => apiFetch('/api/models'),
  stats: () => apiFetch('/api/stats'),
  systemInfo: () => apiFetch('/api/system/info'),
  skills: () => apiFetch('/api/skills'),
  skill: (id) => apiFetch(`/api/skills/${encodeURIComponent(id)}`),
  entries: (p) => apiFetch('/api/entries?' + new URLSearchParams(p)),
  search: (p) => apiFetch('/api/search?' + new URLSearchParams(p)),
  writeEntry: (body) => apiFetch('/api/entries', { method: 'POST', body: JSON.stringify(body) }),
  editEntry: (id, body) => apiFetch(`/api/entries/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteEntry: (id) => apiFetch(`/api/entries/${id}`, { method: 'DELETE' }),
  entryVersions: (id, p = {}) => apiFetch(`/api/entries/${id}/versions?` + new URLSearchParams(p)),
  restoreDeletedEntry: (id) => apiFetch(`/api/entries/${id}/restore`, { method: 'POST' }),
  restoreEntryVersion: (id, version) => apiFetch(`/api/entries/${id}/versions/${version}/restore`, { method: 'POST' }),
  diffVersions: (id, p) => apiFetch(`/api/entries/${id}/diff?` + new URLSearchParams(p)),
  workstreams: (p = {}) => apiFetch('/api/workstreams?' + new URLSearchParams(p)),
  openWorkstream: (body) => apiFetch('/api/workstreams/open', { method: 'POST', body: JSON.stringify(body) }),
  handoffPackage: (id, p = {}) => {
    const params = { ...p };
    if (params.session_id !== undefined && params.execution_id === undefined) params.execution_id = params.session_id;
    delete params.session_id;
    return apiFetch(`/api/workstreams/${encodeURIComponent(id)}/handoff-package?` + new URLSearchParams(params));
  },
  workstreamState: (id, p = {}) => {
    const params = { ...p };
    if (params.session_id !== undefined && params.execution_id === undefined) params.execution_id = params.session_id;
    delete params.session_id;
    return apiFetch(`/api/workstreams/${encodeURIComponent(id)}/state?` + new URLSearchParams(params));
  },
  workstreamResume: (id, p = {}) => {
    const params = { ...p };
    if (params.session_id !== undefined && params.execution_id === undefined) params.execution_id = params.session_id;
    delete params.session_id;
    return apiFetch(`/api/workstreams/${encodeURIComponent(id)}/resume?` + new URLSearchParams(params));
  },
  updateWorkstreamState: (id, body) => apiFetch(`/api/workstreams/${encodeURIComponent(id)}/state`, { method: 'POST', body: JSON.stringify(body) }),
  startExecution: (id, body) => apiFetch(`/api/workstreams/${encodeURIComponent(id)}/executions/start`, { method: 'POST', body: JSON.stringify(body) }),
  closeExecution: (id, body) => apiFetch(`/api/workstreams/${encodeURIComponent(id)}/executions/close`, { method: 'POST', body: JSON.stringify(body) }),
  closeExecutionAndHandoff: (id, body) => apiFetch(`/api/workstreams/${encodeURIComponent(id)}/executions/close-and-handoff`, { method: 'POST', body: JSON.stringify(body) }),
  writeStructuredHandoff: (id, body) => apiFetch(`/api/workstreams/${encodeURIComponent(id)}/handoff`, { method: 'POST', body: JSON.stringify(body) }),
  readStructuredHandoff: (id, p = {}) => apiFetch(`/api/workstreams/${encodeURIComponent(id)}/handoff?` + new URLSearchParams(p)),
  reviewQueue: (p = {}) => apiFetch('/api/review?' + new URLSearchParams(p)),
  reviewWorkstream: (id, p = {}) => apiFetch(`/api/review/workstreams/${encodeURIComponent(id)}?` + new URLSearchParams(p)),
  reviewExecution: (workstreamId, executionId, p = {}) => apiFetch(`/api/review/workstreams/${encodeURIComponent(workstreamId)}/executions/${encodeURIComponent(executionId)}?` + new URLSearchParams(p)),
  workstreamQueue: (p = {}) => apiFetch('/api/workstreams/queue?' + new URLSearchParams(p)),
  compareExecutions: (workstreamId, p = {}) => apiFetch(`/api/workstreams/${encodeURIComponent(workstreamId)}/compare/executions?` + new URLSearchParams(p)),
  compareWorkstreams: (p = {}) => apiFetch('/api/workstreams/compare?' + new URLSearchParams(p)),
  workstreamSwitchPackage: (p = {}) => apiFetch('/api/workstreams/switch-package?' + new URLSearchParams(p)),
  reviewUpdate: (id, body) => apiFetch(`/api/review/${encodeURIComponent(id)}`, { method: 'POST', body: JSON.stringify(body) }),
  consolidate: (body) => apiFetch('/api/consolidate', { method: 'POST', body: JSON.stringify(body) }),
  configUpdate: (body) => apiFetch('/api/config', { method: 'PUT', body: JSON.stringify({ updates: body }) }),
};

let semanticModels = [];


function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function uiSelector(name) {
  const value = String(name ?? '');
  if (window.CSS?.escape) {
    return `[data-ui="${CSS.escape(value)}"]`;
  }
  return `[data-ui="${value.replace(/"/g, '\\"')}"]`;
}

function ui(name, root = document) {
  return (root || document).querySelector(uiSelector(name));
}

function uiAll(name, root = document) {
  return Array.from((root || document).querySelectorAll(uiSelector(name)));
}

const nativeDocumentGetElementById = Document.prototype.getElementById;
Document.prototype.getElementById = function remembDataUiLookup(id) {
  return ui(id, this) || nativeDocumentGetElementById.call(this, id);
};

function stripClassAttributesFromMarkup(markup) {
  return String(markup || '').replace(/\sclass=("[^"]*"|'[^']*')/g, '');
}

const elementInnerHTMLDescriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
if (elementInnerHTMLDescriptor?.set && elementInnerHTMLDescriptor?.get) {
  Object.defineProperty(Element.prototype, 'innerHTML', {
    configurable: true,
    enumerable: elementInnerHTMLDescriptor.enumerable,
    get() {
      return elementInnerHTMLDescriptor.get.call(this);
    },
    set(value) {
      elementInnerHTMLDescriptor.set.call(this, stripClassAttributesFromMarkup(value));
    },
  });
}

function stripClassesFromTree(root) {
  if (!root) return;
  if (root.nodeType === Node.ELEMENT_NODE) {
    root.removeAttribute('class');
  }
  if (root.querySelectorAll) {
    root.querySelectorAll('[class]').forEach((el) => el.removeAttribute('class'));
  }
}

const classlessObserver = new MutationObserver((mutations) => {
  for (const mutation of mutations) {
    if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
      mutation.target.removeAttribute('class');
      continue;
    }
    if (mutation.type === 'childList') {
      mutation.addedNodes.forEach((node) => stripClassesFromTree(node));
    }
  }
});

function hexToRgb(hex) {
  const clean = String(hex || '').trim().replace('#', '');
  const normalized = clean.length === 3 ? clean.split('').map((char) => char + char).join('') : clean;
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return { r: 136, g: 136, b: 136 };
  }
  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  };
}

function rgba(hex, alpha) {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function sectionColor(name) {
  if (!state.config) return '#888888';
  return (state.config.section_colors || {})[name] || '#888888';
}

function sectionTheme(name) {
  const color = sectionColor(name);
  return {
    color,
    headerBg: rgba(color, 0.11),
    headerBorder: rgba(color, 0.2),
    softBg: rgba(color, 0.1),
    softBorder: rgba(color, 0.24),
    glow: rgba(color, 0.14),
    faint: rgba(color, 0.06),
  };
}

function themeVars(theme) {
  const { r, g, b } = hexToRgb(theme.color);
  return [
    `--theme-color:${theme.color}`,
    `--theme-soft-bg:${theme.softBg}`,
    `--theme-soft-border:${theme.softBorder}`,
    `--theme-header-bg:${theme.headerBg}`,
    `--theme-header-border:${theme.headerBorder}`,
    `--theme-faint:${theme.faint}`,
    `--theme-color-rgb:${r}, ${g}, ${b}`,
  ].join(';');
}



function relTime(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  const now = new Date();
  const diff = Math.floor((now - d) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

function previewText(text, max = 96) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim();
  if (clean.length <= max) return clean;
  return clean.slice(0, max - 1) + '…';
}

function readIntInput(id, fallback) {
  const raw = document.getElementById(id)?.value ?? '';
  const parsed = parseInt(String(raw).trim(), 10);
  return Number.isNaN(parsed) ? fallback : parsed;
}

function readFloatInput(id, fallback) {
  const raw = document.getElementById(id)?.value ?? '';
  const parsed = parseFloat(String(raw).trim());
  return Number.isNaN(parsed) ? fallback : parsed;
}

function parseUnifiedDiff(diffText) {
  const rows = [];
  const lines = String(diffText || '').split('\n');

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.startsWith('--- ') || line.startsWith('+++ ') || line.startsWith('@@')) {
      continue;
    }

    if (line.startsWith('-')) {
      const next = lines[index + 1] || '';
      if (next.startsWith('+')) {
        rows.push({ type: 'changed', left: line.slice(1), right: next.slice(1) });
        index += 1;
        continue;
      }
      rows.push({ type: 'removed', left: line.slice(1), right: '' });
      continue;
    }

    if (line.startsWith('+')) {
      rows.push({ type: 'added', left: '', right: line.slice(1) });
      continue;
    }

    const value = line.startsWith(' ') ? line.slice(1) : line;
    rows.push({ type: 'context', left: value, right: value });
  }

  return rows;
}

function tokenizeInlineWords(text) {
  return String(text || '').match(/(\s+|[^\s]+)/g) || [];
}

function renderEscapedTokens(tokens) {
  return tokens.map((token) => escHtml(token)).join('');
}

function renderInlineWordDiff(leftText, rightText, side) {
  const leftTokens = tokenizeInlineWords(leftText);
  const rightTokens = tokenizeInlineWords(rightText);

  let prefix = 0;
  while (
    prefix < leftTokens.length &&
    prefix < rightTokens.length &&
    leftTokens[prefix] === rightTokens[prefix]
  ) {
    prefix += 1;
  }

  let leftSuffix = leftTokens.length - 1;
  let rightSuffix = rightTokens.length - 1;
  while (
    leftSuffix >= prefix &&
    rightSuffix >= prefix &&
    leftTokens[leftSuffix] === rightTokens[rightSuffix]
  ) {
    leftSuffix -= 1;
    rightSuffix -= 1;
  }

  const currentTokens = side === 'left' ? leftTokens : rightTokens;
  const endIndex = side === 'left' ? leftSuffix : rightSuffix;
  const changedTokens = currentTokens.slice(prefix, endIndex + 1);
  const before = renderEscapedTokens(currentTokens.slice(0, prefix));
  const after = renderEscapedTokens(currentTokens.slice(endIndex + 1));
  if (!changedTokens.length) {
    return before + after;
  }

  const diffKind = side === 'left' ? 'removed' : 'added';
  return `${before}<span data-diff-inline="${diffKind}">${renderEscapedTokens(changedTokens)}</span>${after}`;
}

function renderDiffCell(row, side) {
  const value = side === 'left' ? row.left : row.right;
  if (row.type === 'changed') {
    return renderInlineWordDiff(row.left, row.right, side);
  }
  return escHtml(value || '∅');
}

function renderSideBySideDiff(diffText) {
  const rows = parseUnifiedDiff(diffText);
  if (!rows.length) {
    return '<article data-panel="soft" data-empty="true">No content changes.</article>';
  }

  return `
    <article data-panel="shell" data-diff="table">
      <header data-diff-header>
        <div>From</div>
        <div>To</div>
      </header>
      <section data-diff-scroll>
        ${rows.map((row) => `
          <div data-diff-row="${row.type || 'context'}">
            <div${row.left ? '' : ' data-empty="true"'}>${renderDiffCell(row, 'left')}</div>
            <div${row.right ? '' : ' data-empty="true"'}>${renderDiffCell(row, 'right')}</div>
          </div>
        `).join('')}
      </section>
    </article>`;
}

function formatInlineMarkdown(text) {
  let html = escHtml(text || '');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  return html;
}

function renderMarkdown(text) {
  if (!text) return '';
  const lines = String(text).replace(/\r\n?/g, '\n').split('\n');
  const blocks = [];
  let paragraph = [];
  let listItems = [];
  let listMode = null;
  let codeFence = null;

  function flushParagraph() {
    if (!paragraph.length) return;
    blocks.push(`<p>${formatInlineMarkdown(paragraph.join(' '))}</p>`);
    paragraph = [];
  }

  function flushList() {
    if (!listItems.length) return;
    const tag = listMode === 'ol' ? 'ol' : 'ul';
    blocks.push(`<${tag}>${listItems.map((item) => `<li>${formatInlineMarkdown(item)}</li>`).join('')}</${tag}>`);
    listItems = [];
    listMode = null;
  }

  function flushCodeFence() {
    if (!codeFence) return;
    blocks.push(`<pre><code>${escHtml(codeFence.join('\n'))}</code></pre>`);
    codeFence = null;
  }

  for (const line of lines) {
    if (line.startsWith('```')) {
      flushParagraph();
      flushList();
      if (codeFence) {
        flushCodeFence();
      } else {
        codeFence = [];
      }
      continue;
    }

    if (codeFence) {
      codeFence.push(line);
      continue;
    }

    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      flushList();
      blocks.push('<hr>');
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      const level = heading[1].length;
      blocks.push(`<h${level}>${formatInlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    const quote = trimmed.match(/^>\s?(.*)$/);
    if (quote) {
      flushParagraph();
      flushList();
      blocks.push(`<blockquote>${formatInlineMarkdown(quote[1])}</blockquote>`);
      continue;
    }

    const ordered = trimmed.match(/^\d+\.\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      if (listMode && listMode !== 'ol') flushList();
      listMode = 'ol';
      listItems.push(ordered[1]);
      continue;
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      if (listMode && listMode !== 'ul') flushList();
      listMode = 'ul';
      listItems.push(unordered[1]);
      continue;
    }

    paragraph.push(trimmed);
  }

  flushParagraph();
  flushList();
  flushCodeFence();
  return `<article data-markdown="true">${blocks.join('')}</article>`;
}

function parseFrontmatter(text) {
  const source = String(text || '');
  const match = source.match(/^---\s*\n([\s\S]*?)\n---\s*\n?/);
  if (!match) {
    return { attributes: [], body: source };
  }

  const attributes = [];
  const lines = match[1].split('\n');
  const parents = [];
  let multiline = null;

  function normalizeValue(value) {
    return String(value || '').trim().replace(/^['"]|['"]$/g, '');
  }

  function closeMultiline() {
    if (!multiline) return;
    attributes.push({
      key: multiline.key,
      value: multiline.lines.map((line) => line.trim()).filter(Boolean).join(multiline.mode === '|' ? '\n' : ' '),
    });
    multiline = null;
  }

  for (let i = 0; i < lines.length; i += 1) {
    const rawLine = lines[i];
    const line = rawLine.replace(/\t/g, '    ').replace(/\s+$/, '');
    const indent = line.match(/^\s*/)[0].length;

    if (multiline) {
      if (!line.trim()) {
        multiline.lines.push('');
        continue;
      }
      if (indent > multiline.indent) {
        multiline.lines.push(line.trim());
        continue;
      }
      closeMultiline();
    }

    if (!line.trim()) continue;

    const item = line.match(/^(\s*)([^:]+):\s*(.*)$/);
    if (!item) continue;

    const key = item[2].trim();
    const value = item[3].trim();

    while (parents.length && parents[parents.length - 1].indent >= indent) {
      parents.pop();
    }

    const fullKey = [...parents.map((entry) => entry.key), key].join('.');

    if (value === '>' || value === '|') {
      multiline = { key: fullKey, indent, mode: value, lines: [] };
      continue;
    }

    if (!value) {
      parents.push({ key, indent });
      continue;
    }

    attributes.push({ key: fullKey, value: normalizeValue(value) });
  }

  closeMultiline();

  return {
    attributes,
    body: source.slice(match[0].length),
  };
}

function renderSkillFrontmatter(attributes) {
  if (!attributes.length) return '';
  return `
    <section data-panel="default">
      <h4>Frontmatter</h4>
      <dl>
        ${attributes.map(({ key, value }) => `
          <div>
            <dt>${escHtml(key || 'field')}</dt>
            <dd>${escHtml(value || '—')}</dd>
          </div>
        `).join('')}
      </dl>
    </section>
  `;
}

function renderModelSelect(currentValue) {
  const opts = semanticModels.map((m) =>
    `<option value="${escHtml(m.name)}" ${m.name === currentValue ? 'selected' : ''} title="${escHtml(m.description)}">${escHtml(m.label)}</option>`
  ).join('');
  return `<select data-ui="cfg-model" data-role="model-select">${opts}</select>`;
}

function toast(msg, type = 'info', duration = 3000) {
  const accent = type === 'error' ? '#c04040' : (type === 'success' ? '#30b870' : '#04D8E7');
  const el = document.createElement('div');
  el.setAttribute('role', 'status');
  el.style.cssText = 'display:flex;align-items:center;gap:8px;padding:10px 12px;border-radius:10px;background:#0f172a;color:#e2e8f0;box-shadow:var(--shadow-md);margin-top:8px;';
  el.style.borderLeft = `3px solid ${accent}`;
  el.innerHTML = `<span>${msg}</span>`;
  const container = document.getElementById('toast-container');
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 300);
  }, duration);
}

function renderSections() {
  if (!state.config) return;
  const sections = state.config.sections || [];
  const list = document.getElementById('sections-list');
  const allActive = state.section === null && !state.searchMode;

  const allSectionVars = '--section-color: var(--accent); --section-soft-bg: rgba(4,216,231,0.12); --section-soft-border: rgba(4,216,231,0.18);';

  let html = `
    <button data-section="" ${allActive ? 'aria-current="page"' : ''} ${allActive ? `style="${allSectionVars}"` : ''}>
      <span ${allActive ? 'style="--section-color: var(--accent);"' : ''}>◉</span>
      <span>All entries</span>
      <span data-ui="count-all" ${allActive ? `style="${allSectionVars}"` : ''}>${state.total || ''}</span>
    </button>`;

  for (const s of sections) {
    const theme = sectionTheme(s);
    const active = state.section === s && !state.searchMode;
    const activeVars = `--section-color:${theme.color};--section-soft-bg:${theme.softBg};--section-soft-border:${theme.softBorder};`;
    html += `
      <button data-section="${escHtml(s)}" ${active ? 'aria-current="page"' : ''} style="${active ? activeVars : `--section-color:${theme.color};`}">
        <span>●</span>
        <span>${escHtml(s)}</span>
        <span data-ui="count-${escHtml(s)}" ${active ? `style="${activeVars}"` : ''}>—</span>
      </button>`;
  }

  list.innerHTML = html;
  list.querySelectorAll('[data-section]').forEach((el) => {
    el.addEventListener('click', () => {
      const sec = el.dataset.section || null;
      clearSearch(true);
      selectSection(sec);
    });
  });
}

function summarizeDiff(diffText) {
  const rows = parseUnifiedDiff(diffText);
  return rows.reduce((summary, row) => {
    if (row.type === 'added') summary.added += 1;
    else if (row.type === 'removed') summary.removed += 1;
    else if (row.type === 'changed') summary.changed += 1;
    return summary;
  }, { added: 0, removed: 0, changed: 0 });
}



function renderWorkstreamSummary(items) {
  const total = items.length;
  const executions = items.reduce((sum, item) => sum + (item.session_count || 0), 0);
  const awaitingReview = items.filter((item) => item.operational_status === 'awaiting_review').length;
  const readyToResume = items.filter((item) => item.next_execution?.goal).length;
  const queueItems = state.workstreamQueueItems || [];
  const activeQueue = queueItems.filter((item) => item.status === 'active').length;
  const latest = items[0]?.updated_at || '';
  document.getElementById('workstream-summary').innerHTML = `
    <header data-summary-header="split">
      <div>
        <h3>At a glance</h3>
        <p>Current workstreams, review pressure and what is ready to resume.</p>
      </div>
      <div data-pill-row>
        <span data-pill="count">${total} workstream${total === 1 ? '' : 's'}</span>
        <span data-pill="count">${executions} execution cycle${executions === 1 ? '' : 's'}</span>
        <span data-pill="count">${awaitingReview} awaiting_review</span>
        <span data-pill="count">${readyToResume} resume-ready</span>
        <span data-pill="count">${activeQueue} active in queue</span>
        <span data-pill="count">${latest ? `updated ${relTime(latest)}` : 'no history yet'}</span>
      </div>
    </header>`;
}

function renderOperationalQueue(items) {
  const summaryRoot = document.getElementById('workstream-queue-summary');
  const listRoot = document.getElementById('workstream-queue-list');
  if (!summaryRoot || !listRoot) return;

  const active = items.filter((item) => item.status === 'active').length;
  const awaitingReview = items.filter((item) => item.status === 'awaiting_review').length;
  const ready = items.filter((item) => item.status === 'ready').length;

  summaryRoot.innerHTML = `
    <section data-metric-grid>
      <article data-metric-card>
        <strong>${escHtml(items.length)}</strong>
        <small>Queue items</small>
      </article>
      <article data-metric-card>
        <strong>${escHtml(active)}</strong>
        <small>Active</small>
      </article>
      <article data-metric-card>
        <strong>${escHtml(awaitingReview)}</strong>
        <small>Awaiting review</small>
      </article>
      <article data-metric-card>
        <strong>${escHtml(ready)}</strong>
        <small>Resume ready</small>
      </article>
    </section>
  `;

  if (!items.length) {
    listRoot.innerHTML = '<p data-note="muted">No next actions right now. Work that needs attention will appear here.</p>';
    return;
  }

  listRoot.innerHTML = items.slice(0, 6).map((item) => `
    <article data-panel="compact" data-queue-workstream="${escHtml(item.workstream_id || '')}">
      <header data-row="space-between">
        <span data-pill="mono">${escHtml(item.status || 'queued')}</span>
        <time>${escHtml(relTime(item.updated_at || item.created_at || ''))}</time>
      </header>
      <h4>${escHtml(previewText(item.goal || item.workstream_id || 'Untitled queue item', 68))}</h4>
      <p>${escHtml(previewText(item.summary || item.next_execution?.goal || 'No queue summary available.', 150))}</p>
      <footer data-pill-row>
        ${item.workstream_id ? `<span data-pill="mono">${escHtml(item.workstream_id)}</span>` : ''}
        ${item.next_execution?.goal ? `<span data-pill="mono">next:${escHtml(previewText(item.next_execution.goal, 28))}</span>` : ''}
      </footer>
    </article>
  `).join('');

  listRoot.querySelectorAll('[data-queue-workstream]').forEach((node) => {
    node.addEventListener('click', async () => {
      const workstreamId = node.dataset.queueWorkstream;
      if (!workstreamId) return;
      await selectWorkstream(workstreamId);
    });
  });
}

function renderDashboardList(rootId, items, emptyMessage) {
  const root = document.getElementById(rootId);
  if (!root) return;
  if (!items.length) {
    root.innerHTML = `<p data-note="muted">${escHtml(emptyMessage)}</p>`;
    return;
  }
  root.innerHTML = items.map((item) => `
    <article data-panel="tight">
      <header data-row="space-between">
        <div>
          <h4>${escHtml(item.title || '')}</h4>
          <p>${escHtml(item.body || '')}</p>
        </div>
        ${item.meta ? `<span data-pill="mono">${escHtml(item.meta)}</span>` : ''}
      </header>
      ${item.action ? `<footer data-actions><button data-variant="${escHtml(item.action.variant || 'ghost')}" data-size="small" data-dashboard-action="${escHtml(item.action.name)}" data-dashboard-value="${escHtml(item.action.value || '')}" data-dashboard-workstream="${escHtml(item.action.workstreamId || '')}" data-dashboard-entry-id="${escHtml(item.action.entryId || '')}">${escHtml(item.action.label)}</button></footer>` : ''}
    </article>
  `).join('');
  root.querySelectorAll('[data-dashboard-action]').forEach((button) => {
    button.addEventListener('click', async () => {
      const action = button.dataset.dashboardAction;
      const value = button.dataset.dashboardValue;
      if (action === 'open-workstream') {
        switchView('workstreams');
        await selectWorkstream(value);
        return;
      }
      if (action === 'open-review') {
        switchView('workstreams');
        const workstreamId = button.dataset.dashboardWorkstream || value || state.workstreams[0]?.workstream_id || '';
        const entryId = button.dataset.dashboardEntryId || '';
        if (workstreamId) {
          await selectWorkstream(workstreamId);
        }
        state.selectedReviewId = entryId || state.selectedReviewId;
        await setWorkstreamSurfaceFocus('review', { scroll: true, ensureSelected: true });
        return;
      }
      if (action === 'open-memory-admin') {
        switchView('memories');
        return;
      }
      if (action === 'open-runtime-controls') {
        switchView(value || 'settings');
        return;
      }
      if (action === 'open-handoffs') {
        switchView('workstreams');
        const workstreamId = button.dataset.dashboardWorkstream || value || state.workstreams[0]?.workstream_id || '';
        if (workstreamId) {
          await selectWorkstream(workstreamId);
        }
        await setWorkstreamSurfaceFocus('handoffs', { scroll: true, ensureSelected: true });
      }
    });
  });
}

async function renderDashboardView() {
  try {
    const [statsData, workstreamsData, reviewData, queueData] = await Promise.all([
      api.stats(),
      api.workstreams({ include_deleted: 'false', limit: '6' }),
      api.reviewQueue({ pending_only: 'true', limit: '6' }),
      api.workstreamQueue({ limit: '8' }).catch(() => ({ items: [] })),
    ]);
    const workstreams = workstreamsData.items || [];
    const reviewItems = reviewData.items || [];
    const queueItems = queueData.items || [];
    const executionBacklog = queueItems.filter((item) => item.status === 'ready' || item.status === 'active' || item.status === 'awaiting_review').length;
    
    state.workstreams = workstreams;
    state.reviewItems = reviewItems;
    state.workstreamQueueItems = queueItems;
    state.total = statsData.total_entries ?? 0;
    state.dashboardSwitchPackage = workstreams.length > 1
      ? await api.workstreamSwitchPackage({ current_workstream_id: workstreams[0].workstream_id, target_workstream_id: workstreams[1].workstream_id }).catch(() => null)
      : null;

    document.getElementById('dashboard-workstreams-count').textContent = String(workstreams.length);
  document.getElementById('dashboard-workstreams-caption').textContent = workstreams.length ? `${workstreams.filter((item) => (item.session_count || 0) > 0).length} with recent activity` : 'no active workstreams';
    document.getElementById('dashboard-execution-count').textContent = String(executionBacklog);
    document.getElementById('dashboard-execution-caption').textContent = executionBacklog ? `${queueItems.filter((item) => item.status === 'awaiting_review').length} awaiting review · ${queueItems.filter((item) => item.status === 'active').length} active` : 'no execution backlog';
    document.getElementById('dashboard-review-count').textContent = String(reviewItems.length);
    document.getElementById('dashboard-review-caption').textContent = reviewItems.length ? 'items escalated for final validation' : 'nothing escalated right now';
    document.getElementById('dashboard-memory-count').textContent = String(statsData.total_entries ?? 0);
    document.getElementById('dashboard-memory-caption').textContent = `${statsData.deleted_entries ?? 0} deleted · ${Object.values(statsData.sections || {}).filter((count) => count > 0).length} active sections`;

    renderDashboardList(
      'dashboard-workstreams-list',
      [
        ...(state.dashboardSwitchPackage ? [{
          title: `Switch package: ${state.dashboardSwitchPackage.current_workstream_id} -> ${state.dashboardSwitchPackage.target_workstream_id}`,
          body: `needed now=${(state.dashboardSwitchPackage.state_gap?.needed_now_but_not_open || []).join(', ') || 'none'} · risky=${(state.dashboardSwitchPackage.state_gap?.risky_to_carry || []).join(', ') || 'none'}`,
          meta: 'anti-context-switch',
          action: { name: 'open-workstream', value: state.dashboardSwitchPackage.target_workstream_id, label: 'Inspect target workstream', variant: 'ghost' },
        }] : []),
        ...workstreams.slice(0, 4).map((item) => ({
        title: item.goal || item.workstream_id,
        body: `${item.summary || 'No summary available yet.'} next=${item.next_execution?.goal || 'not packaged'} · status=${item.operational_status || 'active'}`,
        meta: item.workstream_id,
        action: { name: 'open-workstream', value: item.workstream_id, label: 'Open workstream', variant: 'ghost' },
      }))],
      'No workstreams yet. Agents will start creating continuity here once work begins.'
    );

    const attentionItems = [];
    if (reviewItems.length) {
      attentionItems.push(...reviewItems.slice(0, 3).map((item) => ({
        title: item.summary || item.entry_id,
        body: `${item.workstream_id || 'no workstream'} · ${item.review_status || 'pending'} · ${(item.review_reasons || []).join(', ') || 'no explicit reason'}`,
        meta: item.entry_kind || 'entry',
        action: { name: 'open-review', value: item.workstream_id || '', workstreamId: item.workstream_id || '', entryId: item.entry_id, label: 'Inspect review', variant: 'primary' },
      })));
    }
    if (attentionItems.length < 4) {
      attentionItems.push({
        title: 'Runtime controls',
        body: 'Memory, stats, settings and skills stay available as controls for the agent runtime without becoming a separate workflow.',
        meta: 'controls',
        action: { name: 'open-runtime-controls', value: 'settings', label: 'Open runtime controls', variant: 'ghost' },
      });
    }
    renderDashboardList('dashboard-attention-list', attentionItems.slice(0, 5), 'No immediate validation backlog. Escalations and admin-only follow-up will surface here.');
  } catch (e) {
    renderDashboardList('dashboard-workstreams-list', [], `Failed to load dashboard: ${e.message}`);
    renderDashboardList('dashboard-attention-list', [], 'Dashboard could not aggregate current state.');
  }
}

function renderWorkstreamCard(item) {
  const selected = item.workstream_id === state.selectedWorkstreamId;
  const status = item.operational_status === 'active' ? 'active' : item.operational_status === 'awaiting_review' ? 'review' : 'idle';
  return `
    <article data-workstream-card="${selected ? 'selected' : 'normal'}" data-workstream-id="${escHtml(item.workstream_id)}">
      <span data-workstream-status="${status}"></span>
      <div>
        <h4>${escHtml(previewText(item.goal || item.workstream_id, 58))}</h4>
        <p>${escHtml(item.workstream_id)} · ${escHtml(item.operational_status || 'active')} · ${escHtml(String(item.entry_count || 0))} entries</p>
      </div>
      <button data-workstream-open="${escHtml(item.workstream_id)}">Open</button>
    </article>`;
}

function renderResumeListSection(title, items, ordered = false) {
  return `
    <section data-panel="list">
      <h4>${escHtml(title)}</h4>
      ${renderMarkdown((items || []).map((item, index) => ordered ? `${index + 1}. ${item}` : `- ${item}`).join('\n') || '_none_')}
    </section>
  `;
}

function renderWorkstreamTimeline(items) {
  if (!items || !items.length) {
    return '<p data-note="muted">No timeline events yet.</p>';
  }
  return `
    <section data-timeline>
      ${items.map((item) => `
        <article data-timeline-item>
          <time>${escHtml(relTime(item.updated_at || item.created_at || ''))}</time>
          <div>
            <header data-pill-row>
              <span data-pill="mono">${escHtml(item.entry_kind || 'entry')}</span>
              ${item.entry_role ? `<span data-pill="default">${escHtml(item.entry_role)}</span>` : ''}
              ${item.session_id ? `<span data-pill="mono">execution:${escHtml(item.session_id)}</span>` : ''}
              <span data-pill="default">${escHtml(item.section || '')}</span>
            </header>
            <p>${escHtml(item.summary || 'No summary available.')}</p>
            ${item.related_entry_ids && item.related_entry_ids.length ? `<footer data-pill-row>${item.related_entry_ids.map((relatedId) => `<span data-pill="mono">${escHtml(relatedId)}</span>`).join('')}</footer>` : ''}
          </div>
        </article>
      `).join('')}
    </section>
  `;
}

function renderWorkstreamDetail() {
  const root = document.getElementById('workstream-detail-root');
  if (!state.selectedWorkstreamId) {
    root.innerHTML = '<article data-panel="empty">Select a workstream to inspect its current state, review, memory trail and handoff actions.</article>';
    return;
  }
  if (
    !state.workstreamDetail ||
    state.workstreamDetail.workstreamId !== state.selectedWorkstreamId ||
    !state.workstreamDetail.stateData ||
    !state.workstreamDetail.resumeData
  ) {
    root.innerHTML = '<article data-panel="loading">Loading workstream detail…</article>';
    return;
  }
  if (state.workstreamDetail.error) {
    root.innerHTML = `<article data-panel="danger">Failed to load workstream detail: ${escHtml(state.workstreamDetail.error)}</article>`;
    return;
  }

  const { workstreamId, stateData, resumeData, handoffData, handoffItems = [], reviewItems = [], reviewSummary = null } = state.workstreamDetail;
  const switchData = state.workstreamDetail.switchData || null;
  const focus = state.workstreamSurfaceFocus;

  let tabContent = '';

  if (focus === 'overview') {
    const nextExecutionPanel = `
      <section data-ui="workstream-section-overview" data-panel="default">
        <h4>Next execution package</h4>
        <p>${escHtml(resumeData.next_execution?.goal || resumeData.goal || '')}</p>
        <p>resume_mode=${escHtml(resumeData.next_execution?.resume_mode || 'goal_oriented')} essential=${escHtml((resumeData.next_execution?.essential_context || []).length)} optional=${escHtml((resumeData.next_execution?.optional_context || []).length)} risky=${escHtml((resumeData.next_execution?.risky_context || []).length)}</p>
      </section>
    `;
    const switchPanel = switchData ? `
      <section data-panel="default">
        <h4>Anti-context-switch package</h4>
        <p>${escHtml(switchData.current_workstream_id)} -> ${escHtml(switchData.target_workstream_id)}</p>
        <p>needed_now=${escHtml((switchData.state_gap?.needed_now_but_not_open || []).length)} optional=${escHtml((switchData.state_gap?.optional_to_load || []).length)} risky=${escHtml((switchData.state_gap?.risky_to_carry || []).length)}</p>
        <div data-pill-row>${(switchData.state_gap?.needed_now_but_not_open || []).map((item) => `<span data-pill="mono">${escHtml(item)}</span>`).join('') || '<span data-note="muted">Target already fits the current context.</span>'}</div>
      </section>
    ` : '';
    tabContent = `
      <section data-panel="default">
        <h4>Goal</h4>
        <p>${escHtml(resumeData.goal || '')}</p>
        <p>${escHtml(resumeData.summary || '')}</p>
      </section>
      <section data-metric-grid>
        <article data-metric-card><strong>${escHtml(stateData.entry_count)}</strong><small>Entries</small></article>
        <article data-metric-card><strong>${escHtml(reviewSummary?.pending_review_count ?? reviewItems.length)}</strong><small>Review pending</small></article>
      </section>
      ${nextExecutionPanel}
      ${switchPanel}
      ${renderResumeListSection('Current state', resumeData.current_state)}
      ${renderResumeListSection('Open loops', resumeData.open_loops)}
      ${renderResumeListSection('Next steps', resumeData.next_steps, true)}
      <section data-panel="default">
        <h4>Restore context</h4>
        <p>section=${escHtml(resumeData.restore_context?.section || '')} query=${escHtml(resumeData.restore_context?.query || '')} include_deleted=${resumeData.restore_context?.include_deleted ? 'true' : 'false'}</p>
      </section>
      <section data-panel="default">
        <h4>Related entries</h4>
        <div data-pill-row>${(resumeData.related_entry_ids || []).map((item) => `<span data-pill="mono">${escHtml(item)}</span>`).join('') || '<span data-note="muted">none</span>'}</div>
      </section>
      <section data-panel="default">
        <h4>Execution history</h4>
        <p>${escHtml(stateData.session_count)} recorded execution cycle(s) · latest execution ${escHtml(stateData.latest_entry?.session_id || resumeData.session_id || 'n/a')}</p>
      </section>
    `;
  } else if (focus === 'review') {
    tabContent = `
      <section data-ui="workstream-section-review" data-panel="default">
        <header data-row="space-between">
          <div>
            <h4>Review in this workstream</h4>
            <p>Validation stays attached to the operational workstream instead of floating as a separate workflow.</p>
          </div>
          <span data-pill="mono">pending:${escHtml(reviewSummary?.pending_review_count ?? reviewItems.length)}</span>
        </header>
        ${reviewItems.length ? `
          <section>
            ${reviewItems.slice(0, 4).map((item) => `
              <article data-panel="compact">
                <h4>${escHtml(previewText(item.summary || item.entry_id, 58))}</h4>
                <p>${escHtml(item.review_status || 'pending')} · ${(item.review_reasons || []).slice(0, 2).map((reason) => escHtml(reason)).join(', ') || 'no explicit reason'}</p>
                <footer data-actions>
                  <button data-variant="ghost" data-size="small" data-workstream-review-open="${escHtml(item.entry_id)}">Inspect review</button>
                </footer>
              </article>
            `).join('')}
          </section>
        ` : '<p data-note="muted">No pending review items for this workstream.</p>'}
        <footer data-actions>
          <button data-variant="ghost" data-size="small" data-ui="btn-persisted-workstream-review">Inspect review queue</button>
        </footer>
      </section>
    `;
  } else if (focus === 'handoffs') {
    const timeline = renderWorkstreamTimeline(stateData.timeline || []);
    const handoffGoal = handoffData?.goal ? `
      <section data-panel="default">
        <h4>Latest structured handoff</h4>
        <p>${escHtml(handoffData.goal)}</p>
        <p>${escHtml(handoffData.summary || '')}</p>
      </section>
    ` : '';
    tabContent = `
      <section data-ui="workstream-section-handoffs" data-panel="default">
        <header data-row="space-between">
          <div>
            <h4>Handoffs in this workstream</h4>
            <p>Continuity packages stay inside the same workstream so restore state and next execution stay visible together.</p>
          </div>
          <span data-pill="mono">count:${escHtml(handoffItems.length)}</span>
        </header>
        ${handoffItems.length ? `
          <section>
            ${handoffItems.slice(0, 4).map((entry) => `
              <article data-panel="compact">
                <h4>${escHtml(previewText(entry.summary || entry.id, 58))}</h4>
                <p>${escHtml(relTime(entry.updated_at || entry.created_at || ''))} · execution ${escHtml(entry.session_id || 'not recorded')}</p>
                <p>${escHtml(previewText(entry.summary || 'No handoff summary available.', 140))}</p>
                <footer data-actions>
                  <button data-variant="ghost" data-size="small" data-workstream-handoff-open="${escHtml(entry.id)}">Open handoff</button>
                  <button data-variant="ghost" data-size="small" data-workstream-handoff-state="${escHtml(entry.id)}">State</button>
                </footer>
              </article>
            `).join('')}
          </section>
        ` : '<p data-note="muted">No handoffs recorded for this workstream yet.</p>'}
      </section>
      <section data-panel="default">
        <h4>Workstream timeline</h4>
        ${timeline}
      </section>
      ${handoffGoal}
    `;
  }

  root.innerHTML = `
    <article data-panel="shell">
      <header>
        <div>
          <h3>${escHtml(workstreamId)}</h3>
          <p>Inspect one operational workstream: memory, review, handoff and next actions in the same context.</p>
        </div>
      </header>
      ${tabContent}
      <footer data-actions>
        <button data-variant="ghost" data-size="small" data-ui="btn-persisted-workstream-state">State</button>
      </footer>
    </article>
  `;

  renderWorkstreamSurfaceTabs();
  document.getElementById('btn-persisted-workstream-state').addEventListener('click', async () => await openWorkstreamStateModal(workstreamId, null));
  document.getElementById('btn-persisted-workstream-review')?.addEventListener('click', async () => {
    await setWorkstreamSurfaceFocus('review', { ensureSelected: true, scroll: true });
  });
  root.querySelectorAll('[data-workstream-review-open]').forEach((button) => {
    button.addEventListener('click', async () => {
      state.selectedReviewId = button.dataset.workstreamReviewOpen;
      await setWorkstreamSurfaceFocus('review', { ensureSelected: true, scroll: true });
    });
  });
  root.querySelectorAll('[data-workstream-handoff-open]').forEach((button) => {
    button.addEventListener('click', () => {
      const entry = handoffItems.find((item) => item.id === button.dataset.workstreamHandoffOpen);
      if (entry) openHandoffViewModal(entry);
    });
  });
  root.querySelectorAll('[data-workstream-handoff-state]').forEach((button) => {
    button.addEventListener('click', async () => {
      const entry = handoffItems.find((item) => item.id === button.dataset.workstreamHandoffState);
      if (entry?.workstream_id) await openWorkstreamStateModal(entry.workstream_id, entry.session_id || null);
    });
  });
}

async function selectWorkstream(workstreamId) {
  state.selectedWorkstreamId = workstreamId;
  state.workstreamDetail = { workstreamId };
  renderWorkstreams(state.workstreams);
  renderWorkstreamDetail();
  try {
    const [stateData, resumeData, reviewData, reviewSummary] = await Promise.all([
      api.workstreamState(workstreamId, { include_deleted: 'false' }),
      api.workstreamResume(workstreamId, { include_deleted: 'false' }),
      api.reviewQueue({ workstream_id: workstreamId, pending_only: 'true', limit: '6' }).catch(() => ({ items: [] })),
      api.reviewWorkstream(workstreamId).catch(() => null),
    ]);
    const handoffData = stateData.latest_handoff ? await api.readStructuredHandoff(workstreamId, { include_deleted: 'true' }).catch(() => null) : null;
    const alternateWorkstream = (state.workstreams || []).find((item) => item.workstream_id !== workstreamId)?.workstream_id || null;
    const switchData = alternateWorkstream
      ? await api.workstreamSwitchPackage({ current_workstream_id: workstreamId, target_workstream_id: alternateWorkstream }).catch(() => null)
      : null;
    const handoffItems = (stateData.timeline || [])
      .filter((item) => item.entry_kind === 'handoff')
      .map((item) => ({ ...item, workstream_id: workstreamId }));
    state.workstreamDetail = { workstreamId, stateData, resumeData, handoffData, handoffItems, reviewItems: reviewData.items || [], reviewSummary, switchData };
  } catch (e) {
    state.workstreamDetail = { workstreamId, error: e.message };
  }
  renderWorkstreamDetail();
  scrollWorkstreamSurfaceSection(false);
}

function renderWorkstreams(items) {
  const grid = document.getElementById('workstream-grid');
  renderWorkstreamSummary(items);
  if (!items.length) {
    grid.innerHTML = '<article data-panel="empty">No workstreams yet. Open a workstream to manage state, review, memory trail and handoffs from one place.</article>';
    state.selectedWorkstreamId = null;
    state.workstreamDetail = null;
    renderWorkstreamDetail();
    return;
  }
  grid.innerHTML = items.map(renderWorkstreamCard).join('');
  grid.querySelectorAll('[data-workstream-open]').forEach((button) => {
    button.addEventListener('click', async () => {
      await selectWorkstream(button.dataset.workstreamOpen);
    });
  });
  grid.querySelectorAll('[data-workstream-state-card]').forEach((button) => {
    button.addEventListener('click', async () => {
      await openWorkstreamStateModal(button.dataset.workstreamStateCard, null);
    });
  });
}

function renderWorkstreamSurfaceTabs() {
  document.querySelectorAll('[data-workstream-surface]').forEach((button) => {
    const isActive = button.dataset.workstreamSurface === state.workstreamSurfaceFocus;
    if (isActive) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
}

function scrollWorkstreamSurfaceSection(smooth = true) {
  const activeSection = document.getElementById(`workstream-section-${state.workstreamSurfaceFocus}`);
  if (activeSection) {
    activeSection.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' });
  }
}

async function setWorkstreamSurfaceFocus(focus, options = {}) {
  state.workstreamSurfaceFocus = focus || 'overview';
  renderWorkstreamSurfaceTabs();
  const ensureSelected = options.ensureSelected !== false;
  if (ensureSelected && !state.selectedWorkstreamId && state.workstreams[0]?.workstream_id) {
    await selectWorkstream(state.workstreams[0].workstream_id);
  } else {
    renderWorkstreamDetail();
  }
  if (options.scroll !== false) scrollWorkstreamSurfaceSection(true);
}

async function loadWorkstreams() {
  try {
    const [data, queueData] = await Promise.all([
      api.workstreams({ include_deleted: String(state.workstreamsIncludeDeleted), limit: '50' }),
      api.workstreamQueue({ limit: '12' }).catch(() => ({ items: [] })),
    ]);
    state.workstreams = data.items || [];
    state.workstreamQueueItems = queueData.items || [];
    renderWorkstreams(state.workstreams);
    renderOperationalQueue(state.workstreamQueueItems);
    renderWorkstreamSummary(state.workstreams);
    const availableIds = new Set(state.workstreams.map((item) => item.workstream_id));
    const nextSelected = availableIds.has(state.selectedWorkstreamId) ? state.selectedWorkstreamId : state.workstreams[0]?.workstream_id || null;
    if (!nextSelected) {
      state.selectedWorkstreamId = null;
      state.workstreamDetail = null;
      renderWorkstreamDetail();
      return;
    }
    await selectWorkstream(nextSelected);
  } catch (e) {
    document.getElementById('workstream-grid').innerHTML = `<article data-panel="danger">Failed to load workstreams: ${escHtml(e.message)}</article>`;
    const queueRoot = document.getElementById('workstream-queue-list');
    if (queueRoot) queueRoot.innerHTML = `<article data-panel="danger">Failed to load operational queue: ${escHtml(e.message)}</article>`;
    document.getElementById('workstream-detail-root').innerHTML = '';
  }
}



function openHandoffViewModal(entry) {
  openModal(modalShell(`
    <header data-modal-header>
      <div>
        <h3>Handoff</h3>
        <p>${escHtml(entry.id)} · ${escHtml(relTime(entry.updated_at || entry.created_at))}</p>
      </div>
      <button data-modal-close>×</button>
    </header>
    <section data-modal-body>
      ${renderMarkdown(entry.content)}
      <footer data-pill-row>
        <span data-pill="mono">${escHtml(entry.id)}</span>
        ${entry.workstream_id ? `<span data-pill="mono">workstream:${escHtml(entry.workstream_id)}</span>` : ''}
        ${entry.session_id ? `<span data-pill="mono">session:${escHtml(entry.session_id)}</span>` : ''}
        ${(entry.tags || []).map((tag) => `<span data-pill="default">${escHtml(tag)}</span>`).join('')}
      </footer>
    </section>
    <footer data-modal-footer>
      ${entry.workstream_id ? `<button data-variant="ghost" data-ui="btn-handoff-open-state">Workstream state</button>` : ''}
      ${entry.workstream_id ? `<button data-variant="ghost" data-ui="btn-handoff-open-resume">Workstream resume</button>` : ''}
      <button data-variant="primary" data-ui="btn-handoff-history">History</button>
    </footer>
  `, 'modal-panel--wide'));
  if (entry.workstream_id) {
    document.getElementById('btn-handoff-open-state').addEventListener('click', async () => {
      await openWorkstreamStateModal(entry.workstream_id, entry.session_id || null);
    });
    document.getElementById('btn-handoff-open-resume').addEventListener('click', async () => {
      await openWorkstreamResumeModal(entry.workstream_id, entry.session_id || null);
    });
  }
  document.getElementById('btn-handoff-history').addEventListener('click', () => {
    closeModal();
    openVersionsModal(entry);
  });
}

async function openWorkstreamStateModal(workstreamId, sessionId = null) {
  try {
    const params = { include_deleted: 'false' };
    if (sessionId) params.session_id = sessionId;
    const data = await api.workstreamState(workstreamId, params);
    const sessions = (data.sessions || []).map((session) => `
      <article data-panel="compact">
        <h4>${escHtml(session.session_id || '(none)')}</h4>
        <p>entries=${escHtml(session.entry_count)} latest=${escHtml(session.latest_entry_id || '')}</p>
      </article>
    `).join('') || '<p data-note="muted">No sessions aggregated.</p>';
    openModal(modalShell(`
      <header data-modal-header>
        <div>
          <h3>Workstream state</h3>
          <p>${escHtml(workstreamId)}${sessionId ? ` · ${escHtml(sessionId)}` : ''}</p>
        </div>
        <button data-modal-close>×</button>
      </header>
      <section data-modal-body>
        <section data-metric-grid>
          <article data-metric-card><strong>${escHtml(data.entry_count)}</strong><small>Entries</small></article>
          <article data-metric-card><strong>${escHtml(data.session_count)}</strong><small>Sessions</small></article>
        </section>
        <section data-panel="default">
          <h4>Latest entry</h4>
          <p>${escHtml(data.latest_entry?.id || '')}</p>
          <p>kind=${escHtml(data.latest_entry?.entry_kind || '')} session=${escHtml(data.latest_entry?.session_id || '')}</p>
        </section>
        <section data-metric-grid>
          <article data-metric-card><strong>${escHtml(data.latest_handoff?.id || '—')}</strong><small>Latest handoff</small></article>
          <article data-metric-card><strong>${escHtml(data.latest_state?.id || '—')}</strong><small>Latest state</small></article>
        </section>
        <section>
          <h4>Aggregated sessions</h4>
          <div data-metric-grid>${sessions}</div>
        </section>
      </section>
      <footer data-modal-footer>
        <button data-variant="ghost" onclick="closeModal()">Close</button>
      </footer>
    `, 'modal-panel--wide'));
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function openWorkstreamResumeModal(workstreamId, sessionId = null) {
  try {
    const params = { include_deleted: 'false' };
    if (sessionId) params.session_id = sessionId;
    const data = await api.workstreamResume(workstreamId, params);
    const listBlock = (title, items, ordered = false) => `
      <section data-panel="default">
        <h4>${escHtml(title)}</h4>
        ${renderMarkdown((items || []).map((item, index) => ordered ? `${index + 1}. ${item}` : `- ${item}`).join('\n') || '_none_')}
      </section>
    `;
    openModal(modalShell(`
      <header data-modal-header>
        <div>
          <h3>Workstream resume</h3>
          <p>${escHtml(workstreamId)}${sessionId ? ` · ${escHtml(sessionId)}` : ''}</p>
        </div>
        <button data-modal-close>×</button>
      </header>
      <section data-modal-body>
        <section data-panel="default">
          <h4>Goal</h4>
          <p>${escHtml(data.goal || '')}</p>
          <p>${escHtml(data.summary || '')}</p>
        </section>
        <section data-metric-grid>
          <article data-metric-card><strong>${escHtml(data.latest_entry_id || '')}</strong><small>Latest entry</small></article>
          <article data-metric-card><strong>${escHtml((data.focus_entry_ids || []).join(', ') || 'none')}</strong><small>Focus entries</small></article>
        </section>
        ${listBlock('Current state', data.current_state)}
        ${listBlock('Open loops', data.open_loops)}
        ${listBlock('Next steps', data.next_steps, true)}
        <section data-panel="default">
          <h4>Restore context</h4>
          <p>section=${escHtml(data.restore_context?.section || '')} query=${escHtml(data.restore_context?.query || '')} include_deleted=${data.restore_context?.include_deleted ? 'true' : 'false'}</p>
        </section>
        <section data-panel="default">
          <h4>Compressed context</h4>
          <div data-pill-row>
            <span data-pill="mono">essential:${escHtml((data.compressed_context?.essential || []).length)}</span>
            <span data-pill="mono">optional:${escHtml((data.compressed_context?.optional || []).length)}</span>
            <span data-pill="mono">archived:${escHtml((data.compressed_context?.archived || []).length)}</span>
            <span data-pill="mono">risky:${escHtml((data.compressed_context?.risky || []).length)}</span>
            <span data-pill="mono">obsolete:${escHtml((data.compressed_context?.obsolete || []).length)}</span>
          </div>
        </section>
        <section data-panel="default">
          <h4>Next execution package</h4>
          <p>${escHtml(data.next_execution?.goal || data.goal || '')}</p>
          <p>resume_mode=${escHtml(data.next_execution?.resume_mode || 'goal_oriented')} essential=${escHtml((data.next_execution?.essential_context || []).length)} risky=${escHtml((data.next_execution?.risky_context || []).length)}</p>
        </section>
        <section data-panel="default">
          <h4>What changed since the last anchor</h4>
          ${renderMarkdown((data.what_changed || []).map((item) => `- ${item.summary || item.id}`).join('\n') || '_none_')}
        </section>
        <section data-panel="default">
          <h4>Related entries</h4>
          <div data-pill-row>${(data.related_entry_ids || []).map((item) => `<span data-pill="mono">${escHtml(item)}</span>`).join('') || '<span data-note="muted">none</span>'}</div>
        </section>
      </section>
      <footer data-modal-footer>
        <button data-variant="ghost" onclick="closeModal()">Close</button>
      </footer>
    `, 'modal-panel--wide'));
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

function statsSummary(statsData) {
  if (!statsData) return null;
  const sections = statsData.sections || {};
  return {
    total: statsData.total_entries ?? 0,
    activeSections: Object.values(sections).filter((n) => n > 0).length,
    sizeKb: statsData.store_size_kb,
    storage: statsData.storage_backend || state.config?.storage_backend || 'json',
    deleted: statsData.deleted_entries ?? 0,
    sections,
    oldest: statsData.oldest || '—',
    newest: statsData.newest || '—',
  };
}

function renderStats(statsData) {
  const s = statsSummary(statsData);
  if (!s) return;
  document.getElementById('stat-total').textContent = s.total ?? '—';
  document.getElementById('stat-sections').textContent = s.activeSections;
  document.getElementById('stat-size').textContent = s.sizeKb != null ? `${Math.round(s.sizeKb)} KB` : '—';
  const storageEl = document.getElementById('stat-storage');
  if (storageEl) storageEl.textContent = s.storage;
  document.getElementById('stat-deleted').textContent = s.deleted;
  document.getElementById('count-all').textContent = s.total ?? '';
  for (const [sec, cnt] of Object.entries(s.sections)) {
    const el = document.getElementById(`count-${sec}`);
    if (el) el.textContent = cnt;
  }
}

function applyDashboardStats(statsData) {
  const s = statsSummary(statsData);
  if (!s) return;
  document.getElementById('dash-total').textContent = s.total;
  document.getElementById('dash-active-sec').textContent = s.activeSections;
  document.getElementById('dash-size').textContent = s.sizeKb != null ? Math.round(s.sizeKb) : '—';
  const dashStorage = document.getElementById('dash-storage');
  if (dashStorage) dashStorage.textContent = s.storage;
  document.getElementById('dash-oldest').textContent = s.oldest;
  document.getElementById('dash-newest').textContent = s.newest;
  document.getElementById('dash-updated').textContent = `Updated ${relTime(new Date().toISOString())} · Deleted ${s.deleted}`;
  const sectionsList = state.config?.sections || [];
  const maxCount = Math.max(...Object.values(s.sections), 1);
  const barsHtml = sectionsList.map((sec) => {
    const count = s.sections[sec] || 0;
    const pct = Math.round((count / maxCount) * 100);
    const color = sectionColor(sec);
    return `<article data-stat-bar>
      <span>${escHtml(sec)}</span>
      <div style="flex:1;height:8px;border-radius:999px;background:#edf2f7;overflow:hidden"><div style="width:${pct}%;height:100%;background:${color}"></div></div>
      <strong>${count}</strong>
    </article>`;
  }).join('');
  document.getElementById('dash-section-bars').innerHTML = barsHtml || '<span data-note="muted">No sections configured.</span>';
}

function renderEntryCard(entry) {
  const theme = sectionTheme(entry.section);
  const themeStyle = themeVars(theme);
  const allTags = entry.tags || [];
  const visibleTags = allTags.slice(0, 3).map((t) =>
    `<span data-pill="default" style="${themeStyle}">${escHtml(t)}</span>`
  ).join('');
  const hiddenCount = allTags.length - 3;
  const overflowPill = hiddenCount > 0
    ? `<span data-pill="default">+${hiddenCount}</span>`
    : '';
  const tagsRow = `<div data-pill-row>${visibleTags}${overflowPill}</div>`;
  const scoreBadge = entry.score != null
    ? `<span data-pill="mono" style="${themeStyle}">${(entry.score * 100).toFixed(0)}%</span>`
    : '';
  const isEdited = entry.updated_at && entry.updated_at !== entry.created_at;
  const displayTime = isEdited ? relTime(entry.updated_at) : relTime(entry.created_at);
  const timeTitle = isEdited ? `Created: ${entry.created_at}\nEdited: ${entry.updated_at}` : (entry.created_at || '');
  const accessBadge = (entry.access_count || 0) > 0
    ? `<time title="Accessed ${entry.access_count} time${entry.access_count === 1 ? '' : 's'}">↻ ${entry.access_count}</time>`
    : '';
  const deletedBadge = entry.deleted_at
    ? `<span data-pill="default">Deleted ${escHtml(relTime(entry.deleted_at))}</span>`
    : '';

  return `
    <article data-panel="solid" data-id="${escHtml(entry.id)}" style="${themeStyle}">
      <div style="background:linear-gradient(90deg, ${rgba(theme.color, 0.85)} 0%, ${rgba(theme.color, 0.18)} 100%);height:4px;border-radius:999px"></div>
      <header data-row="space-between">
        <div data-pill-row>
          <span style="width:8px;height:8px;border-radius:999px;background:${theme.color};display:inline-block"></span>
          ${escHtml(entry.section)}
        </div>
        <div data-pill-row>
          ${deletedBadge}
          ${scoreBadge}
          <time title="${escHtml(timeTitle)}">${isEdited ? '✎ ' : ''}${displayTime}</time>
        </div>
      </header>
      <section>
        ${renderMarkdown(entry.content)}
        ${tagsRow}
      </section>
      <footer data-row="space-between">
        ${accessBadge}
        <span data-pill="mono">${escHtml(entry.id)}</span>
      </footer>
    </article>`;
}

function renderCards(entries, append = false) {
  const grid = document.getElementById('cards-grid');
  if (!append) grid.innerHTML = '';

  if (entries.length === 0 && !append) {
    grid.innerHTML = `
      <article data-panel="empty" style="padding: 64px 20px; border-style: dashed; text-align:center;">
        <div style="font-size: 48px; margin-bottom: 16px;">📭</div>
        <h3 style="font-size: 18px; font-weight: 500; color: var(--fg); margin: 0 0 8px 0;">${state.searchMode ? 'No results found' : 'No entries yet'}</h3>
        <p style="font-size: 14px; color: var(--mute); margin: 0;">${state.searchMode ? 'Try a different search term.' : 'No agent memory recorded yet.'}</p>
      </article>`;
    return;
  }

  for (const entry of entries) {
    const div = document.createElement('div');
    div.innerHTML = renderEntryCard(entry).trim();
    const card = div.firstChild;
    card.addEventListener('click', () => openViewModal(entry));
    grid.appendChild(card);
  }
}

async function loadConfig() {
  try {
    [state.config, { models: semanticModels }] = await Promise.all([api.config(), api.models()]);
    state.limit = state.config.entry_batch_size || 24;
    renderSections();
  } catch (e) {
    toast('Failed to load config: ' + e.message, 'error');
  }
}

async function loadStats() {
  try {
    const stats = await api.stats();
    state.total = stats.total_entries ?? 0;
    renderSections();
    renderStats(stats);
  } catch (e) {
  }
}

async function loadEntries(append = false) {
  if (state.loading) return;
  state.loading = true;
  const grid = document.getElementById('cards-grid');
  if (!append) {
    grid.innerHTML = '<article data-panel="loading">Loading…</article>';
  }

  const offset = append ? state.offset : 0;
  const params = { offset, limit: state.limit, sort_by: state.sort_by, descending: state.descending };
  if (state.section) params.section = state.section;
  if (state.includeDeleted) params.include_deleted = 'true';

  try {
    const data = await api.entries(params);
    const items = data.items || [];
    const total = data.total ?? 0;

    if (!append) {
      state.entries = items;
      state.offset = items.length;
    } else {
      state.entries = [...state.entries, ...items];
      state.offset += items.length;
    }
    state.total = total;
    state.hasMore = data.has_more ?? false;

    document.getElementById('section-title').textContent = state.section || 'Memory';
    document.getElementById('total-badge').textContent = total ? `${total} entries` : '';

    renderCards(items, append);
    renderSections();
    document.getElementById('load-more-wrap').hidden = !state.hasMore;
    await loadStats();
  } catch (e) {
    toast('Failed to load entries: ' + e.message, 'error');
    grid.innerHTML = '';
  } finally {
    state.loading = false;
  }
}

async function doSearch(query) {
  if (!query.trim()) {
    clearSearch();
    return;
  }

  state.searchMode = true;
  state.searchQuery = query;
  const grid = document.getElementById('cards-grid');
  grid.innerHTML = '<article data-panel="loading">Searching…</article>';
  document.getElementById('load-more-wrap').hidden = true;
  document.getElementById('sort-select').hidden = true;
  document.getElementById('section-title').textContent = 'Search results';
  document.getElementById('total-badge').textContent = '';
  document.getElementById('search-results-bar').hidden = false;

  try {
    const params = { q: query, top_k: 40 };
    if (state.section) params.section = state.section;
    if (state.includeDeleted) params.include_deleted = 'true';
    const data = await api.search(params);
    const results = data.results || [];
    document.getElementById('search-results-label').textContent = `${results.length} result${results.length !== 1 ? 's' : ''} for "${query}"`;
    renderCards(results, false);
    renderSections();
  } catch (e) {
    toast('Search failed: ' + e.message, 'error');
    grid.innerHTML = '';
  }
}

function clearSearch(silent = false) {
  state.searchMode = false;
  state.searchQuery = '';
  document.getElementById('search-input').value = '';
  document.getElementById('search-results-bar').hidden = true;
  document.getElementById('sort-select').hidden = false;
  if (!silent && state.config) loadEntries();
}

function selectSection(section) {
  state.section = section || null;
  state.offset = 0;
  loadEntries();
  renderSections();
}

function closeModal() {
  document.getElementById('modal-root').innerHTML = '';
  document.removeEventListener('keydown', handleEsc);
}

function openModal(html) {
  const root = document.getElementById('modal-root');
  root.innerHTML = `<div data-ui="modal-backdrop" data-modal-overlay="true">${html}</div>`;
  stripClassesFromTree(root);
  ui('modal-backdrop', root).addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
  });
  const closeButton = Array.from(root.querySelectorAll('button')).find((button) => {
    const text = (button.textContent || '').trim();
    return text === '×' || text === '✕' || text.toLowerCase() === 'x';
  });
  closeButton?.addEventListener('click', closeModal);
  document.addEventListener('keydown', handleEsc);
}

function handleEsc(e) {
  if (e.key === 'Escape') closeModal();
}

function buildSectionOptions(selected) {
  if (!state.config) return '';
  return (state.config.sections || []).map((s) =>
    `<option value="${escHtml(s)}" ${s === selected ? 'selected' : ''}>${escHtml(s)}</option>`
  ).join('');
}

function modalShell(inner, extraClasses = '') {
  const shell = extraClasses ? String(extraClasses).trim() : 'default';
  return `<article data-modal-panel="${escHtml(shell)}">${inner}</article>`;
}

function openViewModal(entry) {
  const theme = sectionTheme(entry.section);
  const themeStyle = themeVars(theme);
  const isEdited = entry.updated_at && entry.updated_at !== entry.created_at;
  const timeLabel = isEdited ? `Edited ${relTime(entry.updated_at)} · Created ${relTime(entry.created_at)}` : `Created ${relTime(entry.created_at)}`;
  const tags = (entry.tags || []).map((t) => `<span data-pill="default" style="${themeStyle}">${escHtml(t)}</span>`).join('');
  const scoreBadge = entry.score != null ? `<span data-pill="mono" style="${themeStyle}">${(entry.score * 100).toFixed(0)}%</span>` : '';
  const accessBadge = (entry.access_count || 0) > 0 ? `<time title="Accessed ${entry.access_count} time${entry.access_count === 1 ? '' : 's'}">↻ ${entry.access_count}</time>` : '';
  const deletedNotice = entry.deleted_at
    ? `<article data-panel="danger">Deleted ${escHtml(relTime(entry.deleted_at))}. History remains available for inspection.</article>`
    : '';

  openModal(modalShell(`
    <div style="${themeStyle}"></div>
    <header data-modal-header style="${themeStyle}">
      <div data-pill-row>
        <div data-pill="default" style="${themeStyle}">
          <span></span>
          ${escHtml(entry.section)}
        </div>
        ${scoreBadge}
        <time>${escHtml(timeLabel)}</time>
      </div>
      <button data-modal-close>×</button>
    </header>
    <section data-modal-body>
      ${deletedNotice}
      ${renderMarkdown(entry.content)}
      ${tags ? `<div data-pill-row>${tags}</div>` : ''}
      <footer data-pill-row>
        ${accessBadge}
        <span data-pill="mono">${escHtml(entry.id)}</span>
      </footer>
    </section>
    <footer data-modal-footer>
      <button data-variant="ghost" data-ui="btn-view-history">History</button>
    </footer>
  `, 'modal-panel--reading'));
  document.getElementById('btn-view-history').addEventListener('click', () => { closeModal(); openVersionsModal(entry); });
}

async function openDiffModal(entry, fromVersion, toVersion) {
  try {
    const data = await api.diffVersions(entry.id, { from_version: String(fromVersion), to_version: String(toVersion) });
    const diffText = data.diff || '(no content changes)';
    openModal(modalShell(`
      <header data-modal-header>
        <div>
          <h3>Diff for ${escHtml(entry.id)}</h3>
          <p>v${fromVersion} → v${toVersion}</p>
        </div>
        <button data-modal-close>×</button>
      </header>
      <section data-modal-body>
        <section>
          <h4>Side-by-side diff</h4>
          ${renderSideBySideDiff(diffText)}
        </section>
        <section>
          <h4>Unified diff</h4>
          <pre>${escHtml(diffText)}</pre>
        </section>
      </section>
    `, 'modal-panel--wide'));
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function openVersionsModal(entry) {
  try {
    const data = await api.entryVersions(entry.id, { include_deleted: 'true' });
    const versions = data.versions || [];
    const currentVersion = versions[versions.length - 1]?.version;
    const previousVersion = versions.length > 1 ? versions[versions.length - 2]?.version : currentVersion;

    openModal(modalShell(`
      <header data-modal-header>
        <div>
          <h3>Version history</h3>
          <p>${escHtml(entry.id)} · ${versions.length} revision(s)</p>
        </div>
        <button data-modal-close>×</button>
      </header>
      <section data-modal-body>
        <article data-panel="soft">
          <h4>Compare revisions</h4>
          <p>Timeline stays focused on current vs previous for quick inspection. Older revisions can still be diffed against the current state directly from the timeline.</p>
        </article>
        <h4>Timeline</h4>
        <section data-timeline data-ui="timeline-root"></section>
      </section>
    `, 'modal-panel--wide'));

    const timelineRoot = document.getElementById('timeline-root');

    function renderTimeline() {
      timelineRoot.innerHTML = versions.slice().reverse().map((revision, index) => {
        const isCurrent = revision.version === currentVersion;
        const isLast = index === versions.length - 1;
        const isSelectedFrom = revision.version === previousVersion && previousVersion !== currentVersion;
        const isSelectedTo = revision.version === currentVersion;
        const theme = sectionTheme(revision.section || entry.section);
        const preview = previewText(revision.content, 120);
        const activeBorder = isSelectedFrom || isSelectedTo ? `border-color:${theme.color}; box-shadow:0 0 0 1px ${theme.color}, 0 8px 24px ${theme.glow};` : '';
        return `
          <article data-timeline-item data-timeline-card="${revision.version}">
            ${!isLast ? '<span style="height:1px"></span>' : ''}
            <div style="${activeBorder}">
              <header data-pill-row style="background:${theme.faint};padding:8px;border-radius:10px;">
                <span data-pill="mono">v${revision.version}</span>
                <span data-pill="default">${escHtml(revision.section || '')}</span>
                ${revision.deleted_at ? '<span data-pill="default">deleted</span>' : ''}
                ${isCurrent ? '<span data-pill="default">current</span>' : ''}
                ${isSelectedFrom ? '<span data-pill="default">from</span>' : ''}
                ${isSelectedTo ? '<span data-pill="default">to</span>' : ''}
                <time>${escHtml(relTime(revision.updated_at || revision.created_at))}</time>
              </header>
              <p>${escHtml(preview)}</p>
              <footer data-pill-row>
                <span data-pill="mono">Created ${escHtml(relTime(revision.created_at))}</span>
                <span data-pill="mono">Updated ${escHtml(relTime(revision.updated_at || revision.created_at))}</span>
                ${!isCurrent ? `<button data-variant="ghost" data-size="small" data-diff-version="${revision.version}">Diff to current</button>` : ''}
              </footer>
            </div>
          </article>`;
      }).join('');

      timelineRoot.querySelectorAll('[data-diff-version]').forEach((button) => {
        button.addEventListener('click', () => openDiffModal(entry, button.dataset.diffVersion, currentVersion));
      });
    }

    renderTimeline();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

function openConsolidateModal() {
  const sections = state.config?.sections || [];
  const opts = sections.map((s) => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join('');
  openModal(modalShell(`
    <header data-modal-header>
      <h3>Consolidate duplicates</h3>
      <button data-modal-close>×</button>
    </header>
    <section data-modal-body>
      <section>
        <label>Section <small>(optional)</small></label>
        <select data-ui="f-cons-section">
          <option value="">All sections</option>
          ${opts}
        </select>
      </section>
      <section>
        <label>Mode</label>
        <select data-ui="f-cons-mode">
          <option value="exact">Exact (normalized content match)</option>
          <option value="semantic">Semantic (similarity threshold)</option>
        </select>
      </section>
      <section data-ui="threshold-group" hidden>
        <label>Similarity threshold</label>
        <input type="number" data-ui="f-threshold" value="0.88" step="0.01" min="0.5" max="1.0">
        <p>Higher = stricter (less aggressive). Range: 0.5 – 1.0</p>
      </section>
    </section>
    <footer data-modal-footer>
      <button data-variant="ghost" onclick="closeModal()">Cancel</button>
      <button data-variant="primary" data-ui="btn-run-consolidate">Run</button>
    </footer>
  `, 'modal-panel--compact'));

  const modeSelect = document.getElementById('f-cons-mode');
  const thresholdGroup = document.getElementById('threshold-group');
  modeSelect.addEventListener('change', () => {
    thresholdGroup.hidden = modeSelect.value !== 'semantic';
  });

  document.getElementById('btn-run-consolidate').addEventListener('click', async () => {
    const section = document.getElementById('f-cons-section').value || null;
    const mode = modeSelect.value;
    const threshold = parseFloat(document.getElementById('f-threshold').value) || 0.88;
    try {
      const data = await api.consolidate({ section, mode, similarity_threshold: threshold });
      closeModal();
      const result = data.result || {};
      const removed = result.removed_count ?? result.removed ?? result.merged ?? 0;
      toast(`Consolidation complete. Removed: ${removed} duplicate(s).`, 'success', 5000);
      await loadEntries();
    } catch (e) {
      toast('Error: ' + e.message, 'error');
    }
  });
}

function switchView(name) {
  if (name === 'review' || name === 'handoffs') {
    state.workstreamSurfaceFocus = name === 'review' ? 'review' : 'handoffs';
    name = 'workstreams';
  }
  state.view = name;
  document.querySelectorAll('[data-view-panel]').forEach((view) => {
    view.hidden = true;
  });
  document.getElementById(`view-${name}`).hidden = false;
  document.querySelectorAll('nav button[data-nav-view]').forEach((tab) => {
    const active = tab.dataset.view === name;
    if (active) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  });
  // search always visible in sidebar
  if (name === 'dashboard') renderDashboardView();
  else if (name === 'stats') renderStatsView();
  else if (name === 'skills') renderSkillsView();
  else if (name === 'settings') renderSettingsPage();
  else if (name === 'workstreams') loadWorkstreams();
}

async function renderStatsView() {
  try {
    const stats = await api.stats();
    applyDashboardStats(stats);
    const recent = await api.entries({ offset: 0, limit: 8, sort_by: 'recent', descending: true });
    const items = recent.items || [];
    const recentHtml = items.map((e) => {
      const color = sectionColor(e.section);
      return `<article data-row="space-between">
        <span style="width:8px;height:8px;border-radius:999px;background:${color};display:inline-block"></span>
        <span>${escHtml(e.content)}</span>
        <time>${relTime(e.updated_at || e.created_at)}</time>
      </article>`;
    }).join('');
    document.getElementById('dash-recent-list').innerHTML = recentHtml || '<span data-note="muted">No entries yet.</span>';
  } catch (e) {
    toast('Stats error: ' + e.message, 'error');
  }
}

async function openSkillModal(skillId) {
  try {
    const data = await api.skill(skillId);
    const skill = data.skill;
    const parsed = parseFrontmatter(skill?.content || '');
    const body = parsed.body || '';
    openModal(modalShell(`
      <header data-modal-header>
        <div>
          <h3>${escHtml(skill.name || skill.id || 'Skill')}</h3>
          <p>${escHtml(skill.path || '')}</p>
        </div>
        <button data-modal-close>✕</button>
      </header>
      <section data-modal-body>
        <p>${escHtml(skill.description || '')}</p>
        ${renderSkillFrontmatter(parsed.attributes)}
        ${renderMarkdown(body)}
      </section>
    `, 'modal-panel--xl'));
  } catch (e) {
    toast('Skills error: ' + e.message, 'error');
  }
}

function renderSkillsCards(skills) {
  if (!skills.length) {
    return '<article data-panel="empty">No bundled skills found.</article>';
  }

  return `<section data-metric-grid>${skills.map((skill) => `
    <article data-panel="shell" data-open-skill="${escHtml(skill.id || '')}" role="button" tabindex="0" aria-label="View skill ${escHtml(skill.name || skill.id || 'skill')}">
      <h4>${escHtml(skill.name || skill.id)}</h4>
      <p>${escHtml(skill.description || 'No description.')}</p>
      <small title="${escHtml(skill.path || '')}">${escHtml(skill.path || '')}</small>
    </article>
  `).join('')}</section>`;
}

function renderSkillsPackageBanner(info) {
  const banner = document.getElementById('skills-package-banner');
  if (!banner) return;
  if (!info || info.skills_installed) {
    banner.hidden = true;
    banner.innerHTML = '';
    return;
  }
  banner.hidden = false;
  banner.innerHTML = `
    <p><strong>rememb-skills is not installed.</strong> Install optional skills with
    <code>pip install rememb-skills</code> or <code>pip install rememb[skills]</code>.</p>`;
}

async function renderSkillsView() {
  const root = document.getElementById('skills-root');
  root.innerHTML = '<article data-panel="loading">Loading…</article>';
  try {
    const [data, info] = await Promise.all([
      api.skills(),
      state.systemInfo ? Promise.resolve(state.systemInfo) : api.systemInfo(),
    ]);
    state.systemInfo = info;
    renderSkillsPackageBanner(info);
    const skills = data.skills || [];
    state.skills = skills;
    if (!skills.length && !info?.skills_installed) {
      root.innerHTML = '<article data-panel="empty">No skills available. Install the rememb-skills package to browse bundled agent skills.</article>';
    } else if (!skills.length) {
      root.innerHTML = '<article data-panel="empty">No bundled skills found.</article>';
    } else {
      root.innerHTML = renderSkillsCards(skills);
    }
    document.getElementById('skills-updated').textContent = `${skills.length} skills · ${relTime(new Date().toISOString())}`;
    root.querySelectorAll('[data-open-skill]').forEach((card) => {
      card.addEventListener('click', () => openSkillModal(card.dataset.openSkill));
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openSkillModal(card.dataset.openSkill);
        }
      });
    });
  } catch (e) {
    root.innerHTML = '<article data-panel="danger">Failed to load bundled skills.</article>';
    toast('Skills error: ' + e.message, 'error');
  }
}

function settingsSectionTitle(title) {
  return `<header data-row="space-between"><h4>${title}</h4><span style="flex:1;height:1px;background:var(--line)"></span></header>`;
}

function renderSettingsPage() {
  if (!state.config) {
    document.getElementById('settings-form-root').innerHTML = '<article data-panel="empty">Config not loaded.</article>';
    return;
  }

  const cfg = state.config;
  const sectionRows = (cfg.sections || []).map((s) => `
    <tr data-section="${escHtml(s)}">
      <td><span style="display:inline-flex;align-items:center;gap:8px"><span style="width:10px;height:10px;border-radius:999px;background:${sectionColor(s)}"></span><span>${escHtml(s)}</span></span></td>
      <td><input type="color" data-field="color" value="${escHtml((cfg.section_colors || {})[s] || '#888888')}"></td>
      <td><button data-remove="${escHtml(s)}" title="Remove">⨯</button></td>
    </tr>`).join('');

  document.getElementById('settings-form-root').innerHTML = `
    ${settingsSectionTitle('Limits')}
    <section data-panel="tight" data-metric-grid>
      <label>Max content length<input type="number" data-ui="cfg-max-content" value="${escHtml(String(cfg.max_content_length))}"></label>
      <label>Max entries<input type="number" data-ui="cfg-max-entries" value="${escHtml(String(cfg.max_entries))}"></label>
      <label>Max tags per entry<input type="number" data-ui="cfg-max-tags" value="${escHtml(String(cfg.max_tags_per_entry))}"></label>
      <label>Max tag length<input type="number" data-ui="cfg-max-tag-len" value="${escHtml(String(cfg.max_tag_length))}"></label>
      <label>Entry batch size<input type="number" data-ui="cfg-batch-size" min="1" value="${escHtml(String(cfg.entry_batch_size))}"></label>
      <label>Entry load threshold<input type="number" data-ui="cfg-load-threshold" min="0" value="${escHtml(String(cfg.entry_load_threshold))}"></label>
    </section>
    ${settingsSectionTitle('Storage')}
    <section data-panel="tight" data-metric-grid>
      <label>Backend
        <select data-ui="cfg-storage-backend">
          <option value="json"${(cfg.storage_backend || 'json') === 'json' ? ' selected' : ''}>JSON (.rememb/entries.json)</option>
          <option value="sqlite"${cfg.storage_backend === 'sqlite' ? ' selected' : ''}>SQLite (.rememb/entries.db)</option>
        </select>
      </label>
      <div data-panel="default">
        <p>SQLite scales better for large entry volumes. Switching to SQLite migrates existing JSON entries automatically.</p>
        ${state.systemInfo?.storage_files?.length ? `<p><small>Active files: ${escHtml(state.systemInfo.storage_files.join(', '))}</small></p>` : ''}
      </div>
    </section>
    ${settingsSectionTitle('Semantic search')}
    <section data-panel="tight" data-metric-grid>
      <label>Model${renderModelSelect(cfg.semantic_model_name || '')}</label>
      <label>Conflict threshold<input type="number" data-ui="cfg-threshold" step="0.01" min="0.5" max="1.0" value="${escHtml(String(cfg.semantic_conflict_threshold))}"></label>
      <label>Model idle TTL (s)<input type="number" data-ui="cfg-ttl" value="${escHtml(String(cfg.semantic_model_idle_ttl_seconds))}"></label>
    </section>
    ${settingsSectionTitle('Sections')}
    <section data-panel="tight">
      <div>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Color</th>
              <th></th>
            </tr>
          </thead>
          <tbody data-ui="cfg-sections-tbody-page">${sectionRows}</tbody>
        </table>
      </div>
      <div data-actions>
        <input type="text" data-ui="cfg-new-section-page" placeholder="New section name">
        <button data-variant="ghost" data-size="small" data-ui="cfg-add-section-page">+ Add</button>
      </div>
    </section>
    ${settingsSectionTitle('Maintenance')}
    <section data-panel="default" data-row="space-between">
      <div>
        <h4>Consolidate duplicates</h4>
        <p>Remove semantically duplicate entries</p>
      </div>
      <button data-variant="ghost" data-size="small" data-ui="btn-consolidate-page">Run consolidate</button>
    </section>
    <footer data-actions>
      <button data-variant="primary" data-ui="btn-save-config-page">Save settings</button>
    </footer>`;

  document.getElementById('cfg-sections-tbody-page').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-remove]');
    if (btn) btn.closest('tr').remove();
  });

  document.getElementById('cfg-add-section-page').addEventListener('click', () => {
    const inp = document.getElementById('cfg-new-section-page');
    const name = inp.value.trim().toLowerCase().replace(/\s+/g, '_');
    if (!name) return;
    if (document.querySelector(`#cfg-sections-tbody-page [data-section="${CSS.escape(name)}"]`)) {
      toast('Section already exists.', 'error');
      return;
    }
    const tbody = document.getElementById('cfg-sections-tbody-page');
    const tr = document.createElement('tr');
    tr.dataset.section = name;
    tr.innerHTML = `
      <td><span style="display:inline-flex;align-items:center;gap:8px"><span style="width:10px;height:10px;border-radius:999px;background:#888888"></span><span>${escHtml(name)}</span></span></td>
      <td><input type="color" data-field="color" value="#888888"></td>
      <td><button data-remove="${escHtml(name)}" title="Remove">⨯</button></td>`;
    tbody.appendChild(tr);
    inp.value = '';
  });

  document.getElementById('btn-consolidate-page').addEventListener('click', openConsolidateModal);

  document.getElementById('btn-save-config-page').addEventListener('click', async () => {
    const rows = document.querySelectorAll('#cfg-sections-tbody-page tr');
    const sections = [];
    const section_colors = {};
    rows.forEach((row) => {
      const name = row.dataset.section;
      sections.push(name);
      section_colors[name] = row.querySelector('[data-field="color"]').value;
    });
    const updates = {
      max_content_length: readIntInput('cfg-max-content', cfg.max_content_length),
      max_entries: readIntInput('cfg-max-entries', cfg.max_entries),
      max_tags_per_entry: readIntInput('cfg-max-tags', cfg.max_tags_per_entry),
      max_tag_length: readIntInput('cfg-max-tag-len', cfg.max_tag_length),
      entry_batch_size: readIntInput('cfg-batch-size', cfg.entry_batch_size),
      entry_load_threshold: readIntInput('cfg-load-threshold', cfg.entry_load_threshold),
      semantic_model_name: document.getElementById('cfg-model').value.trim() || cfg.semantic_model_name,
      semantic_conflict_threshold: readFloatInput('cfg-threshold', cfg.semantic_conflict_threshold),
      semantic_model_idle_ttl_seconds: readIntInput('cfg-ttl', cfg.semantic_model_idle_ttl_seconds),
      storage_backend: document.getElementById('cfg-storage-backend').value,
      sections,
      section_colors,
    };
    try {
      state.config = await api.configUpdate(updates);
      state.limit = state.config.entry_batch_size || 24;
      toast('Settings saved.', 'success');
      renderSections();
      renderSettingsPage();
      if (!state.searchMode) loadEntries();
    } catch (e) {
      toast('Error: ' + e.message, 'error');
    }
  });
}

let searchTimer = null;
document.getElementById('search-input').addEventListener('input', (e) => {
  const q = e.target.value.trim();
  clearTimeout(searchTimer);
  if (!q) {
    clearSearch();
    return;
  }
  searchTimer = setTimeout(() => doSearch(q), 400);
});

document.getElementById('search-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const q = e.target.value.trim();
    if (!q) return;
    clearTimeout(searchTimer);
    if (state.view !== 'memories') switchView('memories');
    doSearch(q);
  }
});

document.addEventListener('keydown', (e) => {
  const tag = document.activeElement?.tagName;
  if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA') {
    e.preventDefault();
    const inp = document.getElementById('search-input');
    if (inp) {
      inp.focus();
      inp.select();
    }
  }
});


document.getElementById('btn-consolidate').addEventListener('click', openConsolidateModal);
document.getElementById('btn-load-more').addEventListener('click', () => loadEntries(true));
document.getElementById('clear-search').addEventListener('click', clearSearch);

document.getElementById('toggle-workstreams-include-deleted').addEventListener('change', async (e) => {
  state.workstreamsIncludeDeleted = e.target.checked;
  await loadWorkstreams();
});








document.getElementById('sort-select').addEventListener('change', (e) => {
  const [sortBy, dir] = e.target.value.split('-');
  state.sort_by = sortBy;
  state.descending = dir === 'desc';
  state.offset = 0;
  loadEntries();
});

document.getElementById('toggle-include-deleted').addEventListener('change', async (e) => {
  state.includeDeleted = e.target.checked;
  state.offset = 0;
  if (state.searchMode && state.searchQuery) {
    await doSearch(state.searchQuery);
    return;
  }
  await loadEntries();
});

document.querySelectorAll('nav button[data-nav-view]').forEach((tab) => tab.addEventListener('click', () => switchView(tab.dataset.view)));
document.querySelectorAll('[data-shortcut-view]').forEach((button) => {
  button.addEventListener('click', async () => {
    switchView(button.dataset.shortcutView);
    if (button.dataset.shortcutPanel) {
      await setWorkstreamSurfaceFocus(button.dataset.shortcutPanel, { ensureSelected: true, scroll: true });
    }
  });
});
document.querySelectorAll('[data-workstream-surface]').forEach((button) => {
  button.addEventListener('click', async () => {
    await setWorkstreamSurfaceFocus(button.dataset.workstreamSurface, { ensureSelected: true, scroll: true });
  });
});

async function loadSystemInfo() {
  try {
    state.systemInfo = await api.systemInfo();
    const versionEl = document.querySelector('[data-ui="logo-version"]');
    if (versionEl && state.systemInfo?.version) {
      versionEl.textContent = `v${state.systemInfo.version}`;
    }
  } catch (e) {
    // non-fatal
  }
}

async function boot() {
  classlessObserver.observe(document.documentElement, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['class'],
  });
  stripClassesFromTree(document.documentElement);
  await Promise.all([loadConfig(), loadSystemInfo()]);
  document.getElementById('toggle-include-deleted').checked = state.includeDeleted;
  document.getElementById('toggle-workstreams-include-deleted').checked = state.workstreamsIncludeDeleted;
  await loadStats();
  await loadEntries();
  switchView('memories');
}

boot();
