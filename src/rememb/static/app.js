const state = {
  view: 'dashboard',
  section: null,
  config: null,
  entries: [],
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
  loading: false,
  systemInfo: null,
};

let dashboardRecentEntries = [];

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

function toast(msg, type = 'info', duration = 3000) {
  const accent = type === 'error' ? '#ef4444' : (type === 'success' ? '#22c55e' : '#0891b2');
  const el = document.createElement('div');
  el.className = 'toast';
  el.setAttribute('role', 'status');
  el.style.borderLeftColor = accent;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 300);
  }, duration);
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

const VIEW_META = {
  dashboard: { title: 'Overview', subtitle: 'Memory store at a glance' },
  memories: { title: 'Memory', subtitle: 'Entries persisted by the agent' },
  stats: { title: 'Stats', subtitle: 'Store size and section distribution' },
  settings: { title: 'Settings', subtitle: 'Runtime configuration for this workspace' },
  skills: { title: 'Skills', subtitle: 'Optional bundled agent skills' },
};

function updatePageHeader(view, subtitle) {
  const meta = VIEW_META[view] || { title: view, subtitle: '' };
  setText('page-title', meta.title);
  setText('page-subtitle', subtitle || meta.subtitle);
}

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

function renderModelSelect(currentValue) {
  const opts = semanticModels.map((m) =>
    `<option value="${escHtml(m.name)}" ${m.name === currentValue ? 'selected' : ''} title="${escHtml(m.description)}">${escHtml(m.label)}</option>`
  ).join('');
  return `<select id="cfg-model" class="select">${opts}</select>`;
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
    return '<article class="panel panel-soft" data-empty="true">No content changes.</article>';
  }

  return `
    <article class="panel panel-shell">
      <header class="diff-head">
        <div>From</div>
        <div>To</div>
      </header>
      <section class="diff-scroll">
        ${rows.map((row) => `
          <div class="diff-row ${escHtml(row.type || 'context')}">
            <div>${renderDiffCell(row, 'left')}</div>
            <div>${renderDiffCell(row, 'right')}</div>
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
  return `<div class="prose">${blocks.join('')}</div>`;
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
    <section class="panel">
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

