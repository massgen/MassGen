import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';

import {
  blocksToMarkdown,
  buildSimplePdf,
  csvToTasks,
  defaultData,
  htmlToBlocks,
  markdownToBlocks,
  search,
  server,
} from '../server.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DATA_FILE = path.join(ROOT, 'data', 'noteflow-db.json');
const UPLOAD_DIR = path.join(ROOT, 'uploads');
const PORT = 3107;
const BASE = `http://127.0.0.1:${PORT}`;

function cleanupRuntimeFiles() {
  if (fs.existsSync(DATA_FILE)) fs.rmSync(DATA_FILE, { force: true });
  if (fs.existsSync(UPLOAD_DIR)) {
    for (const file of fs.readdirSync(UPLOAD_DIR)) fs.rmSync(path.join(UPLOAD_DIR, file), { force: true });
  }
}

async function waitForServer() {
  for (let i = 0; i < 50; i += 1) {
    try {
      const response = await fetch(`${BASE}/api/bootstrap`);
      if (response.ok) return;
    } catch {}
    await delay(100);
  }
  throw new Error('Server did not start in time');
}

test('content helpers parse and export blocks', () => {
  const blocks = markdownToBlocks('# Title\n\n- [ ] Todo\n> Quote');
  assert.equal(blocks[0].type, 'heading1');
  assert.equal(blocks[1].type, 'divider');
  assert.equal(blocks[2].type, 'todo');
  const htmlBlocks = htmlToBlocks('<h1>Hello</h1><p>Body</p>');
  assert.equal(htmlBlocks[0].type, 'paragraph');
  const markdown = blocksToMarkdown({ blocks: [{ type: 'heading1', text: 'Hello' }, { type: 'todo', text: 'Ship', checked: true }] });
  assert.match(markdown, /# Hello/);
  assert.match(markdown, /- \[x\] Ship/);
  const pdf = buildSimplePdf('Hello PDF');
  assert.equal(pdf.subarray(0, 8).toString('utf8'), '%PDF-1.4');
  const tasks = csvToTasks('title,status,priority,dueDate\nLaunch,todo,high,2026-05-05', 'ws_1', 'pg_1');
  assert.equal(tasks[0].title, 'Launch');
});

test('search ranks accessible page results', () => {
  const data = defaultData();
  const user = { id: 'usr_test', email: 'a@example.com' };
  data.users.push({ ...user, name: 'A', passwordHash: 'x', notificationPreferences: {}, identity: {}, twoFactorEnabled: false });
  data.workspaces.push({ id: 'ws_test', name: 'Team', kind: 'team', ownerId: user.id, members: [{ userId: user.id, role: 'owner' }], settings: {} });
  data.pages.push({
    id: 'pg_test', workspaceId: 'ws_test', parentId: null, title: 'Launch Plan', icon: '🚀', cover: '', slug: 'launch-plan', customUrl: '', kind: 'page', locked: false, fullWidth: false, smallText: false, verified: false, deletedAt: null,
    favoriteBy: [], recentBy: [], published: false, seo: { title: 'Launch Plan', description: '' }, share: { enabled: false, token: 'shr', expiresAt: '', allowedDomain: '' }, permissions: [],
    blocks: [{ id: 'blk_1', type: 'paragraph', text: 'Prepare launch checklist' }], history: [], commentsEnabled: true, commentsSummary: { total: 0, unresolved: 0 }, templateId: null, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), createdBy: user.id,
  });
  const results = search(data, user.id, { q: 'launch' });
  assert.equal(results[0].title, 'Launch Plan');
});

