# TexForge

TexForge is a full-stack collaborative LaTeX editing platform prototype inspired by Overleaf. It ships as a Python-first local app with:

- project and file lifecycle management (create, clone, archive, delete, move/rename, delete files)
- template marketplace with search, preview, and one-click project instantiation (IEEE, ACM, thesis, resume)
- responsive split-view editor and PDF preview
- real-time collaboration over WebSockets with presence and cursor updates
- email/password authentication with cookie sessions
- role-aware sharing (owner/editor/viewer), project memberships, and org-style dashboards
- threaded comments with resolve/unresolve, suggestions, snapshots, explicit lightweight branches, diffing, restore, sharing links, notifications, and activity timeline
- bibliography import and citation autocomplete for DOI/arXiv/Scholar-style flows
- compile job queue simulation with downloadable PDF and ZIP export
- offline deterministic AI assist endpoint for LaTeX generation/fixes
- admin metrics for users, projects, memberships, compile jobs, and reference usage

## Run

```bash
uv run python -m uvicorn run:app --reload
```

Then open http://127.0.0.1:8000

## Test

```bash
PYTHONPATH=. UV_CACHE_DIR=.massgen_scratch/uv-cache uv run pytest tests/test_texforge.py -q -p no:cacheprovider
```

## Notes

- This environment does not include Docker or TeX Live, so the compile layer is implemented as a worker-style simulation with real logs, artifacts, and extension points.
- The collaboration and product architecture are designed so a real Yjs/worker/object-storage stack can replace the local services without changing the product surface.
- Guest mode remains available for local demo browsing, while authenticated users unlock permissions, memberships, reference tools, and admin metrics.
