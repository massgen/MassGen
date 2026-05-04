import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const DATA_DIR = path.join(__dirname, 'data');
const PUBLIC_DIR = path.join(__dirname, 'public');
const UPLOAD_DIR = path.join(__dirname, 'uploads');
const DB_FILE = path.join(DATA_DIR, 'noteflow-db.json');
const PORT = Number(process.env.PORT || 3000);
const SESSION_COOKIE = 'noteflow_session';
const SSE_CLIENTS = new Map();
const PRESENCE = new Map();

fs.mkdirSync(DATA_DIR, { recursive: true });
fs.mkdirSync(PUBLIC_DIR, { recursive: true });
fs.mkdirSync(UPLOAD_DIR, { recursive: true });

function now() {
  return new Date().toISOString();
}

function id(prefix = 'id') {
  return `${prefix}_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
}

function hashPassword(password, salt = crypto.randomBytes(16).toString('hex')) {
  const derived = crypto.pbkdf2Sync(password, salt, 100000, 64, 'sha512').toString('hex');
  return `${salt}:${derived}`;
}

function verifyPassword(password, stored) {
  const [salt] = String(stored || '').split(':');
  if (!salt) return false;
  return hashPassword(password, salt) === stored;
}

function parseCookies(req) {
  const header = req.headers.cookie || '';
  return Object.fromEntries(
    header
      .split(';')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((pair) => {
        const idx = pair.indexOf('=');
        return [pair.slice(0, idx), decodeURIComponent(pair.slice(idx + 1))];
      }),
  );
}

function setCookie(res, name, value, options = {}) {
  const parts = [`${name}=${encodeURIComponent(value)}`, 'Path=/', 'HttpOnly', 'SameSite=Lax'];
  if (options.maxAge !== undefined) parts.push(`Max-Age=${options.maxAge}`);
  res.setHeader('Set-Cookie', parts.join('; '));
}

function clearCookie(res, name) {
  setCookie(res, name, '', { maxAge: 0 });
}

function json(res, status, payload) {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

function html(res, status, payload) {
  res.writeHead(status, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(payload);
}

function text(res, status, payload, contentType = 'text/plain; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': contentType });
  res.end(payload);
}

function redirect(res, location) {
  res.writeHead(302, { Location: location });
  res.end();
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => {
      try {
        const raw = Buffer.concat(chunks).toString('utf8');
        resolve(raw ? JSON.parse(raw) : {});
      } catch (error) {
        reject(error);
      }
    });
    req.on('error', reject);
  });
}

function safeReadJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return fallback;
  }
}

function starterTemplates() {
  return [
    {
      id: 'tpl_project_brief',
      name: 'Project Brief',
      icon: '🚀',
      description: 'Goal, scope, milestones, and linked tasks',
      blocks: [
        { id: id('blk'), type: 'heading1', text: 'Project Brief' },
        { id: id('blk'), type: 'callout', text: 'Summarize the mission, owner, and due date.' },
        { id: id('blk'), type: 'heading2', text: 'Goals' },
        { id: id('blk'), type: 'bullet', text: 'Primary outcome' },
        { id: id('blk'), type: 'bullet', text: 'Success metric' },
        { id: id('blk'), type: 'heading2', text: 'Milestones' },
        { id: id('blk'), type: 'todo', text: 'Define scope', checked: false },
      ],
    },
    {
      id: 'tpl_meeting_notes',
      name: 'Meeting Notes',
      icon: '📝',
      description: 'Agenda, notes, decisions, and follow-ups',
      blocks: [
        { id: id('blk'), type: 'heading1', text: 'Meeting Notes' },
        { id: id('blk'), type: 'heading2', text: 'Agenda' },
        { id: id('blk'), type: 'bullet', text: 'Topic 1' },
        { id: id('blk'), type: 'heading2', text: 'Decisions' },
        { id: id('blk'), type: 'quote', text: 'Record key decisions here.' },
      ],
    },
    {
      id: 'tpl_task_hub',
      name: 'Task Hub',
      icon: '✅',
      description: 'Work tracker with status, priority, and owners',
      blocks: [
        { id: id('blk'), type: 'heading1', text: 'Task Hub' },
        { id: id('blk'), type: 'paragraph', text: 'Use the Tasks panel to manage project execution.' },
        { id: id('blk'), type: 'bookmark', text: 'Link related specs or docs here.', url: 'https://example.com' },
      ],
    },
  ];
}

function defaultData() {
  const templates = starterTemplates();
  const demoWorkspaceId = id('ws');
  const demoPageId = id('pg');
  const demoTaskId = id('tsk');
  const demoFileId = id('fil');
  const demoDatabaseId = id('db');
  const demoRowId = id('row');
  return {
    users: [],
    sessions: [],
    workspaces: [
      {
        id: demoWorkspaceId,
        name: 'NoteFlow Demo Workspace',
        kind: 'team',
        ownerId: 'system',
        createdAt: now(),
        settings: {
          storageQuotaMb: 100,
          domainRestriction: '',
          allowGuests: true,
          publicSharing: true,
          databasePermissions: 'workspace-role',
          samlEnabled: false,
          scimEnabled: false,
        },
        members: [],
      },
    ],
    pages: [
      {
        id: demoPageId,
        workspaceId: demoWorkspaceId,
        parentId: null,
        title: 'Welcome to NoteFlow',
        icon: '🌊',
        cover: 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1200&q=80',
        slug: 'welcome-to-noteflow',
        customUrl: '/welcome-to-noteflow',
        kind: 'page',
        locked: false,
        fullWidth: true,
        smallText: false,
        verified: true,
        deletedAt: null,
        favoriteBy: [],
        recentBy: [],
        published: true,
        seo: {
          title: 'Welcome to NoteFlow',
          description: 'Explore the NoteFlow collaborative workspace starter experience.',
        },
        share: {
          enabled: true,
          token: id('shr'),
          expiresAt: '',
          allowedDomain: '',
        },
        permissions: [],
        blocks: [
          { id: id('blk'), type: 'heading1', text: 'Welcome to NoteFlow' },
          {
            id: id('blk'),
            type: 'callout',
            text: 'This demo shows nested pages, templates, comments, backlinks, tasks, search, notifications, publishing, sharing, and export.',
          },
          { id: id('blk'), type: 'heading2', text: 'Try these features' },
          { id: id('blk'), type: 'bullet', text: 'Create a page with the slash menu' },
          { id: id('blk'), type: 'bullet', text: 'Open the search palette with Cmd/Ctrl + K' },
          { id: id('blk'), type: 'bullet', text: 'Upload files and attach them to pages' },
          { id: id('blk'), type: 'heading2', text: 'Backlinks demo' },
          { id: id('blk'), type: 'paragraph', text: 'Mention [[Welcome to NoteFlow]] from another page to create backlinks.' },
        ],
        history: [],
        commentsEnabled: true,
        commentsSummary: { total: 0, unresolved: 0 },
        templateId: null,
        createdAt: now(),
        updatedAt: now(),
        createdBy: 'system',
      },
    ],
    comments: [],
    tasks: [
      {
        id: demoTaskId,
        workspaceId: demoWorkspaceId,
        pageId: demoPageId,
        title: 'Explore NoteFlow demo workspace',
        description: 'Review page management, tasks, search, and sharing features.',
        assigneeUserId: null,
        dueDate: new Date(Date.now() + 86400000).toISOString().slice(0, 10),
        priority: 'high',
        status: 'in-progress',
        recurring: 'weekly',
        reminderAt: new Date(Date.now() + 3600000).toISOString(),
        dependencies: [],
        subItems: [{ id: id('sub'), text: 'Open the Welcome page', done: true }],
        milestone: false,
        progress: 40,
        linkedPageId: demoPageId,
        createdAt: now(),
        updatedAt: now(),
      },
    ],
    databases: [
      {
        id: demoDatabaseId,
        workspaceId: demoWorkspaceId,
        pageId: demoPageId,
        title: 'Roadmap Database',
        description: 'Track initiatives with multiple workspace views.',
        icon: '🗂️',
        fields: [
          { id: 'fld_name', name: 'Name', type: 'title' },
          { id: 'fld_status', name: 'Status', type: 'status', options: ['Backlog', 'In Progress', 'Done'] },
          { id: 'fld_owner', name: 'Owner', type: 'person' },
          { id: 'fld_due', name: 'Due', type: 'date' },
          { id: 'fld_priority', name: 'Priority', type: 'select', options: ['low', 'medium', 'high'] },
        ],
        views: [
          { id: 'view_table', name: 'Table', type: 'table' },
          { id: 'view_board', name: 'Board', type: 'board', groupBy: 'fld_status' },
          { id: 'view_calendar', name: 'Calendar', type: 'calendar', dateField: 'fld_due' },
          { id: 'view_timeline', name: 'Timeline', type: 'timeline', dateField: 'fld_due' },
          { id: 'view_gallery', name: 'Gallery', type: 'gallery' },
        ],
        permissions: [],
        createdAt: now(),
        updatedAt: now(),
        createdBy: 'system',
      },
    ],
    databaseRows: [
      {
        id: demoRowId,
        databaseId: demoDatabaseId,
        workspaceId: demoWorkspaceId,
        pageId: demoPageId,
        values: {
          fld_name: 'Launch public demo',
          fld_status: 'In Progress',
          fld_owner: 'system',
          fld_due: new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10),
          fld_priority: 'high',
        },
        verified: true,
        createdAt: now(),
        updatedAt: now(),
        createdBy: 'system',
      },
    ],
    files: [
      {
        id: demoFileId,
        workspaceId: demoWorkspaceId,
        pageId: demoPageId,
        name: 'noteflow-demo.txt',
        type: 'text/plain',
        size: 28,
        storagePath: '',
        preview: 'NoteFlow demo attachment file',
        versions: [],
        createdAt: now(),
        updatedAt: now(),
        uploadedBy: 'system',
      },
    ],
    notifications: [],
    invitations: [],
    activity: [],
    templates,
    recentSearches: [],
    emailOutbox: [],
  };
}

function loadDb() {
  if (!fs.existsSync(DB_FILE)) {
    fs.writeFileSync(DB_FILE, JSON.stringify(defaultData(), null, 2));
  }
  const data = safeReadJson(DB_FILE, defaultData());
  data.users ||= [];
  data.sessions ||= [];
  data.workspaces ||= [];
  data.pages ||= [];
  data.comments ||= [];
  data.tasks ||= [];
  data.databases ||= [];
  data.databaseRows ||= [];
  data.files ||= [];
  data.notifications ||= [];
  data.invitations ||= [];
  data.activity ||= [];
  data.templates ||= starterTemplates();
  data.recentSearches ||= [];
  data.emailOutbox ||= [];
  data.magicLinks ||= [];
  return data;
}

function saveDb(data) {
  fs.writeFileSync(DB_FILE, JSON.stringify(data, null, 2));
}

function getSession(req, data) {
  const cookies = parseCookies(req);
  const sessionId = cookies[SESSION_COOKIE];
  if (!sessionId) return null;
  const session = data.sessions.find((item) => item.id === sessionId);
  if (!session) return null;
  session.lastSeenAt = now();
  const user = data.users.find((item) => item.id === session.userId);
  if (!user) return null;
  return { session, user };
}

function publicUser(user) {
  if (!user) return null;
  const { passwordHash, twoFactorSecret, recoveryCodes, ...rest } = user;
  return rest;
}

function roleRank(role) {
  return { guest: 1, viewer: 1, commenter: 2, editor: 3, owner: 4 }[role] || 0;
}

function getWorkspace(data, workspaceId) {
  return data.workspaces.find((workspace) => workspace.id === workspaceId) || null;
}

function getMembership(workspace, userId) {
  return workspace?.members?.find((member) => member.userId === userId) || null;
}

function getWorkspaceRole(data, workspaceId, userId) {
  const workspace = getWorkspace(data, workspaceId);
  if (!workspace || !userId) return null;
  if (workspace.ownerId === userId) return 'owner';
  return getMembership(workspace, userId)?.role || null;
}

function canAccessWorkspace(data, workspaceId, userId) {
  const workspace = getWorkspace(data, workspaceId);
  if (!workspace) return false;
  if (workspace.ownerId === 'system') return true;
  return Boolean(getWorkspaceRole(data, workspaceId, userId));
}

function canAccessPage(data, page, userId, mode = 'view') {
  if (!page) return false;
  if (page.deletedAt && mode !== 'restore') return false;
  const role = getWorkspaceRole(data, page.workspaceId, userId);
  if (!role && getWorkspace(data, page.workspaceId)?.ownerId !== 'system') return false;
  const pageRule = (page.permissions || []).find((item) => item.userId === userId);
  const access = pageRule?.access || role || 'viewer';
  if (mode === 'view') return roleRank(access) >= 1;
  if (mode === 'comment') return roleRank(access) >= 2;
  if (mode === 'edit') {
    if (page.locked && access !== 'owner') return false;
    return roleRank(access) >= 3;
  }
  if (mode === 'restore') return roleRank(access) >= 3;
  return false;
}

function getDatabase(data, databaseId) {
  return data.databases.find((database) => database.id === databaseId) || null;
}

function canAccessDatabase(data, database, userId, mode = 'view') {
  if (!database) return false;
  const role = getWorkspaceRole(data, database.workspaceId, userId);
  if (!role && getWorkspace(data, database.workspaceId)?.ownerId !== 'system') return false;
  const rule = (database.permissions || []).find((item) => item.userId === userId);
  const access = rule?.access || role || 'viewer';
  if (mode === 'view') return roleRank(access) >= 1;
  if (mode === 'edit') return roleRank(access) >= 3;
  return false;
}

function getAccessibleWorkspaceIds(data, userId) {
  return data.workspaces
    .filter((workspace) => workspace.ownerId === 'system' || getWorkspaceRole(data, workspace.id, userId))
    .map((workspace) => workspace.id);
}

function createActivity(data, payload) {
  data.activity.unshift({ id: id('act'), createdAt: now(), ...payload });
  data.activity = data.activity.slice(0, 200);
}

function ensureAuthMethod(user, method) {
  user.identity ||= {};
  user.identity.authMethods ||= [];
  if (!user.identity.authMethods.includes(method)) user.identity.authMethods.push(method);
  user.identity.lastAuditAt = now();
}

function upsertWorkspaceMember(workspace, userId, role = 'viewer') {
  workspace.members ||= [];
  const existing = workspace.members.find((member) => member.userId === userId);
  if (existing) {
    existing.role = role || existing.role;
    existing.acceptedAt ||= now();
    return existing;
  }
  const member = { userId, role: role || 'viewer', invitedAt: now(), acceptedAt: now() };
  workspace.members.push(member);
  return member;
}

function acceptPendingInvitations(data, user, actorUserId = user.id, source = 'workspace.invite.accepted') {
  const accepted = [];
  for (const invitation of data.invitations || []) {
    if (invitation.acceptedAt || invitation.email !== user.email) continue;
    const workspace = getWorkspace(data, invitation.workspaceId);
    if (!workspace) continue;
    upsertWorkspaceMember(workspace, user.id, invitation.role || 'viewer');
    invitation.acceptedAt = now();
    accepted.push(invitation);
    createActivity(data, {
      actorUserId,
      workspaceId: workspace.id,
      kind: source,
      message: `${user.email} joined ${workspace.name}`,
    });
  }
  return accepted;
}

function queueNotification(data, payload) {
  const notification = {
    id: id('ntf'),
    read: false,
    createdAt: now(),
    delivery: ['in-app'],
    ...payload,
  };
  data.notifications.unshift(notification);
  const user = data.users.find((item) => item.id === payload.userId);
  if (user?.notificationPreferences?.email !== false) {
    data.emailOutbox.unshift({
      id: id('mail'),
      to: user.email,
      subject: payload.title,
      body: payload.body,
      createdAt: now(),
      digestKey: payload.batchKey || '',
      type: payload.type,
    });
  }
  return notification;
}

function bootstrapWorkspaceForUser(data, user) {
  const personalWorkspace = {
    id: id('ws'),
    name: `${user.name.split(' ')[0]}'s Workspace`,
    kind: 'personal',
    ownerId: user.id,
    createdAt: now(),
    settings: {
      storageQuotaMb: 250,
      domainRestriction: '',
      allowGuests: true,
      publicSharing: true,
      databasePermissions: 'workspace-role',
      samlEnabled: false,
      scimEnabled: false,
    },
    members: [{ userId: user.id, role: 'owner', invitedAt: now(), acceptedAt: now() }],
  };
  const teamWorkspace = {
    id: id('ws'),
    name: `${user.name.split(' ')[0]}'s Team Space`,
    kind: 'team',
    ownerId: user.id,
    createdAt: now(),
    settings: {
      storageQuotaMb: 500,
      domainRestriction: '',
      allowGuests: true,
      publicSharing: true,
      databasePermissions: 'workspace-role',
      samlEnabled: false,
      scimEnabled: false,
    },
    members: [{ userId: user.id, role: 'owner', invitedAt: now(), acceptedAt: now() }],
  };
  const rootPage = {
    id: id('pg'),
    workspaceId: personalWorkspace.id,
    parentId: null,
    title: 'Home',
    icon: '🏠',
    cover: '',
    slug: `home-${user.id.slice(-5)}`,
    customUrl: `/home-${user.id.slice(-5)}`,
    kind: 'page',
    locked: false,
    fullWidth: false,
    smallText: false,
    verified: true,
    deletedAt: null,
    favoriteBy: [user.id],
    recentBy: [{ userId: user.id, visitedAt: now() }],
    published: false,
    seo: { title: 'Home', description: 'Personal home page' },
    share: { enabled: false, token: id('shr'), expiresAt: '', allowedDomain: '' },
    permissions: [],
    blocks: [
      { id: id('blk'), type: 'heading1', text: `Welcome, ${user.name}` },
      { id: id('blk'), type: 'paragraph', text: 'Use / to insert blocks, create nested pages, and collaborate in real time.' },
      { id: id('blk'), type: 'todo', text: 'Create your first project page', checked: false },
    ],
    history: [],
    commentsEnabled: true,
    commentsSummary: { total: 0, unresolved: 0 },
    templateId: null,
    createdAt: now(),
    updatedAt: now(),
    createdBy: user.id,
  };
  const starterDatabase = {
    id: id('db'),
    workspaceId: personalWorkspace.id,
    pageId: rootPage.id,
    title: 'My Tasks Database',
    description: 'A starter database for milestones, tasks, and planning views.',
    icon: '🗃️',
    fields: [
      { id: 'fld_name', name: 'Name', type: 'title' },
      { id: 'fld_status', name: 'Status', type: 'status', options: ['Backlog', 'In Progress', 'Done'] },
      { id: 'fld_owner', name: 'Owner', type: 'person' },
      { id: 'fld_due', name: 'Due', type: 'date' },
      { id: 'fld_priority', name: 'Priority', type: 'select', options: ['low', 'medium', 'high'] },
    ],
    views: [
      { id: 'view_table', name: 'Table', type: 'table' },
      { id: 'view_board', name: 'Board', type: 'board', groupBy: 'fld_status' },
      { id: 'view_calendar', name: 'Calendar', type: 'calendar', dateField: 'fld_due' },
      { id: 'view_timeline', name: 'Timeline', type: 'timeline', dateField: 'fld_due' },
      { id: 'view_gallery', name: 'Gallery', type: 'gallery' },
    ],
    permissions: [],
    createdAt: now(),
    updatedAt: now(),
    createdBy: user.id,
  };
  const starterRow = {
    id: id('row'),
    databaseId: starterDatabase.id,
    workspaceId: personalWorkspace.id,
    pageId: rootPage.id,
    values: {
      fld_name: 'Ship first workspace doc',
      fld_status: 'Backlog',
      fld_owner: user.id,
      fld_due: new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10),
      fld_priority: 'medium',
    },
    verified: false,
    createdAt: now(),
    updatedAt: now(),
    createdBy: user.id,
  };
  data.workspaces.push(personalWorkspace, teamWorkspace);
  data.pages.push(rootPage);
  data.databases.push(starterDatabase);
  data.databaseRows.push(starterRow);
  queueNotification(data, {
    userId: user.id,
    type: 'welcome',
    title: 'Welcome to NoteFlow',
    body: 'Your workspaces are ready. Start with Home or create a page from a template.',
    category: 'workspace',
    batchKey: 'welcome',
  });
  createActivity(data, { actorUserId: user.id, kind: 'workspace.created', message: 'Created initial workspaces', workspaceId: personalWorkspace.id });
}

