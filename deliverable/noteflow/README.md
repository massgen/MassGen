# NoteFlow

NoteFlow is a self-contained full-stack collaborative workspace app inspired by Notion. It ships as a zero-dependency Node.js application with a browser-based editor, workspace/page hierarchy, first-class databases, tasks, search, sharing, notifications, auth, import/export, file management, and realtime presence via Server-Sent Events.

## Run locally

```bash
node server.mjs
```

Then open: http://localhost:3000

## Default behavior

- First run seeds a demo workspace and starter templates.
- Create an account with email/password, or use the demo OAuth buttons.
- Data persists to `data/noteflow-db.json` and uploaded files under `uploads/`.

## Implemented highlights

- Personal and team workspaces
- Nested pages, templates, breadcrumbs, favorites, recent pages, trash/restore
- Block editor with slash insertion, drag/drop reorder, markdown-ish shortcuts, synced blocks, comments, backlinks, table of contents, version history, publish/share controls, SEO/custom URL settings
- First-class databases with schemas, row CRUD, and table/board/calendar/timeline/gallery views
- Realtime presence + page refresh events via SSE
- Task database with priorities, statuses, dependencies, reminders, recurrence, dashboards, my tasks, workload grouping, ICS export
- Global search across pages, database rows, comments, tasks, and files with filters
- File uploads, signed access URLs, version replacement, quota checks
- In-app notifications + email-preview outbox + preferences
- Email/password auth, magic links, demo OAuth flows, demo SSO/SAML login, SCIM provisioning, 2FA setup/verify, sessions/device metadata, profile management
- Admin center for workspace security settings, invite tracking, audit activity, page/database permission grants, and publishing/share controls
- Import/export for Markdown, HTML, CSV, JSON, simple PDF generation, plus database CSV/JSON/Markdown export

## Testing

```bash
node --test tests/*.test.mjs
```
