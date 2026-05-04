const state = {
  data: null,
  activeWorkspaceId: null,
  activePageId: null,
  activeDatabaseId: null,
  activeDatabaseView: '',
  activePanel: 'comments',
  searchOpen: false,
  searchResults: [],
  searchQuery: '',
  searchType: '',
  searchWorkspaceId: '',
  localPage: null,
  dirty: false,
  draftRecovered: false,
  dragBlockId: null,
  selectedBlocks: new Set(),
  sse: null,
  lastMagicToken: '',
  presence: [],
  notice: '',
};

const BLOCK_TYPES = [
  'paragraph', 'heading1', 'heading2', 'heading3', 'bullet', 'numbered', 'todo', 'toggle', 'quote', 'callout', 'divider', 'code',
  'equation', 'table', 'columns', 'embed', 'bookmark', 'image', 'video', 'audio', 'pdf', 'synced',
];

const app = document.getElementById('app');

function draftKey(pageId) {
  return `noteflow:draft:${pageId}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();
  if (!response.ok) throw new Error(payload.error || payload || `Request failed: ${response.status}`);
  return payload;
}

function formatDate(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function pageById(id) {
  return state.data?.pages?.find((page) => page.id === id) || null;
}

function workspaceById(id) {
  return state.data?.workspaces?.find((workspace) => workspace.id === id) || null;
}

function pagesForWorkspace(workspaceId) {
  return (state.data?.pages || []).filter((page) => page.workspaceId === workspaceId);
}

function activeWorkspace() {
  return workspaceById(state.activeWorkspaceId) || state.data?.workspaces?.[0] || null;
}

function activePage() {
  return state.localPage || pageById(state.activePageId) || null;
}

function commentsForPage(pageId) {
  return (state.data?.comments || []).filter((comment) => comment.pageId === pageId);
}

function tasksForWorkspace(workspaceId) {
  return (state.data?.tasks || []).filter((task) => task.workspaceId === workspaceId);
}

function databasesForWorkspace(workspaceId) {
  return (state.data?.databases || []).filter((database) => database.workspaceId === workspaceId);
}

function rowsForDatabase(databaseId) {
  return (state.data?.databaseRows || []).filter((row) => row.databaseId === databaseId);
}

function filesForWorkspace(workspaceId) {
  return (state.data?.files || []).filter((file) => file.workspaceId === workspaceId);
}

function invitationsForWorkspace(workspaceId) {
  return (state.data?.invitations || []).filter((invitation) => invitation.workspaceId === workspaceId);
}

function activityForWorkspace(workspaceId) {
  return (state.data?.activity || []).filter((entry) => entry.workspaceId === workspaceId);
}

function databaseById(id) {
  return (state.data?.databases || []).find((database) => database.id === id) || null;
}

function activeDatabase() {
  return databaseById(state.activeDatabaseId) || null;
}

function currentUser() {
  return state.data?.user || null;
}

function userDirectory() {
  return state.data?.directory || (currentUser() ? [currentUser()] : []);
}

function workspaceMembers(workspace) {
  const directory = userDirectory();
  return (workspace?.members || []).map((member) => ({
    ...member,
    user: directory.find((entry) => entry.id === member.userId),
  }));
}

function currentWorkspaceRole(workspace) {
  if (!workspace || !currentUser()) return null;
  if (workspace.ownerId === currentUser().id) return 'owner';
  return workspace.members?.find((member) => member.userId === currentUser().id)?.role || null;
}

function sharedPagesForWorkspace(workspaceId) {
  return pagesForWorkspace(workspaceId).filter((page) => !page.deletedAt && (
    page.published
    || page.share?.enabled
    || (page.permissions || []).length
  ));
}

function toDateTimeLocal(value) {
  if (!value) return '';
  try {
    return new Date(value).toISOString().slice(0, 16);
  } catch {
    return '';
  }
}

function breadcrumbs(page) {
  const chain = [];
  let cursor = page;
  while (cursor) {
    chain.unshift(cursor);
    cursor = cursor.parentId ? pageById(cursor.parentId) : null;
  }
  return chain;
}

function computeToC(page) {
  return (page?.blocks || []).filter((block) => ['heading1', 'heading2', 'heading3'].includes(block.type));
}

function saveDraft(page) {
  localStorage.setItem(draftKey(page.id), JSON.stringify(page));
  state.dirty = true;
}

function clearDraft(pageId) {
  localStorage.removeItem(draftKey(pageId));
  state.dirty = false;
  state.draftRecovered = false;
}

function restoreDraftIfPresent(page) {
  const raw = localStorage.getItem(draftKey(page.id));
  if (!raw) return structuredClone(page);
  try {
    const parsed = JSON.parse(raw);
    state.draftRecovered = true;
    state.notice = 'Recovered an offline draft for this page.';
    return parsed;
  } catch {
    return structuredClone(page);
  }
}

function selectWorkspace(workspaceId) {
  state.activeWorkspaceId = workspaceId;
  localStorage.setItem('noteflow:workspace', workspaceId);
  const candidate = pagesForWorkspace(workspaceId).find((page) => !page.deletedAt) || null;
  selectPage(candidate?.id || null, false);
}

function selectPage(pageId, rerender = true) {
  state.activePageId = pageId;
  state.activeDatabaseId = null;
  localStorage.setItem('noteflow:page', pageId || '');
  const page = pageById(pageId);
  state.localPage = page ? restoreDraftIfPresent(page) : null;
  state.selectedBlocks = new Set();
  connectEvents();
  if (rerender) render();
}

function selectDatabase(databaseId, rerender = true) {
  state.activeDatabaseId = databaseId;
  const database = databaseById(databaseId);
  state.activeDatabaseView = database?.views?.[0]?.id || '';
  state.activePanel = 'databases';
  if (rerender) render();
}

let saveTimer = null;
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saveCurrentPage(), 700);
}

async function saveCurrentPage() {
  const page = activePage();
  if (!page || !currentUser()) return;
  try {
    await api(`/api/pages/${page.id}`, { method: 'PUT', body: JSON.stringify(page) });
    clearDraft(page.id);
    state.notice = 'Saved';
    await refresh(false);
  } catch (error) {
    state.notice = error.message;
    renderNotice();
  }
}

function touchPageVisit() {
  const page = activePage();
  if (!page || !currentUser()) return;
  api(`/api/pages/${page.id}/recent`, { method: 'POST', body: '{}' }).catch(() => {});
}

async function refresh(initial = false) {
  state.data = await api('/api/bootstrap');
  if (!state.activeWorkspaceId) state.activeWorkspaceId = localStorage.getItem('noteflow:workspace') || state.data.workspaces?.[0]?.id || null;
  if (!workspaceById(state.activeWorkspaceId)) state.activeWorkspaceId = state.data.workspaces?.[0]?.id || null;
  const defaultPageId = localStorage.getItem('noteflow:page') || pagesForWorkspace(state.activeWorkspaceId).find((page) => !page.deletedAt)?.id || state.data.pages?.[0]?.id || null;
  if (!state.activePageId || !pageById(state.activePageId)) state.activePageId = defaultPageId;
  const current = pageById(state.activePageId);
  if (!state.localPage || !state.dirty || !initial) state.localPage = current ? restoreDraftIfPresent(current) : null;
  render();
  touchPageVisit();
  connectEvents();
}

function renderNotice() {
  const node = document.querySelector('[data-role="notice"]');
  if (node) node.innerHTML = state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : '';
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function snippet(value, length = 90) {
  const text = String(value || '');
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function buildPageTree(workspaceId, parentId = null, depth = 0) {
  return pagesForWorkspace(workspaceId)
    .filter((page) => page.parentId === parentId && !page.deletedAt)
    .sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt))
    .map((page) => `
      <div>
        <button class="page-item ${state.activePageId === page.id ? 'active' : ''} page-indent-${Math.min(depth, 3)}" data-action="open-page" data-page-id="${page.id}">
          <span><strong>${escapeHtml(page.icon || '📄')} ${escapeHtml(page.title)}</strong><small>${escapeHtml(page.kind || 'page')} · ${page.backlinks?.length || 0} backlinks</small></span>
          <span class="badge">${page.commentsSummary?.unresolved || 0} 💬</span>
        </button>
        ${buildPageTree(workspaceId, page.id, depth + 1)}
      </div>`)
    .join('');
}

function renderSidebar(workspace, page) {
  const pages = pagesForWorkspace(workspace?.id || '');
  const databases = databasesForWorkspace(workspace?.id || '');
  const favorites = pages.filter((item) => item.favoriteBy?.includes(currentUser()?.id));
  const sharedPages = sharedPagesForWorkspace(workspace?.id || '');
  const recent = pages.filter((item) => item.recentBy?.some((entry) => entry.userId === currentUser()?.id)).sort((a, b) => {
    const aDate = a.recentBy?.find((entry) => entry.userId === currentUser()?.id)?.visitedAt || '';
    const bDate = b.recentBy?.find((entry) => entry.userId === currentUser()?.id)?.visitedAt || '';
    return String(bDate).localeCompare(String(aDate));
  });
  const trash = pages.filter((item) => item.deletedAt);
  return `
    <aside class="sidebar panel">
      <div class="brand"><div class="brand-badge">🌊</div><div><div>NoteFlow</div><small class="muted">Collaborative workspace</small></div></div>
      <div class="section ${currentUser() ? '' : 'hero-auth'}">
        ${currentUser() ? `
          <div class="list-card">
            <div class="inline-actions">
              <div class="avatar" style="background:${currentUser().avatarColor || '#4f46e5'}">${escapeHtml(currentUser().name?.[0] || 'U')}</div>
              <div><strong>${escapeHtml(currentUser().name)}</strong><div class="muted">${escapeHtml(currentUser().email)}</div></div>
            </div>
          </div>` : '<div class="notice">Read-only demo mode. Sign in to edit, collaborate, upload, or export.</div>'}
        <div class="workspace-switcher section">
          <select data-action="workspace-select">
            ${(state.data.workspaces || []).map((item) => `<option value="${item.id}" ${item.id === workspace?.id ? 'selected' : ''}>${escapeHtml(item.name)} (${item.kind})</option>`).join('')}
          </select>
          ${currentUser() ? `<button class="primary small" data-action="create-workspace">New workspace</button>` : ''}
        </div>
      </div>
      <div class="section">
        <div class="toolbar-row">
          <button class="primary small" data-action="new-page">New page</button>
          <button class="small" data-action="new-page-template">From template</button>
          ${currentUser() ? '<button class="small" data-action="create-database">New database</button>' : ''}
          <button class="small" data-action="open-search">Search ⌘K</button>
        </div>
      </div>
      <div class="section">
        <h3>Favorites</h3>
        ${favorites.length ? favorites.map((item) => `<button class="page-item" data-action="open-page" data-page-id="${item.id}">${escapeHtml(item.icon || '⭐')} ${escapeHtml(item.title)}</button>`).join('') : '<div class="muted">No favorites yet</div>'}
      </div>
      <div class="section">
        <h3>Recent pages</h3>
        ${recent.length ? recent.slice(0, 6).map((item) => `<button class="page-item" data-action="open-page" data-page-id="${item.id}">${escapeHtml(item.icon || '🕘')} ${escapeHtml(item.title)}</button>`).join('') : '<div class="muted">Open a page to track recents</div>'}
      </div>
      <div class="section">
        <h3>Pages</h3>
        <div class="page-tree">${workspace ? buildPageTree(workspace.id) : '<div class="muted">No workspace selected</div>'}</div>
      </div>
      <div class="section">
        <h3>Databases</h3>
        ${databases.length ? databases.map((database) => `<button class="page-item ${state.activePanel === 'databases' && state.activeDatabaseId === database.id ? 'active' : ''}" data-action="open-database" data-database-id="${database.id}">
          <span><strong>${escapeHtml(database.icon || '🗂️')} ${escapeHtml(database.title)}</strong><small>${escapeHtml(database.views?.map((view) => view.type).join(' · ') || 'table')}</small></span>
          <span class="badge">${rowsForDatabase(database.id).length} rows</span>
        </button>`).join('') : '<div class="muted">No databases yet</div>'}
      </div>
      <div class="section">
        <h3>Shared & published</h3>
        ${sharedPages.length ? sharedPages.slice(0, 8).map((item) => `<button class="page-item" data-action="open-page" data-page-id="${item.id}">
          <span><strong>${escapeHtml(item.icon || '🔗')} ${escapeHtml(item.title)}</strong><small>${item.published ? 'Published' : 'Shared internally'}</small></span>
        </button>`).join('') : '<div class="muted">No shared pages in this workspace</div>'}
      </div>
      <div class="section">
        <h3>Trash</h3>
        ${trash.length ? trash.map((item) => `<div class="list-card"><strong>${escapeHtml(item.title)}</strong><div class="muted">Deleted ${formatDate(item.deletedAt)}</div><button class="small good" data-action="restore-page" data-page-id="${item.id}">Restore</button></div>`).join('') : '<div class="muted">Trash is empty</div>'}
      </div>
    </aside>`;
}

function renderAuthSection() {
  if (currentUser()) return '';
  const teamWorkspaces = (state.data?.workspaces || []).filter((workspace) => workspace.kind === 'team');
  return `
    <div class="panel hero-auth section">
      <h2>Sign in to collaborate</h2>
      <p class="muted">Use email/password, demo OAuth, or a magic link. You can still browse the public demo workspace below.</p>
      <div class="auth-grid">
        <form class="form" data-form="register">
          <strong>Create account</strong>
          <input name="name" placeholder="Your name" required />
          <input name="email" type="email" placeholder="name@example.com" required />
          <input name="password" type="password" placeholder="Password" required />
          <button class="primary" type="submit">Register</button>
        </form>
        <form class="form" data-form="login">
          <strong>Sign in</strong>
          <input name="email" type="email" placeholder="name@example.com" required />
          <input name="password" type="password" placeholder="Password" required />
          <input name="code" placeholder="2FA code (if enabled)" />
          <button class="primary" type="submit">Login</button>
          <div class="toolbar-row">
            <button class="ghost" type="button" data-action="oauth" data-provider="google">Google OAuth</button>
            <button class="ghost" type="button" data-action="oauth" data-provider="github">GitHub OAuth</button>
          </div>
        </form>
      </div>
      <form class="form section" data-form="magic-link">
        <strong>Magic link</strong>
        <div class="toolbar-row">
          <input name="email" type="email" placeholder="email for magic link" required />
          <button type="submit">Send magic link</button>
        </div>
        ${state.lastMagicToken ? `<div class="notice">Dev token: <code>${escapeHtml(state.lastMagicToken)}</code> <button class="small" data-action="consume-magic">Use it now</button></div>` : ''}
      </form>
      <form class="form section" data-form="sso-login">
        <strong>Enterprise SSO / SAML demo</strong>
        <select name="workspaceId" required>
          ${teamWorkspaces.map((workspace) => `<option value="${workspace.id}">${escapeHtml(workspace.name)}</option>`).join('')}
        </select>
        <input name="name" placeholder="Full name" />
        <input name="email" type="email" placeholder="teammate@company.com" required />
        <input name="externalId" placeholder="SAML external id" />
        <button class="primary" type="submit">Sign in with SSO</button>
      </form>
    </div>`;
}

function databaseField(database, type) {
  return (database?.fields || []).find((field) => field.type === type) || database?.fields?.[0] || null;
}

function rowTitle(database, row) {
  const field = databaseField(database, 'title');
  return String(row?.values?.[field?.id] || 'Untitled row');
}

function rowStatus(database, row) {
  const field = databaseField(database, 'status');
  return String(row?.values?.[field?.id] || 'Unspecified');
}

function rowDue(database, row) {
  const field = databaseField(database, 'date');
  return String(row?.values?.[field?.id] || '');
}

function rowOwner(database, row) {
  const field = databaseField(database, 'person');
  const userId = row?.values?.[field?.id];
  return userDirectory().find((entry) => entry.id === userId)?.name || String(userId || 'Unassigned');
}

function renderBlock(block, index) {
  return `
    <div class="block-card ${state.selectedBlocks.has(block.id) ? 'selected' : ''}" draggable="true" data-action="drag-block" data-block-id="${block.id}" data-type="${block.type}">
      <div class="block-handle" title="Drag to reorder">⋮⋮</div>
      <div class="block-body">
        <div class="block-toolbar">
          <select data-action="block-type" data-block-id="${block.id}">
            ${BLOCK_TYPES.map((type) => `<option value="${type}" ${type === block.type ? 'selected' : ''}>${type}</option>`).join('')}
          </select>
          <label class="inline-actions"><input type="checkbox" data-action="select-block" data-block-id="${block.id}" ${state.selectedBlocks.has(block.id) ? 'checked' : ''}> Select</label>
          ${block.type === 'todo' ? `<label class="inline-checkbox"><input type="checkbox" data-action="toggle-check" data-block-id="${block.id}" ${block.checked ? 'checked' : ''}> Done</label>` : ''}
        </div>
        <textarea data-action="block-text" data-block-id="${block.id}" placeholder="Type / for commands">${escapeHtml(block.text || '')}</textarea>
        ${['bookmark','embed','image','video','audio','pdf'].includes(block.type) ? `<input data-action="block-url" data-block-id="${block.id}" value="${escapeHtml(block.url || '')}" placeholder="https://…" />` : ''}
        ${block.type === 'code' ? `<div class="code-preview">${escapeHtml(block.text || '')}</div>` : ''}
        ${String(block.text || '').startsWith('/') ? '<div class="slash-help">Slash commands: /heading1 /heading2 /bullet /todo /quote /code /image /bookmark /synced</div>' : ''}
      </div>
      <div class="inline-actions">
        <button class="small" data-action="duplicate-block" data-block-id="${block.id}">Duplicate</button>
        <button class="small warn" data-action="comment-block" data-block-id="${block.id}">Comment</button>
        <button class="small danger" data-action="delete-block" data-block-id="${block.id}">Delete</button>
      </div>
    </div>`;
}

function renderEditor(workspace, page) {
  if (!page) return '<div class="panel editor-card empty-state">Create or select a page to begin.</div>';
  const breadcrumbsHtml = breadcrumbs(page).map((item) => `<span>${escapeHtml(item.title)}</span>`).join(' / ');
  const toc = computeToC(page);
  const readOnly = !currentUser();
  const backlinks = page.backlinks || [];
  const publicUrl = page.published ? `${location.origin}/p/${page.slug}` : '';
  return `
    <section class="panel header-card">
      <div>
        <div class="muted">${escapeHtml(workspace?.name || 'Workspace')}</div>
        <h2 style="margin:4px 0 0">${escapeHtml(page.title)}</h2>
      </div>
      <div class="inline-actions">
        <button class="small" data-action="open-search">Quick switcher</button>
        ${currentUser() ? `<button class="small" data-action="logout">Logout</button>` : ''}
      </div>
    </section>
    ${renderAuthSection()}
    <section class="panel editor-card">
      <div class="cover ${page.cover ? '' : 'empty'}" style="background-image:url('${escapeHtml(page.cover || '')}')"></div>
      <div class="editor-meta">
        <div class="breadcrumbs">${breadcrumbsHtml || 'Root'}</div>
        <div class="title-row">
          <div class="page-icon">${escapeHtml(page.icon || '📄')}</div>
          <div style="flex:1;min-width:0">
            <input class="page-title" data-action="page-title" value="${escapeHtml(page.title)}" ${readOnly ? 'disabled' : ''} />
            <div class="muted">Custom URL: ${escapeHtml(page.customUrl || `/p/${page.slug}`)} · ${page.verified ? 'Verified' : 'Unverified'} · ${page.published ? 'Published' : 'Private'}</div>
          </div>
        </div>
        <div class="page-config">
          <label><input type="checkbox" data-action="page-toggle" data-field="locked" ${page.locked ? 'checked' : ''} ${readOnly ? 'disabled' : ''}/> Locked</label>
          <label><input type="checkbox" data-action="page-toggle" data-field="fullWidth" ${page.fullWidth ? 'checked' : ''} ${readOnly ? 'disabled' : ''}/> Full width</label>
          <label><input type="checkbox" data-action="page-toggle" data-field="smallText" ${page.smallText ? 'checked' : ''} ${readOnly ? 'disabled' : ''}/> Small text</label>
          <label><input type="checkbox" data-action="page-toggle" data-field="verified" ${page.verified ? 'checked' : ''} ${readOnly ? 'disabled' : ''}/> Verified</label>
          ${currentUser() ? `
            <button class="small" data-action="favorite-page">${page.favoriteBy?.includes(currentUser().id) ? '★ Favorited' : '☆ Favorite'}</button>
            <button class="small" data-action="duplicate-page">Duplicate</button>
            <button class="small ${page.published ? 'good' : ''}" data-action="publish-page">${page.published ? 'Unpublish' : 'Publish'}</button>
            <button class="small" data-action="share-page">${page.share?.enabled ? 'Shared' : 'Share link'}</button>
            <button class="small danger" data-action="trash-page">Trash</button>
            <button class="small" data-action="save-page">Save</button>` : ''}
          ${publicUrl ? `<a class="badge" href="${publicUrl}" target="_blank" rel="noreferrer">Open public page ↗</a>` : ''}
        </div>
      </div>
      <div class="editor-wrap ${page.fullWidth ? 'full-width' : ''} ${page.smallText ? 'small-text' : ''}">
        <div data-role="notice">${state.notice ? `<div class="notice">${escapeHtml(state.notice)}</div>` : ''}</div>
        ${state.draftRecovered ? '<div class="notice">Offline draft restored. Save to persist it to the server.</div>' : ''}
        <div class="toolbar-row section">
          ${currentUser() ? `<button class="primary small" data-action="add-block">Add block</button>
          <button class="small" data-action="bulk-duplicate">Duplicate selected</button>
          <button class="small danger" data-action="bulk-delete">Delete selected</button>
          <button class="small" data-action="page-settings">Share/SEO</button>
          <button class="small" data-action="export-page" data-format="markdown">Export MD</button>
          <button class="small" data-action="export-page" data-format="html">Export HTML</button>
          <button class="small" data-action="export-page" data-format="pdf">Export PDF</button>
          <button class="small" data-action="export-page" data-format="json">Export JSON</button>
          <button class="small" data-action="export-page" data-format="csv">Export CSV</button>` : ''}
        </div>
        <div class="block-list">${(page.blocks || []).map(renderBlock).join('')}</div>
        ${currentUser() ? '<div class="section"><button class="ghost" data-action="add-block">+ Add another block</button></div>' : ''}
        <div class="section toc">
          <h3>Table of contents</h3>
          ${toc.length ? toc.map((block) => `<a href="#">${escapeHtml(block.text || block.type)}</a>`).join('') : '<div class="muted">Add headings to generate a TOC.</div>'}
        </div>
        <div class="section">
          <h3>Backlinks</h3>
          ${backlinks.length ? backlinks.map((item) => `<button class="page-item" data-action="open-page" data-page-id="${item.id}">${escapeHtml(item.title)}</button>`).join('') : '<div class="muted">No backlinks yet. Mention [[Page Title]] in another page.</div>'}
        </div>
      </div>
    </section>`;
}

function renderCommentsPanel(page) {
  const comments = commentsForPage(page?.id).sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
  const directory = userDirectory();
  const renderThread = (parentId = null) => comments
    .filter((comment) => comment.parentCommentId === parentId)
    .map((comment) => {
      const author = directory.find((entry) => entry.id === comment.authorUserId) || { name: 'Unknown', avatarColor: '#94a3b8' };
      return `<div class="comment-card ${comment.parentCommentId ? 'comment-thread' : ''}">
        <div class="inline-actions"><div class="avatar" style="background:${author.avatarColor || '#94a3b8'}">${escapeHtml(author.name?.[0] || '?')}</div><strong>${escapeHtml(author.name)}</strong><span class="badge">${comment.resolved ? 'Resolved' : 'Open'}</span></div>
        <div>${escapeHtml(comment.text)}</div>
        <div class="muted">${formatDate(comment.createdAt)} ${comment.blockId ? '· inline block comment' : ''}</div>
        <div class="toolbar-row">
          ${currentUser() ? `<button class="small" data-action="reply-comment" data-comment-id="${comment.id}">Reply</button>
          <button class="small" data-action="resolve-comment" data-comment-id="${comment.id}">${comment.resolved ? 'Reopen' : 'Resolve'}</button>` : ''}
        </div>
        ${renderThread(comment.id)}
      </div>`;
    }).join('');
  return `
    <div class="section">
      <h3>Page comments & discussions</h3>
      ${currentUser() ? `
        <form class="form" data-form="comment">
          <textarea name="text" placeholder="Add a threaded comment, mention teammates, or annotate a block…" required></textarea>
          <input name="mentions" placeholder="Mention user ids separated by commas (optional)" />
          <button class="primary" type="submit">Post comment</button>
        </form>` : '<div class="muted">Sign in to comment.</div>'}
    </div>
    ${renderThread() || '<div class="muted">No comments yet.</div>'}`;
}

function renderTasksPanel(workspace) {
  const tasks = tasksForWorkspace(workspace?.id || '');
  const mine = tasks.filter((task) => task.assigneeUserId === currentUser()?.id);
  const open = tasks.filter((task) => task.status !== 'done');
  const milestones = tasks.filter((task) => task.milestone);
  const workload = Object.values(tasks.reduce((acc, task) => {
    const key = task.assigneeUserId || 'unassigned';
    acc[key] ||= { label: userDirectory().find((entry) => entry.id === task.assigneeUserId)?.name || 'Unassigned', count: 0 };
    acc[key].count += 1;
    return acc;
  }, {}));
  return `
    <div class="metric-grid section">
      <div class="metric"><div class="muted">Open tasks</div><strong>${open.length}</strong></div>
      <div class="metric"><div class="muted">My tasks</div><strong>${mine.length}</strong></div>
      <div class="metric"><div class="muted">Milestones</div><strong>${milestones.length}</strong></div>
    </div>
    ${currentUser() ? `
      <form class="form section" data-form="task">
        <h3>Create task</h3>
        <input name="title" placeholder="Task title" required />
        <textarea name="description" placeholder="Description, linked doc, or dependencies"></textarea>
        <div class="grid-two">
          <input name="dueDate" type="date" />
          <select name="priority"><option>low</option><option selected>medium</option><option>high</option></select>
          <select name="status"><option value="todo">todo</option><option value="in-progress">in-progress</option><option value="blocked">blocked</option><option value="done">done</option></select>
          <input name="assigneeUserId" placeholder="Assignee user id" />
          <input name="recurring" placeholder="Recurrence e.g. weekly" />
          <input name="dependencies" placeholder="Dependency task ids comma-separated" />
        </div>
        <label><input name="milestone" type="checkbox" /> Milestone</label>
        <button class="primary" type="submit">Add task</button>
      </form>` : ''}
    <div class="section">
      <div class="toolbar-row"><button class="small" data-action="download-ics">Calendar (.ics)</button></div>
      <h3>Team task views</h3>
      ${tasks.length ? tasks.map((task) => `<div class="task-card">
        <strong>${escapeHtml(task.title)}</strong>
        <div class="muted">${escapeHtml(task.status)} · ${escapeHtml(task.priority)} · due ${escapeHtml(task.dueDate || 'n/a')}</div>
        <div>${escapeHtml(task.description || '')}</div>
        <div class="muted">Dependencies: ${(task.dependencies || []).join(', ') || 'none'} · Progress ${task.progress || 0}%</div>
        ${currentUser() ? `<div class="toolbar-row"><button class="small" data-action="advance-task" data-task-id="${task.id}">Advance status</button><button class="small" data-action="link-task-page" data-task-id="${task.id}">Link current page</button></div>` : ''}
      </div>`).join('') : '<div class="muted">No tasks in this workspace.</div>'}
    </div>
    <div class="section">
      <h3>Workload view</h3>
      ${workload.map((item) => `<div class="list-card"><strong>${escapeHtml(item.label)}</strong><div class="muted">${item.count} tasks assigned</div></div>`).join('') || '<div class="muted">No workload data yet.</div>'}
    </div>`;
}

function renderFilesPanel(workspace, page) {
  const files = filesForWorkspace(workspace?.id || '');
  const usedMb = (files.reduce((sum, file) => sum + (file.size || 0), 0) / (1024 * 1024)).toFixed(2);
  return `
    <div class="section">
      <h3>Files & media</h3>
      <div class="muted">Usage: ${usedMb} MB / ${(workspace?.settings?.storageQuotaMb || 0)} MB · Signed URL delivery enabled</div>
    </div>
    ${currentUser() ? `
      <form class="form section" data-form="upload">
        <input name="file" type="file" required />
        <button class="primary" type="submit">Upload & attach</button>
      </form>` : ''}
    ${files.map((file) => `<div class="file-card">
      <strong>${escapeHtml(file.name)}</strong>
      <div class="muted">${escapeHtml(file.type)} · ${(file.size / 1024).toFixed(1)} KB · versions ${file.versions?.length || 0}</div>
      <div class="toolbar-row">
        <a class="badge" href="${file.signedUrl || `/files/${file.id}`}" target="_blank" rel="noreferrer">Open</a>
        ${currentUser() ? `<button class="small" data-action="replace-file" data-file-id="${file.id}">Replace version</button>` : ''}
      </div>
    </div>`).join('') || '<div class="muted">No files yet.</div>'}`;
}

function renderNotificationsPanel() {
  const notifications = state.data?.notifications || [];
  const emailOutbox = state.data?.emailOutbox || [];
  return `
    <div class="section">
      <h3>Notification inbox</h3>
      ${(notifications.length ? notifications : []).map((notification) => `<div class="notification-card">
        <strong>${escapeHtml(notification.title)}</strong>
        <div>${escapeHtml(notification.body)}</div>
        <div class="muted">${formatDate(notification.createdAt)} · ${escapeHtml(notification.type)}</div>
        ${!notification.read && currentUser() ? `<button class="small" data-action="mark-read" data-notification-id="${notification.id}">Mark read</button>` : ''}
      </div>`).join('') || '<div class="muted">No notifications yet.</div>'}
    </div>
    <div class="section">
      <h3>Email digest preview</h3>
      ${emailOutbox.map((mail) => `<div class="list-card"><strong>${escapeHtml(mail.subject)}</strong><div>${escapeHtml(mail.body)}</div><div class="muted">to ${escapeHtml(mail.to)} · ${formatDate(mail.createdAt)}</div></div>`).join('') || '<div class="muted">No email previews queued.</div>'}
    </div>
    ${currentUser() ? `
      <form class="form section" data-form="notification-preferences">
        <h4>Preferences</h4>
        <label><input type="checkbox" name="email" ${currentUser().notificationPreferences?.email !== false ? 'checked' : ''}/> Email notifications</label>
        <label><input type="checkbox" name="mentions" ${currentUser().notificationPreferences?.mentions !== false ? 'checked' : ''}/> Mentions</label>
        <label><input type="checkbox" name="comments" ${currentUser().notificationPreferences?.comments !== false ? 'checked' : ''}/> Comments</label>
        <label><input type="checkbox" name="assignments" ${currentUser().notificationPreferences?.assignments !== false ? 'checked' : ''}/> Assignments</label>
        <label><input type="checkbox" name="digest" ${currentUser().notificationPreferences?.digest !== false ? 'checked' : ''}/> Digest emails</label>
        <button class="primary" type="submit">Save preferences</button>
      </form>` : ''}`;
}

function renderHistoryPanel(page) {
  return `
    <div class="section">
      <h3>Page history & versioning</h3>
      ${(page?.history || []).map((version) => `<div class="history-card">
        <strong>${escapeHtml(version.title)}</strong>
        <div class="muted">${formatDate(version.createdAt)} · ${escapeHtml(version.userId)}</div>
        ${currentUser() ? `<button class="small" data-action="restore-version" data-version-id="${version.id}">Restore snapshot</button>` : ''}
      </div>`).join('') || '<div class="muted">No snapshots yet. Save page updates to create history.</div>'}
    </div>`;
}

function renderSearchImportPanel(workspace, page) {
  return `
    <div class="section">
      <h3>Search & knowledge</h3>
      <div class="toolbar-row"><button class="small" data-action="open-search">Open quick switcher</button></div>
      ${(state.searchResults || []).slice(0, 8).map((result) => `<div class="search-result"><strong>${escapeHtml(result.title)}</strong><div>${escapeHtml(result.snippet)}</div><div class="muted">${result.type} · ${formatDate(result.updatedAt)}</div></div>`).join('') || '<div class="muted">Run a search to see ranking, snippets, and permission-trimmed results.</div>'}
    </div>
    ${currentUser() ? `
      <form class="form section" data-form="import">
        <h3>Import</h3>
        <div class="grid-two">
          <select name="format"><option value="markdown">Markdown</option><option value="html">HTML</option><option value="csv">CSV Tasks</option><option value="docx">DOCX text</option></select>
          <input name="title" placeholder="Imported page title" />
        </div>
        <textarea name="content" placeholder="Paste Markdown, HTML, CSV, or extracted DOCX text here" required></textarea>
        <button class="primary" type="submit">Import into current workspace</button>
      </form>
      <div class="section">
        <h3>Workspace export</h3>
        <button class="small" data-action="export-workspace">Download workspace JSON</button>
      </div>` : ''}`;
}

function renderDatabaseView(database, rows) {
  const selectedView = database?.views?.find((view) => view.id === state.activeDatabaseView) || database?.views?.[0] || { type: 'table', name: 'Table' };
  const type = selectedView.type || 'table';
  if (type === 'board') {
    const statusField = selectedView.groupBy || databaseField(database, 'status')?.id;
    const groups = [...new Set(rows.map((row) => row.values?.[statusField] || 'Unspecified'))];
    return `<div class="database-board">${groups.map((group) => `<div class="board-column"><h4>${escapeHtml(group)}</h4>${rows.filter((row) => (row.values?.[statusField] || 'Unspecified') === group).map((row) => `<div class="task-card"><strong>${escapeHtml(rowTitle(database, row))}</strong><div class="muted">${escapeHtml(rowOwner(database, row))} · ${escapeHtml(rowDue(database, row) || 'No date')}</div><div class="toolbar-row">${currentUser() ? `<button class="small" data-action="advance-row" data-row-id="${row.id}">Advance</button><button class="small" data-action="verify-row" data-row-id="${row.id}">${row.verified ? 'Unverify' : 'Verify'}</button>` : ''}</div></div>`).join('') || '<div class="muted">No rows</div>'}</div>`).join('')}</div>`;
  }
  if (type === 'calendar' || type === 'timeline') {
    return `<div class="section">${rows.slice().sort((a, b) => String(rowDue(database, a)).localeCompare(String(rowDue(database, b)))).map((row) => `<div class="list-card"><strong>${escapeHtml(rowDue(database, row) || 'No date')}</strong><div>${escapeHtml(rowTitle(database, row))}</div><div class="muted">${escapeHtml(rowStatus(database, row))} · ${escapeHtml(rowOwner(database, row))}</div></div>`).join('') || '<div class="muted">No scheduled rows yet.</div>'}</div>`;
  }
  if (type === 'gallery') {
    return `<div class="database-gallery">${rows.map((row) => `<div class="file-card"><strong>${escapeHtml(rowTitle(database, row))}</strong><div class="muted">${escapeHtml(rowStatus(database, row))}</div><div>${escapeHtml(rowOwner(database, row))}</div><div class="muted">${escapeHtml(rowDue(database, row) || 'No date')}</div></div>`).join('') || '<div class="muted">No cards to display.</div>'}</div>`;
  }
  return `<div class="database-table-wrap"><table class="database-table"><thead><tr>${(database?.fields || []).map((field) => `<th>${escapeHtml(field.name)}</th>`).join('')}<th>Actions</th></tr></thead><tbody>${rows.map((row) => `<tr>${(database?.fields || []).map((field) => `<td>${escapeHtml(row.values?.[field.id] ?? '')}</td>`).join('')}<td><div class="toolbar-row">${currentUser() ? `<button class="small" data-action="edit-row" data-row-id="${row.id}">Edit</button><button class="small" data-action="advance-row" data-row-id="${row.id}">Advance</button><button class="small" data-action="verify-row" data-row-id="${row.id}">${row.verified ? 'Unverify' : 'Verify'}</button>` : ''}</div></td></tr>`).join('') || '<tr><td colspan="99">No rows yet.</td></tr>'}</tbody></table></div>`;
}

function renderDatabasesPanel(workspace) {
  const database = activeDatabase() || databasesForWorkspace(workspace?.id || '')[0] || null;
  const rows = database ? rowsForDatabase(database.id) : [];
  const selectedView = database?.views?.find((view) => view.id === state.activeDatabaseView) || database?.views?.[0] || null;
  if (!database) {
    return `<div class="section"><h3>Databases</h3><div class="muted">Create a database to manage projects, tasks, milestones, and team knowledge.</div>${currentUser() ? '<button class="primary small" data-action="create-database">Create database</button>' : ''}</div>`;
  }
  return `
    <div class="section">
      <div class="inline-actions"><h3 style="margin:0">${escapeHtml(database.icon || '🗂️')} ${escapeHtml(database.title)}</h3><span class="badge">${rows.length} rows</span></div>
      <div class="muted">${escapeHtml(database.description || 'Workspace database')}</div>
      <div class="metric-grid section">
        <div class="metric"><div class="muted">Views</div><strong>${database.views?.length || 0}</strong></div>
        <div class="metric"><div class="muted">Rows</div><strong>${rows.length}</strong></div>
        <div class="metric"><div class="muted">Verified</div><strong>${rows.filter((row) => row.verified).length}</strong></div>
      </div>
      <div class="toolbar-row">
        <select data-action="database-view-select">${(database.views || []).map((view) => `<option value="${view.id}" ${selectedView?.id === view.id ? 'selected' : ''}>${escapeHtml(view.name)} (${escapeHtml(view.type)})</option>`).join('')}</select>
        ${currentUser() ? `<button class="small" data-action="export-database" data-format="csv">Export CSV</button><button class="small" data-action="export-database" data-format="json">Export JSON</button><button class="small" data-action="export-database" data-format="markdown">Export MD</button>` : ''}
      </div>
    </div>
    ${currentUser() ? `<form class="form section" data-form="database-row"><h4>Add row</h4>${(database.fields || []).map((field) => {
      if (field.type === 'status' || field.type === 'select') return `<select name="${field.id}">${(field.options || ['']).map((option) => `<option value="${escapeHtml(option)}">${escapeHtml(option)}</option>`).join('')}</select>`;
      if (field.type === 'date') return `<input name="${field.id}" type="date" placeholder="${escapeHtml(field.name)}" />`;
      return `<input name="${field.id}" placeholder="${escapeHtml(field.name)}" ${field.type === 'title' ? 'required' : ''} />`;
    }).join('')}<button class="primary" type="submit">Add row</button></form>` : ''}
    <div class="section">
      <h4>${escapeHtml(selectedView?.name || 'View')}</h4>
      ${renderDatabaseView(database, rows)}
    </div>`;
}

function renderAdminPanel(workspace, page) {
  const workspaceRole = currentWorkspaceRole(workspace);
  const invitations = invitationsForWorkspace(workspace?.id || '');
  const activity = activityForWorkspace(workspace?.id || '').slice(0, 16);
  const database = activeDatabase() || databasesForWorkspace(workspace?.id || '')[0] || null;
  const pagePermissions = page?.permissions || [];
  const databasePermissions = database?.permissions || [];
  const assignableUsers = userDirectory().filter((entry) => entry.id !== currentUser()?.id);
  return `
    <div class="section">
      <h3>Workspace admin & security</h3>
      <div class="muted">${workspaceRole === 'owner' ? 'Owner controls for sharing, enterprise identity, and provisioning.' : 'Read-only audit and identity overview for this workspace.'}</div>
    </div>
    ${workspaceRole === 'owner' ? `
      <form class="form section" data-form="workspace-settings">
        <h4>Workspace settings</h4>
        <div class="grid-two">
          <input name="domainRestriction" value="${escapeHtml(workspace?.settings?.domainRestriction || '')}" placeholder="Domain restriction e.g. example.com" />
          <input name="storageQuotaMb" type="number" min="25" value="${escapeHtml(workspace?.settings?.storageQuotaMb || 250)}" placeholder="Storage quota (MB)" />
          <select name="databasePermissions">
            <option value="workspace-role" ${(workspace?.settings?.databasePermissions || '') === 'workspace-role' ? 'selected' : ''}>Workspace role</option>
            <option value="explicit" ${(workspace?.settings?.databasePermissions || '') === 'explicit' ? 'selected' : ''}>Explicit grants</option>
          </select>
          <div class="inline-actions">
            <label><input type="checkbox" name="allowGuests" ${workspace?.settings?.allowGuests !== false ? 'checked' : ''}/> Guests</label>
            <label><input type="checkbox" name="publicSharing" ${workspace?.settings?.publicSharing !== false ? 'checked' : ''}/> Public sharing</label>
            <label><input type="checkbox" name="samlEnabled" ${workspace?.settings?.samlEnabled ? 'checked' : ''}/> SAML</label>
            <label><input type="checkbox" name="scimEnabled" ${workspace?.settings?.scimEnabled ? 'checked' : ''}/> SCIM</label>
          </div>
        </div>
        <button class="primary" type="submit">Save workspace settings</button>
      </form>
      <form class="form section" data-form="scim-provision">
        <h4>SCIM provisioning</h4>
        <div class="grid-two">
          <input name="name" placeholder="Provisioned member name" required />
          <input name="email" type="email" placeholder="member@company.com" required />
          <input name="externalId" placeholder="SCIM external id" required />
          <input name="title" placeholder="Job title" />
          <select name="role"><option value="viewer">viewer</option><option value="commenter">commenter</option><option value="editor">editor</option></select>
        </div>
        <button class="primary" type="submit">Provision member</button>
      </form>` : ''}
    <div class="section">
      <h4>Pending and accepted invitations</h4>
      ${invitations.map((invitation) => `<div class="list-card"><strong>${escapeHtml(invitation.email)}</strong><div class="muted">${escapeHtml(invitation.role)} · invited ${formatDate(invitation.createdAt)} · ${invitation.acceptedAt ? `accepted ${formatDate(invitation.acceptedAt)}` : 'pending'}</div></div>`).join('') || '<div class="muted">No invitations yet.</div>'}
    </div>
    <div class="section">
      <h4>Identity & device sessions</h4>
      <div class="list-card">
        <strong>${escapeHtml(currentUser()?.name || 'Guest')}</strong>
        <div class="muted">Auth methods: ${(currentUser()?.identity?.authMethods || []).map(escapeHtml).join(', ') || 'none'}</div>
        <div class="muted">Last identity audit: ${formatDate(currentUser()?.identity?.lastAuditAt)}</div>
        <div class="toolbar-row">
          ${currentUser() ? `<button class="small" type="button" data-action="setup-2fa">${currentUser().twoFactorEnabled ? '2FA enabled' : 'Enable 2FA'}</button>` : ''}
        </div>
      </div>
      ${(state.data?.sessions || []).map((session) => `<div class="list-card"><strong>${escapeHtml(session.label || 'Session')}</strong><div class="muted">${escapeHtml(session.userAgent || 'unknown')} · ${escapeHtml(session.ipAddress || 'unknown')} · last seen ${formatDate(session.lastSeenAt)}</div></div>`).join('') || '<div class="muted">No active sessions.</div>'}
    </div>
    <div class="section">
      <h4>Page sharing, SEO & permissions</h4>
      ${page ? `
        <form class="form section" data-form="page-sharing">
          <div class="grid-two">
            <input name="slug" value="${escapeHtml(page.slug || '')}" placeholder="Public slug" />
            <input name="customUrl" value="${escapeHtml(page.customUrl || '')}" placeholder="Custom URL (/product-strategy)" />
            <input name="seoTitle" value="${escapeHtml(page.seo?.title || page.title || '')}" placeholder="SEO title" />
            <input name="seoDescription" value="${escapeHtml(page.seo?.description || '')}" placeholder="SEO description" />
            <input name="allowedDomain" value="${escapeHtml(page.share?.allowedDomain || '')}" placeholder="Allowed domain" />
            <input name="expiresAt" type="datetime-local" value="${escapeHtml(toDateTimeLocal(page.share?.expiresAt || ''))}" />
          </div>
          <div class="inline-actions">
            <label><input type="checkbox" name="published" ${page.published ? 'checked' : ''}/> Published</label>
            <label><input type="checkbox" name="shared" ${page.share?.enabled ? 'checked' : ''}/> Shared link</label>
          </div>
          <button class="primary" type="submit">Save share settings</button>
        </form>
        <div class="section">
          ${pagePermissions.map((rule) => {
            const user = userDirectory().find((entry) => entry.id === rule.userId);
            return `<div class="list-card"><strong>${escapeHtml(user?.name || rule.userId)}</strong><div class="muted">Page access: ${escapeHtml(rule.access)}</div></div>`;
          }).join('') || '<div class="muted">No page-specific grants yet.</div>'}
          ${workspaceRole === 'owner' || workspaceRole === 'editor' ? `<form class="form" data-form="page-permission">
            <select name="userId" required>${assignableUsers.map((entry) => `<option value="${entry.id}">${escapeHtml(entry.name)} · ${escapeHtml(entry.email)}</option>`).join('')}</select>
            <select name="access"><option value="viewer">viewer</option><option value="commenter">commenter</option><option value="editor">editor</option><option value="owner">owner</option></select>
            <button class="primary" type="submit">Grant page access</button>
          </form>` : ''}
        </div>` : '<div class="muted">Select a page to manage sharing.</div>'}
    </div>
    <div class="section">
      <h4>Database permissions</h4>
      ${database ? `
        ${(databasePermissions.map((rule) => {
          const user = userDirectory().find((entry) => entry.id === rule.userId);
          return `<div class="list-card"><strong>${escapeHtml(user?.name || rule.userId)}</strong><div class="muted">Database access: ${escapeHtml(rule.access)}</div></div>`;
        }).join('')) || '<div class="muted">No database-specific grants yet.</div>'}
        ${workspaceRole === 'owner' || workspaceRole === 'editor' ? `<form class="form" data-form="database-permission">
          <select name="userId" required>${assignableUsers.map((entry) => `<option value="${entry.id}">${escapeHtml(entry.name)} · ${escapeHtml(entry.email)}</option>`).join('')}</select>
          <select name="access"><option value="viewer">viewer</option><option value="editor">editor</option><option value="owner">owner</option></select>
          <button class="primary" type="submit">Grant database access</button>
        </form>` : ''}` : '<div class="muted">Open a database to manage database-level access.</div>'}
    </div>
    <div class="section">
      <h4>Workspace activity feed</h4>
      ${activity.map((entry) => `<div class="history-card"><strong>${escapeHtml(entry.kind)}</strong><div>${escapeHtml(entry.message || '')}</div><div class="muted">${formatDate(entry.createdAt)}</div></div>`).join('') || '<div class="muted">No activity yet.</div>'}
    </div>`;
}

function renderDetails(workspace, page) {
  const members = workspaceMembers(workspace);
  return `
    <aside class="details panel">
      <div class="right-panel-tabs">
        ${['comments', 'tasks', 'databases', 'files', 'notifications', 'history', 'search', 'admin'].map((tab) => `<button class="small ${state.activePanel === tab ? 'primary' : ''}" data-action="set-panel" data-panel="${tab}">${tab}</button>`).join('')}
      </div>
      <div class="section">
        <h3>Presence</h3>
        <div class="presence-row">${(state.presence || []).map((person) => `<div class="badge"><span class="avatar" style="background:${person.avatarColor || '#64748b'}">${escapeHtml(person.name?.[0] || '?')}</span>${escapeHtml(person.name)}</div>`).join('') || '<span class="muted">No active collaborators on this page.</span>'}</div>
      </div>
      <div class="section">
        <h3>Workspace members</h3>
        ${members.map((member) => `<div class="list-card"><strong>${escapeHtml(member.user?.name || member.userId)}</strong><div class="muted">${escapeHtml(member.role)} · ${escapeHtml(member.user?.email || '')}</div></div>`).join('') || '<div class="muted">No members yet.</div>'}
        ${currentUser() ? `<form class="form" data-form="invite"><input name="email" type="email" placeholder="Invite by email" required /><select name="role"><option>viewer</option><option>commenter</option><option selected>editor</option></select><button class="primary" type="submit">Invite</button></form>` : ''}
      </div>
      ${state.activePanel === 'comments' ? renderCommentsPanel(page) : ''}
      ${state.activePanel === 'tasks' ? renderTasksPanel(workspace) : ''}
      ${state.activePanel === 'databases' ? renderDatabasesPanel(workspace) : ''}
      ${state.activePanel === 'files' ? renderFilesPanel(workspace, page) : ''}
      ${state.activePanel === 'notifications' ? renderNotificationsPanel() : ''}
      ${state.activePanel === 'history' ? renderHistoryPanel(page) : ''}
      ${state.activePanel === 'search' ? renderSearchImportPanel(workspace, page) : ''}
      ${state.activePanel === 'admin' ? renderAdminPanel(workspace, page) : ''}
    </aside>`;
}

function renderSearchModal() {
  if (!state.searchOpen) return '';
  return `
    <div class="search-modal" data-action="close-search">
      <div class="search-dialog" onclick="event.stopPropagation()">
        <div class="section"><input type="search" id="search-input" placeholder="Search pages, databases, rows, comments, tasks, and files…" value="${escapeHtml(state.searchQuery)}" autofocus /></div>
        <div class="search-filters section">
          <select id="search-type"><option value="" ${state.searchType === '' ? 'selected' : ''}>All types</option><option value="page" ${state.searchType === 'page' ? 'selected' : ''}>Pages</option><option value="task" ${state.searchType === 'task' ? 'selected' : ''}>Tasks</option><option value="database" ${state.searchType === 'database' ? 'selected' : ''}>Databases</option><option value="database_row" ${state.searchType === 'database_row' ? 'selected' : ''}>Database rows</option><option value="comment" ${state.searchType === 'comment' ? 'selected' : ''}>Comments</option><option value="file" ${state.searchType === 'file' ? 'selected' : ''}>Files</option></select>
          <select id="search-workspace"><option value="" ${state.searchWorkspaceId === '' ? 'selected' : ''}>All workspaces</option>${(state.data.workspaces || []).map((workspace) => `<option value="${workspace.id}" ${state.searchWorkspaceId === workspace.id ? 'selected' : ''}>${escapeHtml(workspace.name)}</option>`).join('')}</select>
        </div>
        <div id="search-results">${(state.searchResults || []).map((result) => `<div class="search-result"><strong>${escapeHtml(result.title)}</strong><div>${escapeHtml(result.snippet)}</div><div class="muted">${escapeHtml(result.type)} · ${formatDate(result.updatedAt)}</div>${result.type === 'page' ? `<button class="small" data-action="open-page" data-page-id="${result.id}">Open</button>` : ''}${result.type === 'database' ? `<button class="small" data-action="open-database" data-database-id="${result.id}">Open</button>` : ''}${result.type === 'database_row' ? `<button class="small" data-action="open-database" data-database-id="${result.parentId}">Open database</button>` : ''}</div>`).join('') || '<div class="muted">Type to search.</div>'}</div>
      </div>
    </div>`;
}

function render() {
  const workspace = activeWorkspace();
  const page = activePage();
  app.innerHTML = `
    <div class="shell">
      ${renderSidebar(workspace, page)}
      <main class="main">${renderEditor(workspace, page)}</main>
      ${renderDetails(workspace, page)}
    </div>
    ${renderSearchModal()}`;
  document.body.classList.toggle('modal-open', state.searchOpen);
  attachListeners();
}

function markdownShortcut(block) {
  const text = String(block.text || '');
  const slash = text.trim().slice(1);
  if (text.startsWith('/')) {
    if (BLOCK_TYPES.includes(slash)) {
      block.type = slash;
      block.text = '';
      return block;
    }
  }
  if (text.startsWith('# ')) { block.type = 'heading1'; block.text = text.slice(2); }
  if (text.startsWith('## ')) { block.type = 'heading2'; block.text = text.slice(3); }
  if (text.startsWith('### ')) { block.type = 'heading3'; block.text = text.slice(4); }
  if (text.startsWith('- [ ] ')) { block.type = 'todo'; block.text = text.slice(6); block.checked = false; }
  if (text.startsWith('- [x] ')) { block.type = 'todo'; block.text = text.slice(6); block.checked = true; }
  if (text.startsWith('- ')) { block.type = 'bullet'; block.text = text.slice(2); }
  if (/^\d+\. /.test(text)) { block.type = 'numbered'; block.text = text.replace(/^\d+\. /, ''); }
  if (text.startsWith('> ')) { block.type = 'quote'; block.text = text.slice(2); }
  return block;
}

function mutateLocalPage(mutator) {
  if (!state.localPage) return;
  mutator(state.localPage);
  state.localPage.updatedAt = new Date().toISOString();
  saveDraft(state.localPage);
}

function findBlock(blockId) {
  return activePage()?.blocks?.find((block) => block.id === blockId) || null;
}

function attachListeners() {
  app.querySelectorAll('[data-action="open-page"]').forEach((button) => button.addEventListener('click', () => selectPage(button.dataset.pageId)));
  app.querySelectorAll('[data-action="open-database"]').forEach((button) => button.addEventListener('click', () => selectDatabase(button.dataset.databaseId)));
  app.querySelectorAll('[data-action="workspace-select"]').forEach((select) => select.addEventListener('change', () => selectWorkspace(select.value)));
  app.querySelectorAll('[data-action="set-panel"]').forEach((button) => button.addEventListener('click', () => { state.activePanel = button.dataset.panel; render(); }));
  app.querySelectorAll('[data-action="open-search"]').forEach((button) => button.addEventListener('click', () => { state.searchOpen = true; render(); bindSearchInputs(); }));
  app.querySelectorAll('[data-action="close-search"]').forEach((button) => button.addEventListener('click', () => { state.searchOpen = false; render(); }));
  app.querySelectorAll('[data-form]').forEach((form) => form.addEventListener('submit', handleFormSubmit));
  app.querySelectorAll('[data-action="oauth"]').forEach((button) => button.addEventListener('click', () => oauth(button.dataset.provider)));
  app.querySelectorAll('[data-action="consume-magic"]').forEach((button) => button.addEventListener('click', consumeMagicToken));
  app.querySelectorAll('[data-action="logout"]').forEach((button) => button.addEventListener('click', logout));
  app.querySelectorAll('[data-action="new-page"]').forEach((button) => button.addEventListener('click', () => createPage()));
  app.querySelectorAll('[data-action="new-page-template"]').forEach((button) => button.addEventListener('click', () => createPage(true)));
  app.querySelectorAll('[data-action="create-database"]').forEach((button) => button.addEventListener('click', createDatabase));
  app.querySelectorAll('[data-action="create-workspace"]').forEach((button) => button.addEventListener('click', createWorkspace));
  app.querySelectorAll('[data-action="restore-page"]').forEach((button) => button.addEventListener('click', () => restorePage(button.dataset.pageId)));
  app.querySelectorAll('[data-action="page-title"]').forEach((input) => input.addEventListener('input', () => mutateLocalPage((page) => { page.title = input.value; scheduleSave(); })));
  app.querySelectorAll('[data-action="page-toggle"]').forEach((input) => input.addEventListener('change', () => mutateLocalPage((page) => { page[input.dataset.field] = input.checked; scheduleSave(); render(); })));
  app.querySelectorAll('[data-action="favorite-page"]').forEach((button) => button.addEventListener('click', favoritePage));
  app.querySelectorAll('[data-action="duplicate-page"]').forEach((button) => button.addEventListener('click', duplicatePage));
  app.querySelectorAll('[data-action="publish-page"]').forEach((button) => button.addEventListener('click', publishPage));
  app.querySelectorAll('[data-action="share-page"]').forEach((button) => button.addEventListener('click', sharePage));
  app.querySelectorAll('[data-action="trash-page"]').forEach((button) => button.addEventListener('click', trashPage));
  app.querySelectorAll('[data-action="save-page"]').forEach((button) => button.addEventListener('click', saveCurrentPage));
  app.querySelectorAll('[data-action="page-settings"]').forEach((button) => button.addEventListener('click', updatePageSettings));
  app.querySelectorAll('[data-action="add-block"]').forEach((button) => button.addEventListener('click', addBlock));
  app.querySelectorAll('[data-action="block-text"]').forEach((textarea) => textarea.addEventListener('input', () => mutateLocalPage((page) => {
    const block = page.blocks.find((item) => item.id === textarea.dataset.blockId);
    block.text = textarea.value;
    markdownShortcut(block);
    scheduleSave();
  })));
  app.querySelectorAll('[data-action="block-url"]').forEach((input) => input.addEventListener('input', () => mutateLocalPage((page) => {
    const block = page.blocks.find((item) => item.id === input.dataset.blockId);
    block.url = input.value;
    scheduleSave();
  })));
  app.querySelectorAll('[data-action="block-type"]').forEach((select) => select.addEventListener('change', () => mutateLocalPage((page) => {
    const block = page.blocks.find((item) => item.id === select.dataset.blockId);
    block.type = select.value;
    scheduleSave();
    render();
  })));
  app.querySelectorAll('[data-action="select-block"]').forEach((checkbox) => checkbox.addEventListener('change', () => {
    if (checkbox.checked) state.selectedBlocks.add(checkbox.dataset.blockId); else state.selectedBlocks.delete(checkbox.dataset.blockId);
    render();
  }));
  app.querySelectorAll('[data-action="toggle-check"]').forEach((checkbox) => checkbox.addEventListener('change', () => mutateLocalPage((page) => {
    const block = page.blocks.find((item) => item.id === checkbox.dataset.blockId);
    block.checked = checkbox.checked;
    scheduleSave();
  })));
  app.querySelectorAll('[data-action="duplicate-block"]').forEach((button) => button.addEventListener('click', () => duplicateBlock(button.dataset.blockId)));
  app.querySelectorAll('[data-action="delete-block"]').forEach((button) => button.addEventListener('click', () => deleteBlock(button.dataset.blockId)));
  app.querySelectorAll('[data-action="comment-block"]').forEach((button) => button.addEventListener('click', () => quickComment(button.dataset.blockId)));
  app.querySelectorAll('[data-action="bulk-delete"]').forEach((button) => button.addEventListener('click', bulkDelete));
  app.querySelectorAll('[data-action="bulk-duplicate"]').forEach((button) => button.addEventListener('click', bulkDuplicate));
  app.querySelectorAll('[data-action="download-ics"]').forEach((button) => button.addEventListener('click', downloadIcs));
  app.querySelectorAll('[data-action="advance-task"]').forEach((button) => button.addEventListener('click', () => advanceTask(button.dataset.taskId)));
  app.querySelectorAll('[data-action="link-task-page"]').forEach((button) => button.addEventListener('click', () => linkTaskPage(button.dataset.taskId)));
  app.querySelectorAll('[data-action="replace-file"]').forEach((button) => button.addEventListener('click', () => replaceFile(button.dataset.fileId)));
  app.querySelectorAll('[data-action="mark-read"]').forEach((button) => button.addEventListener('click', () => markRead(button.dataset.notificationId)));
  app.querySelectorAll('[data-action="resolve-comment"]').forEach((button) => button.addEventListener('click', () => resolveComment(button.dataset.commentId)));
  app.querySelectorAll('[data-action="reply-comment"]').forEach((button) => button.addEventListener('click', () => replyComment(button.dataset.commentId)));
  app.querySelectorAll('[data-action="restore-version"]').forEach((button) => button.addEventListener('click', () => restoreVersion(button.dataset.versionId)));
  app.querySelectorAll('[data-action="export-page"]').forEach((button) => button.addEventListener('click', () => exportPage(button.dataset.format)));
  app.querySelectorAll('[data-action="export-database"]').forEach((button) => button.addEventListener('click', () => exportDatabase(button.dataset.format)));
  app.querySelectorAll('[data-action="export-workspace"]').forEach((button) => button.addEventListener('click', exportWorkspace));
  app.querySelectorAll('[data-action="database-view-select"]').forEach((select) => select.addEventListener('change', () => { state.activeDatabaseView = select.value; render(); }));
  app.querySelectorAll('[data-action="edit-row"]').forEach((button) => button.addEventListener('click', () => editRow(button.dataset.rowId)));
  app.querySelectorAll('[data-action="advance-row"]').forEach((button) => button.addEventListener('click', () => advanceRow(button.dataset.rowId)));
  app.querySelectorAll('[data-action="verify-row"]').forEach((button) => button.addEventListener('click', () => verifyRow(button.dataset.rowId)));
  app.querySelectorAll('[data-action="setup-2fa"]').forEach((button) => button.addEventListener('click', setupTwoFactor));
  attachDragAndDrop();
}

function bindSearchInputs() {
  const input = document.getElementById('search-input');
  const type = document.getElementById('search-type');
  const workspace = document.getElementById('search-workspace');
  if (!input) return;
  const run = async () => {
    if (!currentUser()) return;
    state.searchQuery = input.value;
    state.searchType = type.value;
    state.searchWorkspaceId = workspace.value;
    const query = new URLSearchParams({ q: state.searchQuery, type: state.searchType, workspaceId: state.searchWorkspaceId });
    state.searchResults = await api(`/api/search?${query.toString()}`);
    render();
    bindSearchInputs();
    document.getElementById('search-input')?.focus();
    document.getElementById('search-input')?.setSelectionRange(input.value.length, input.value.length);
  };
  input.addEventListener('input', run);
  type.addEventListener('change', run);
  workspace.addEventListener('change', run);
  setTimeout(() => input.focus(), 0);
}

function attachDragAndDrop() {
  app.querySelectorAll('[data-action="drag-block"]').forEach((card) => {
    card.addEventListener('dragstart', () => {
      state.dragBlockId = card.dataset.blockId;
      card.classList.add('dragging');
    });
    card.addEventListener('dragend', () => {
      state.dragBlockId = null;
      card.classList.remove('dragging');
    });
    card.addEventListener('dragover', (event) => event.preventDefault());
    card.addEventListener('drop', () => {
      if (!state.dragBlockId || state.dragBlockId === card.dataset.blockId) return;
      mutateLocalPage((page) => {
        const from = page.blocks.findIndex((block) => block.id === state.dragBlockId);
        const to = page.blocks.findIndex((block) => block.id === card.dataset.blockId);
        const [moved] = page.blocks.splice(from, 1);
        page.blocks.splice(to, 0, moved);
        scheduleSave();
      });
      render();
    });
  });
}

async function handleFormSubmit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  try {
    if (form.dataset.form === 'register') {
      await api('/api/auth/register', { method: 'POST', body: JSON.stringify(Object.fromEntries(formData.entries())) });
      state.lastMagicToken = '';
      await refresh();
      return;
    }
    if (form.dataset.form === 'login') {
      await api('/api/auth/login', { method: 'POST', body: JSON.stringify(Object.fromEntries(formData.entries())) });
      await refresh();
      return;
    }
    if (form.dataset.form === 'magic-link') {
      const result = await api('/api/auth/magic-link/request', { method: 'POST', body: JSON.stringify(Object.fromEntries(formData.entries())) });
      state.lastMagicToken = result.token;
      state.notice = 'Magic link token generated for local development.';
      render();
      return;
    }
    if (form.dataset.form === 'sso-login') {
      await api('/api/auth/sso', { method: 'POST', body: JSON.stringify(Object.fromEntries(formData.entries())) });
      await refresh();
      return;
    }
    if (form.dataset.form === 'comment') {
      const page = activePage();
      await api(`/api/pages/${page.id}/comments`, {
        method: 'POST',
        body: JSON.stringify({
          text: formData.get('text'),
          mentions: String(formData.get('mentions') || '').split(',').map((item) => item.trim()).filter(Boolean),
        }),
      });
      await refresh();
      return;
    }
    if (form.dataset.form === 'task') {
      const deps = String(formData.get('dependencies') || '').split(',').map((item) => item.trim()).filter(Boolean);
      await api('/api/tasks', {
        method: 'POST',
        body: JSON.stringify({
          workspaceId: activeWorkspace().id,
          pageId: activePage()?.id || null,
          title: formData.get('title'),
          description: formData.get('description'),
          dueDate: formData.get('dueDate'),
          priority: formData.get('priority'),
          status: formData.get('status'),
          assigneeUserId: formData.get('assigneeUserId') || null,
          recurring: formData.get('recurring'),
          dependencies: deps,
          milestone: Boolean(formData.get('milestone')),
          linkedPageId: activePage()?.id || null,
        }),
      });
      await refresh();
      return;
    }
    if (form.dataset.form === 'upload') {
      const file = formData.get('file');
      if (!(file instanceof File)) throw new Error('Choose a file first');
      const base64 = await readFileAsBase64(file);
      await api('/api/files', {
        method: 'POST',
        body: JSON.stringify({ workspaceId: activeWorkspace().id, pageId: activePage()?.id || null, name: file.name, type: file.type, data: base64 }),
      });
      await refresh();
      return;
    }
    if (form.dataset.form === 'invite') {
      await api(`/api/workspaces/${activeWorkspace().id}/invite`, { method: 'POST', body: JSON.stringify(Object.fromEntries(formData.entries())) });
      await refresh();
      return;
    }
    if (form.dataset.form === 'workspace-settings') {
      const payload = {
        domainRestriction: formData.get('domainRestriction'),
        storageQuotaMb: Number(formData.get('storageQuotaMb') || 250),
        databasePermissions: formData.get('databasePermissions'),
        allowGuests: formData.get('allowGuests') === 'on',
        publicSharing: formData.get('publicSharing') === 'on',
        samlEnabled: formData.get('samlEnabled') === 'on',
        scimEnabled: formData.get('scimEnabled') === 'on',
      };
      await api(`/api/workspaces/${activeWorkspace().id}/settings`, { method: 'PUT', body: JSON.stringify(payload) });
      await refresh();
      state.activePanel = 'admin';
      return;
    }
    if (form.dataset.form === 'notification-preferences') {
      const payload = Object.fromEntries([...formData.keys()].map((key) => [key, true]));
      const names = ['email', 'mentions', 'comments', 'assignments', 'digest'];
      for (const name of names) payload[name] = formData.get(name) === 'on';
      await api('/api/preferences/notifications', { method: 'PUT', body: JSON.stringify(payload) });
      await refresh();
      return;
    }
    if (form.dataset.form === 'import') {
      await api('/api/import', {
        method: 'POST',
        body: JSON.stringify({
          workspaceId: activeWorkspace().id,
          parentId: activePage()?.id || null,
          format: formData.get('format'),
          title: formData.get('title'),
          content: formData.get('content'),
        }),
      });
      await refresh();
      return;
    }
    if (form.dataset.form === 'database-row') {
      const database = activeDatabase();
      const values = Object.fromEntries((database?.fields || []).map((field) => [field.id, formData.get(field.id)]));
      await api(`/api/databases/${database.id}/rows`, {
        method: 'POST',
        body: JSON.stringify({ values, pageId: activePage()?.id || null }),
      });
      await refresh();
      state.activePanel = 'databases';
      state.activeDatabaseId = database.id;
      return;
    }
    if (form.dataset.form === 'page-sharing') {
      const page = activePage();
      const payload = {
        customUrl: String(formData.get('customUrl') || ''),
        seo: {
          title: String(formData.get('seoTitle') || page.title),
          description: String(formData.get('seoDescription') || ''),
        },
      };
      await api(`/api/pages/${page.id}`, { method: 'PUT', body: JSON.stringify(payload) });
      await api(`/api/pages/${page.id}/publish`, {
        method: 'POST',
        body: JSON.stringify({
          published: formData.get('published') === 'on',
          slug: String(formData.get('slug') || page.slug),
          allowedDomain: String(formData.get('allowedDomain') || ''),
          expiresAt: formData.get('expiresAt') ? new Date(String(formData.get('expiresAt'))).toISOString() : '',
          seo: payload.seo,
        }),
      });
      await api(`/api/pages/${page.id}/share`, {
        method: 'POST',
        body: JSON.stringify({
          enabled: formData.get('shared') === 'on',
          allowedDomain: String(formData.get('allowedDomain') || ''),
          expiresAt: formData.get('expiresAt') ? new Date(String(formData.get('expiresAt'))).toISOString() : '',
        }),
      });
      await refresh();
      state.activePanel = 'admin';
      return;
    }
    if (form.dataset.form === 'page-permission') {
      const page = activePage();
      const permissions = upsertPermission(page.permissions || [], String(formData.get('userId') || ''), String(formData.get('access') || 'viewer'));
      await api(`/api/pages/${page.id}`, { method: 'PUT', body: JSON.stringify({ permissions }) });
      await refresh();
      state.activePanel = 'admin';
      return;
    }
    if (form.dataset.form === 'database-permission') {
      const database = activeDatabase() || databasesForWorkspace(activeWorkspace().id)[0];
      const permissions = upsertPermission(database.permissions || [], String(formData.get('userId') || ''), String(formData.get('access') || 'viewer'));
      await api(`/api/databases/${database.id}`, { method: 'PUT', body: JSON.stringify({ permissions }) });
      await refresh();
      state.activePanel = 'admin';
      state.activeDatabaseId = database.id;
      return;
    }
    if (form.dataset.form === 'scim-provision') {
      await api(`/api/workspaces/${activeWorkspace().id}/scim/users`, { method: 'POST', body: JSON.stringify(Object.fromEntries(formData.entries())) });
      await refresh();
      state.activePanel = 'admin';
      return;
    }
  } catch (error) {
    state.notice = error.message;
    render();
  }
}

async function oauth(provider) {
  try {
    await api('/api/auth/oauth', { method: 'POST', body: JSON.stringify({ provider }) });
    await refresh();
  } catch (error) {
    state.notice = error.message;
    render();
  }
}

async function consumeMagicToken() {
  try {
    await api('/api/auth/magic-link/consume', { method: 'POST', body: JSON.stringify({ token: state.lastMagicToken }) });
    await refresh();
  } catch (error) {
    state.notice = error.message;
    render();
  }
}

async function logout() {
  await api('/api/auth/logout', { method: 'POST', body: '{}' });
  state.localPage = null;
  await refresh();
}

async function createWorkspace() {
  const name = prompt('Workspace name', 'New Workspace');
  if (!name) return;
  await api('/api/workspaces', { method: 'POST', body: JSON.stringify({ name, kind: 'team' }) });
  await refresh();
}

async function createDatabase() {
  if (!currentUser()) return;
  const title = prompt('Database title', 'Project Database');
  if (!title) return;
  const description = prompt('Description', 'Track work with multiple views') || '';
  const database = await api('/api/databases', {
    method: 'POST',
    body: JSON.stringify({
      workspaceId: activeWorkspace().id,
      pageId: activePage()?.id || null,
      title,
      description,
      icon: '🗂️',
      fields: [
        { id: 'fld_name', name: 'Name', type: 'title' },
        { id: 'fld_status', name: 'Status', type: 'status', options: ['Backlog', 'In Progress', 'Done'] },
        { id: 'fld_owner', name: 'Owner', type: 'person' },
        { id: 'fld_due', name: 'Due', type: 'date' },
      ],
      views: [
        { id: 'view_table', name: 'Table', type: 'table' },
        { id: 'view_board', name: 'Board', type: 'board', groupBy: 'fld_status' },
        { id: 'view_calendar', name: 'Calendar', type: 'calendar', dateField: 'fld_due' },
        { id: 'view_timeline', name: 'Timeline', type: 'timeline', dateField: 'fld_due' },
        { id: 'view_gallery', name: 'Gallery', type: 'gallery' },
      ],
    }),
  });
  await refresh();
  selectDatabase(database.id);
}

async function createPage(fromTemplate = false) {
  if (!currentUser()) return;
  const title = prompt('Page title', fromTemplate ? 'New template page' : 'Untitled');
  if (!title) return;
  let templateId = null;
  if (fromTemplate) {
    const options = (state.data.templates || []).map((tpl) => `${tpl.id}: ${tpl.name}`).join('\n');
    templateId = prompt(`Choose template id:\n${options}`, state.data.templates?.[0]?.id || '') || null;
  }
  const page = await api('/api/pages', {
    method: 'POST',
    body: JSON.stringify({ workspaceId: activeWorkspace().id, parentId: activePage()?.id || null, title, templateId }),
  });
  await refresh();
  selectPage(page.id);
}

async function restorePage(pageId) {
  await api(`/api/pages/${pageId}/restore`, { method: 'POST', body: '{}' });
  await refresh();
  selectPage(pageId);
}

async function favoritePage() {
  await api(`/api/pages/${activePage().id}/favorite`, { method: 'POST', body: '{}' });
  await refresh();
}

async function duplicatePage() {
  const copy = await api(`/api/pages/${activePage().id}/duplicate`, { method: 'POST', body: '{}' });
  await refresh();
  selectPage(copy.id);
}

async function publishPage() {
  const page = activePage();
  const slug = prompt('Public slug', page.slug) || page.slug;
  await api(`/api/pages/${page.id}/publish`, { method: 'POST', body: JSON.stringify({ published: !page.published, slug }) });
  await refresh();
}

async function sharePage() {
  const page = activePage();
  const allowedDomain = prompt('Domain restriction (optional, e.g. example.com)', page.share?.allowedDomain || '') ?? (page.share?.allowedDomain || '');
  await api(`/api/pages/${page.id}/share`, { method: 'POST', body: JSON.stringify({ enabled: !page.share?.enabled, allowedDomain }) });
  await refresh();
}

async function trashPage() {
  if (!confirm('Move this page to trash?')) return;
  await api(`/api/pages/${activePage().id}/trash`, { method: 'POST', body: '{}' });
  await refresh();
}

async function updatePageSettings() {
  const page = activePage();
  const customUrl = prompt('Custom page URL (e.g. /product-strategy)', page.customUrl || '') ?? (page.customUrl || '');
  const seoTitle = prompt('SEO title', page.seo?.title || page.title) ?? (page.seo?.title || page.title);
  const seoDescription = prompt('SEO description', page.seo?.description || '') ?? (page.seo?.description || '');
  const cover = prompt('Cover image URL', page.cover || '') ?? (page.cover || '');
  mutateLocalPage((draft) => {
    draft.customUrl = customUrl;
    draft.seo = { ...(draft.seo || {}), title: seoTitle, description: seoDescription };
    draft.cover = cover;
  });
  render();
  await saveCurrentPage();
}

function addBlock() {
  mutateLocalPage((page) => {
    page.blocks.push({ id: cryptoRandomId('blk'), type: 'paragraph', text: '', checked: false, url: '' });
    scheduleSave();
  });
  render();
}

function cryptoRandomId(prefix) {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function duplicateBlock(blockId) {
  mutateLocalPage((page) => {
    const index = page.blocks.findIndex((block) => block.id === blockId);
    const copy = structuredClone(page.blocks[index]);
    copy.id = cryptoRandomId('blk');
    page.blocks.splice(index + 1, 0, copy);
    scheduleSave();
  });
  render();
}

function deleteBlock(blockId) {
  mutateLocalPage((page) => {
    page.blocks = page.blocks.filter((block) => block.id !== blockId);
    scheduleSave();
  });
  render();
}

function upsertPermission(existingPermissions, userId, access) {
  const next = (existingPermissions || []).filter((rule) => rule.userId !== userId);
  if (userId) next.push({ userId, access });
  return next;
}

async function setupTwoFactor() {
  if (!currentUser() || currentUser().twoFactorEnabled) {
    state.notice = currentUser()?.twoFactorEnabled ? 'Two-factor authentication is already enabled.' : 'Sign in first.';
    render();
    return;
  }
  try {
    const setup = await api('/api/auth/2fa/setup', { method: 'POST', body: '{}' });
    await api('/api/auth/2fa/verify', { method: 'POST', body: JSON.stringify({ code: setup.currentCode }) });
    state.notice = `2FA enabled. Secret: ${setup.secret}. Recovery codes: ${(setup.recoveryCodes || []).join(', ')}`;
    await refresh();
    state.activePanel = 'admin';
  } catch (error) {
    state.notice = error.message;
    render();
  }
}

async function quickComment(blockId) {
  const text = prompt('Comment for this block');
  if (!text) return;
  await api(`/api/pages/${activePage().id}/comments`, { method: 'POST', body: JSON.stringify({ text, blockId }) });
  state.activePanel = 'comments';
  await refresh();
}

function bulkDelete() {
  if (!state.selectedBlocks.size) return;
  mutateLocalPage((page) => {
    page.blocks = page.blocks.filter((block) => !state.selectedBlocks.has(block.id));
    scheduleSave();
  });
  state.selectedBlocks = new Set();
  render();
}

function bulkDuplicate() {
  if (!state.selectedBlocks.size) return;
  mutateLocalPage((page) => {
    const additions = page.blocks.filter((block) => state.selectedBlocks.has(block.id)).map((block) => ({ ...structuredClone(block), id: cryptoRandomId('blk') }));
    page.blocks.push(...additions);
    scheduleSave();
  });
  render();
}

async function downloadIcs() {
  const response = await fetch(`/api/tasks.ics?workspaceId=${activeWorkspace().id}`);
  const text = await response.text();
  downloadBlob(new Blob([text], { type: 'text/calendar' }), `noteflow-${activeWorkspace().name}.ics`);
}

async function advanceTask(taskId) {
  const task = (state.data.tasks || []).find((item) => item.id === taskId);
  const statuses = ['todo', 'in-progress', 'blocked', 'done'];
  const nextStatus = statuses[(statuses.indexOf(task.status) + 1) % statuses.length];
  await api(`/api/tasks/${taskId}`, { method: 'PUT', body: JSON.stringify({ status: nextStatus, progress: nextStatus === 'done' ? 100 : Math.min((task.progress || 0) + 25, 95) }) });
  await refresh();
}

async function linkTaskPage(taskId) {
  await api(`/api/tasks/${taskId}`, { method: 'PUT', body: JSON.stringify({ linkedPageId: activePage()?.id || null, pageId: activePage()?.id || null }) });
  await refresh();
}

async function replaceFile(fileId) {
  const input = document.createElement('input');
  input.type = 'file';
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    const base64 = await readFileAsBase64(file);
    await api(`/api/files/${fileId}/replace`, { method: 'POST', body: JSON.stringify({ data: base64 }) });
    await refresh();
  };
  input.click();
}

async function markRead(notificationId) {
  await api(`/api/notifications/${notificationId}/read`, { method: 'POST', body: '{}' });
  await refresh();
}

async function resolveComment(commentId) {
  await api(`/api/comments/${commentId}/resolve`, { method: 'POST', body: '{}' });
  await refresh();
}

async function replyComment(commentId) {
  const text = prompt('Reply');
  if (!text) return;
  await api(`/api/pages/${activePage().id}/comments`, { method: 'POST', body: JSON.stringify({ text, parentCommentId: commentId }) });
  await refresh();
}

async function restoreVersion(versionId) {
  await api(`/api/pages/${activePage().id}/history/${versionId}/restore`, { method: 'POST', body: '{}' });
  clearDraft(activePage().id);
  await refresh();
}

async function exportPage(format) {
  const response = await fetch(`/api/export/page/${activePage().id}?format=${format}`);
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob();
  downloadBlob(blob, `${activePage().title.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.${format === 'markdown' ? 'md' : format}`);
}

async function exportWorkspace() {
  const response = await fetch(`/api/export/workspace/${activeWorkspace().id}`);
  const blob = await response.blob();
  downloadBlob(blob, `${activeWorkspace().name.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.json`);
}

async function exportDatabase(format) {
  const database = activeDatabase();
  if (!database) return;
  const response = await fetch(`/api/export/database/${database.id}?format=${format}`);
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob();
  downloadBlob(blob, `${database.title.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}.${format === 'markdown' ? 'md' : format}`);
}

async function editRow(rowId) {
  const database = activeDatabase();
  const row = rowsForDatabase(database.id).find((item) => item.id === rowId);
  if (!row) return;
  const values = { ...row.values };
  for (const field of database.fields || []) {
    const next = prompt(field.name, values[field.id] || '');
    if (next !== null) values[field.id] = next;
  }
  await api(`/api/databases/${database.id}/rows/${row.id}`, { method: 'PUT', body: JSON.stringify({ values }) });
  await refresh();
  state.activeDatabaseId = database.id;
  state.activePanel = 'databases';
}

async function advanceRow(rowId) {
  const database = activeDatabase();
  const row = rowsForDatabase(database.id).find((item) => item.id === rowId);
  if (!row) return;
  const statusField = databaseField(database, 'status');
  const options = statusField?.options || ['Backlog', 'In Progress', 'Done'];
  const current = row.values?.[statusField?.id] || options[0];
  const next = options[(options.indexOf(current) + 1) % options.length];
  await api(`/api/databases/${database.id}/rows/${row.id}`, { method: 'PUT', body: JSON.stringify({ values: { [statusField.id]: next } }) });
  await refresh();
  state.activeDatabaseId = database.id;
  state.activePanel = 'databases';
}

async function verifyRow(rowId) {
  const database = activeDatabase();
  const row = rowsForDatabase(database.id).find((item) => item.id === rowId);
  if (!row) return;
  await api(`/api/databases/${database.id}/rows/${row.id}`, { method: 'PUT', body: JSON.stringify({ verified: !row.verified }) });
  await refresh();
  state.activeDatabaseId = database.id;
  state.activePanel = 'databases';
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function connectEvents() {
  if (state.sse) state.sse.close();
  const workspace = activeWorkspace();
  const page = activePage();
  if (!currentUser() || !workspace) return;
  state.sse = new EventSource(`/api/events?workspaceId=${workspace.id}&pageId=${page?.id || ''}`);
  state.sse.addEventListener('presence.updated', (event) => {
    const payload = JSON.parse(event.data);
    state.presence = payload.presence || [];
    if (!state.dirty) render();
  });
  ['page.created','page.updated','page.restored','comment.created','comment.resolved','task.created','task.updated','database.created','database.updated','database.row.created','database.row.updated','file.uploaded','file.replaced'].forEach((name) => {
    state.sse.addEventListener(name, async () => {
      if (!state.dirty) await refresh(false);
    });
  });
  sendPresence();
}

async function sendPresence() {
  const page = activePage();
  const workspace = activeWorkspace();
  if (!currentUser() || !page || !workspace) return;
  try {
    state.presence = await api('/api/presence', { method: 'POST', body: JSON.stringify({ workspaceId: workspace.id, pageId: page.id, cursor: { x: 0, y: 0 } }) });
  } catch {}
}

window.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    state.searchOpen = true;
    render();
    bindSearchInputs();
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault();
    saveCurrentPage();
  }
  if (event.key === 'Escape' && state.searchOpen) {
    state.searchOpen = false;
    render();
  }
});

setInterval(() => {
  if (currentUser() && activePage()) sendPresence();
}, 12000);

refresh(true).catch((error) => {
  app.innerHTML = `<div class="panel hero-auth"><h1>NoteFlow failed to load</h1><pre>${escapeHtml(error.message)}</pre></div>`;
});