function renderSections() {
  if (!state.config) return;
  const sections = state.config.sections || [];
  const list = document.getElementById('sections-list');
  const allActive = state.section === null && !state.searchMode;

  let html = `
    <button class="chip" data-section="" ${allActive ? 'aria-current="page"' : ''}>
      All <span id="count-all">${state.total || ''}</span>
    </button>`;

  for (const s of sections) {
    const active = state.section === s && !state.searchMode;
    html += `
      <button class="chip" data-section="${escHtml(s)}" ${active ? 'aria-current="page"' : ''}>
        ${escHtml(s)} <span id="count-${escHtml(s)}">—</span>
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

function renderDashboardList(rootId, items, emptyMessage) {
  const root = document.getElementById(rootId);
  if (!root) return;
  if (!items.length) {
    root.innerHTML = `<p class="meta">${escHtml(emptyMessage)}</p>`;
    return;
  }
  root.innerHTML = items.map((item) => `
    <article class="card card-compact">
      <div class="row">
        <div class="row-main">
          <h4>${escHtml(item.title || '')}</h4>
          <p>${escHtml(item.body || '')}</p>
        </div>
        ${item.meta ? `<span class="tag-mono">${escHtml(item.meta)}</span>` : ''}
      </div>
      ${item.action ? `<footer class="actions"><button class="btn btn-ghost btn-sm" data-dashboard-action="${escHtml(item.action.name)}" data-dashboard-value="${escHtml(item.action.value || '')}" data-dashboard-entry-id="${escHtml(item.action.entryId || '')}">${escHtml(item.action.label)}</button></footer>` : ''}
    </article>
  `).join('');
  root.querySelectorAll('[data-dashboard-action]').forEach((button) => {
    button.addEventListener('click', async () => {
      const action = button.dataset.dashboardAction;
      const value = button.dataset.dashboardValue;
      if (action === 'open-entry') {
        const entryId = button.dataset.dashboardEntryId;
        const entry = dashboardRecentEntries.find((item) => item.id === entryId);
        if (entry) openViewModal(entry);
        return;
      }
      if (action === 'open-memory-admin') {
        switchView('memories');
        return;
      }
      if (action === 'open-runtime-controls') {
        switchView(value || 'settings');
      }
    });
  });
}

async function renderDashboardView() {
  try {
    const [statsData, recentData] = await Promise.all([
      api.stats(),
      api.entries({ offset: 0, limit: 6, sort_by: 'recent', descending: true }),
    ]);
    const summary = statsSummary(statsData);
    const recentEntries = recentData.items || [];
    dashboardRecentEntries = recentEntries;

    setText('dashboard-entries-count', String(summary?.total ?? 0));
    setText('dashboard-entries-caption', summary?.newest && summary.newest !== '—'
      ? `newest ${relTime(summary.newest)}`
      : 'no entries yet');
    setText('dashboard-sections-count', String(summary?.activeSections ?? 0));
    setText('dashboard-sections-caption', summary?.storage
      ? `${summary.storage} backend`
      : 'storage backend unknown');
    setText('dashboard-deleted-count', String(summary?.deleted ?? 0));
    setText('dashboard-deleted-caption', summary?.oldest && summary.oldest !== '—'
      ? `oldest ${relTime(summary.oldest)}`
      : 'no deleted entries');
    setText('dashboard-size-count', summary?.sizeKb != null ? String(Math.round(summary.sizeKb)) : '—');
    setText('dashboard-size-caption', summary?.activeSections
      ? `${summary.activeSections} active section${summary.activeSections === 1 ? '' : 's'}`
      : 'no section data');

    renderDashboardList(
      'dashboard-recent-list',
      recentEntries.map((entry) => ({
        title: previewText(entry.content, 68),
        body: `${entry.section} · ${relTime(entry.updated_at || entry.created_at)}${entry.deleted_at ? ' · deleted' : ''}`,
        meta: entry.id,
        action: { name: 'open-entry', entryId: entry.id, label: 'View entry' },
      })),
      'No memory entries yet. The agent will persist context here via MCP.'
    );

    renderDashboardList(
      'dashboard-links-list',
      [
        {
          title: 'Stats',
          body: 'Store size, section distribution, and recent activity.',
          action: { name: 'open-runtime-controls', value: 'stats', label: 'Open stats' },
        },
        {
          title: 'Settings',
          body: 'Runtime configuration, storage backend, and sections.',
          action: { name: 'open-runtime-controls', value: 'settings', label: 'Open settings' },
        },
        {
          title: 'Skills',
          body: 'Optional bundled agent skills installed with rememb-skills.',
          action: { name: 'open-runtime-controls', value: 'skills', label: 'Browse skills' },
        },
      ],
      'No quick links available.'
    );
  } catch (e) {
    renderDashboardList('dashboard-recent-list', [], `Failed to load dashboard: ${e.message}`);
    renderDashboardList('dashboard-links-list', [], 'Dashboard could not load quick links.');
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
  setText('count-all', s.total ?? '');
  for (const [sec, cnt] of Object.entries(s.sections)) {
    setText(`count-${sec}`, cnt);
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
  setText('dash-updated', `Updated ${relTime(new Date().toISOString())} · ${s.deleted} deleted`);
  const sectionsList = state.config?.sections || [];
  const maxCount = Math.max(...Object.values(s.sections), 1);
  const barsHtml = sectionsList.map((sec) => {
    const count = s.sections[sec] || 0;
    const pct = Math.round((count / maxCount) * 100);
    const color = sectionColor(sec);
    return `<div class="bar-row">
      <span>${escHtml(sec)}</span>
      <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div>
      <strong>${count}</strong>
    </div>`;
  }).join('');
  document.getElementById('dash-section-bars').innerHTML = barsHtml || '<p class="meta">No sections configured.</p>';
}

function renderEntryCard(entry) {
  const theme = sectionTheme(entry.section);
  const isEdited = entry.updated_at && entry.updated_at !== entry.created_at;
  const displayTime = isEdited ? relTime(entry.updated_at) : relTime(entry.created_at);
  const timeTitle = isEdited ? `Created: ${entry.created_at}\nEdited: ${entry.updated_at}` : (entry.created_at || '');
  const tags = (entry.tags || []).slice(0, 3).map((t) => `<span class="tag">${escHtml(t)}</span>`).join('');
  const extraTags = (entry.tags || []).length > 3 ? `<span class="tag">+${entry.tags.length - 3}</span>` : '';
  const preview = previewText(entry.content, 280);

  return `
    <article class="card memory-card" data-id="${escHtml(entry.id)}" style="--section-color:${theme.color}">
      <div class="memory-card-accent"></div>
      <div class="card-body">
        <header class="card-head">
          <span class="tag">${escHtml(entry.section)}</span>
          <span class="tags">
            ${entry.deleted_at ? '<span class="tag">Deleted</span>' : ''}
            ${entry.score != null ? `<span class="tag-mono">${(entry.score * 100).toFixed(0)}%</span>` : ''}
            <time title="${escHtml(timeTitle)}">${isEdited ? '✎ ' : ''}${displayTime}</time>
          </span>
        </header>
        <div class="card-content">${escHtml(preview)}</div>
        ${tags ? `<div class="tags">${tags}${extraTags}</div>` : ''}
        <footer class="card-foot">
          ${(entry.access_count || 0) > 0 ? `<time>↻ ${entry.access_count}</time>` : '<span></span>'}
          <span class="tag-mono">${escHtml(entry.id)}</span>
        </footer>
      </div>
    </article>`;
}

function renderCards(entries, append = false) {
  const grid = document.getElementById('cards-grid');
  if (!append) grid.innerHTML = '';

  if (entries.length === 0 && !append) {
    grid.innerHTML = `
      <div class="state">
        <h3>${state.searchMode ? 'No results' : 'No entries'}</h3>
        <p>${state.searchMode ? 'Try another search term.' : 'The agent has not written any memory yet.'}</p>
      </div>`;
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
    const [config, modelsData] = await Promise.all([api.config(), api.models()]);
    state.config = config;
    semanticModels = modelsData.models || [];
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
    grid.innerHTML = '<article class="state state-loading">Loading…</article>';
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

    if (state.view === 'memories') {
      const label = state.searchMode ? 'Search results' : (state.section ? `Section: ${state.section}` : VIEW_META.memories.title);
      updatePageHeader('memories', total ? `${total} entries · ${label}` : label);
    }

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
  grid.innerHTML = '<article class="state state-loading">Searching…</article>';
  document.getElementById('load-more-wrap').hidden = true;
  document.getElementById('sort-select').hidden = true;
  updatePageHeader('memories', `Search: "${query}"`);
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
  root.innerHTML = `<div class="modal-backdrop">${html}</div>`;
  root.querySelector('.modal-backdrop').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
  });
  root.querySelector('.modal-close')?.addEventListener('click', closeModal);
  document.addEventListener('keydown', handleEsc);
}

function modalShell(inner, size = '') {
  const sizes = {
    'modal-panel--wide': 'modal-wide',
    'modal-panel--xl': 'modal-xl',
    'modal-panel--compact': 'modal-compact',
    'modal-panel--reading': '',
  };
  const extra = sizes[size] || '';
  return `<div class="modal ${extra}">${inner}</div>`;
}

function handleEsc(e) {
  if (e.key === 'Escape') closeModal();
}

function openViewModal(entry) {
  const theme = sectionTheme(entry.section);
  const themeStyle = themeVars(theme);
  const isEdited = entry.updated_at && entry.updated_at !== entry.created_at;
  const timeLabel = isEdited ? `Edited ${relTime(entry.updated_at)} · Created ${relTime(entry.created_at)}` : `Created ${relTime(entry.created_at)}`;
  const tags = (entry.tags || []).map((t) => `<span class="tag" style="${themeStyle}">${escHtml(t)}</span>`).join('');
  const scoreBadge = entry.score != null ? `<span class="tag-mono" style="${themeStyle}">${(entry.score * 100).toFixed(0)}%</span>` : '';
  const accessBadge = (entry.access_count || 0) > 0 ? `<time title="Accessed ${entry.access_count} time${entry.access_count === 1 ? '' : 's'}">↻ ${entry.access_count}</time>` : '';
  const deletedNotice = entry.deleted_at
    ? `<article class="state state-error">Deleted ${escHtml(relTime(entry.deleted_at))}. History remains available for inspection.</article>`
    : '';

  openModal(modalShell(`
    <header class="modal-head" style="${themeStyle}">
      <div class="tags">
        <div class="tag" style="${themeStyle}">
          <span></span>
          ${escHtml(entry.section)}
        </div>
        ${scoreBadge}
        <time>${escHtml(timeLabel)}</time>
      </div>
      <button class="modal-close" type="button">×</button>
    </header>
    <section class="modal-body prose">
      ${deletedNotice}
      ${renderMarkdown(entry.content)}
      ${tags ? `<div class="tags">${tags}</div>` : ''}
      <footer class="tags">
        ${accessBadge}
        <span class="tag-mono">${escHtml(entry.id)}</span>
      </footer>
    </section>
    <footer class="modal-foot">
      <button class="btn btn-ghost" id="btn-view-history" type="button">History</button>
    </footer>
  `, 'modal-panel--reading'));
  document.getElementById('btn-view-history').addEventListener('click', () => { closeModal(); openVersionsModal(entry); });
}

async function openDiffModal(entry, fromVersion, toVersion) {
  try {
    const data = await api.diffVersions(entry.id, { from_version: String(fromVersion), to_version: String(toVersion) });
    const diffText = data.diff || '(no content changes)';
    openModal(modalShell(`
      <header class="modal-head">
        <div>
          <h3>Diff for ${escHtml(entry.id)}</h3>
          <p>v${fromVersion} → v${toVersion}</p>
        </div>
        <button class="modal-close" type="button">×</button>
      </header>
      <section class="modal-body">
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
      <header class="modal-head">
        <div>
          <h3>Version history</h3>
          <p>${escHtml(entry.id)} · ${versions.length} revision(s)</p>
        </div>
        <button class="modal-close" type="button">×</button>
      </header>
      <section class="modal-body">
        <article class="panel panel-soft">
          <h4>Compare revisions</h4>
          <p>Timeline stays focused on current vs previous for quick inspection. Older revisions can still be diffed against the current state directly from the timeline.</p>
        </article>
        <h4>Timeline</h4>
        <section class="timeline" id="timeline-root"></section>
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
          <article class="version-item">
            <div class="version-item-inner" style="${activeBorder}">
              <header class="tags" style="background:${theme.faint};padding:8px;border-radius:10px;">
                <span class="tag-mono">v${revision.version}</span>
                <span class="tag">${escHtml(revision.section || '')}</span>
                ${revision.deleted_at ? '<span class="tag">deleted</span>' : ''}
                ${isCurrent ? '<span class="tag">current</span>' : ''}
                ${isSelectedFrom ? '<span class="tag">from</span>' : ''}
                ${isSelectedTo ? '<span class="tag">to</span>' : ''}
                <time>${escHtml(relTime(revision.updated_at || revision.created_at))}</time>
              </header>
              <p>${escHtml(preview)}</p>
              <footer class="tags">
                <span class="tag-mono">Created ${escHtml(relTime(revision.created_at))}</span>
                <span class="tag-mono">Updated ${escHtml(relTime(revision.updated_at || revision.created_at))}</span>
                ${!isCurrent ? `<button class="btn btn-ghost btn-sm" type="button" data-diff-version="${revision.version}">Diff to current</button>` : ''}
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
    <header class="modal-head">
      <h3>Consolidate duplicates</h3>
      <button class="modal-close" type="button">×</button>
    </header>
    <section class="modal-body">
      <label class="field">Section <small>(optional)</small>
        <select id="f-cons-section" class="select">
          <option value="">All sections</option>
          ${opts}
        </select>
      </label>
      <label class="field">Mode
        <select id="f-cons-mode" class="select">
          <option value="exact">Exact (normalized content match)</option>
          <option value="semantic">Semantic (similarity threshold)</option>
        </select>
      </label>
      <label class="field" id="threshold-group" hidden>Similarity threshold
        <input type="number" id="f-threshold" value="0.88" step="0.01" min="0.5" max="1.0">
        <span class="meta">Higher = stricter (less aggressive). Range: 0.5 – 1.0</span>
      </label>
    </section>
    <footer class="modal-foot">
      <button class="btn btn-ghost" type="button" onclick="closeModal()">Cancel</button>
      <button class="btn btn-primary" type="button" id="btn-run-consolidate">Run</button>
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
  state.view = name;
  document.querySelectorAll('.view').forEach((view) => {
    view.hidden = true;
  });
  document.getElementById(`view-${name}`).hidden = false;
  document.querySelectorAll('[data-nav-view]').forEach((tab) => {
    const active = tab.dataset.view === name;
    if (active) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  });
  const badge = document.querySelector('.topbar .badge');
  if (badge) badge.hidden = name === 'settings';
  updatePageHeader(name);
  if (name === 'dashboard') renderDashboardView();
  else if (name === 'stats') renderStatsView();
  else if (name === 'skills') renderSkillsView();
  else if (name === 'settings') renderSettingsPage();
}

async function renderStatsView() {
  try {
    const stats = await api.stats();
    applyDashboardStats(stats);
    const recent = await api.entries({ offset: 0, limit: 8, sort_by: 'recent', descending: true });
    const items = recent.items || [];
    const recentHtml = items.map((e) => {
      const color = sectionColor(e.section);
      return `<article class="row">
        <span class="swatch" style="background:${color}"></span>
        <span class="row-main">${escHtml(previewText(e.content, 80))}</span>
        <time>${relTime(e.updated_at || e.created_at)}</time>
      </article>`;
    }).join('');
    document.getElementById('dash-recent-list').innerHTML = recentHtml || '<p class="meta">No entries yet.</p>';
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
      <header class="modal-head">
        <div>
          <h3>${escHtml(skill.name || skill.id || 'Skill')}</h3>
          <p>${escHtml(skill.path || '')}</p>
        </div>
        <button class="modal-close" type="button">✕</button>
      </header>
      <section class="modal-body prose">
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
    return '<article class="state">No bundled skills found.</article>';
  }

  return skills.map((skill) => `
    <article class="card skill-card" data-open-skill="${escHtml(skill.id || '')}" role="button" tabindex="0" aria-label="View skill ${escHtml(skill.name || skill.id || 'skill')}">
      <h4>${escHtml(skill.name || skill.id)}</h4>
      <p>${escHtml(skill.description || 'No description.')}</p>
      <small class="meta" title="${escHtml(skill.path || '')}">${escHtml(skill.path || '')}</small>
    </article>
  `).join('');
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
  root.innerHTML = '<article class="state state-loading">Loading…</article>';
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
      root.innerHTML = '<article class="state">No skills available. Install the rememb-skills package to browse bundled agent skills.</article>';
    } else if (!skills.length) {
      root.innerHTML = '<article class="state">No bundled skills found.</article>';
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
    root.innerHTML = '<article class="state state-error">Failed to load bundled skills.</article>';
    toast('Skills error: ' + e.message, 'error');
  }
}