function ensureUserRecordDefaults(user) {
  user.avatarColor ||= '#4f46e5';
  user.title ||= 'Workspace builder';
  user.bio ||= '';
  user.notificationPreferences ||= {
    email: true,
    mentions: true,
    comments: true,
    assignments: true,
    shares: true,
    reminders: true,
    digest: true,
  };
  user.identity ||= {
    authMethods: ['password'],
    lastAuditAt: now(),
    deviceMetadata: [],
    samlExternalId: '',
    scimExternalId: '',
  };
  user.twoFactorEnabled ||= false;
}

function createSession(data, user, req) {
  const session = {
    id: id('ses'),
    userId: user.id,
    createdAt: now(),
    lastSeenAt: now(),
    userAgent: req.headers['user-agent'] || 'unknown',
    ipAddress: req.headers['x-forwarded-for'] || req.socket?.remoteAddress || 'unknown',
    label: `Session ${new Date().toLocaleString()}`,
  };
  data.sessions.push(session);
  user.identity ||= {};
  user.identity.deviceMetadata ||= [];
  user.identity.deviceMetadata = [
    {
      sessionId: session.id,
      userAgent: session.userAgent,
      ipAddress: session.ipAddress,
      lastSeenAt: session.lastSeenAt,
    },
    ...user.identity.deviceMetadata.filter((entry) => entry.sessionId !== session.id),
  ].slice(0, 12);
  user.identity.lastAuditAt = now();
  return session;
}

function recentByForUser(page, userId) {
  return (page.recentBy || []).find((item) => item.userId === userId) || null;
}

function updateRecentPage(page, userId) {
  page.recentBy ||= [];
  page.recentBy = page.recentBy.filter((item) => item.userId !== userId);
  page.recentBy.unshift({ userId, visitedAt: now() });
  page.recentBy = page.recentBy.slice(0, 20);
}

function normalizeBlocks(blocks) {
  return (Array.isArray(blocks) ? blocks : []).map((block, index) => ({
    id: block.id || id('blk'),
    type: block.type || 'paragraph',
    text: block.text || '',
    checked: Boolean(block.checked),
    url: block.url || '',
    data: block.data || null,
    syncKey: block.syncKey || '',
    color: block.color || '',
    background: block.background || '',
    level: block.level || 0,
    order: index,
  }));
}

function createHistorySnapshot(page, userId) {
  page.history ||= [];
  page.history.unshift({
    id: id('ver'),
    createdAt: now(),
    userId,
    title: page.title,
    blocks: structuredClone(page.blocks || []),
    meta: {
      icon: page.icon,
      cover: page.cover,
      slug: page.slug,
      fullWidth: page.fullWidth,
      smallText: page.smallText,
      verified: page.verified,
      published: page.published,
      seo: page.seo,
    },
  });
  page.history = page.history.slice(0, 25);
}

