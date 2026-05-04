# Change Document

**Sources reviewed:** [agent1.2]

## Summary
Delivered the final NoteFlow app as a zero-dependency full-stack Node.js workspace platform with a browser SPA, seeded demo data, tests, and an enterprise collaboration/admin layer. The final delivery keeps the broad Notion-style surface from the prior base and includes workspace/page management, a block editor, databases, tasks, search, files, notifications, authentication, import/export, realtime presence, and admin/governance workflows such as SSO/SAML demo auth, SCIM provisioning, invitation acceptance, audit activity, 2FA setup, and page/database permission management.

## Decisions

### DEC-001: Keep the zero-dependency full-stack Node delivery from agent1.1/agent1.2
**Origin:** agent1.2 (kept)
**Choice:** Retain the single-process Node server plus static SPA architecture.
**Why:** The task required a very broad product surface in one deliverable. This architecture keeps startup friction low, ships cleanly with built-in Node APIs only, and lets the app cover pages, databases, tasks, search, files, auth, and collaboration in one runnable project.
**Alternatives considered:**
- Replatform to a heavier framework: rejected because it would reduce shipped scope and increase setup complexity for this delivery.
**Implementation:**
- `server.mjs` → HTTP server, routing, persistence, SSE presence/events, auth/session handling, import/export helpers, search, file APIs, workspace/page/database/task endpoints
- `public/index.html` → SPA shell
- `public/styles.css` → application layout and feature styling
- `public/app.js` → client-side state management, page editor UI, databases/tasks/search/files/notifications/admin experiences
- `package.json` → runnable start/dev/test scripts

### DEC-002: Preserve first-class databases and extend them with permission management rather than replacing the model
**Origin:** agent1.2 (kept) → [SELF] (modified)
**Choice:** Keep databases/rows/views as a core primitive and extend them with admin-managed access grants.
**Why:** Notion-style collaboration depends on structured databases being a first-class workspace object, not an afterthought. Extending the existing database model with governance controls closes a major gap between a document app and a real team workspace platform.
**Alternatives considered:**
- Leave databases unchanged: rejected because it would leave collaboration and governance incomplete for team use.
**Implementation:**
- `server.mjs` → database CRUD routes, row CRUD routes, workspace settings, permission-bearing database records returned through `/api/bootstrap`
- `public/app.js` → database rendering, row editing, view switching, and `renderAdminPanel()` flows for database permission grants
- `tests/noteflow.test.mjs` → database creation, row update, search, export, and enterprise coverage regression tests

### DEC-003: Add an enterprise admin/security slice as the highest-leverage missing product area
**Origin:** [SELF] — NEW
**Choice:** Introduce workspace settings, audit feed, invitation lifecycle visibility, SSO/SAML demo login, SCIM provisioning, device/session metadata, 2FA activation, and explicit page/database permission grants.
**Why:** The broad collaboration surface was already strong, but the largest remaining mismatch with the original brief was enterprise governance and identity administration. Making these flows visible and usable in both API and UI materially improves fidelity to the requested NoteFlow platform.
**Alternatives considered:**
- Keep enterprise behaviors implicit or backend-only: rejected because the brief asked for production-style collaboration, identity, and permissions features that should be operable from the product.
**Implementation:**
- `server.mjs` → `ensureAuthMethod()`, `upsertWorkspaceMember()`, `acceptPendingInvitations()`, `/api/auth/sso`, `/api/workspaces/:id/settings`, `/api/workspaces/:id/invitations`, `/api/workspaces/:id/activity`, `/api/workspaces/:id/scim/users`, session/device metadata, audit logging, and sharing control enforcement
- `public/app.js` → `renderAdminPanel()`, workspace settings form, SSO entry flow, SCIM provisioning form, invitation tracking, page/database permission forms, activity feed rendering, and `setupTwoFactor()`
- `README.md` → shipped feature summary including enterprise admin/security capabilities
- `tests/noteflow.test.mjs` → regression coverage for workspace settings, SSO invite acceptance, audit logging, and SCIM membership sync

## Deliberation Trail

### [SELF] (synthesized from agent1.2)
- DEC-001: Kept the existing zero-dependency Node architecture because it remained the fastest way to preserve breadth and ship a fully runnable product.
- DEC-002: Kept first-class databases from agent1.2 and extended them so governance applies to databases as well as pages.
- DEC-003: NEW — added the enterprise collaboration/admin slice because it was the clearest remaining gap against the original NoteFlow brief.
