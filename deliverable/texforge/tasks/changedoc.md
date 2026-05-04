# Change Document

**Sources reviewed:** agent1.2, agent_a

## Summary
Delivered the final TexForge workspace as a runnable FastAPI-based collaborative LaTeX platform slice with authenticated projects, multi-file editing, template instantiation, WebSocket collaboration, threaded review, compile/export simulation, references, snapshots/diffs, and explicit lightweight branches. The final code keeps the Python-first architecture from earlier rounds and preserves the expanded marketplace, lifecycle, review, and branching workflows introduced in coordination.

## Decisions

### DEC-001: Keep the Python-first full-stack architecture
**Origin:** agent1.1 → agent1.2 (kept)
**Choice:** Implement TexForge with FastAPI, Jinja templates, vanilla JavaScript, SQLite, and WebSockets.
**Why:** The available environment supports a strong Python delivery path without requiring a JS build toolchain, so this architecture maximizes runnable product surface area while still covering frontend, backend, persistence, and realtime behavior.
**Alternatives considered:**
- Rebuild the UI in a richer frontend stack: rejected because it would reduce shipped functionality in the current environment.
- Limit the deliverable to API-only behavior: rejected because the task calls for a full-stack platform.
**Implementation:**
- `texforge/app.py` → `create_app()` wires the HTTP, HTML, auth, compile, review, search, sharing, reference, branch, and admin flows.
- `texforge/db.py` → `Database` owns the SQLite schema and persistence helpers for projects, files, comments, snapshots, branches, references, and memberships.
- `texforge/templates/dashboard.html`, `texforge/templates/project.html`, `texforge/static/app.js`, and `texforge/static/style.css` provide the browser-facing product surface.

### DEC-002: Promote templates into a usable marketplace workflow
**Origin:** agent_a NEW (extends agent1.2)
**Choice:** Support searchable template listing, preview-by-slug, and one-step project creation from a selected template.
**Why:** Template support is much more useful when users can browse, inspect, and instantiate a template directly instead of treating it as a static catalog entry.
**Alternatives considered:**
- Keep template use implicit inside generic project creation: rejected because it hides a major requested workflow.
- Add community submission/moderation before browse/preview/use flows: rejected because core marketplace usability comes first.
**Implementation:**
- `texforge/app.py` → `api_templates()`, `api_template_preview()`, `api_create_project_from_template()`.
- `texforge/db.py` → `search_templates()`.
- `texforge/templates/dashboard.html` and `texforge/static/app.js` → dashboard search, preview, and create-from-template interactions.
- `tests/test_texforge.py` → `test_template_marketplace_preview_search_and_instantiation()`.

### DEC-003: Complete the core project and file lifecycle
**Origin:** agent_a NEW (extends agent1.2)
**Choice:** Add file move/rename, file delete, and project delete flows on top of existing create, clone, and archive behavior.
**Why:** The platform brief explicitly requires create/delete/archive project management and practical organization of multi-file LaTeX trees.
**Alternatives considered:**
- Prioritize a richer tree UI before lifecycle correctness: rejected because backend lifecycle completeness is the stronger foundation.
- Leave deletion out to avoid destructive actions: rejected because missing delete flows would leave the platform operationally incomplete.
**Implementation:**
- `texforge/app.py` → `api_move_file()`, `api_delete_file()`, `api_delete_project()`.
- `texforge/db.py` → `move_file()`, `delete_file()`, `delete_project()`.
- `texforge/templates/project.html` and `texforge/static/app.js` → file action controls and destructive-action handlers.
- `tests/test_texforge.py` → `test_file_move_delete_and_project_delete()`.

### DEC-004: Turn review into threaded, stateful collaboration
**Origin:** agent_a NEW (extends agent1.2)
**Choice:** Expose threaded comment retrieval and resolve/unresolve actions, while preserving suggestions and acceptance flows.
**Why:** Academic review needs discussion threads that can be worked through and closed, not only flat comments.
**Alternatives considered:**
- Keep replies stored but not surfaced as threads: rejected because the UI would still behave like flat review.
- Focus only on suggestion acceptance: rejected because threaded review improves the wider collaboration loop.
**Implementation:**
- `texforge/app.py` → `api_comment()`, `api_list_comments()`, `api_resolve_comment()`, `api_unresolve_comment()`, `api_suggestion()`, `api_accept_suggestion()`.
- `texforge/db.py` → `list_comment_threads()`, `set_comment_resolved()`, `create_suggestion()`, `accept_suggestion()`.
- `texforge/static/app.js` → threaded comment rendering and resolution toggles.
- `tests/test_texforge.py` → `test_threaded_comments_resolution_and_branches()` plus existing suggestion coverage.

### DEC-005: Represent lightweight branching as an explicit restorable object
**Origin:** agent_a NEW (extends agent1.2)
**Choice:** Persist named branches anchored to snapshots, list them separately, and allow branch restore through the API and UI.
**Why:** The requested version-control surface includes lightweight branching and named restore points; explicit branch objects are clearer and more demonstrable than implied branches.
**Alternatives considered:**
- Treat snapshots alone as informal branches: rejected because that leaves the branching workflow ambiguous.
- Attempt full git-style merge semantics locally: rejected because named branch creation and restore delivers the higher-value lightweight slice here.
**Implementation:**
- `texforge/app.py` → `api_create_branch()`, `api_list_branches()`, `api_restore_branch()`.
- `texforge/db.py` → `create_branch()`, `list_branches()`, `restore_branch()` and the `branches` table.
- `texforge/templates/project.html` and `texforge/static/app.js` → branch creation, listing, and restore controls.
- `tests/test_texforge.py` → `test_threaded_comments_resolution_and_branches()`.

## Deliberation Trail
- **agent1.1 → agent1.2:** Established the runnable Python-first TexForge architecture and broad product slice.
- **agent_a NEW:** Completed the template gallery into a searchable, previewable marketplace with direct instantiation.
- **agent_a NEW:** Closed basic lifecycle gaps by adding file move/delete and project delete operations.
- **agent_a NEW:** Finished the latent threaded review model with explicit resolve/unresolve flows.
- **agent_a NEW:** Elevated snapshots into explicit lightweight branches with restore behavior.