function syncSyncedBlocks(data) {
  const syncMap = new Map();
  for (const page of data.pages) {
    for (const block of page.blocks || []) {
      if (block.type === 'synced' && block.syncKey) {
        if (!syncMap.has(block.syncKey)) syncMap.set(block.syncKey, { text: block.text, url: block.url, data: block.data });
      }
    }
  }
  for (const page of data.pages) {
    for (const block of page.blocks || []) {
      if (block.type === 'synced' && block.syncKey && syncMap.has(block.syncKey)) {
        const source = syncMap.get(block.syncKey);
        block.text = source.text;
        block.url = source.url;
        block.data = source.data;
      }
    }
  }
}

function findBacklinks(data, targetPage) {
  const titleNeedle = `[[${targetPage.title}]]`.toLowerCase();
  return data.pages
    .filter((page) => page.id !== targetPage.id && !page.deletedAt)
    .filter((page) => (page.blocks || []).some((block) => `${block.text || ''} ${block.url || ''}`.toLowerCase().includes(titleNeedle)))
    .map((page) => ({ id: page.id, title: page.title, workspaceId: page.workspaceId }));
}

function computeCommentsSummary(data, pageId) {
  const pageComments = data.comments.filter((comment) => comment.pageId === pageId);
  return {
    total: pageComments.length,
    unresolved: pageComments.filter((comment) => !comment.resolved).length,
  };
}

function workspaceUsageBytes(data, workspaceId) {
  return data.files.filter((file) => file.workspaceId === workspaceId).reduce((sum, file) => sum + (file.size || 0), 0);
}

function signedFileToken(fileId) {
  return crypto.createHash('sha256').update(`${fileId}:${new Date().toISOString().slice(0, 13)}`).digest('hex');
}

function renderBlockHtml(block) {
  const esc = escapeHtml(block.text || '');
  const link = block.url ? escapeHtml(block.url) : '';
  switch (block.type) {
    case 'heading1': return `<h1>${esc}</h1>`;
    case 'heading2': return `<h2>${esc}</h2>`;
    case 'heading3': return `<h3>${esc}</h3>`;
    case 'bullet': return `<ul><li>${esc}</li></ul>`;
    case 'numbered': return `<ol><li>${esc}</li></ol>`;
    case 'todo': return `<label><input type="checkbox" ${block.checked ? 'checked' : ''} disabled> ${esc}</label>`;
    case 'quote': return `<blockquote>${esc}</blockquote>`;
    case 'callout': return `<div class="pub-callout">💡 ${esc}</div>`;
    case 'divider': return '<hr>';
    case 'code': return `<pre><code>${esc}</code></pre>`;
    case 'equation': return `<pre class="equation">${esc}</pre>`;
    case 'bookmark': return `<a class="bookmark" href="${link}" target="_blank" rel="noreferrer">${link || esc}</a>`;
    case 'image': return link ? `<img src="${link}" alt="${esc}" />` : `<p>${esc}</p>`;
    case 'video': return link ? `<video controls src="${link}"></video>` : `<p>${esc}</p>`;
    case 'audio': return link ? `<audio controls src="${link}"></audio>` : `<p>${esc}</p>`;
    case 'pdf': return link ? `<iframe src="${link}" title="PDF" style="width:100%;min-height:480px"></iframe>` : `<p>${esc}</p>`;
    case 'embed': return link ? `<iframe src="${link}" title="Embed" style="width:100%;min-height:420px"></iframe>` : `<p>${esc}</p>`;
    case 'table': return `<pre>${esc}</pre>`;
    case 'columns': return `<div class="columns">${esc}</div>`;
    case 'toggle': return `<details><summary>${esc || 'Toggle'}</summary><p>${esc}</p></details>`;
    default: return `<p>${esc}</p>`;
  }
}