test('HTTP flows cover register, page creation, comments, tasks, files, search, publish, and export', async (t) => {
  cleanupRuntimeFiles();
  await new Promise((resolve) => server.listen(PORT, '127.0.0.1', resolve));
  t.after(() => server.close());
  await waitForServer();

  let cookie = '';
  const request = async (pathname, options = {}) => {
    const response = await fetch(`${BASE}${pathname}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(cookie ? { Cookie: cookie } : {}),
        ...(options.headers || {}),
      },
    });
    const setCookie = response.headers.get('set-cookie');
    if (setCookie) cookie = setCookie.split(';')[0];
    return response;
  };

  const publicBootstrap = await request('/api/bootstrap');
  assert.equal(publicBootstrap.status, 200);
  const publicData = await publicBootstrap.json();
  assert.ok(publicData.pages.length >= 1);

  const register = await request('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ name: 'Test User', email: 'test@example.com', password: 'secret123' }),
  });
  assert.equal(register.status, 201);

  const authedBootstrap = await request('/api/bootstrap');
  const authedData = await authedBootstrap.json();
  assert.equal(authedData.user.email, 'test@example.com');
  const ownedWorkspace = authedData.workspaces.find((workspace) => workspace.ownerId === authedData.user.id && workspace.kind === 'personal');
  assert.ok(ownedWorkspace);

  const createPage = await request('/api/pages', {
    method: 'POST',
    body: JSON.stringify({ workspaceId: ownedWorkspace.id, title: 'Launch Notes' }),
  });
  const createPageBody = await createPage.text();
  assert.equal(createPage.status, 201, createPageBody);
  const page = JSON.parse(createPageBody);

  const updatePage = await request(`/api/pages/${page.id}`, {
    method: 'PUT',
    body: JSON.stringify({
      title: 'Launch Notes',
      blocks: [
        { id: 'blk_sync_a', type: 'synced', text: 'Shared content', syncKey: 'shared-1' },
        { id: 'blk_2', type: 'heading1', text: 'Launch heading' },
        { id: 'blk_3', type: 'paragraph', text: 'Prepare launch checklist and publish docs.' },
      ],
    }),
  });
  assert.equal(updatePage.status, 200);

  const comment = await request(`/api/pages/${page.id}/comments`, {
    method: 'POST',
    body: JSON.stringify({ text: 'Looks good for launch.' }),
  });
  assert.equal(comment.status, 201);

  const task = await request('/api/tasks', {
    method: 'POST',
    body: JSON.stringify({ workspaceId: ownedWorkspace.id, pageId: page.id, title: 'Ship launch', description: 'Coordinate milestone', priority: 'high', status: 'todo' }),
  });
  assert.equal(task.status, 201);

  const upload = await request('/api/files', {
    method: 'POST',
    body: JSON.stringify({ workspaceId: ownedWorkspace.id, pageId: page.id, name: 'launch.txt', type: 'text/plain', data: Buffer.from('launch asset').toString('base64') }),
  });
  assert.equal(upload.status, 201);

  const searchResponse = await request(`/api/search?q=launch&workspaceId=${ownedWorkspace.id}`);
  const searchResults = await searchResponse.json();
  assert.ok(searchResults.some((result) => result.title.includes('Launch Notes')));

  const publish = await request(`/api/pages/${page.id}/publish`, {
    method: 'POST',
    body: JSON.stringify({ published: true, slug: 'launch-notes-public' }),
  });
  assert.equal(publish.status, 200);

  const pdf = await request(`/api/export/page/${page.id}?format=pdf`);
  assert.equal(pdf.status, 200);
  assert.equal(pdf.headers.get('content-type'), 'application/pdf');

  const publicPage = await fetch(`${BASE}/p/launch-notes-public`);
  const publicHtml = await publicPage.text();
  assert.equal(publicPage.status, 200);
  assert.match(publicHtml, /Launch Notes/);
});

test('HTTP flows cover databases, rows, search, and export', async (t) => {
  cleanupRuntimeFiles();
  await new Promise((resolve) => server.listen(PORT, '127.0.0.1', resolve));
  t.after(() => server.close());
  await waitForServer();

  let cookie = '';
  const request = async (pathname, options = {}) => {
    const response = await fetch(`${BASE}${pathname}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(cookie ? { Cookie: cookie } : {}),
        ...(options.headers || {}),
      },
    });
    const setCookie = response.headers.get('set-cookie');
    if (setCookie) cookie = setCookie.split(';')[0];
    return response;
  };

  const register = await request('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ name: 'DB User', email: 'db@example.com', password: 'secret123' }),
  });
  assert.equal(register.status, 201);

  const bootstrap = await request('/api/bootstrap');
  const data = await bootstrap.json();
  const ownedWorkspace = data.workspaces.find((workspace) => workspace.ownerId === data.user.id && workspace.kind === 'personal');
  assert.ok(ownedWorkspace);

  const createDatabase = await request('/api/databases', {
    method: 'POST',
    body: JSON.stringify({
      workspaceId: ownedWorkspace.id,
      title: 'Product Roadmap',
      description: 'Track initiatives',
      icon: '🗺️',
      fields: [
        { id: 'fld_name', name: 'Name', type: 'title' },
        { id: 'fld_status', name: 'Status', type: 'status', options: ['Backlog', 'In Progress', 'Done'] },
        { id: 'fld_owner', name: 'Owner', type: 'person' },
        { id: 'fld_due', name: 'Due', type: 'date' },
      ],
      views: [
        { id: 'view_table', name: 'Table', type: 'table' },
        { id: 'view_board', name: 'Board', type: 'board', groupBy: 'fld_status' },
      ],
    }),
  });
  const createDatabaseBody = await createDatabase.text();
  assert.equal(createDatabase.status, 201, createDatabaseBody);
  const database = JSON.parse(createDatabaseBody);
  assert.equal(database.title, 'Product Roadmap');

  const createRow = await request(`/api/databases/${database.id}/rows`, {
    method: 'POST',
    body: JSON.stringify({
      values: {
        fld_name: 'Launch v1',
        fld_status: 'In Progress',
        fld_owner: data.user.id,
        fld_due: '2026-05-10',
      },
      pageId: null,
    }),
  });
  const createRowBody = await createRow.text();
  assert.equal(createRow.status, 201, createRowBody);
  const row = JSON.parse(createRowBody);
  assert.equal(row.values.fld_name, 'Launch v1');

  const updateRow = await request(`/api/databases/${database.id}/rows/${row.id}`, {
    method: 'PUT',
    body: JSON.stringify({
      values: {
        fld_name: 'Launch v1',
        fld_status: 'Done',
        fld_owner: data.user.id,
        fld_due: '2026-05-12',
      },
      verified: true,
    }),
  });
  assert.equal(updateRow.status, 200);

  const databaseSearch = await request(`/api/search?q=launch&type=database_row&workspaceId=${ownedWorkspace.id}`);
  const results = await databaseSearch.json();
  assert.ok(results.some((result) => result.title.includes('Launch v1')));

  const exportCsv = await request(`/api/export/database/${database.id}?format=csv`);
  assert.equal(exportCsv.status, 200);
  const csv = await exportCsv.text();
  assert.match(csv, /Launch v1/);
  assert.match(csv, /Done/);

  const bootstrapAfter = await request('/api/bootstrap');
  const afterData = await bootstrapAfter.json();
  assert.ok(afterData.databases.some((entry) => entry.id === database.id));
  assert.ok(afterData.databaseRows.some((entry) => entry.id === row.id));
});


