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

function bindEvent(id, event, handler) {
  const el = document.getElementById(id);
  if (!el) return;
  el.addEventListener(event, handler);
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

function sectionColor(name) {
  if (!state.config) return '#888888';
  return (state.config.section_colors || {})[name] || '#888888';
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

function truncateContent(text, max = 96) {
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
    return '<article class="surface surface--muted" data-empty="true">No content changes.</article>';
  }

  return `
    <article class="surface surface--flush">
      <header class="diff-head">
        <div>From</div>
        <div>To</div>
      </header>
      <section class="diff-scroll">
        ${rows.map((row) => `
          <div class="diff-line ${escHtml(row.type || 'context')}">
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
    <section class="surface">
      <h4>Frontmatter</h4>
      <dl class="facts">
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
  const list = document.getElementById('sections-list');
  if (!list) return;
  const sections = state.config.sections || [];
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

function renderEntryRows(rootId, entries, emptyMessage) {
  const root = document.getElementById(rootId);
  if (!root) return;
  if (!entries.length) {
    root.innerHTML = `<p class="lede">${escHtml(emptyMessage)}</p>`;
    return;
  }
  root.innerHTML = entries.map((entry) => `
    <article class="row row--clickable" data-entry-id="${escHtml(entry.id)}" tabindex="0" role="button">
      <div>
        <p class="row-title"><span class="dot" style="--dot-color:${escHtml(entry.color)}"></span>${escHtml(entry.title)}</p>
        <p class="row-meta">${escHtml(entry.meta)}</p>
      </div>
      ${entry.idLabel ? `<span class="mono">${escHtml(entry.idLabel)}</span>` : `<time>${escHtml(entry.time || '')}</time>`}
    </article>
  `).join('');

  root.querySelectorAll('[data-entry-id]').forEach((row) => {
    const open = () => {
      const entry = entries.find((item) => item.id === row.dataset.entryId);
      if (entry?.source) openViewModal(entry.source);
    };
    row.addEventListener('click', open);
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        open();
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

    setText('dashboard-entries-count', String(summary?.total ?? 0));
    setText('dashboard-sections-count', String(summary?.activeSections ?? 0));
    setText('dashboard-deleted-count', String(summary?.deleted ?? 0));
    setText('dashboard-size-count', summary?.sizeKb != null ? String(Math.round(summary.sizeKb)) : '—');

    renderEntryRows(
      'dashboard-recent-list',
      recentEntries.map((entry) => ({
        id: entry.id,
        source: entry,
        title: truncateContent(entry.content, 72),
        meta: `${entry.section} · ${relTime(entry.updated_at || entry.created_at)}${entry.deleted_at ? ' · deleted' : ''}`,
        idLabel: entry.id,
        color: sectionColor(entry.section),
      })),
      'No memory entries yet. The agent will persist context here via MCP.'
    );
  } catch (e) {
    renderEntryRows('dashboard-recent-list', [], `Failed to load dashboard: ${e.message}`);
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
  setText('dash-total', String(s.total));
  setText('dash-active-sec', String(s.activeSections));
  setText('dash-size', s.sizeKb != null ? String(Math.round(s.sizeKb)) : '—');
  setText('dash-storage', s.storage);
  setText('dash-oldest', s.oldest);
  setText('dash-newest', s.newest);
  setText('dash-updated', `Updated ${relTime(new Date().toISOString())} · ${s.deleted} deleted`);
  const sectionsList = state.config?.sections || [];
  const maxCount = Math.max(...Object.values(s.sections), 1);
  const barsHtml = sectionsList.map((sec) => {
    const count = s.sections[sec] || 0;
    const pct = Math.round((count / maxCount) * 100);
    const color = sectionColor(sec);
    return `<div class="bar">
      <span>${escHtml(sec)}</span>
      <div class="bar-track"><div class="bar-fill" style="--bar-width:${pct}%;--bar-color:${color}"></div></div>
      <strong>${count}</strong>
    </div>`;
  }).join('');
  const barsRoot = document.getElementById('dash-section-bars');
  if (barsRoot) barsRoot.innerHTML = barsHtml || '<p class="lede">No sections configured.</p>';
}

function renderEntryCard(entry) {
  const color = sectionColor(entry.section);
  const isEdited = entry.updated_at && entry.updated_at !== entry.created_at;
  const displayTime = isEdited ? relTime(entry.updated_at) : relTime(entry.created_at);
  const timeTitle = isEdited ? `Created: ${entry.created_at}\nEdited: ${entry.updated_at}` : (entry.created_at || '');
  const tags = (entry.tags || []).slice(0, 3).map((t) => `<span class="tag">${escHtml(t)}</span>`).join('');
  const extraTags = (entry.tags || []).length > 3 ? `<span class="tag">+${entry.tags.length - 3}</span>` : '';
  const preview = truncateContent(entry.content, 240);

  return `
    <article class="entry${entry.deleted_at ? ' is-deleted' : ''}" data-id="${escHtml(entry.id)}" tabindex="0" role="button" style="--section-color:${color}">
      <header class="entry-head">
        <span class="entry-section"><span class="dot" style="--dot-color:${color}"></span>${escHtml(entry.section)}</span>
        <span class="tags">
          ${entry.deleted_at ? '<span class="tag">Deleted</span>' : ''}
          ${entry.score != null ? `<span class="mono">${(entry.score * 100).toFixed(0)}%</span>` : ''}
          <time title="${escHtml(timeTitle)}">${isEdited ? '✎ ' : ''}${displayTime}</time>
        </span>
      </header>
      <div class="entry-body">${escHtml(preview)}</div>
      ${tags ? `<div class="tags">${tags}${extraTags}</div>` : ''}
      <footer class="entry-foot">
        ${(entry.access_count || 0) > 0 ? `<time>↻ ${entry.access_count}</time>` : '<span></span>'}
        <span class="mono">${escHtml(entry.id)}</span>
      </footer>
    </article>`;
}

function renderCards(entries, append = false) {
  const grid = document.getElementById('cards-grid');
  if (!grid) return;
  if (!append) grid.innerHTML = '';

  if (entries.length === 0 && !append) {
    grid.innerHTML = `
      <div class="empty">
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
    card.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openViewModal(entry);
      }
    });
    grid.appendChild(card);
  }
}

async function loadConfig() {
  try {
    const config = await api.config();
    state.config = config;
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
  if (!grid) {
    state.loading = false;
    return;
  }

  if (!append) {
    grid.innerHTML = '<article class="empty empty-loading">Loading…</article>';
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
    const loadMore = document.getElementById('load-more-wrap');
    if (loadMore) loadMore.hidden = !state.hasMore;
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
  if (!grid) return;
  grid.innerHTML = '<article class="empty empty-loading">Searching…</article>';
  const loadMore = document.getElementById('load-more-wrap');
  const sortSelect = document.getElementById('sort-select');
  const searchBar = document.getElementById('search-results-bar');
  if (loadMore) loadMore.hidden = true;
  if (sortSelect) sortSelect.hidden = true;
  updatePageHeader('memories', `Search: "${query}"`);
  if (searchBar) searchBar.hidden = false;

  try {
    const params = { q: query, top_k: 40 };
    if (state.section) params.section = state.section;
    if (state.includeDeleted) params.include_deleted = 'true';
    const data = await api.search(params);
    const results = data.results || [];
    const label = document.getElementById('search-results-label');
    if (label) label.textContent = `${results.length} result${results.length !== 1 ? 's' : ''} for "${query}"`;
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
  const searchInput = document.getElementById('search-input');
  const searchBar = document.getElementById('search-results-bar');
  const sortSelect = document.getElementById('sort-select');
  if (searchInput) searchInput.value = '';
  if (searchBar) searchBar.hidden = true;
  if (sortSelect) sortSelect.hidden = false;
  if (!silent && state.config && state.view === 'memories') loadEntries();
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
  const extra = size ? ` ${size}` : '';
  return `<div class="modal${extra}">${inner}</div>`;
}

function handleEsc(e) {
  if (e.key === 'Escape') closeModal();
}

function updateTopbarBadge(view) {
  const badge = document.getElementById('topbar-badge');
  if (!badge) return;
  if (view === 'settings') {
    badge.textContent = 'Editable';
    badge.classList.add('badge--editable');
    return;
  }
  badge.textContent = 'Read-only';
  badge.classList.remove('badge--editable');
}

function openViewModal(entry) {
  const color = sectionColor(entry.section);
  const isEdited = entry.updated_at && entry.updated_at !== entry.created_at;
  const timeLabel = isEdited ? `Edited ${relTime(entry.updated_at)} · Created ${relTime(entry.created_at)}` : `Created ${relTime(entry.created_at)}`;
  const tags = (entry.tags || []).map((t) => `<span class="tag">${escHtml(t)}</span>`).join('');
  const scoreBadge = entry.score != null ? `<span class="mono">${(entry.score * 100).toFixed(0)}%</span>` : '';
  const accessBadge = (entry.access_count || 0) > 0 ? `<time>↻ ${entry.access_count}</time>` : '';
  const deletedNotice = entry.deleted_at
    ? `<article class="empty empty-error">Deleted ${escHtml(relTime(entry.deleted_at))}. History remains available.</article>`
    : '';

  openModal(modalShell(`
    <header class="modal-head">
      <div class="tags">
        <span class="tag"><span class="dot" style="--dot-color:${color}"></span>${escHtml(entry.section)}</span>
        ${scoreBadge}
        <time>${escHtml(timeLabel)}</time>
      </div>
      <button class="modal-close" type="button" aria-label="Close">×</button>
    </header>
    <section class="modal-body prose">
      ${deletedNotice}
      ${renderMarkdown(entry.content)}
      ${tags ? `<div class="tags">${tags}</div>` : ''}
      <footer class="tags">
        ${accessBadge}
        <span class="mono">${escHtml(entry.id)}</span>
      </footer>
    </section>
    <footer class="modal-foot">
      <button class="btn btn-ghost" id="btn-view-history" type="button">Version history</button>
    </footer>
  `));
  const historyBtn = document.getElementById('btn-view-history');
  if (historyBtn) {
    historyBtn.addEventListener('click', () => { closeModal(); openVersionsModal(entry); });
  }
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
    `, 'modal-wide'));
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
        <h4>Timeline</h4>
        <section class="timeline" id="timeline-root"></section>
      </section>
    `, 'modal-wide'));

    const timelineRoot = document.getElementById('timeline-root');

    function renderTimeline() {
      timelineRoot.innerHTML = versions.slice().reverse().map((revision, index) => {
        const isCurrent = revision.version === currentVersion;
        const isLast = index === versions.length - 1;
        const isSelectedFrom = revision.version === previousVersion && previousVersion !== currentVersion;
        const isSelectedTo = revision.version === currentVersion;
        const color = sectionColor(revision.section || entry.section);
        const preview = truncateContent(revision.content, 120);
        const activeClass = isSelectedFrom || isSelectedTo ? ' is-active' : '';
        return `
          <article class="version">
            <div class="version-inner${activeClass}" style="--section-color:${color}">
              <header class="tags">
                <span class="mono">v${revision.version}</span>
                <span class="tag">${escHtml(revision.section || '')}</span>
                ${revision.deleted_at ? '<span class="tag">deleted</span>' : ''}
                ${isCurrent ? '<span class="tag">current</span>' : ''}
                ${isSelectedFrom ? '<span class="tag">from</span>' : ''}
                ${isSelectedTo ? '<span class="tag">to</span>' : ''}
                <time>${escHtml(relTime(revision.updated_at || revision.created_at))}</time>
              </header>
              <p>${escHtml(preview)}</p>
              <footer class="tags">
                <span class="mono">Created ${escHtml(relTime(revision.created_at))}</span>
                <span class="mono">Updated ${escHtml(relTime(revision.updated_at || revision.created_at))}</span>
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
      <p class="lede">Merge entries with identical normalized content. Near-duplicates stay separate for the agent to review.</p>
      <label class="field">Section <small>(optional)</small>
        <select id="f-cons-section" class="input">
          <option value="">All sections</option>
          ${opts}
        </select>
      </label>
    </section>
    <footer class="modal-foot">
      <button class="btn btn-ghost" type="button" id="btn-cancel-consolidate">Cancel</button>
      <button class="btn btn-primary" type="button" id="btn-run-consolidate">Run</button>
    </footer>
  `, 'modal-compact'));

  bindEvent('btn-cancel-consolidate', 'click', closeModal);
  bindEvent('btn-run-consolidate', 'click', async () => {
    const section = document.getElementById('f-cons-section').value || null;
    try {
      const data = await api.consolidate({ section });
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
  const activeView = document.getElementById(`view-${name}`);
  if (activeView) activeView.hidden = false;
  document.querySelectorAll('[data-nav-view]').forEach((tab) => {
    const active = tab.dataset.view === name;
    if (active) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  });
  updateTopbarBadge(name);
  updatePageHeader(name);
  if (name === 'dashboard') renderDashboardView();
  else if (name === 'memories') loadEntries();
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
    renderEntryRows(
      'dash-recent-list',
      items.map((e) => ({
        id: e.id,
        source: e,
        title: truncateContent(e.content, 80),
        meta: `${e.section} · ${relTime(e.updated_at || e.created_at)}`,
        time: relTime(e.updated_at || e.created_at),
        color: sectionColor(e.section),
      })),
      'No entries yet.'
    );
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
    `, 'modal-xl'));
  } catch (e) {
    toast('Skills error: ' + e.message, 'error');
  }
}