function renderPublicPage(page, data) {
  const blocks = (page.blocks || []).map(renderBlockHtml).join('\n');
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(page.seo?.title || page.title)}</title>
  <meta name="description" content="${escapeHtml(page.seo?.description || '')}" />
  <style>
    body{font-family:Inter,ui-sans-serif,system-ui,sans-serif;margin:0;background:#fafaf9;color:#1f2937}
    .wrap{max-width:${page.fullWidth ? '1180px' : '860px'};margin:0 auto;padding:32px}
    .cover{width:100%;height:220px;object-fit:cover;border-radius:22px;background:#e5e7eb}
    .pub-callout{padding:16px;border-radius:16px;background:#eef2ff;border:1px solid #c7d2fe}
    blockquote{border-left:4px solid #cbd5e1;padding-left:16px;color:#475569}
    pre{background:#111827;color:#e5e7eb;padding:14px;border-radius:14px;overflow:auto}
    a.bookmark{display:inline-flex;padding:10px 14px;border:1px solid #d1d5db;border-radius:12px;text-decoration:none;color:#1d4ed8;background:white}
    img,video{max-width:100%;border-radius:16px}
    .meta{display:flex;gap:10px;align-items:center;color:#64748b;margin:14px 0 28px}
  </style>
</head>
<body>
  <div class="wrap">
    ${page.cover ? `<img class="cover" src="${escapeHtml(page.cover)}" alt="cover">` : ''}
    <div class="meta"><span>${escapeHtml(page.icon || '📄')}</span><span>Published with NoteFlow</span></div>
    ${blocks}
    <hr>
    <section>
      <h3>Backlinks</h3>
      <ul>${findBacklinks(data, page).map((item) => `<li>${escapeHtml(item.title)}</li>`).join('') || '<li>No backlinks yet</li>'}</ul>
    </section>
  </div>
</body>
</html>`;
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function markdownToBlocks(content) {
  const lines = String(content || '').replace(/\r/g, '').split('\n');
  return lines.filter((line, index, arr) => !(line === '' && arr[index - 1] === '')).map((line) => {
    if (line.startsWith('# ')) return { id: id('blk'), type: 'heading1', text: line.slice(2) };
    if (line.startsWith('## ')) return { id: id('blk'), type: 'heading2', text: line.slice(3) };
    if (line.startsWith('### ')) return { id: id('blk'), type: 'heading3', text: line.slice(4) };
    if (line.startsWith('- [ ] ')) return { id: id('blk'), type: 'todo', text: line.slice(6), checked: false };
    if (line.startsWith('- [x] ')) return { id: id('blk'), type: 'todo', text: line.slice(6), checked: true };
    if (line.startsWith('- ')) return { id: id('blk'), type: 'bullet', text: line.slice(2) };
    if (line.match(/^\d+\. /)) return { id: id('blk'), type: 'numbered', text: line.replace(/^\d+\. /, '') };
    if (line.startsWith('> ')) return { id: id('blk'), type: 'quote', text: line.slice(2) };
    if (line.startsWith('```')) return { id: id('blk'), type: 'code', text: '' };
    if (!line.trim()) return { id: id('blk'), type: 'divider', text: '' };
    return { id: id('blk'), type: 'paragraph', text: line };
  });
}

function htmlToBlocks(content) {
  const textOnly = String(content || '').replace(/<[^>]+>/g, '\n').split('\n').map((line) => line.trim()).filter(Boolean).join('\n');
  return markdownToBlocks(textOnly);
}

function csvToTasks(content, workspaceId, pageId) {
  const lines = String(content || '').trim().split(/\r?\n/).filter(Boolean);
  const rows = lines.slice(1);
  return rows.map((row) => {
    const [title, status = 'todo', priority = 'medium', dueDate = ''] = row.split(',').map((cell) => cell.trim());
    return {
      id: id('tsk'),
      workspaceId,
      pageId,
      title,
      description: '',
      assigneeUserId: null,
      dueDate,
      priority,
      status,
      recurring: '',
      reminderAt: '',
      dependencies: [],
      subItems: [],
      milestone: false,
      progress: 0,
      linkedPageId: pageId,
      createdAt: now(),
      updatedAt: now(),
    };
  });
}

function blocksToMarkdown(page) {
  return (page.blocks || []).map((block) => {
    switch (block.type) {
      case 'heading1': return `# ${block.text}`;
      case 'heading2': return `## ${block.text}`;
      case 'heading3': return `### ${block.text}`;
      case 'bullet': return `- ${block.text}`;
      case 'numbered': return `1. ${block.text}`;
      case 'todo': return `- [${block.checked ? 'x' : ' '}] ${block.text}`;
      case 'quote': return `> ${block.text}`;
      case 'code': return `\`\`\`\n${block.text}\n\`\`\``;
      case 'divider': return '---';
      default: return block.text || '';
    }
  }).join('\n\n');
}

function blocksToHtml(page) {
  return `<!doctype html><html><body>${(page.blocks || []).map(renderBlockHtml).join('')}</body></html>`;
}

function tasksToCsv(tasks) {
  return ['title,status,priority,dueDate,assigneeUserId,progress'].concat(
    tasks.map((task) => [task.title, task.status, task.priority, task.dueDate || '', task.assigneeUserId || '', task.progress || 0].map((value) => `"${String(value).replaceAll('"', '""')}"`).join(',')),
  ).join('\n');
}

function buildSimplePdf(textContent) {
  const text = String(textContent || '').replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');
  const lines = text.split('\n').slice(0, 40);
  let y = 760;
  const commands = ['BT', '/F1 12 Tf'];
  for (const line of lines) {
    commands.push(`72 ${y} Td (${line.slice(0, 90)}) Tj`);
    y -= 16;
  }
  commands.push('ET');
  const stream = commands.join('\n');
  const objects = [];
  const pushObj = (body) => objects.push(body);
  pushObj('<< /Type /Catalog /Pages 2 0 R >>');
  pushObj('<< /Type /Pages /Kids [3 0 R] /Count 1 >>');
  pushObj('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>');
  pushObj(`<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`);
  pushObj('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>');
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  objects.forEach((obj, index) => {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${index + 1} 0 obj\n${obj}\nendobj\n`;
  });
  const xrefOffset = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (let i = 1; i < offsets.length; i += 1) pdf += `${String(offsets[i]).padStart(10, '0')} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return Buffer.from(pdf, 'utf8');
}

function workspaceTree(data, workspaceId, userId) {
  const pages = data.pages.filter((page) => page.workspaceId === workspaceId && !page.deletedAt && canAccessPage(data, page, userId, 'view'));
  return pages.map((page) => ({
    ...page,
    backlinks: findBacklinks(data, page),
  }));
}

function databaseTitleField(database) {
  return (database?.fields || []).find((field) => field.type === 'title') || database?.fields?.[0] || null;
}

function databaseToCsv(database, rows) {
  const fields = database?.fields || [];
  const header = fields.map((field) => field.name);
  return [header.join(',')].concat(
    rows.map((row) => fields.map((field) => `"${String(row.values?.[field.id] ?? '').replaceAll('"', '""')}"`).join(',')),
  ).join('\n');
}

function databaseToMarkdown(database, rows) {
  const fields = database?.fields || [];
  const header = `| ${fields.map((field) => field.name).join(' | ')} |`;
  const divider = `| ${fields.map(() => '---').join(' | ')} |`;
  const body = rows.map((row) => `| ${fields.map((field) => String(row.values?.[field.id] ?? '')).join(' | ')} |`);
  return [`# ${database.title}`, '', header, divider, ...body].join('\n');
}

function search(data, userId, params) {
  const q = String(params.q || '').trim().toLowerCase();
  const type = params.type || '';
  const workspaceId = params.workspaceId || '';
  const dateFrom = params.dateFrom || '';
  const dateTo = params.dateTo || '';
  const matchesDate = (value) => {
    if (!value) return true;
    if (dateFrom && value < dateFrom) return false;
    if (dateTo && value > `${dateTo}T23:59:59.999Z`) return false;
    return true;
  };
  const pages = data.pages
    .filter((page) => !page.deletedAt && canAccessPage(data, page, userId, 'view'))
    .filter((page) => !workspaceId || page.workspaceId === workspaceId)
    .filter((page) => !type || type === 'page')
    .filter((page) => matchesDate(page.updatedAt))
    .map((page) => {
      const haystack = `${page.title} ${(page.blocks || []).map((block) => block.text).join(' ')}`.toLowerCase();
      const score = q ? (page.title.toLowerCase().includes(q) ? 10 : 0) + (haystack.includes(q) ? 5 : 0) : 1;
      return {
        id: page.id,
        type: 'page',
        workspaceId: page.workspaceId,
        title: page.title,
        snippet: haystack.includes(q) ? (page.blocks.find((block) => String(block.text || '').toLowerCase().includes(q))?.text || page.title) : page.title,
        score,
        updatedAt: page.updatedAt,
      };
    });
  const comments = data.comments
    .filter((comment) => {
      const page = data.pages.find((item) => item.id === comment.pageId);
      return page && canAccessPage(data, page, userId, 'view');
    })
    .filter((comment) => !type || type === 'comment')
    .filter((comment) => matchesDate(comment.createdAt))
    .map((comment) => ({
      id: comment.id,
      type: 'comment',
      workspaceId: data.pages.find((page) => page.id === comment.pageId)?.workspaceId,
      title: `Comment on ${data.pages.find((page) => page.id === comment.pageId)?.title || 'page'}`,
      snippet: comment.text,
      score: q && comment.text.toLowerCase().includes(q) ? 4 : 0,
      updatedAt: comment.createdAt,
    }));
  const tasks = data.tasks
    .filter((task) => canAccessWorkspace(data, task.workspaceId, userId))
    .filter((task) => !workspaceId || task.workspaceId === workspaceId)
    .filter((task) => !type || type === 'task')
    .filter((task) => matchesDate(task.updatedAt))
    .map((task) => ({
      id: task.id,
      type: 'task',
      workspaceId: task.workspaceId,
      title: task.title,
      snippet: task.description,
      score: q && `${task.title} ${task.description}`.toLowerCase().includes(q) ? 5 : 0,
      updatedAt: task.updatedAt,
    }));
  const databases = data.databases
    .filter((database) => canAccessDatabase(data, database, userId, 'view'))
    .filter((database) => !workspaceId || database.workspaceId === workspaceId)
    .filter((database) => !type || type === 'database')
    .filter((database) => matchesDate(database.updatedAt))
    .map((database) => ({
      id: database.id,
      type: 'database',
      workspaceId: database.workspaceId,
      title: database.title,
      snippet: database.description || (database.fields || []).map((field) => field.name).join(', '),
      score: q && `${database.title} ${database.description || ''}`.toLowerCase().includes(q) ? 6 : 0,
      updatedAt: database.updatedAt,
    }));
  const databaseRows = data.databaseRows
    .filter((row) => {
      const database = getDatabase(data, row.databaseId);
      return database && canAccessDatabase(data, database, userId, 'view');
    })
    .filter((row) => !workspaceId || row.workspaceId === workspaceId)
    .filter((row) => !type || type === 'database_row')
    .filter((row) => matchesDate(row.updatedAt))
    .map((row) => {
      const database = getDatabase(data, row.databaseId);
      const titleField = databaseTitleField(database);
      const rowTitle = String(row.values?.[titleField?.id] ?? `Row ${row.id.slice(-4)}`);
      const haystack = Object.values(row.values || {}).join(' ').toLowerCase();
      return {
        id: row.id,
        parentId: row.databaseId,
        type: 'database_row',
        workspaceId: row.workspaceId,
        title: rowTitle,
        snippet: `${database?.title || 'Database'} · ${haystack}`,
        score: q && `${rowTitle} ${haystack}`.toLowerCase().includes(q) ? 7 : 0,
        updatedAt: row.updatedAt,
      };
    });
  const files = data.files
    .filter((file) => canAccessWorkspace(data, file.workspaceId, userId))
    .filter((file) => !workspaceId || file.workspaceId === workspaceId)
    .filter((file) => !type || type === 'file')
    .map((file) => ({
      id: file.id,
      type: 'file',
      workspaceId: file.workspaceId,
      title: file.name,
      snippet: file.preview || file.type,
      score: q && `${file.name} ${file.preview || ''}`.toLowerCase().includes(q) ? 3 : 0,
      updatedAt: file.updatedAt,
    }));
  const results = [...pages, ...comments, ...tasks, ...databases, ...databaseRows, ...files]
    .filter((item) => !q || item.score > 0)
    .sort((a, b) => b.score - a.score || String(b.updatedAt).localeCompare(String(a.updatedAt)));
  data.recentSearches = [{ userId, query: params.q || '', createdAt: now() }]
    .concat((data.recentSearches || []).filter((entry) => !(entry.userId === userId && entry.query === (params.q || ''))))
    .slice(0, 25);
  return results;
}

function emitEvent(type, payload) {
  const event = `event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`;
  for (const client of SSE_CLIENTS.values()) {
    const matchesWorkspace = !payload.workspaceId || client.workspaceId === payload.workspaceId;
    const matchesPage = !payload.pageId || client.pageId === payload.pageId || !client.pageId;
    if (matchesWorkspace && matchesPage) client.res.write(event);
  }
}

function currentPresence(pageId) {
  const pagePresence = PRESENCE.get(pageId) || new Map();
  const expiry = Date.now() - 30000;
  for (const [userId, entry] of pagePresence.entries()) {
    if (new Date(entry.lastSeenAt).getTime() < expiry) pagePresence.delete(userId);
  }
  PRESENCE.set(pageId, pagePresence);
  return Array.from(pagePresence.values());
}

function buildBootstrap(data, user) {
  const accessibleWorkspaceIds = getAccessibleWorkspaceIds(data, user?.id);
  const workspaces = data.workspaces.filter((workspace) => accessibleWorkspaceIds.includes(workspace.id) || workspace.ownerId === 'system');
  const pages = data.pages
    .filter((page) => {
      if (!user) return page.published || getWorkspace(data, page.workspaceId)?.ownerId === 'system';
      if (page.deletedAt) return canAccessPage(data, page, user.id, 'restore');
      return canAccessPage(data, page, user.id, 'view');
    })
    .map((page) => ({
      ...page,
      backlinks: findBacklinks(data, page),
      commentsSummary: computeCommentsSummary(data, page.id),
    }));
  const directoryUserIds = new Set(
    workspaces
      .flatMap((workspace) => workspace.members || [])
      .map((member) => member.userId)
      .concat(user?.id ? [user.id] : []),
  );
  return {
    user: publicUser(user),
    workspaces,
    pages,
    databases: user ? data.databases.filter((database) => canAccessDatabase(data, database, user.id, 'view')) : data.databases.filter((database) => getWorkspace(data, database.workspaceId)?.ownerId === 'system'),
    databaseRows: user ? data.databaseRows.filter((row) => {
      const database = getDatabase(data, row.databaseId);
      return database && canAccessDatabase(data, database, user.id, 'view');
    }) : data.databaseRows.filter((row) => getWorkspace(data, row.workspaceId)?.ownerId === 'system'),
    comments: user ? data.comments.filter((comment) => {
      const page = data.pages.find((item) => item.id === comment.pageId);
      return page && canAccessPage(data, page, user.id, 'view');
    }) : [],
    tasks: user ? data.tasks.filter((task) => accessibleWorkspaceIds.includes(task.workspaceId)) : [],
    files: user ? data.files.filter((file) => accessibleWorkspaceIds.includes(file.workspaceId)).map((file) => ({ ...file, signedUrl: `/files/${file.id}?token=${signedFileToken(file.id)}` })) : [],
    notifications: user ? data.notifications.filter((notification) => notification.userId === user.id) : [],
    invitations: user ? data.invitations.filter((invitation) => {
      const workspace = getWorkspace(data, invitation.workspaceId);
      if (!workspace) return false;
      return workspace.ownerId === user.id || invitation.email === user.email || getWorkspaceRole(data, workspace.id, user.id) === 'owner';
    }) : [],
    activity: user ? data.activity.filter((entry) => !entry.workspaceId || accessibleWorkspaceIds.includes(entry.workspaceId)) : [],
    templates: data.templates,
    recentSearches: user ? (data.recentSearches || []).filter((entry) => entry.userId === user.id) : [],
    emailOutbox: user ? data.emailOutbox.filter((entry) => entry.to === user.email).slice(0, 20) : [],
    sessions: user ? data.sessions.filter((session) => session.userId === user.id) : [],
    directory: data.users.filter((entry) => directoryUserIds.has(entry.id)).map(publicUser),
  };
}

async function handleApi(req, res, pathname, data, sessionInfo) {
  const user = sessionInfo?.user || null;

  if (pathname === '/api/bootstrap' && req.method === 'GET') {
    saveDb(data);
    return json(res, 200, buildBootstrap(data, user));
  }

  if (pathname === '/api/auth/register' && req.method === 'POST') {
    const body = await readBody(req);
    if (!body.email || !body.password || !body.name) return json(res, 400, { error: 'name, email, and password are required' });
    if (data.users.some((item) => item.email.toLowerCase() === body.email.toLowerCase())) return json(res, 400, { error: 'Email already exists' });
    const newUser = {
      id: id('usr'),
      name: body.name,
      email: body.email.toLowerCase(),
      passwordHash: hashPassword(body.password),
      avatarColor: body.avatarColor || '#4f46e5',
      title: 'Workspace builder',
      bio: '',
      createdAt: now(),
      notificationPreferences: {},
      identity: { authMethods: ['password'], lastAuditAt: now(), deviceMetadata: [] },
      twoFactorEnabled: false,
      twoFactorSecret: '',
      recoveryCodes: [],
    };
    ensureUserRecordDefaults(newUser);
    ensureAuthMethod(newUser, 'password');
    data.users.push(newUser);
    bootstrapWorkspaceForUser(data, newUser);
    acceptPendingInvitations(data, newUser);
    const session = createSession(data, newUser, req);
    setCookie(res, SESSION_COOKIE, session.id);
    saveDb(data);
    return json(res, 201, { user: publicUser(newUser) });
  }

  if (pathname === '/api/auth/login' && req.method === 'POST') {
    const body = await readBody(req);
    const existing = data.users.find((item) => item.email === String(body.email || '').toLowerCase());
    if (!existing || !verifyPassword(body.password || '', existing.passwordHash)) return json(res, 401, { error: 'Invalid credentials' });
    if (existing.twoFactorEnabled) {
      const code = String(body.code || '');
      if (!verifyTotpCode(existing.twoFactorSecret, code)) return json(res, 401, { error: '2FA code required or invalid' });
    }
    ensureAuthMethod(existing, 'password');
    acceptPendingInvitations(data, existing);
    const session = createSession(data, existing, req);
    setCookie(res, SESSION_COOKIE, session.id);
    saveDb(data);
    return json(res, 200, { user: publicUser(existing) });
  }

  if (pathname === '/api/auth/sso' && req.method === 'POST') {
    const body = await readBody(req);
    const workspace = getWorkspace(data, body.workspaceId);
    if (!workspace) return json(res, 404, { error: 'Workspace not found' });
    if (!workspace.settings?.samlEnabled) return json(res, 400, { error: 'SAML/SSO is not enabled for this workspace' });
    const email = String(body.email || '').toLowerCase();
    if (!email) return json(res, 400, { error: 'email is required' });
    const emailDomain = email.split('@')[1] || '';
    if (workspace.settings.domainRestriction && emailDomain !== workspace.settings.domainRestriction) {
      return json(res, 403, { error: `SSO restricted to ${workspace.settings.domainRestriction}` });
    }
    let existing = data.users.find((item) => item.email === email);
    if (!existing) {
      existing = {
        id: id('usr'),
        name: body.name || email.split('@')[0],
        email,
        passwordHash: hashPassword(crypto.randomUUID()),
        avatarColor: '#0f766e',
        title: 'Enterprise member',
        bio: '',
        createdAt: now(),
        notificationPreferences: {},
        identity: { authMethods: ['saml'], lastAuditAt: now(), deviceMetadata: [], samlExternalId: '', scimExternalId: '' },
        twoFactorEnabled: false,
        twoFactorSecret: '',
        recoveryCodes: [],
      };
      ensureUserRecordDefaults(existing);
      data.users.push(existing);
      bootstrapWorkspaceForUser(data, existing);
    }
    ensureAuthMethod(existing, 'saml');
    existing.identity.samlExternalId = body.externalId || existing.identity.samlExternalId || `saml-${workspace.id}-${email}`;
    acceptPendingInvitations(data, existing, existing.id, 'workspace.sso-login');
    const session = createSession(data, existing, req);
    setCookie(res, SESSION_COOKIE, session.id);
    createActivity(data, {
      actorUserId: existing.id,
      workspaceId: workspace.id,
      kind: 'workspace.sso-login',
      message: `${existing.email} signed in with SSO to ${workspace.name}`,
    });
    saveDb(data);
    return json(res, 200, { user: publicUser(existing), workspaceId: workspace.id });
  }

  if (pathname === '/api/auth/oauth' && req.method === 'POST') {
    const body = await readBody(req);
    const provider = ['google', 'github'].includes(body.provider) ? body.provider : 'google';
    const email = `${provider}-${Date.now()}@demo.noteflow.local`;
    const demoUser = {
      id: id('usr'),
      name: `${provider[0].toUpperCase()}${provider.slice(1)} User`,
      email,
      passwordHash: hashPassword(crypto.randomUUID()),
      avatarColor: provider === 'google' ? '#ea4335' : '#111827',
      title: `${provider} linked account`,
      bio: `Signed in with ${provider}`,
      createdAt: now(),
      notificationPreferences: {},
      identity: { authMethods: [provider], lastAuditAt: now(), deviceMetadata: [] },
      twoFactorEnabled: false,
      twoFactorSecret: '',
      recoveryCodes: [],
    };
    ensureUserRecordDefaults(demoUser);
    ensureAuthMethod(demoUser, provider);
    data.users.push(demoUser);
    bootstrapWorkspaceForUser(data, demoUser);
    acceptPendingInvitations(data, demoUser);
    const session = createSession(data, demoUser, req);
    setCookie(res, SESSION_COOKIE, session.id);
    saveDb(data);
    return json(res, 200, { user: publicUser(demoUser) });
  }

  if (pathname === '/api/auth/magic-link/request' && req.method === 'POST') {
    const body = await readBody(req);
    const token = id('magic');
    data.magicLinks ||= [];
    data.magicLinks.push({ token, email: String(body.email || '').toLowerCase(), expiresAt: new Date(Date.now() + 15 * 60 * 1000).toISOString() });
    saveDb(data);
    return json(res, 200, { token, note: 'Local dev returns the magic token directly.' });
  }

  if (pathname === '/api/auth/magic-link/consume' && req.method === 'POST') {
    const body = await readBody(req);
    const record = (data.magicLinks || []).find((item) => item.token === body.token && item.expiresAt > now());
    if (!record) return json(res, 400, { error: 'Invalid or expired token' });
    let existing = data.users.find((item) => item.email === record.email);
    if (!existing) {
      existing = {
        id: id('usr'),
        name: record.email.split('@')[0],
        email: record.email,
        passwordHash: hashPassword(crypto.randomUUID()),
        avatarColor: '#16a34a',
        title: 'Magic link account',
        bio: '',
        createdAt: now(),
        notificationPreferences: {},
        identity: { authMethods: ['magic-link'], lastAuditAt: now(), deviceMetadata: [] },
        twoFactorEnabled: false,
        twoFactorSecret: '',
        recoveryCodes: [],
      };
      ensureUserRecordDefaults(existing);
      data.users.push(existing);
      bootstrapWorkspaceForUser(data, existing);
    }
    ensureAuthMethod(existing, 'magic-link');
    acceptPendingInvitations(data, existing);
    const session = createSession(data, existing, req);
    setCookie(res, SESSION_COOKIE, session.id);
    saveDb(data);
    return json(res, 200, { user: publicUser(existing) });
  }

  if (pathname === '/api/auth/logout' && req.method === 'POST') {
    if (sessionInfo?.session) data.sessions = data.sessions.filter((item) => item.id !== sessionInfo.session.id);
    clearCookie(res, SESSION_COOKIE);
    saveDb(data);
    return json(res, 200, { ok: true });
  }

  if (pathname === '/api/auth/sessions' && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    return json(res, 200, data.sessions.filter((session) => session.userId === user.id));
  }

  if (pathname === '/api/auth/2fa/setup' && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    user.twoFactorSecret = crypto.randomBytes(10).toString('hex');
    user.recoveryCodes = Array.from({ length: 5 }, () => crypto.randomBytes(3).toString('hex'));
    saveDb(data);
    return json(res, 200, {
      secret: user.twoFactorSecret,
      currentCode: generateTotpCode(user.twoFactorSecret),
      recoveryCodes: user.recoveryCodes,
      note: 'For local dev, the current TOTP code is returned directly.',
    });
  }

  if (pathname === '/api/auth/2fa/verify' && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    if (!verifyTotpCode(user.twoFactorSecret, body.code)) return json(res, 400, { error: 'Invalid code' });
    user.twoFactorEnabled = true;
    user.identity.lastAuditAt = now();
    saveDb(data);
    return json(res, 200, { ok: true });
  }

  if (pathname === '/api/profile' && req.method === 'PUT') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    user.name = body.name || user.name;
    user.title = body.title ?? user.title;
    user.bio = body.bio ?? user.bio;
    user.avatarColor = body.avatarColor || user.avatarColor;
    user.identity.lastAuditAt = now();
    saveDb(data);
    emitEvent('profile.updated', { workspaceId: null, actorUserId: user.id });
    return json(res, 200, { user: publicUser(user) });
  }

  if (pathname === '/api/workspaces' && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    const workspace = {
      id: id('ws'),
      name: body.name || 'Untitled workspace',
      kind: body.kind === 'team' ? 'team' : 'personal',
      ownerId: user.id,
      createdAt: now(),
      settings: {
        storageQuotaMb: Number(body.storageQuotaMb || 250),
        domainRestriction: body.domainRestriction || '',
        allowGuests: body.allowGuests !== false,
        publicSharing: body.publicSharing !== false,
        databasePermissions: body.databasePermissions || 'workspace-role',
        samlEnabled: Boolean(body.samlEnabled),
        scimEnabled: Boolean(body.scimEnabled),
      },
      members: [{ userId: user.id, role: 'owner', invitedAt: now(), acceptedAt: now() }],
    };
    data.workspaces.push(workspace);
    saveDb(data);
    createActivity(data, { actorUserId: user.id, workspaceId: workspace.id, kind: 'workspace.created', message: `Created workspace ${workspace.name}` });
    emitEvent('workspace.created', { workspaceId: workspace.id, actorUserId: user.id });
    return json(res, 201, workspace);
  }

  const workspaceSettingsMatch = pathname.match(/^\/api\/workspaces\/([^/]+)\/settings$/);
  if (workspaceSettingsMatch) {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const workspace = getWorkspace(data, workspaceSettingsMatch[1]);
    if (!workspace || getWorkspaceRole(data, workspace.id, user.id) !== 'owner') return json(res, 403, { error: 'Forbidden' });
    if (req.method === 'GET') return json(res, 200, workspace);
    if (req.method === 'PUT') {
      const body = await readBody(req);
      workspace.settings = {
        ...workspace.settings,
        storageQuotaMb: Number(body.storageQuotaMb ?? workspace.settings.storageQuotaMb ?? 250),
        domainRestriction: body.domainRestriction ?? workspace.settings.domainRestriction ?? '',
        allowGuests: body.allowGuests ?? workspace.settings.allowGuests ?? true,
        publicSharing: body.publicSharing ?? workspace.settings.publicSharing ?? true,
        databasePermissions: body.databasePermissions ?? workspace.settings.databasePermissions ?? 'workspace-role',
        samlEnabled: body.samlEnabled ?? workspace.settings.samlEnabled ?? false,
        scimEnabled: body.scimEnabled ?? workspace.settings.scimEnabled ?? false,
      };
      createActivity(data, {
        actorUserId: user.id,
        workspaceId: workspace.id,
        kind: 'workspace.settings.updated',
        message: `Updated security and sharing settings for ${workspace.name}`,
      });
      saveDb(data);
      emitEvent('workspace.settings.updated', { workspaceId: workspace.id, actorUserId: user.id });
      return json(res, 200, workspace);
    }
  }

  const workspaceInvitationsMatch = pathname.match(/^\/api\/workspaces\/([^/]+)\/invitations$/);
  if (workspaceInvitationsMatch && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const workspace = getWorkspace(data, workspaceInvitationsMatch[1]);
    if (!workspace || getWorkspaceRole(data, workspace.id, user.id) !== 'owner') return json(res, 403, { error: 'Forbidden' });
    return json(res, 200, data.invitations.filter((invitation) => invitation.workspaceId === workspace.id));
  }

  const workspaceActivityMatch = pathname.match(/^\/api\/workspaces\/([^/]+)\/activity$/);
  if (workspaceActivityMatch && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const workspace = getWorkspace(data, workspaceActivityMatch[1]);
    if (!workspace || !canAccessWorkspace(data, workspace.id, user.id)) return json(res, 403, { error: 'Forbidden' });
    return json(res, 200, data.activity.filter((entry) => entry.workspaceId === workspace.id));
  }

  const workspaceInviteMatch = pathname.match(/^\/api\/workspaces\/([^/]+)\/invite$/);
  if (workspaceInviteMatch && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const workspace = getWorkspace(data, workspaceInviteMatch[1]);
    if (!workspace || getWorkspaceRole(data, workspace.id, user.id) !== 'owner') return json(res, 403, { error: 'Forbidden' });
    const body = await readBody(req);
    const invitation = { id: id('inv'), workspaceId: workspace.id, email: String(body.email || '').toLowerCase(), role: body.role || 'viewer', invitedBy: user.id, createdAt: now(), acceptedAt: '' };
    data.invitations.push(invitation);
    const invitee = data.users.find((item) => item.email === invitation.email);
    if (invitee) {
      upsertWorkspaceMember(workspace, invitee.id, invitation.role);
      invitation.acceptedAt = now();
      queueNotification(data, { userId: invitee.id, type: 'workspace-invite', title: `Invited to ${workspace.name}`, body: `${user.name} added you as ${invitation.role}.`, category: 'workspace' });
    }
    createActivity(data, {
      actorUserId: user.id,
      workspaceId: workspace.id,
      kind: 'workspace.invited',
      message: `Invited ${invitation.email} to ${workspace.name} as ${invitation.role}`,
    });
    saveDb(data);
    return json(res, 200, invitation);
  }

  const workspaceMemberRoleMatch = pathname.match(/^\/api\/workspaces\/([^/]+)\/members\/([^/]+)$/);
  if (workspaceMemberRoleMatch && req.method === 'PUT') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const workspace = getWorkspace(data, workspaceMemberRoleMatch[1]);
    if (!workspace || getWorkspaceRole(data, workspace.id, user.id) !== 'owner') return json(res, 403, { error: 'Forbidden' });
    const body = await readBody(req);
    const member = getMembership(workspace, workspaceMemberRoleMatch[2]);
    if (!member) return json(res, 404, { error: 'Member not found' });
    member.role = body.role || member.role;
    saveDb(data);
    return json(res, 200, member);
  }

  const workspaceDomainMatch = pathname.match(/^\/api\/workspaces\/([^/]+)\/domain$/);
  if (workspaceDomainMatch && req.method === 'PUT') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const workspace = getWorkspace(data, workspaceDomainMatch[1]);
    if (!workspace || getWorkspaceRole(data, workspace.id, user.id) !== 'owner') return json(res, 403, { error: 'Forbidden' });
    const body = await readBody(req);
    workspace.settings.domainRestriction = body.domain || '';
    workspace.settings.samlEnabled = Boolean(body.samlEnabled);
    workspace.settings.scimEnabled = Boolean(body.scimEnabled);
    saveDb(data);
    return json(res, 200, workspace);
  }

  const workspaceScimUsersMatch = pathname.match(/^\/api\/workspaces\/([^/]+)\/scim\/users$/);
  if (workspaceScimUsersMatch && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const workspace = getWorkspace(data, workspaceScimUsersMatch[1]);
    if (!workspace || getWorkspaceRole(data, workspace.id, user.id) !== 'owner') return json(res, 403, { error: 'Forbidden' });
    if (!workspace.settings?.scimEnabled) return json(res, 400, { error: 'SCIM provisioning is not enabled for this workspace' });
    const body = await readBody(req);
    const email = String(body.email || '').toLowerCase();
    if (!email || !body.externalId) return json(res, 400, { error: 'email and externalId are required' });
    let provisioned = data.users.find((item) => item.identity?.scimExternalId === body.externalId || item.email === email);
    if (!provisioned) {
      provisioned = {
        id: id('usr'),
        name: body.name || email.split('@')[0],
        email,
        passwordHash: hashPassword(crypto.randomUUID()),
        avatarColor: body.avatarColor || '#7c3aed',
        title: body.title || 'Provisioned member',
        bio: '',
        createdAt: now(),
        notificationPreferences: {},
        identity: { authMethods: ['scim'], lastAuditAt: now(), deviceMetadata: [], samlExternalId: '', scimExternalId: '' },
        twoFactorEnabled: false,
        twoFactorSecret: '',
        recoveryCodes: [],
      };
      ensureUserRecordDefaults(provisioned);
      data.users.push(provisioned);
    }
    ensureAuthMethod(provisioned, 'scim');
    provisioned.name = body.name || provisioned.name;
    provisioned.title = body.title || provisioned.title;
    provisioned.identity.scimExternalId = body.externalId;
    upsertWorkspaceMember(workspace, provisioned.id, body.role || 'viewer');
    createActivity(data, {
      actorUserId: user.id,
      workspaceId: workspace.id,
      kind: 'workspace.scim-provisioned',
      message: `Provisioned ${provisioned.email} via SCIM`,
    });
    saveDb(data);
    emitEvent('workspace.scim-provisioned', { workspaceId: workspace.id, actorUserId: user.id, targetUserId: provisioned.id });
    return json(res, 201, { user: publicUser(provisioned), workspaceId: workspace.id });
  }

  if (pathname === '/api/databases' && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    return json(res, 200, data.databases.filter((database) => canAccessDatabase(data, database, user.id, 'view')));
  }

  if (pathname === '/api/databases' && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    if (!canAccessWorkspace(data, body.workspaceId, user.id)) return json(res, 403, { error: 'Forbidden' });
    const database = {
      id: id('db'),
      workspaceId: body.workspaceId,
      pageId: body.pageId || null,
      title: body.title || 'Untitled database',
      description: body.description || '',
      icon: body.icon || '🗂️',
      fields: Array.isArray(body.fields) && body.fields.length ? body.fields : [
        { id: 'fld_name', name: 'Name', type: 'title' },
        { id: 'fld_status', name: 'Status', type: 'status', options: ['Backlog', 'In Progress', 'Done'] },
        { id: 'fld_due', name: 'Due', type: 'date' },
      ],
      views: Array.isArray(body.views) && body.views.length ? body.views : [
        { id: 'view_table', name: 'Table', type: 'table' },
        { id: 'view_board', name: 'Board', type: 'board' },
        { id: 'view_calendar', name: 'Calendar', type: 'calendar' },
      ],
      permissions: Array.isArray(body.permissions) ? body.permissions : [],
      createdAt: now(),
      updatedAt: now(),
      createdBy: user.id,
    };
    data.databases.push(database);
    saveDb(data);
    createActivity(data, { actorUserId: user.id, workspaceId: database.workspaceId, kind: 'database.created', message: `Created database ${database.title}` });
    emitEvent('database.created', { workspaceId: database.workspaceId, databaseId: database.id, actorUserId: user.id });
    return json(res, 201, database);
  }

  const databaseMatch = pathname.match(/^\/api\/databases\/([^/]+)$/);
  if (databaseMatch && req.method === 'PUT') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const database = getDatabase(data, databaseMatch[1]);
    if (!database || !canAccessDatabase(data, database, user.id, 'edit')) return json(res, 403, { error: 'Forbidden' });
    const body = await readBody(req);
    database.title = body.title ?? database.title;
    database.description = body.description ?? database.description;
    database.icon = body.icon ?? database.icon;
    database.pageId = body.pageId !== undefined ? body.pageId : database.pageId;
    database.fields = Array.isArray(body.fields) && body.fields.length ? body.fields : database.fields;
    database.views = Array.isArray(body.views) && body.views.length ? body.views : database.views;
    database.permissions = Array.isArray(body.permissions) ? body.permissions : database.permissions;
    database.updatedAt = now();
    saveDb(data);
    emitEvent('database.updated', { workspaceId: database.workspaceId, databaseId: database.id, actorUserId: user.id });
    return json(res, 200, database);
  }

  const databaseRowsMatch = pathname.match(/^\/api\/databases\/([^/]+)\/rows$/);
  if (databaseRowsMatch && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const database = getDatabase(data, databaseRowsMatch[1]);
    if (!database || !canAccessDatabase(data, database, user.id, 'edit')) return json(res, 403, { error: 'Forbidden' });
    const body = await readBody(req);
    const row = {
      id: id('row'),
      databaseId: database.id,
      workspaceId: database.workspaceId,
      pageId: body.pageId || database.pageId || null,
      values: body.values || {},
      verified: Boolean(body.verified),
      createdAt: now(),
      updatedAt: now(),
      createdBy: user.id,
    };
    data.databaseRows.push(row);
    database.updatedAt = now();
    const personValue = Object.values(row.values || {}).find((value) => data.users.some((entry) => entry.id === value));
    if (personValue) queueNotification(data, { userId: personValue, type: 'database-assignment', title: `Assigned in ${database.title}`, body: String(row.values?.[databaseTitleField(database)?.id] || 'Database row'), category: 'database' });
    saveDb(data);
    emitEvent('database.row.created', { workspaceId: database.workspaceId, databaseId: database.id, rowId: row.id, actorUserId: user.id });
    return json(res, 201, row);
  }

  const databaseRowMatch = pathname.match(/^\/api\/databases\/([^/]+)\/rows\/([^/]+)$/);
  if (databaseRowMatch && req.method === 'PUT') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const database = getDatabase(data, databaseRowMatch[1]);
    if (!database || !canAccessDatabase(data, database, user.id, 'edit')) return json(res, 403, { error: 'Forbidden' });
    const row = data.databaseRows.find((item) => item.id === databaseRowMatch[2] && item.databaseId === database.id);
    if (!row) return json(res, 404, { error: 'Row not found' });
    const body = await readBody(req);
    row.values = body.values ? { ...row.values, ...body.values } : row.values;
    row.pageId = body.pageId !== undefined ? body.pageId : row.pageId;
    row.verified = body.verified ?? row.verified;
    row.updatedAt = now();
    database.updatedAt = now();
    saveDb(data);
    emitEvent('database.row.updated', { workspaceId: database.workspaceId, databaseId: database.id, rowId: row.id, actorUserId: user.id });
    return json(res, 200, row);
  }

  if (pathname === '/api/pages' && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    if (!canAccessWorkspace(data, body.workspaceId, user.id)) return json(res, 403, { error: 'Forbidden' });
    const template = data.templates.find((item) => item.id === body.templateId) || null;
    const page = {
      id: id('pg'),
      workspaceId: body.workspaceId,
      parentId: body.parentId || null,
      title: body.title || template?.name || 'Untitled',
      icon: body.icon || template?.icon || '📄',
      cover: body.cover || '',
      slug: body.slug || `${(body.title || template?.name || 'untitled').toLowerCase().replace(/[^a-z0-9]+/g, '-')}-${Math.random().toString(36).slice(2, 6)}`,
      customUrl: '',
      kind: body.kind || 'page',
      locked: false,
      fullWidth: false,
      smallText: false,
      verified: false,
      deletedAt: null,
      favoriteBy: [],
      recentBy: [],
      published: false,
      seo: { title: body.title || template?.name || 'Untitled', description: '' },
      share: { enabled: false, token: id('shr'), expiresAt: '', allowedDomain: '' },
      permissions: [],
      blocks: normalizeBlocks(body.blocks || template?.blocks || [{ id: id('blk'), type: 'paragraph', text: '' }]),
      history: [],
      commentsEnabled: true,
      commentsSummary: { total: 0, unresolved: 0 },
      templateId: template?.id || null,
      createdAt: now(),
      updatedAt: now(),
      createdBy: user.id,
    };
    data.pages.push(page);
    updateRecentPage(page, user.id);
    saveDb(data);
    createActivity(data, { actorUserId: user.id, workspaceId: page.workspaceId, pageId: page.id, kind: 'page.created', message: `Created page ${page.title}` });
    emitEvent('page.created', { workspaceId: page.workspaceId, pageId: page.id, actorUserId: user.id });
    return json(res, 201, page);
  }

  const pageMatch = pathname.match(/^\/api\/pages\/([^/]+)$/);
  if (pageMatch && req.method === 'PUT') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const page = data.pages.find((item) => item.id === pageMatch[1]);
    if (!page || !canAccessPage(data, page, user.id, 'edit')) return json(res, 403, { error: 'Forbidden' });
    const body = await readBody(req);
    createHistorySnapshot(page, user.id);
    page.title = body.title ?? page.title;
    page.icon = body.icon ?? page.icon;
    page.cover = body.cover ?? page.cover;
    page.parentId = body.parentId !== undefined ? body.parentId : page.parentId;
    page.slug = body.slug ?? page.slug;
    page.customUrl = body.customUrl ?? page.customUrl;
    page.locked = body.locked ?? page.locked;
    page.fullWidth = body.fullWidth ?? page.fullWidth;
    page.smallText = body.smallText ?? page.smallText;
    page.verified = body.verified ?? page.verified;
    page.kind = body.kind ?? page.kind;
    page.permissions = Array.isArray(body.permissions) ? body.permissions : page.permissions;
    page.seo = body.seo ? { ...page.seo, ...body.seo } : page.seo;
    if (body.blocks) page.blocks = normalizeBlocks(body.blocks);
    page.updatedAt = now();
    syncSyncedBlocks(data);
    saveDb(data);
    createActivity(data, { actorUserId: user.id, workspaceId: page.workspaceId, pageId: page.id, kind: 'page.updated', message: `Updated page ${page.title}` });
    emitEvent('page.updated', { workspaceId: page.workspaceId, pageId: page.id, actorUserId: user.id });
    return json(res, 200, page);
  }

  const pageDuplicateMatch = pathname.match(/^\/api\/pages\/([^/]+)\/duplicate$/);
  if (pageDuplicateMatch && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const page = data.pages.find((item) => item.id === pageDuplicateMatch[1]);
    if (!page || !canAccessPage(data, page, user.id, 'view')) return json(res, 403, { error: 'Forbidden' });
    const copy = structuredClone(page);
    copy.id = id('pg');
    copy.title = `${page.title} (Copy)`;
    copy.slug = `${page.slug}-copy-${Math.random().toString(36).slice(2, 5)}`;
    copy.createdAt = now();
    copy.updatedAt = now();
    copy.createdBy = user.id;
    copy.history = [];
    copy.deletedAt = null;
    data.pages.push(copy);
    saveDb(data);
    emitEvent('page.created', { workspaceId: copy.workspaceId, pageId: copy.id, actorUserId: user.id });
    return json(res, 201, copy);
  }

  const pageTrashMatch = pathname.match(/^\/api\/pages\/([^/]+)\/(trash|restore|favorite|recent|publish|share)$/);
  if (pageTrashMatch && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const page = data.pages.find((item) => item.id === pageTrashMatch[1]);
    const action = pageTrashMatch[2];
    const mode = action === 'recent' ? 'view' : action === 'restore' ? 'restore' : 'edit';
    if (!page || !canAccessPage(data, page, user.id, mode)) return json(res, 403, { error: 'Forbidden' });
    const body = await readBody(req).catch(() => ({}));
    const workspace = getWorkspace(data, page.workspaceId);
    if (action === 'trash') page.deletedAt = now();
    if (action === 'restore') page.deletedAt = null;
    if (action === 'favorite') {
      page.favoriteBy ||= [];
      page.favoriteBy = page.favoriteBy.includes(user.id) ? page.favoriteBy.filter((item) => item !== user.id) : page.favoriteBy.concat(user.id);
    }
    if (action === 'recent') updateRecentPage(page, user.id);
    if (action === 'publish') {
      const nextPublished = body.published ?? !page.published;
      if (nextPublished && workspace?.settings?.publicSharing === false) return json(res, 400, { error: 'Workspace public sharing is disabled' });
      page.published = body.published ?? !page.published;
      page.slug = body.slug || page.slug;
      page.seo = { ...page.seo, ...(body.seo || {}) };
      page.share.expiresAt = body.expiresAt || page.share.expiresAt;
      page.share.allowedDomain = body.allowedDomain ?? page.share.allowedDomain;
    }
    if (action === 'share') {
      const nextShared = body.enabled ?? !page.share.enabled;
      if (nextShared && workspace?.settings?.publicSharing === false) return json(res, 400, { error: 'Workspace public sharing is disabled' });
      if (nextShared && workspace?.settings?.allowGuests === false && !(body.allowedDomain || page.share.allowedDomain)) {
        return json(res, 400, { error: 'Guest sharing is disabled for this workspace. Add an allowed domain.' });
      }
      page.share.enabled = body.enabled ?? !page.share.enabled;
      page.share.expiresAt = body.expiresAt || page.share.expiresAt;
      page.share.allowedDomain = body.allowedDomain ?? page.share.allowedDomain;
      page.share.token ||= id('shr');
    }
    page.updatedAt = now();
    saveDb(data);
    emitEvent(`page.${action}`, { workspaceId: page.workspaceId, pageId: page.id, actorUserId: user.id });
    return json(res, 200, page);
  }

  const commentsMatch = pathname.match(/^\/api\/pages\/([^/]+)\/comments$/);
  if (commentsMatch) {
    const page = data.pages.find((item) => item.id === commentsMatch[1]);
    if (!page) return json(res, 404, { error: 'Page not found' });
    if (req.method === 'GET') {
      if (!user || !canAccessPage(data, page, user.id, 'view')) return json(res, 403, { error: 'Forbidden' });
      return json(res, 200, data.comments.filter((comment) => comment.pageId === page.id));
    }
    if (req.method === 'POST') {
      if (!user || !canAccessPage(data, page, user.id, 'comment')) return json(res, 403, { error: 'Forbidden' });
      const body = await readBody(req);
      const comment = {
        id: id('cmt'),
        pageId: page.id,
        parentCommentId: body.parentCommentId || null,
        blockId: body.blockId || null,
        authorUserId: user.id,
        text: body.text || '',
        mentions: Array.isArray(body.mentions) ? body.mentions : [],
        resolved: false,
        createdAt: now(),
      };
      data.comments.push(comment);
      page.commentsSummary = computeCommentsSummary(data, page.id);
      for (const mentionUserId of comment.mentions) {
        queueNotification(data, { userId: mentionUserId, type: 'mention', title: `${user.name} mentioned you`, body: comment.text, category: 'comment', batchKey: `mention:${page.id}` });
      }
      saveDb(data);
      emitEvent('comment.created', { workspaceId: page.workspaceId, pageId: page.id, commentId: comment.id, actorUserId: user.id });
      return json(res, 201, comment);
    }
  }

  const commentResolveMatch = pathname.match(/^\/api\/comments\/([^/]+)\/resolve$/);
  if (commentResolveMatch && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const comment = data.comments.find((item) => item.id === commentResolveMatch[1]);
    const page = data.pages.find((item) => item.id === comment?.pageId);
    if (!comment || !page || !canAccessPage(data, page, user.id, 'comment')) return json(res, 403, { error: 'Forbidden' });
    comment.resolved = !comment.resolved;
    page.commentsSummary = computeCommentsSummary(data, page.id);
    saveDb(data);
    emitEvent('comment.resolved', { workspaceId: page.workspaceId, pageId: page.id, commentId: comment.id, actorUserId: user.id });
    return json(res, 200, comment);
  }

  const pageHistoryMatch = pathname.match(/^\/api\/pages\/([^/]+)\/history(?:\/([^/]+)\/restore)?$/);
  if (pageHistoryMatch) {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const page = data.pages.find((item) => item.id === pageHistoryMatch[1]);
    if (!page || !canAccessPage(data, page, user.id, pageHistoryMatch[2] ? 'edit' : 'view')) return json(res, 403, { error: 'Forbidden' });
    if (req.method === 'GET') return json(res, 200, page.history || []);
    if (req.method === 'POST' && pageHistoryMatch[2]) {
      const version = (page.history || []).find((item) => item.id === pageHistoryMatch[2]);
      if (!version) return json(res, 404, { error: 'Version not found' });
      createHistorySnapshot(page, user.id);
      page.title = version.title;
      page.blocks = structuredClone(version.blocks);
      Object.assign(page, version.meta || {});
      page.updatedAt = now();
      saveDb(data);
      emitEvent('page.restored', { workspaceId: page.workspaceId, pageId: page.id, actorUserId: user.id });
      return json(res, 200, page);
    }
  }

  if (pathname === '/api/search' && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const url = new URL(req.url, `http://${req.headers.host}`);
    const results = search(data, user.id, Object.fromEntries(url.searchParams.entries()));
    saveDb(data);
    return json(res, 200, results);
  }

  if (pathname === '/api/tasks' && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    return json(res, 200, data.tasks.filter((task) => canAccessWorkspace(data, task.workspaceId, user.id)));
  }

  if (pathname === '/api/tasks' && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    if (!canAccessWorkspace(data, body.workspaceId, user.id)) return json(res, 403, { error: 'Forbidden' });
    const task = {
      id: id('tsk'),
      workspaceId: body.workspaceId,
      pageId: body.pageId || null,
      title: body.title || 'Untitled task',
      description: body.description || '',
      assigneeUserId: body.assigneeUserId || null,
      dueDate: body.dueDate || '',
      priority: body.priority || 'medium',
      status: body.status || 'todo',
      recurring: body.recurring || '',
      reminderAt: body.reminderAt || '',
      dependencies: Array.isArray(body.dependencies) ? body.dependencies : [],
      subItems: Array.isArray(body.subItems) ? body.subItems : [],
      milestone: Boolean(body.milestone),
      progress: Number(body.progress || 0),
      linkedPageId: body.linkedPageId || body.pageId || null,
      createdAt: now(),
      updatedAt: now(),
    };
    data.tasks.push(task);
    if (task.assigneeUserId) queueNotification(data, { userId: task.assigneeUserId, type: 'assignment', title: `Assigned: ${task.title}`, body: task.description, category: 'task', batchKey: `assignment:${task.assigneeUserId}` });
    saveDb(data);
    emitEvent('task.created', { workspaceId: task.workspaceId, pageId: task.pageId, actorUserId: user.id });
    return json(res, 201, task);
  }

  const taskMatch = pathname.match(/^\/api\/tasks\/([^/]+)$/);
  if (taskMatch && req.method === 'PUT') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const task = data.tasks.find((item) => item.id === taskMatch[1]);
    if (!task || !canAccessWorkspace(data, task.workspaceId, user.id)) return json(res, 403, { error: 'Forbidden' });
    const body = await readBody(req);
    Object.assign(task, {
      title: body.title ?? task.title,
      description: body.description ?? task.description,
      assigneeUserId: body.assigneeUserId ?? task.assigneeUserId,
      dueDate: body.dueDate ?? task.dueDate,
      priority: body.priority ?? task.priority,
      status: body.status ?? task.status,
      recurring: body.recurring ?? task.recurring,
      reminderAt: body.reminderAt ?? task.reminderAt,
      dependencies: Array.isArray(body.dependencies) ? body.dependencies : task.dependencies,
      subItems: Array.isArray(body.subItems) ? body.subItems : task.subItems,
      milestone: body.milestone ?? task.milestone,
      progress: body.progress ?? task.progress,
      linkedPageId: body.linkedPageId ?? task.linkedPageId,
      updatedAt: now(),
    });
    saveDb(data);
    emitEvent('task.updated', { workspaceId: task.workspaceId, pageId: task.pageId, actorUserId: user.id });
    return json(res, 200, task);
  }

  if (pathname === '/api/tasks.ics' && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const url = new URL(req.url, `http://${req.headers.host}`);
    const workspaceId = url.searchParams.get('workspaceId');
    const tasks = data.tasks.filter((task) => (!workspaceId || task.workspaceId === workspaceId) && canAccessWorkspace(data, task.workspaceId, user.id));
    const ics = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//NoteFlow//EN'];
    for (const task of tasks.filter((item) => item.dueDate)) {
      ics.push('BEGIN:VEVENT');
      ics.push(`UID:${task.id}@noteflow.local`);
      ics.push(`DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z')}`);
      ics.push(`DTSTART;VALUE=DATE:${task.dueDate.replaceAll('-', '')}`);
      ics.push(`SUMMARY:${task.title}`);
      ics.push(`DESCRIPTION:${(task.description || '').replace(/\n/g, ' ')}`);
      ics.push('END:VEVENT');
    }
    ics.push('END:VCALENDAR');
    return text(res, 200, ics.join('\r\n'), 'text/calendar; charset=utf-8');
  }

  if (pathname === '/api/files' && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    if (!canAccessWorkspace(data, body.workspaceId, user.id)) return json(res, 403, { error: 'Forbidden' });
    const workspace = getWorkspace(data, body.workspaceId);
    const buffer = Buffer.from(String(body.data || ''), 'base64');
    const usedBytes = workspaceUsageBytes(data, body.workspaceId);
    if (usedBytes + buffer.length > (workspace.settings.storageQuotaMb || 100) * 1024 * 1024) return json(res, 400, { error: 'Storage quota exceeded' });
    const file = {
      id: id('fil'),
      workspaceId: body.workspaceId,
      pageId: body.pageId || null,
      name: body.name || 'upload.bin',
      type: body.type || 'application/octet-stream',
      size: buffer.length,
      storagePath: '',
      preview: buffer.toString('utf8', 0, Math.min(buffer.length, 120)),
      versions: [],
      createdAt: now(),
      updatedAt: now(),
      uploadedBy: user.id,
    };
    const ext = path.extname(file.name) || '.bin';
    const filePath = path.join(UPLOAD_DIR, `${file.id}${ext}`);
    fs.writeFileSync(filePath, buffer);
    file.storagePath = filePath;
    data.files.push(file);
    saveDb(data);
    emitEvent('file.uploaded', { workspaceId: file.workspaceId, pageId: file.pageId, actorUserId: user.id });
    return json(res, 201, { ...file, signedUrl: `/files/${file.id}?token=${signedFileToken(file.id)}` });
  }

  const replaceFileMatch = pathname.match(/^\/api\/files\/([^/]+)\/replace$/);
  if (replaceFileMatch && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const file = data.files.find((item) => item.id === replaceFileMatch[1]);
    if (!file || !canAccessWorkspace(data, file.workspaceId, user.id)) return json(res, 403, { error: 'Forbidden' });
    const body = await readBody(req);
    const buffer = Buffer.from(String(body.data || ''), 'base64');
    file.versions.unshift({ replacedAt: now(), size: file.size, preview: file.preview });
    file.versions = file.versions.slice(0, 10);
    file.size = buffer.length;
    file.preview = buffer.toString('utf8', 0, Math.min(buffer.length, 120));
    file.updatedAt = now();
    fs.writeFileSync(file.storagePath, buffer);
    saveDb(data);
    emitEvent('file.replaced', { workspaceId: file.workspaceId, pageId: file.pageId, actorUserId: user.id });
    return json(res, 200, { ...file, signedUrl: `/files/${file.id}?token=${signedFileToken(file.id)}` });
  }

  const signedFileMatch = pathname.match(/^\/api\/files\/([^/]+)\/signed$/);
  if (signedFileMatch && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const file = data.files.find((item) => item.id === signedFileMatch[1]);
    if (!file || !canAccessWorkspace(data, file.workspaceId, user.id)) return json(res, 403, { error: 'Forbidden' });
    return json(res, 200, { url: `/files/${file.id}?token=${signedFileToken(file.id)}` });
  }

  if (pathname === '/api/import' && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    if (!canAccessWorkspace(data, body.workspaceId, user.id)) return json(res, 403, { error: 'Forbidden' });
    if (body.format === 'csv') {
      const tasks = csvToTasks(body.content, body.workspaceId, body.parentId || null);
      data.tasks.push(...tasks);
      saveDb(data);
      return json(res, 201, { imported: tasks.length, target: 'tasks' });
    }
    const blocks = body.format === 'html' ? htmlToBlocks(body.content) : markdownToBlocks(body.content);
    const page = {
      id: id('pg'),
      workspaceId: body.workspaceId,
      parentId: body.parentId || null,
      title: body.title || body.fileName || `Imported ${body.format.toUpperCase()}`,
      icon: '📥',
      cover: '',
      slug: `import-${Math.random().toString(36).slice(2, 7)}`,
      customUrl: '',
      kind: 'page',
      locked: false,
      fullWidth: false,
      smallText: false,
      verified: false,
      deletedAt: null,
      favoriteBy: [],
      recentBy: [],
      published: false,
      seo: { title: body.title || 'Imported page', description: '' },
      share: { enabled: false, token: id('shr'), expiresAt: '', allowedDomain: '' },
      permissions: [],
      blocks,
      history: [],
      commentsEnabled: true,
      commentsSummary: { total: 0, unresolved: 0 },
      templateId: null,
      createdAt: now(),
      updatedAt: now(),
      createdBy: user.id,
    };
    data.pages.push(page);
    saveDb(data);
    return json(res, 201, { imported: 1, target: 'page', page });
  }

  const exportPageMatch = pathname.match(/^\/api\/export\/page\/([^/]+)$/);
  if (exportPageMatch && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const url = new URL(req.url, `http://${req.headers.host}`);
    const format = url.searchParams.get('format') || 'markdown';
    const page = data.pages.find((item) => item.id === exportPageMatch[1]);
    if (!page || !canAccessPage(data, page, user.id, 'view')) return json(res, 403, { error: 'Forbidden' });
    if (format === 'markdown') return text(res, 200, blocksToMarkdown(page), 'text/markdown; charset=utf-8');
    if (format === 'html') return text(res, 200, blocksToHtml(page), 'text/html; charset=utf-8');
    if (format === 'json') return json(res, 200, page);
    if (format === 'pdf') {
      const pdf = buildSimplePdf(`${page.title}\n\n${blocksToMarkdown(page)}`);
      res.writeHead(200, { 'Content-Type': 'application/pdf', 'Content-Length': pdf.length });
      return res.end(pdf);
    }
    if (format === 'csv') {
      const tasks = data.tasks.filter((task) => task.pageId === page.id || task.linkedPageId === page.id);
      return text(res, 200, tasksToCsv(tasks), 'text/csv; charset=utf-8');
    }
    return json(res, 400, { error: 'Unsupported export format' });
  }

  const exportWorkspaceMatch = pathname.match(/^\/api\/export\/workspace\/([^/]+)$/);
  if (exportWorkspaceMatch && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    if (!canAccessWorkspace(data, exportWorkspaceMatch[1], user.id)) return json(res, 403, { error: 'Forbidden' });
    const payload = {
      workspace: getWorkspace(data, exportWorkspaceMatch[1]),
      pages: data.pages.filter((page) => page.workspaceId === exportWorkspaceMatch[1]),
      databases: data.databases.filter((database) => database.workspaceId === exportWorkspaceMatch[1]),
      databaseRows: data.databaseRows.filter((row) => row.workspaceId === exportWorkspaceMatch[1]),
      tasks: data.tasks.filter((task) => task.workspaceId === exportWorkspaceMatch[1]),
      files: data.files.filter((file) => file.workspaceId === exportWorkspaceMatch[1]),
      comments: data.comments.filter((comment) => data.pages.find((page) => page.id === comment.pageId)?.workspaceId === exportWorkspaceMatch[1]),
    };
    return json(res, 200, payload);
  }

  const exportDatabaseMatch = pathname.match(/^\/api\/export\/database\/([^/]+)$/);
  if (exportDatabaseMatch && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const database = getDatabase(data, exportDatabaseMatch[1]);
    if (!database || !canAccessDatabase(data, database, user.id, 'view')) return json(res, 403, { error: 'Forbidden' });
    const url = new URL(req.url, `http://${req.headers.host}`);
    const format = url.searchParams.get('format') || 'json';
    const rows = data.databaseRows.filter((row) => row.databaseId === database.id);
    if (format === 'json') return json(res, 200, { database, rows });
    if (format === 'csv') return text(res, 200, databaseToCsv(database, rows), 'text/csv; charset=utf-8');
    if (format === 'markdown') return text(res, 200, databaseToMarkdown(database, rows), 'text/markdown; charset=utf-8');
    return json(res, 400, { error: 'Unsupported export format' });
  }

  if (pathname === '/api/events' && req.method === 'GET') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const url = new URL(req.url, `http://${req.headers.host}`);
    const workspaceId = url.searchParams.get('workspaceId') || '';
    const pageId = url.searchParams.get('pageId') || '';
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    });
    const clientId = id('sse');
    SSE_CLIENTS.set(clientId, { res, userId: user.id, workspaceId, pageId });
    res.write(`event: hello\ndata: ${JSON.stringify({ userId: user.id, workspaceId, pageId, now: now() })}\n\n`);
    req.on('close', () => {
      SSE_CLIENTS.delete(clientId);
    });
    return;
  }

  if (pathname === '/api/presence' && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    const pageId = body.pageId;
    const page = data.pages.find((item) => item.id === pageId);
    if (!page || !canAccessPage(data, page, user.id, 'view')) return json(res, 403, { error: 'Forbidden' });
    const pagePresence = PRESENCE.get(pageId) || new Map();
    pagePresence.set(user.id, {
      userId: user.id,
      name: user.name,
      avatarColor: user.avatarColor,
      cursor: body.cursor || { x: 0, y: 0 },
      lastSeenAt: now(),
    });
    PRESENCE.set(pageId, pagePresence);
    const snapshot = currentPresence(pageId);
    emitEvent('presence.updated', { workspaceId: page.workspaceId, pageId, presence: snapshot });
    return json(res, 200, snapshot);
  }

  const notificationMatch = pathname.match(/^\/api\/notifications\/([^/]+)\/read$/);
  if (notificationMatch && req.method === 'POST') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const notification = data.notifications.find((item) => item.id === notificationMatch[1] && item.userId === user.id);
    if (!notification) return json(res, 404, { error: 'Notification not found' });
    notification.read = true;
    saveDb(data);
    return json(res, 200, notification);
  }

  if (pathname === '/api/preferences/notifications' && req.method === 'PUT') {
    if (!user) return json(res, 401, { error: 'Unauthorized' });
    const body = await readBody(req);
    user.notificationPreferences = { ...user.notificationPreferences, ...body };
    saveDb(data);
    return json(res, 200, user.notificationPreferences);
  }

  return json(res, 404, { error: 'Not found' });
}