test('enterprise collaboration flows cover workspace settings, invite acceptance via SSO, and audit activity', async (t) => {
  cleanupRuntimeFiles();
  await new Promise((resolve) => server.listen(PORT, '127.0.0.1', resolve));
  t.after(() => server.close());
  await waitForServer();

  const makeClient = () => {
    let cookie = '';
    return async (pathname, options = {}) => {
      const response = await fetch(`${BASE}${pathname}`, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(cookie ? { Cookie: cookie } : {}),
          ...(options.headers || {}),
        },
      });
      const setCookie = response.headers.get('set-cookie');
      if (setCookie) cookie = setCookie.split(';')[0];
      return response;
    };
  };

  const owner = makeClient();
  const teammate = makeClient();

  const register = await owner('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ name: 'Owner User', email: 'owner@example.com', password: 'secret123' }),
  });
  assert.equal(register.status, 201);

  const bootstrap = await owner('/api/bootstrap');
  const data = await bootstrap.json();
  const teamWorkspace = data.workspaces.find((workspace) => workspace.ownerId === data.user.id && workspace.kind === 'team');
  assert.ok(teamWorkspace);

  const updateSettings = await owner(`/api/workspaces/${teamWorkspace.id}/settings`, {
    method: 'PUT',
    body: JSON.stringify({
      domainRestriction: 'example.com',
      samlEnabled: true,
      scimEnabled: true,
      allowGuests: false,
      publicSharing: false,
      storageQuotaMb: 42,
    }),
  });
  assert.equal(updateSettings.status, 200);
  const settingsBody = await updateSettings.json();
  assert.equal(settingsBody.settings.domainRestriction, 'example.com');
  assert.equal(settingsBody.settings.samlEnabled, true);
  assert.equal(settingsBody.settings.scimEnabled, true);
  assert.equal(settingsBody.settings.storageQuotaMb, 42);

  const invite = await owner(`/api/workspaces/${teamWorkspace.id}/invite`, {
    method: 'POST',
    body: JSON.stringify({ email: 'teammate@example.com', role: 'editor' }),
  });
  assert.equal(invite.status, 200);

  const sso = await teammate('/api/auth/sso', {
    method: 'POST',
    body: JSON.stringify({ workspaceId: teamWorkspace.id, email: 'teammate@example.com', name: 'Teammate User', externalId: 'saml-ext-1' }),
  });
  assert.equal(sso.status, 200);
  const ssoBody = await sso.json();
  assert.equal(ssoBody.user.email, 'teammate@example.com');
  assert.equal(ssoBody.user.identity.samlExternalId, 'saml-ext-1');
  assert.ok(ssoBody.user.identity.authMethods.includes('saml'));

  const teammateBootstrap = await teammate('/api/bootstrap');
  const teammateData = await teammateBootstrap.json();
  assert.ok(teammateData.workspaces.some((workspace) => workspace.id === teamWorkspace.id));

  const invitations = await owner(`/api/workspaces/${teamWorkspace.id}/invitations`);
  assert.equal(invitations.status, 200);
  const invitationList = await invitations.json();
  assert.ok(invitationList.some((entry) => entry.email === 'teammate@example.com' && entry.acceptedAt));

  const activity = await owner(`/api/workspaces/${teamWorkspace.id}/activity`);
  assert.equal(activity.status, 200);
  const activityEntries = await activity.json();
  assert.ok(activityEntries.some((entry) => entry.kind === 'workspace.settings.updated'));
  assert.ok(activityEntries.some((entry) => entry.kind === 'workspace.invited'));
  assert.ok(activityEntries.some((entry) => entry.kind === 'workspace.sso-login'));
});