function settingsSectionTitle(title) {
  return `<h3 class="settings-heading">${escHtml(title)}</h3>`;
}

function renderSettingsPage() {
  if (!state.config) {
    document.getElementById('settings-form-root').innerHTML = '<article class="state">Config not loaded.</article>';
    return;
  }

  const cfg = state.config;
  const sectionRows = (cfg.sections || []).map((s) => `
    <tr data-section="${escHtml(s)}">
      <td><span class="swatch" style="background:${sectionColor(s)}"></span>${escHtml(s)}</td>
      <td><input type="color" class="field-color" data-field="color" value="${escHtml((cfg.section_colors || {})[s] || '#888888')}"></td>
      <td><button class="btn btn-ghost btn-sm" type="button" data-remove="${escHtml(s)}" title="Remove">×</button></td>
    </tr>`).join('');

  document.getElementById('settings-form-root').innerHTML = `
    <div class="settings-form">
      <div class="panel-grid">
        <section class="panel panel-tight">
          ${settingsSectionTitle('Limits')}
          <div class="form-grid">
            <label class="field">Max content length<input type="number" id="cfg-max-content" value="${escHtml(String(cfg.max_content_length))}"></label>
            <label class="field">Max entries<input type="number" id="cfg-max-entries" value="${escHtml(String(cfg.max_entries))}"></label>
            <label class="field">Max tags per entry<input type="number" id="cfg-max-tags" value="${escHtml(String(cfg.max_tags_per_entry))}"></label>
            <label class="field">Max tag length<input type="number" id="cfg-max-tag-len" value="${escHtml(String(cfg.max_tag_length))}"></label>
            <label class="field">Entry batch size<input type="number" id="cfg-batch-size" min="1" value="${escHtml(String(cfg.entry_batch_size))}"></label>
            <label class="field">Entry load threshold<input type="number" id="cfg-load-threshold" min="0" value="${escHtml(String(cfg.entry_load_threshold))}"></label>
          </div>
        </section>
        <section class="panel panel-tight">
          ${settingsSectionTitle('Storage backend')}
          <label class="field">Backend
            <select id="cfg-storage-backend" class="select">
              <option value="json"${(cfg.storage_backend || 'json') === 'json' ? ' selected' : ''}>JSON (.rememb/entries.json)</option>
              <option value="sqlite"${cfg.storage_backend === 'sqlite' ? ' selected' : ''}>SQLite (.rememb/entries.db)</option>
            </select>
          </label>
          <p class="meta">SQLite scales better for large entry volumes. Switching migrates existing JSON entries automatically.</p>
          ${state.systemInfo?.storage_files?.length ? `<p class="meta">Active files: ${escHtml(state.systemInfo.storage_files.join(', '))}</p>` : ''}
        </section>
        <section class="panel panel-tight">
          ${settingsSectionTitle('Semantic search')}
          <div class="form-grid">
            <label class="field">Model${renderModelSelect(cfg.semantic_model_name || '')}</label>
            <label class="field">Conflict threshold<input type="number" id="cfg-threshold" step="0.01" min="0.5" max="1.0" value="${escHtml(String(cfg.semantic_conflict_threshold))}"></label>
            <label class="field">Model idle TTL (s)<input type="number" id="cfg-ttl" value="${escHtml(String(cfg.semantic_model_idle_ttl_seconds))}"></label>
          </div>
        </section>
        <section class="panel panel-tight">
          ${settingsSectionTitle('Sections')}
          <table class="config-table">
            <thead><tr><th>Name</th><th>Color</th><th></th></tr></thead>
            <tbody id="cfg-sections-tbody-page">${sectionRows}</tbody>
          </table>
          <div class="actions">
            <input type="text" id="cfg-new-section-page" class="select" placeholder="New section name">
            <button class="btn btn-ghost btn-sm" type="button" id="cfg-add-section-page">+ Add</button>
          </div>
        </section>
      </div>
      <section class="panel row">
        <div class="row-main">
          <h4>Consolidate duplicates</h4>
          <p class="meta">Remove semantically duplicate entries from the store.</p>
        </div>
        <button class="btn btn-ghost btn-sm" type="button" id="btn-consolidate-page">Run consolidate</button>
      </section>
      <footer class="actions settings-actions">
        <button class="btn btn-primary" type="button" id="btn-save-config-page">Save settings</button>
      </footer>
    </div>`;

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
      <td><span class="swatch" style="background:#888888"></span>${escHtml(name)}</td>
      <td><input type="color" class="field-color" data-field="color" value="#888888"></td>
      <td><button class="btn btn-ghost btn-sm" type="button" data-remove="${escHtml(name)}" title="Remove">×</button></td>`;
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


document.getElementById('btn-load-more').addEventListener('click', () => loadEntries(true));
document.getElementById('clear-search').addEventListener('click', clearSearch);

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
  button.addEventListener('click', () => {
    switchView(button.dataset.shortcutView);
  });
});

async function loadSystemInfo() {
  try {
    state.systemInfo = await api.systemInfo();
    const versionEl = document.getElementById('logo-version');
    if (versionEl && state.systemInfo?.version) {
      versionEl.textContent = `v${state.systemInfo.version}`;
    }
  } catch (e) {
    // non-fatal
  }
}

async function boot() {
  await Promise.all([loadConfig(), loadSystemInfo()]);
  document.getElementById('toggle-include-deleted').checked = state.includeDeleted;
  await loadStats();
  await loadEntries();
  switchView('dashboard');
}

boot();