function generateTotpCode(secret) {
  const step = Math.floor(Date.now() / 30000);
  const hmac = crypto.createHmac('sha1', secret).update(String(step)).digest('hex');
  return hmac.slice(-6).replace(/[^0-9]/g, '0').padEnd(6, '0').slice(0, 6);
}

function verifyTotpCode(secret, code) {
  if (!secret || !code) return false;
  const normalize = String(code).trim();
  const current = generateTotpCode(secret);
  const previous = (() => {
    const oldNow = Date.now;
    Date.now = () => oldNow() - 30000;
    const value = generateTotpCode(secret);
    Date.now = oldNow;
    return value;
  })();
  return normalize === current || normalize === previous;
}

function serveStatic(res, filePath) {
  if (!fs.existsSync(filePath)) return false;
  const ext = path.extname(filePath).toLowerCase();
  const type = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.txt': 'text/plain; charset=utf-8',
  }[ext] || 'application/octet-stream';
  const buffer = fs.readFileSync(filePath);
  res.writeHead(200, { 'Content-Type': type, 'Cache-Control': 'no-store' });
  res.end(buffer);
  return true;
}

const server = http.createServer(async (req, res) => {
  try {
    const data = loadDb();
    const sessionInfo = getSession(req, data);
    const url = new URL(req.url, `http://${req.headers.host}`);
    const pathname = decodeURIComponent(url.pathname);

    if (pathname.startsWith('/api/')) return await handleApi(req, res, pathname, data, sessionInfo);

    const fileDownloadMatch = pathname.match(/^\/files\/([^/]+)$/);
    if (fileDownloadMatch) {
      const file = data.files.find((item) => item.id === fileDownloadMatch[1]);
      if (!file) return json(res, 404, { error: 'File not found' });
      const token = url.searchParams.get('token');
      if (token !== signedFileToken(file.id)) return json(res, 403, { error: 'Invalid signed URL' });
      res.writeHead(200, {
        'Content-Type': file.type,
        'Content-Disposition': `inline; filename="${file.name.replaceAll('"', '')}"`,
        'Cache-Control': 'public, max-age=3600, immutable',
      });
      return fs.createReadStream(file.storagePath).pipe(res);
    }

    const publicPageMatch = pathname.match(/^\/(?:pub|p)\/([^/]+)$/);
    if (publicPageMatch) {
      const slug = publicPageMatch[1];
      const page = data.pages.find((item) => item.slug === slug || item.customUrl === `/${slug}`);
      if (!page || !page.published) return html(res, 404, '<h1>Published page not found</h1>');
      if (page.share.expiresAt && page.share.expiresAt < now()) return html(res, 403, '<h1>Share link expired</h1>');
      if (page.share.allowedDomain) {
        const viewer = sessionInfo?.user;
        if (!viewer || !viewer.email.endsWith(`@${page.share.allowedDomain}`)) return html(res, 403, `<h1>Access restricted to ${escapeHtml(page.share.allowedDomain)}</h1>`);
      }
      return html(res, 200, renderPublicPage(page, data));
    }

    if (pathname === '/' || pathname === '/index.html') {
      return serveStatic(res, path.join(PUBLIC_DIR, 'index.html'));
    }

    if (serveStatic(res, path.join(PUBLIC_DIR, pathname))) return;
    return redirect(res, '/');
  } catch (error) {
    console.error(error);
    return json(res, 500, { error: error.message, stack: error.stack });
  }
});

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  server.listen(PORT, () => {
    console.log(`NoteFlow running at http://localhost:${PORT}`);
  });
}

export {
  defaultData,
  markdownToBlocks,
  htmlToBlocks,
  csvToTasks,
  blocksToMarkdown,
  buildSimplePdf,
  search,
  normalizeBlocks,
  server,
};