function renderSkillsCards(skills) {
  if (!skills.length) {
    return '<article class="empty">No bundled skills found.</article>';
  }

  return skills.map((skill) => `
    <article class="entry entry--skill" data-open-skill="${escHtml(skill.id || '')}" role="button" tabindex="0" aria-label="View skill ${escHtml(skill.name || skill.id || 'skill')}">
      <h3>${escHtml(skill.name || skill.id)}</h3>
      <p>${escHtml(skill.description || 'No description.')}</p>
      <small class="lede" title="${escHtml(skill.path || '')}">${escHtml(skill.path || '')}</small>
    </article>
  `).join('');
}

async function renderSkillsView() {
  const root = document.getElementById('skills-root');
  root.innerHTML = '<article class="empty empty-loading">Loading…</article>';
  try {
    const data = await api.skills();
    const skills = data.skills || [];
    state.skills = skills;
    root.innerHTML = renderSkillsCards(skills);
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
    root.innerHTML = '<article class="empty empty-error">Failed to load bundled skills.</article>';
    toast('Skills error: ' + e.message, 'error');
  }
}

function settingsSectionTitle(title) {
  return `<h3 class="settings-title">${escHtml(title)}</h3>`;
}

function renderSettingsPage() {
  if (!state.config) {
    document.getElementById('settings-form-root').innerHTML = '<article class="empty">Config not loaded.</article>';
    return;
  }

  const cfg = state.config;
  const sectionRows = (cfg.sections || []).map((s) => `
    <tr data-section="${escHtml(s)}">
      <td><span class="dot" style="--dot-color:${sectionColor(s)}"></span>${escHtml(s)}</td>
      <td><input type="color" class="field-color" data-field="color" value="${escHtml((cfg.section_colors || {})[s] || '#888888')}"></td>
      <td><button class="btn btn-ghost btn-sm" type="button" data-remove="${escHtml(s)}" title="Remove">×</button></td>
    </tr>`).join('');

  document.getElementById('settings-form-root').innerHTML = `
    <div class="settings">
      <div class="settings-grid">
        <section class="surface">
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
        <section class="surface">
          ${settingsSectionTitle('Storage backend')}
          <label class="field">Backend
            <select id="cfg-storage-backend" class="input">
              <option value="json"${(cfg.storage_backend || 'json') === 'json' ? ' selected' : ''}>JSON (.rememb/entries.json)</option>
              <option value="sqlite"${cfg.storage_backend === 'sqlite' ? ' selected' : ''}>SQLite (.rememb/entries.db)</option>
            </select>
          </label>
          <p class="lede">SQLite scales better for large entry volumes. Switching migrates existing JSON entries automatically.</p>
          ${state.systemInfo?.storage_files?.length ? `<p class="lede">Active files: ${escHtml(state.systemInfo.storage_files.join(', '))}</p>` : ''}
        </section>
        <section class="surface">
          ${settingsSectionTitle('Sections')}
          <table class="table">
            <thead><tr><th>Name</th><th>Color</th><th></th></tr></thead>
            <tbody id="cfg-sections-tbody-page">${sectionRows}</tbody>
          </table>
          <div class="actions">
            <input type="text" id="cfg-new-section-page" class="input" placeholder="New section name">
            <button class="btn btn-ghost btn-sm" type="button" id="cfg-add-section-page">+ Add</button>
          </div>
        </section>
      </div>
      <section class="surface surface--split">
        <div>
          <h4>Consolidate duplicates</h4>
          <p class="lede">Remove literal duplicate entries with identical normalized content. Review near-duplicates in the agent before merging.</p>
        </div>
        <button class="btn btn-ghost btn-sm" type="button" id="btn-consolidate-page">Run consolidate</button>
      </section>
      <footer class="actions settings-foot">
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
      <td><span class="dot" style="--dot-color:#888888"></span>${escHtml(name)}</td>
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
bindEvent('search-input', 'input', (e) => {
  const q = e.target.value.trim();
  clearTimeout(searchTimer);
  if (!q) {
    clearSearch();
    return;
  }
  searchTimer = setTimeout(() => doSearch(q), 400);
});

bindEvent('search-input', 'keydown', (e) => {
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

bindEvent('btn-load-more', 'click', () => loadEntries(true));
bindEvent('clear-search', 'click', clearSearch);

bindEvent('sort-select', 'change', (e) => {
  const [sortBy, dir] = e.target.value.split('-');
  state.sort_by = sortBy;
  state.descending = dir === 'desc';
  state.offset = 0;
  loadEntries();
});

bindEvent('toggle-include-deleted', 'change', async (e) => {
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
  const includeDeletedToggle = document.getElementById('toggle-include-deleted');
  if (includeDeletedToggle) includeDeletedToggle.checked = state.includeDeleted;
  await loadStats();
  switchView('dashboard');
}

boot();