test('enterprise provisioning covers SCIM user creation and membership sync', async (t) => {
  cleanupRuntimeFiles();
  await new Promise((resolve) => server.listen(PORT, '127.0.0.1', resolve));
  t.after(() => server.close());
  await waitForServer();

  let cookie = '';
  const request = async (pathname, options = {}) => {
    const response = await fetch(`${BASE}${pathname}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(cookie ? { Cookie: cookie } : {}),
        ...(options.headers || {}),
      },
    });
    const setCookie = response.headers.get('set-cookie');
    if (setCookie) cookie = setCookie.split(';')[0];
    return response;
  };

  const register = await request('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ name: 'SCIM Owner', email: 'scim-owner@example.com', password: 'secret123' }),
  });
  assert.equal(register.status, 201);

  const bootstrap = await request('/api/bootstrap');
  const data = await bootstrap.json();
  const teamWorkspace = data.workspaces.find((workspace) => workspace.ownerId === data.user.id && workspace.kind === 'team');
  assert.ok(teamWorkspace);

  const updateSettings = await request(`/api/workspaces/${teamWorkspace.id}/settings`, {
    method: 'PUT',
    body: JSON.stringify({ scimEnabled: true, domainRestriction: 'example.com' }),
  });
  assert.equal(updateSettings.status, 200);

  const provision = await request(`/api/workspaces/${teamWorkspace.id}/scim/users`, {
    method: 'POST',
    body: JSON.stringify({
      email: 'provisioned@example.com',
      name: 'Provisioned Person',
      externalId: 'scim-42',
      role: 'viewer',
      title: 'Analyst',
    }),
  });
  assert.equal(provision.status, 201);
  const provisioned = await provision.json();
  assert.equal(provisioned.user.email, 'provisioned@example.com');
  assert.equal(provisioned.user.identity.scimExternalId, 'scim-42');

  const invitations = await request(`/api/workspaces/${teamWorkspace.id}/invitations`);
  assert.equal(invitations.status, 200);

  const activity = await request(`/api/workspaces/${teamWorkspace.id}/activity`);
  assert.equal(activity.status, 200);
  const activityEntries = await activity.json();
  assert.ok(activityEntries.some((entry) => entry.kind === 'workspace.scim-provisioned'));

  const refreshed = await request('/api/bootstrap');
  const refreshedData = await refreshed.json();
  const refreshedWorkspace = refreshedData.workspaces.find((workspace) => workspace.id === teamWorkspace.id);
  assert.ok(refreshedWorkspace.members.some((member) => member.role === 'viewer'));
  assert.ok(refreshedData.directory.some((entry) => entry.email === 'provisioned@example.com'));
});
