#!/usr/bin/env python3
"""
Project evaluator for rental-platform submissions.

Metrics:
- FC: Feature Completeness (%) — LLM judge (GPT-4o-mini)
- SV: Structural Validity (%)  — static: structure + syntax + import resolution + lint
- BS: Build Success (pass/fail) — static: py_compile + npm run build
- CQ: Code Quality (0-100)     — static: lint density + cyclomatic complexity + duplication
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import statistics
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXCLUDE_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", ".nuxt",
    ".massgen_scratch", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "evaluation", "reports",
    "out",           # Next.js static export — compiled artefacts, not source
    ".eval_pycache", # our own cache dir
}

TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".json", ".md", ".txt", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".html", ".css", ".scss", ".sql",
}

CODE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx"}

# Extensions that carry meaningful source content for the LLM judge
SOURCE_EXTENSIONS = {".py", ".js", ".jsx", ".ts", ".tsx", ".sql", ".yaml", ".yml", ".toml"}

ROUTE_PATTERNS = [
    re.compile(r'@(?:app|router)\.(?:get|post|put|patch|delete|websocket)\(\s*["\']([^"\']+)["\']'),
    re.compile(r'(?:app|router)\.(?:get|post|put|patch|delete)\(\s*["\']([^"\']+)["\']'),
]

LOCAL_IMPORT_RE = re.compile(
    r"(?:import|export)\s+[^;]*?\s+from\s*['\"]([^'\"]+)['\"]"
    r"|require\(\s*['\"]([^'\"]+)['\"]\s*\)"
)

PY_DECISION_NODES = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp,
    ast.Try, ast.ExceptHandler, ast.BoolOp, ast.With, ast.AsyncWith,
) + ((ast.Match,) if hasattr(ast, "Match") else ())

# Approximate chars per token for budget estimation
CHARS_PER_TOKEN = 4
# Max source tokens to send to LLM judge per project (keep cost manageable)
MAX_SOURCE_TOKENS = 40_000
# Max chars per individual file included in the judge context
MAX_FILE_CHARS = 6_000


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


@dataclass
class FeatureScore:
    id: str
    name: str
    score: float          # 0.0–1.0
    implemented: bool
    reasoning: str        # LLM explanation
    evidence: List[str]   # quoted snippets / file references from LLM


@dataclass
class ProjectSnapshot:
    root: Path
    files: List[Path]
    rel_files: List[str]
    text_by_relpath: Dict[str, str]
    import_lines: List[str]
    routes: List[str]
    has_python: bool
    has_js: bool
    has_ts: bool


@dataclass
class ProjectResult:
    project: str
    fc: float
    sv: float
    bs: bool
    cq: float
    feature_breakdown: List[FeatureScore] = field(default_factory=list)
    structural_details: Dict = field(default_factory=dict)
    build_details: Dict = field(default_factory=dict)
    quality_details: Dict = field(default_factory=dict)
    llm_judge_model: str = ""
    llm_judge_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

def list_source_files(root: Path) -> List[Path]:
    files: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            suffix = path.suffix.lower()
            if suffix in TEXT_EXTENSIONS or filename in {"package.json", "requirements.txt"}:
                files.append(path)
    return files


def safe_read_text(path: Path) -> Optional[str]:
    for enc in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
        except Exception:
            return None
    return None


def build_snapshot(root: Path) -> ProjectSnapshot:
    files = list_source_files(root)
    rel_files = [str(p.relative_to(root)).replace(os.sep, "/") for p in files]

    text_by_relpath: Dict[str, str] = {}
    import_lines: List[str] = []
    routes: List[str] = []
    has_python = False
    has_js = False
    has_ts = False

    for path, rel in zip(files, rel_files):
        text = safe_read_text(path)
        if text is None:
            continue
        text_by_relpath[rel] = text

        suffix = path.suffix.lower()
        if suffix == ".py":
            has_python = True
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    import_lines.append(s)
        if suffix in {".js", ".jsx"}:
            has_js = True
        if suffix in {".ts", ".tsx"}:
            has_ts = True
        if suffix in {".js", ".jsx", ".ts", ".tsx"}:
            for m in LOCAL_IMPORT_RE.finditer(text):
                spec = m.group(1) or m.group(2)
                if spec:
                    import_lines.append(spec)
        for route_re in ROUTE_PATTERNS:
            for m in route_re.finditer(text):
                route = (m.group(1) or "").strip()
                if route:
                    routes.append(route)

    return ProjectSnapshot(
        root=root,
        files=files,
        rel_files=rel_files,
        text_by_relpath=text_by_relpath,
        import_lines=import_lines,
        routes=routes,
        has_python=has_python,
        has_js=has_js,
        has_ts=has_ts,
    )


# ---------------------------------------------------------------------------
# Static Feature Completeness — file detection + import + schema + route
# ---------------------------------------------------------------------------

def _feature_signal_score(snapshot: ProjectSnapshot, feature: dict) -> FeatureScore:
    """
    Score one feature using purely static signals:
      - file_patterns  : glob-style filename substrings  (weight 0.30)
      - import_keywords: words found in import lines      (weight 0.25)
      - schema_keywords: words found anywhere in source   (weight 0.20)
      - route_patterns : URL strings found in routes      (weight 0.15)
      - code_keywords  : identifiers in source code       (weight 0.10)

    Each signal category scores 1.0 if ANY match is found, else 0.0.
    Final score = weighted sum, normalised so absent categories don't penalise.
    """
    det = feature.get("detection", {})

    weights = {
        "file_patterns":   0.30,
        "import_keywords": 0.25,
        "schema_keywords": 0.20,
        "route_patterns":  0.15,
        "code_keywords":   0.10,
    }

    hits: Dict[str, bool] = {}

    # --- file_patterns: substring match against relative file paths ---
    pats = [p.lower().strip("*") for p in det.get("file_patterns", []) if p]
    if pats:
        hits["file_patterns"] = any(
            any(pat in rf.lower() for pat in pats)
            for rf in snapshot.rel_files
        )

    # --- import_keywords: match against collected import lines ---
    imp_kws = [k.lower() for k in det.get("import_keywords", []) if k]
    if imp_kws:
        import_blob = " ".join(snapshot.import_lines).lower()
        hits["import_keywords"] = any(kw in import_blob for kw in imp_kws)

    # --- schema_keywords: match across ALL source text ---
    schema_kws = [k.lower() for k in det.get("schema_keywords", []) if k]
    if schema_kws:
        # Build combined source blob once (reused across keywords)
        source_blob = " ".join(
            text.lower()
            for rel, text in snapshot.text_by_relpath.items()
            if Path(rel).suffix.lower() in SOURCE_EXTENSIONS
        )
        hits["schema_keywords"] = any(kw in source_blob for kw in schema_kws)
    else:
        source_blob = ""  # may be needed below

    # --- route_patterns: match against extracted API routes ---
    route_pats = [r.lower().strip("/") for r in det.get("route_patterns", []) if r]
    if route_pats:
        routes_blob = " ".join(snapshot.routes).lower()
        hits["route_patterns"] = any(rp in routes_blob for rp in route_pats)

    # --- code_keywords: identifier-level match in source ---
    code_kws = [k.lower() for k in det.get("code_keywords", []) if k]
    if code_kws:
        if not source_blob:
            source_blob = " ".join(
                text.lower()
                for rel, text in snapshot.text_by_relpath.items()
                if Path(rel).suffix.lower() in SOURCE_EXTENSIONS
            )
        hits["code_keywords"] = any(kw in source_blob for kw in code_kws)

    # Weighted score over only the categories that have detection rules
    active = {k: v for k, v in weights.items() if k in hits}
    if not active:
        raw = 0.0
        evidence = ["no detection rules defined"]
    else:
        total_w = sum(active.values())
        raw = sum(weights[k] * (1.0 if hits[k] else 0.0) for k in active) / total_w
        evidence = [f"{k}={'HIT' if hits[k] else 'MISS'}" for k in sorted(active)]

    # Map continuous [0,1] raw score to paper rubric anchors
    if raw >= 0.80:
        score = 1.0
    elif raw >= 0.55:
        score = 0.7
    elif raw >= 0.30:
        score = 0.4
    elif raw > 0.0:
        score = 0.1
    else:
        score = 0.0

    return FeatureScore(
        id=feature["id"],
        name=feature["name"],
        score=score,
        implemented=score >= 0.7,
        reasoning=f"Static signals: raw={raw:.2f} → score={score}",
        evidence=evidence,
    )


def evaluate_features_static(
    snapshot: ProjectSnapshot,
    features: List[dict],
) -> List[FeatureScore]:
    """
    Pure-static FC evaluation per paper definition:
    file detection + import analysis + schema inspection + route checking.
    """
    return [_feature_signal_score(snapshot, f) for f in features]


# ---------------------------------------------------------------------------
# LLM Judge — kept for optional reference / ablation only
# ---------------------------------------------------------------------------

def _build_source_context(snapshot: ProjectSnapshot) -> str:
    """
    Assemble a compact source-code context to send to the judge.
    Agent-related files are prioritised; remaining files sorted by size descending.
    """
    AGENT_KEYWORDS = {"agent", "booking", "marketplace", "host", "guest", "negotiat",
                      "pricing", "monitor", "approval", "dispute", "turnover"}

    source_pairs = [
        (rel, text)
        for rel, text in snapshot.text_by_relpath.items()
        if Path(rel).suffix.lower() in SOURCE_EXTENSIONS
        and not rel.startswith("package-lock")
    ]

    def _priority(item: Tuple[str, str]) -> Tuple[int, int]:
        rel_lower = item[0].lower()
        is_agent = any(kw in rel_lower for kw in AGENT_KEYWORDS)
        return (0 if is_agent else 1, -len(item[1]))

    source_pairs.sort(key=_priority)

    chunks: List[str] = []
    total_chars = 0
    budget = MAX_SOURCE_TOKENS * CHARS_PER_TOKEN

    for rel, text in source_pairs:
        if total_chars >= budget:
            break
        rel_lower = rel.lower()
        is_agent = any(kw in rel_lower for kw in AGENT_KEYWORDS)
        per_file_limit = MAX_FILE_CHARS * 2 if is_agent else MAX_FILE_CHARS
        snippet = text[:per_file_limit]
        if len(text) > per_file_limit:
            snippet += f"\n... [truncated, {len(text) - per_file_limit} more chars]"
        entry = f"### FILE: {rel}\n```\n{snippet}\n```"
        chunks.append(entry)
        total_chars += len(entry)

    # Always include the full file tree so the LLM can reason about what exists
    tree_lines = sorted(snapshot.rel_files)
    tree = "### FILE TREE\n" + "\n".join(tree_lines)

    # Also inject extracted routes and imports as structured signals
    route_block = ""
    if snapshot.routes:
        route_block = "\n### DETECTED ROUTES\n" + "\n".join(sorted(set(snapshot.routes)))
    import_block = ""
    if snapshot.import_lines:
        unique_imports = sorted(set(snapshot.import_lines))[:200]
        import_block = "\n### DETECTED IMPORTS\n" + "\n".join(unique_imports)

    return tree + route_block + import_block + "\n\n" + "\n\n".join(chunks)


def _build_judge_prompt(source_context: str, features: List[dict]) -> str:
    features_json = json.dumps(
        [{"id": f["id"], "name": f["name"], "description": f.get("description", ""),
          "detection_hints": f.get("detection", {})}
         for f in features],
        indent=2,
    )

    return f"""\
You are a strict senior software engineer evaluating a rental-platform submission for \
an academic benchmark. This is a hard task — most submissions are incomplete. \
Be conservative: when in doubt, score lower. Do not infer or assume functionality \
that is not explicitly present in the code.

## SEMANTIC NAMING — USE BROAD RECOGNITION
The `detection_hints` in each feature are SEMANTIC HINTS, not string-match rules. \
Apply your judgment to recognize naming variants: "HouseAgent", "PropertyManager", \
"LandlordBot" all count as the host agent. Never reject evidence solely because it \
lacks the exact hint keyword. However, recognising a name is NOT sufficient for a \
high score — you must also verify real logic exists behind that name.

## SIGNAL STRENGTH — READ THIS CAREFULLY

Signals are NOT equal. Before scoring, classify each signal you find:

**WEAK signals** (file name match, import reference):
- A file named `search.ts` exists → WEAK
- An import `from './guestAgent'` exists → WEAK
- A TypeScript type alias `type BookingStatus = string` → WEAK
- Weak signals alone CANNOT justify a score above 0.4

**STRONG signals** (schema with real fields, route with real handler, executable logic):
- A Pydantic/SQLAlchemy/Prisma model with ≥3 meaningful fields → STRONG
- A route handler that reads/writes a database or calls an LLM → STRONG
- A function that performs state transitions, not just returns a hardcoded value → STRONG
- A class with methods that branch on real input state → STRONG

**Scoring requires STRONG signals for scores above 0.4.** \
File names and imports alone cannot produce 0.7 or 1.0.

## HOW TO EVALUATE EACH FEATURE

For every feature, check all four signals in order and classify each as WEAK or STRONG:

1. **File detection** (WEAK by default): A matching filename is only evidence that \
the developer intended to implement this feature. Open the file content. If it \
contains only imports, type stubs, empty functions, or UI components with no \
backend logic, it remains WEAK. It becomes STRONG only if the file contains \
substantive executable logic for this feature.

2. **Import analysis** (WEAK by default): An import line proves a module was \
referenced, not that it works. It becomes STRONG only if the imported module \
itself contains real logic (verify in the file contents).

3. **Schema inspection** (STRONG if real): A data model with ≥3 meaningful fields \
representing this feature's core data, defined in Pydantic, SQLAlchemy, Prisma, \
Drizzle, Zod, or raw SQL. A single-field type alias or empty interface is WEAK.

4. **Route checking** (STRONG if real): An API endpoint whose handler contains \
real logic (DB query, LLM call, state update). An empty handler or one that \
returns a hardcoded 200/mock response is WEAK.

## SCORING RUBRIC — QUANTIFIED

  1.0 — 3 or 4 STRONG signals AND real end-to-end working logic: actual DB writes, \
LLM API calls with dynamic context, or real state machine transitions. \
The feature is reachable and functional end-to-end.

  0.7 — 2 STRONG signals, core logic substantially present but one meaningful \
piece missing (e.g. no error handling, one sub-flow absent, logic partially \
hardcoded but not fully).

  0.4 — 1 STRONG signal OR multiple WEAK signals only. Code is scaffold, skeleton, \
mock, or UI-only. Logic is present in structure but not in execution.

  0.1 — 1 WEAK signal only: a comment, TODO, type alias, or UI label with zero \
executable logic behind it.

  0.0 — No signals of any kind. Feature completely absent.

## DISQUALIFYING PATTERNS — hard cap at 0.4, no exceptions

**CRITICAL SCOPE RULE**: Disqualifying patterns apply ONLY to the specific feature \
they describe. They do NOT propagate to other features. If a project uses in-memory \
storage (pattern #1), ONLY the `persistent_state` feature is capped at 0.4 — all \
other features (agent logic, booking lifecycle, A2A negotiation, etc.) must still be \
evaluated independently on their own merits. Never let one disqualifying pattern \
lower the score of an unrelated feature.

If ANY of the following are true FOR THE SPECIFIC FEATURE BEING EVALUATED, \
the maximum score for THAT FEATURE is 0.4:

1. **Fake persistence** (applies only to `persistent_state` feature): State is stored \
ONLY in browser localStorage, sessionStorage, Zustand/Redux with localStorage backend, \
or an in-memory JS Map/object/array with no server-side persistence. \
A real database means: SQLite, PostgreSQL, MySQL, MongoDB, a file written to disk \
by the backend (not the browser), or any server-side durable store. \
Zustand `persist` middleware with localStorage does NOT count. \
NOTE: A project that uses in-memory storage can still score 1.0 on agent logic, \
booking lifecycle, A2A negotiation, and other features — judge those independently.

2. **Fake agent decisions** (applies to agent-related features): Agent "decisions" \
use `Math.random()`, `random.randint()`, pick from a hardcoded array, or always \
return the same string regardless of input. \
Real decisions include: LLM API calls (Anthropic, OpenAI SDK), branching on actual \
state read from the data model, or rule engines that operate on real runtime data. \
An `import Anthropic` + `anthropic.messages.create(...)` with a dynamic prompt \
based on actual booking/user state = real agent logic regardless of DB backend.

3. **No backend** (applies to all features): The entire project is frontend-only \
(HTML/CSS/JS/React with no server process, no API routes, no Python/Node backend). \
A pure Next.js static export with no API routes counts as frontend-only.

4. **Fake agent-to-agent** (applies only to `agent_to_agent_negotiation` feature): \
Agents only interact by both reading the same database table with no direct \
message passing, invocation, or event/queue/webhook between agent objects.

## FRAMEWORK-NEUTRAL RULES (do NOT penalise these):
- Next.js API routes (`/api/...`) count as real backend routes
- TypeScript interfaces + Zod schemas with ≥3 meaningful fields count as schema
- LLM SDK calls (Anthropic, OpenAI) with dynamic, state-dependent prompts = real agent logic
- /tmp JSON file written by a server process = a real (if minimal) database
- tsx / ts-node runtime scripts = runnable backend code

## FEATURES TO EVALUATE
{features_json}

## CODEBASE
{source_context}

## OUTPUT FORMAT
Return ONLY a valid JSON object — no markdown fences, no commentary:
{{
  "results": [
    {{
      "id": "<feature id>",
      "score": <0.0 to 1.0, one decimal place>,
      "reasoning": "<2-4 sentences: list each signal as WEAK or STRONG with why, state whether any disqualifying pattern applies, then justify the score>",
      "evidence": ["<specific file:line or code snippet that determined your score>"]
    }},
    ...
  ]
}}
"""



def _call_openai_judge(
    prompt: str,
    model: str = "gpt-4o-mini",
    dotenv_path: Optional[str] = None,
) -> Tuple[str, float]:
    """
    Call OpenAI chat completions. Returns (response_text, cost_usd_approx).
    Loads .env from dotenv_path if provided.
    """
    try:
        from dotenv import load_dotenv
        if dotenv_path:
            load_dotenv(dotenv_path)
    except ImportError:
        pass  # python-dotenv not installed; rely on env vars being set already

    try:
        import openai
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    client = openai.OpenAI()

    # Models like gpt-5-mini don't support temperature=0; omit it to use default
    MODELS_NO_TEMPERATURE = {"gpt-5-mini", "gpt-5", "gpt-5-nano", "o3-mini", "o4-mini"}
    use_temperature = model not in MODELS_NO_TEMPERATURE

    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            create_kwargs: dict = dict(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content":
                     "You are a precise code evaluator. Always return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
            )
            if use_temperature:
                create_kwargs["temperature"] = 0.0
            response = client.chat.completions.create(**create_kwargs)
            text = response.choices[0].message.content or ""
            usage = response.usage
            # Approximate cost for gpt-4o-mini: $0.15/1M input, $0.60/1M output
            cost = 0.0
            if usage:
                cost = (usage.prompt_tokens * 0.15 + usage.completion_tokens * 0.60) / 1_000_000
            return text, cost
        except Exception as exc:
            last_exc = exc
            print(f"  [warn] LLM call attempt {attempt + 1} failed: {exc}", file=sys.stderr)

    raise RuntimeError(f"LLM judge failed after 3 attempts: {last_exc}")


def _parse_judge_response(raw: str, features: List[dict]) -> List[FeatureScore]:
    """
    Parse the JSON returned by the LLM judge.
    Accepts both a bare array and a wrapped object {"results": [...]}.
    """
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"  [warn] LLM judge returned unparseable JSON: {e}", file=sys.stderr)
        print(f"  raw (first 500): {raw[:500]}", file=sys.stderr)
        return [
            FeatureScore(
                id=f["id"], name=f["name"],
                score=0.0, implemented=False,
                reasoning="LLM response parse error",
                evidence=[],
            )
            for f in features
        ]

    # Unwrap {"results": [...]} or {"features": [...]} if model wrapped the array
    if isinstance(parsed, dict):
        for key in ("results", "features", "evaluations", "scores"):
            if isinstance(parsed.get(key), list):
                parsed = parsed[key]
                break
        else:
            # If still a dict, convert values to list if they look like feature items
            vals = list(parsed.values())
            if vals and isinstance(vals[0], dict):
                parsed = vals

    if not isinstance(parsed, list):
        print(f"  [warn] unexpected JSON structure, got {type(parsed)}", file=sys.stderr)
        return [
            FeatureScore(id=f["id"], name=f["name"], score=0.0,
                         implemented=False, reasoning="unexpected JSON structure", evidence=[])
            for f in features
        ]

    by_id = {item["id"]: item for item in parsed if isinstance(item, dict) and "id" in item}
    scores: List[FeatureScore] = []
    for feat in features:
        fid = feat["id"]
        item = by_id.get(fid, {})
        score = float(item.get("score", 0.0))
        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))
        # implemented = substantially present (score >= 0.7 per rubric)
        implemented = score >= 0.7
        scores.append(FeatureScore(
            id=fid,
            name=feat["name"],
            score=score,
            implemented=implemented,
            reasoning=item.get("reasoning", ""),
            evidence=item.get("evidence", []),
        ))
    return scores


def evaluate_features_llm(
    snapshot: ProjectSnapshot,
    features: List[dict],
    model: str = "gpt-4o-mini",
    dotenv_path: Optional[str] = None,
) -> Tuple[List[FeatureScore], float]:
    """
    LLM judge for Feature Completeness.
    The judge explicitly performs the four static-style checks from the paper
    (file detection, import analysis, schema inspection, route checking) but uses
    semantic understanding to handle naming variants the model may have used.
    Returns (feature_scores, cost_usd).
    """
    print(f"  → LLM judge ({model}): building context...", flush=True)
    source_context = _build_source_context(snapshot)
    approx_tokens = len(source_context) // CHARS_PER_TOKEN
    print(f"  → context ~{approx_tokens:,} tokens, calling LLM...", flush=True)

    prompt = _build_judge_prompt(source_context, features)
    raw, cost = _call_openai_judge(prompt, model=model, dotenv_path=dotenv_path)
    print(f"  → LLM judge done. cost ≈ ${cost:.4f}", flush=True)

    scores = _parse_judge_response(raw, features)
    return scores, cost


# ---------------------------------------------------------------------------
# Structural Validity — static checks (unchanged)
# ---------------------------------------------------------------------------

def validate_project_structure(snapshot: ProjectSnapshot) -> Tuple[float, Dict]:
    checks: Dict[str, bool] = {}
    root = snapshot.root

    has_package = (
        (root / "package.json").exists()
        or (root / "frontend" / "package.json").exists()
    )
    has_requirements = (root / "requirements.txt").exists()

    if snapshot.has_python:
        checks["python_requirements"] = has_requirements
        checks["python_source_layout"] = (
            (root / "src").exists()
            or (root / "backend").exists()
            or any(f.endswith(".py") for f in snapshot.rel_files)
        )
    if snapshot.has_js or snapshot.has_ts:
        checks["node_package_manifest"] = has_package
        checks["node_source_layout"] = (
            (root / "src").exists()
            or (root / "frontend").exists()
            or (root / "webapp").exists()
            or (root / "app").exists()          # Next.js app dir
            or (root / "lib").exists()          # ts library layout
        )

    if not checks:
        return 0.0, checks
    passed = sum(1 for ok in checks.values() if ok)
    return passed / len(checks), checks


def syntax_check_python(snapshot: ProjectSnapshot) -> Tuple[float, List[str]]:
    py_files = [r for r in snapshot.rel_files if r.endswith(".py")]
    if not py_files:
        return 1.0, []
    failures: List[str] = []
    for rel in py_files:
        text = snapshot.text_by_relpath.get(rel, "")
        try:
            ast.parse(text, filename=rel)
        except SyntaxError as e:
            failures.append(f"{rel}:{e.lineno}:{e.msg}")
    return max(1.0 - len(failures) / max(len(py_files), 1), 0.0), failures


def python_module_exists(root: Path, module: str) -> bool:
    parts = module.split(".")
    candidate = root.joinpath(*parts)
    return candidate.with_suffix(".py").exists() or (candidate / "__init__.py").exists()


def resolve_local_python_imports(snapshot: ProjectSnapshot) -> Tuple[int, int, List[str]]:
    py_files = [r for r in snapshot.rel_files if r.endswith(".py")]
    if not py_files:
        return 0, 0, []
    top_level_dirs = {Path(r).parts[0] for r in py_files if len(Path(r).parts) > 1}
    unresolved: List[str] = []
    checked = 0
    for rel in py_files:
        text = snapshot.text_by_relpath.get(rel, "")
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in top_level_dirs:
                        checked += 1
                        if not python_module_exists(snapshot.root, alias.name):
                            unresolved.append(f"{rel}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0 or not node.module:
                    continue
                top = node.module.split(".")[0]
                if top in top_level_dirs:
                    checked += 1
                    if not python_module_exists(snapshot.root, node.module):
                        unresolved.append(f"{rel}: from {node.module} import ...")
    return checked, len(unresolved), unresolved[:100]


def js_import_exists(root: Path, base_dir: str, spec: str) -> bool:
    base = root / base_dir
    target = (root / spec.lstrip("/")) if spec.startswith("/") else (base / spec)
    candidates = [
        target,
        target.with_suffix(".js"), target.with_suffix(".jsx"),
        target.with_suffix(".ts"), target.with_suffix(".tsx"),
        target / "index.js", target / "index.jsx",
        target / "index.ts", target / "index.tsx",
    ]
    return any(c.exists() for c in candidates)


def resolve_local_js_imports(snapshot: ProjectSnapshot) -> Tuple[int, int, List[str]]:
    files = [r for r in snapshot.rel_files if r.endswith((".js", ".jsx", ".ts", ".tsx"))]
    unresolved: List[str] = []
    checked = 0
    for rel in files:
        text = snapshot.text_by_relpath.get(rel, "")
        for m in LOCAL_IMPORT_RE.finditer(text):
            spec = m.group(1) or m.group(2)
            if not spec or not (spec.startswith(".") or spec.startswith("/")):
                continue
            checked += 1
            if not js_import_exists(snapshot.root, Path(rel).parent.as_posix(), spec):
                unresolved.append(f"{rel}: {spec}")
    return checked, len(unresolved), unresolved[:100]


def find_executable(name: str) -> Optional[str]:
    from shutil import which
    return which(name)


def find_local_eslint(root: Path) -> Optional[str]:
    candidates = [
        root / "node_modules" / ".bin" / "eslint",
        root / "frontend" / "node_modules" / ".bin" / "eslint",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def count_lint_issues(output: str) -> int:
    return sum(1 for line in output.splitlines() if re.search(r":\d+:\d+:", line))


def approx_loc(snapshot: ProjectSnapshot) -> int:
    return sum(
        sum(1 for line in text.splitlines() if line.strip())
        for rel, text in snapshot.text_by_relpath.items()
        if rel.endswith(tuple(CODE_EXTENSIONS))
    )


def lint_score_from_density(issue_count: int, loc: int) -> float:
    density = issue_count / max(loc / 1000.0, 1.0)
    return max(0.0, 100.0 - density * 12.0)


def run_command(cmd: Sequence, cwd: Path, timeout: int = 180) -> CommandResult:
    proc = subprocess.run(
        cmd, cwd=str(cwd), text=True, capture_output=True, timeout=timeout,
    )
    return CommandResult(
        command=" ".join(str(x) for x in cmd),
        returncode=proc.returncode,
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
    )


def run_lint_checks(snapshot: ProjectSnapshot) -> Tuple[float, Dict]:
    details: Dict = {"lint_tools": [], "issues": 0, "logs": []}
    scores: List[float] = []

    if snapshot.has_python:
        ruff = find_executable("ruff")
        if ruff:
            res = run_command([ruff, "check", str(snapshot.root)], cwd=snapshot.root, timeout=180)
            details["lint_tools"].append("ruff")
            n = count_lint_issues(res.stdout + "\n" + res.stderr)
            details["issues"] = int(details["issues"]) + n
            details["logs"].append({"tool": "ruff", "code": res.returncode})
            scores.append(lint_score_from_density(n, approx_loc(snapshot)))

    if snapshot.has_js or snapshot.has_ts:
        eslint = find_local_eslint(snapshot.root)
        if eslint:
            res = run_command(
                [eslint, ".", "--ext", ".js,.jsx,.ts,.tsx", "--format", "unix"],
                cwd=snapshot.root, timeout=240,
            )
            details["lint_tools"].append("eslint")
            n = count_lint_issues(res.stdout + "\n" + res.stderr)
            details["issues"] = int(details["issues"]) + n
            details["logs"].append({"tool": "eslint", "code": res.returncode})
            scores.append(lint_score_from_density(n, approx_loc(snapshot)))

    if not scores:
        details["lint_tools"] = ["none"]
        return 1.0, details
    return statistics.mean(scores) / 100.0, details


def compute_structural_validity(
    snapshot: ProjectSnapshot,
    cached_lint: Optional[Tuple[float, Dict]] = None,
) -> Tuple[float, Dict]:
    structure_score, structure_checks = validate_project_structure(snapshot)
    py_syntax_score, py_syntax_failures = syntax_check_python(snapshot)

    py_checked, py_unresolved, py_samples = resolve_local_python_imports(snapshot)
    js_checked, js_unresolved, js_samples = resolve_local_js_imports(snapshot)
    total_checked = py_checked + js_checked
    total_unresolved = py_unresolved + js_unresolved
    import_score = (
        max(0.0, 1.0 - total_unresolved / total_checked)
        if total_checked > 0 else 1.0
    )

    if cached_lint is not None:
        lint_score, lint_details = cached_lint
    else:
        lint_score, lint_details = run_lint_checks(snapshot)

    # Dynamic weights: only include py_syntax weight when Python files exist.
    # Prevents pure-TS projects from receiving a free 0.40 credit.
    if snapshot.has_python:
        sv = (
            0.20 * structure_score
            + 0.40 * py_syntax_score
            + 0.30 * import_score
            + 0.10 * lint_score
        )
    else:
        # No Python: redistribute syntax weight to import resolution and structure
        sv = (
            0.30 * structure_score
            + 0.55 * import_score
            + 0.15 * lint_score
        )
    return sv * 100.0, {
        "structure_checks": structure_checks,
        "python_syntax_failures": py_syntax_failures[:50],
        "imports_checked": total_checked,
        "imports_unresolved": total_unresolved,
        "import_unresolved_samples": (py_samples + js_samples)[:50],
        "lint": lint_details,
    }


# ---------------------------------------------------------------------------
# Build Success — static
# ---------------------------------------------------------------------------

def read_package_scripts(pkg_json: Path) -> Dict[str, str]:
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        if isinstance(scripts, dict):
            return {str(k): str(v) for k, v in scripts.items()}
    except Exception:
        pass
    return {}


def run_python_compile(snapshot: ProjectSnapshot) -> CommandResult:
    import py_compile
    py_files = [r for r in snapshot.rel_files if r.endswith(".py")]
    if not py_files:
        return CommandResult("py_compile (no files)", 0, "no python files", "")
    cache_dir = snapshot.root / ".eval_pycache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    errors: List[str] = []
    for rel in py_files:
        src = snapshot.root / rel
        cfile = cache_dir / (rel.replace("/", "__") + "c")
        cfile.parent.mkdir(parents=True, exist_ok=True)
        try:
            py_compile.compile(str(src), cfile=str(cfile), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{rel}: {e.msg}")
        except Exception as e:
            errors.append(f"{rel}: {e}")
    if errors:
        return CommandResult("py_compile", 1, "", "\n".join(errors[:50]))
    return CommandResult("py_compile", 0, f"compiled {len(py_files)} files", "")


def compute_build_success(snapshot: ProjectSnapshot) -> Tuple[bool, Dict]:
    commands: List[CommandResult] = []
    notes: List[str] = []
    root = snapshot.root

    # --- Node / TypeScript ---
    pkg_roots = [root, root / "frontend"]
    ran_node_build = False
    has_node_manifest = False
    has_build_script = False
    has_runtime_script = False   # start / dev / serve without build

    for pkg_dir in pkg_roots:
        pkg_json = pkg_dir / "package.json"
        if not pkg_json.exists():
            continue
        has_node_manifest = True
        scripts = read_package_scripts(pkg_json)
        if "build" in scripts:
            has_build_script = True
            result = run_command(["npm", "run", "build"], cwd=pkg_dir, timeout=360)
            commands.append(result)
            ran_node_build = True
        elif any(s in scripts for s in ("start", "dev", "serve")):
            has_runtime_script = True

    # Node project with no build script but has start/dev (e.g. tsx runtime) → N/A pass
    if (snapshot.has_js or snapshot.has_ts) and has_node_manifest:
        if not ran_node_build:
            if has_runtime_script:
                notes.append(
                    "No `build` script found; project uses runtime execution "
                    "(tsx/ts-node/vite dev). Treating as N/A-pass."
                )
                # Still run python compile if present
            else:
                notes.append("Node project has package.json but no build or start script.")
                return False, {"commands": [], "notes": notes}

    # --- Python ---
    if snapshot.has_python:
        commands.append(run_python_compile(snapshot))

    if not commands:
        return True, {"commands": [], "notes": ["No explicit build command; N/A-pass"]}

    bs = all(c.success for c in commands)
    return bs, {
        "notes": notes,
        "commands": [
            {
                "command": c.command,
                "returncode": c.returncode,
                "stdout_tail": "\n".join(c.stdout.splitlines()[-20:]),
                "stderr_tail": "\n".join(c.stderr.splitlines()[-20:]),
            }
            for c in commands
        ],
    }


# ---------------------------------------------------------------------------
# Code Quality — static
# ---------------------------------------------------------------------------

class ComplexityVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.function_scores: List[int] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_scores.append(self._complexity(node))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_scores.append(self._complexity(node))
        self.generic_visit(node)

    def _complexity(self, func: ast.AST) -> int:
        score = 1
        for node in ast.walk(func):
            if isinstance(node, PY_DECISION_NODES):
                score += 1
        return score


def python_complexities(snapshot: ProjectSnapshot) -> List[int]:
    scores: List[int] = []
    for rel in snapshot.rel_files:
        if not rel.endswith(".py"):
            continue
        text = snapshot.text_by_relpath.get(rel, "")
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            continue
        vis = ComplexityVisitor()
        vis.visit(tree)
        scores.extend(vis.function_scores)
    return scores


def js_complexity_estimate(snapshot: ProjectSnapshot) -> List[int]:
    decision_re = re.compile(r"\b(if|for|while|case|catch|&&|\|\|)\b|\?")
    function_re = re.compile(r"\bfunction\b|=>")
    scores: List[int] = []
    for rel in snapshot.rel_files:
        if not rel.endswith((".js", ".jsx", ".ts", ".tsx")):
            continue
        text = snapshot.text_by_relpath.get(rel, "")
        fn_count = len(function_re.findall(text))
        dec_count = len(decision_re.findall(text))
        if fn_count == 0 and dec_count == 0:
            continue
        scores.append(int(round(1 + dec_count / max(fn_count, 1))))
    return scores


def complexity_score(snapshot: ProjectSnapshot) -> Tuple[float, Dict]:
    values = python_complexities(snapshot) + js_complexity_estimate(snapshot)
    if not values:
        return 100.0, {"avg_complexity": 0.0, "function_count": 0}
    avg = statistics.mean(values)
    if avg <= 4:    score = 100.0
    elif avg <= 7:  score = 85.0
    elif avg <= 10: score = 70.0
    elif avg <= 15: score = 50.0
    else:           score = 30.0
    return score, {"avg_complexity": round(avg, 2), "function_count": len(values)}


def normalize_line(line: str) -> str:
    s = line.strip()
    if not s or s.startswith(("#", "//", "/*", "*")):
        return ""
    return re.sub(r"\s+", " ", s)


def duplication_score(snapshot: ProjectSnapshot, window: int = 6) -> Tuple[float, Dict]:
    windows: Dict[str, List[str]] = {}
    total_windows = 0
    duplicate_windows = 0

    for rel in snapshot.rel_files:
        if not rel.endswith(tuple(CODE_EXTENSIONS)):
            continue
        text = snapshot.text_by_relpath.get(rel, "")
        lines = [normalize_line(x) for x in text.splitlines()]
        lines = [x for x in lines if x]
        if len(lines) < window:
            continue
        for i in range(0, len(lines) - window + 1):
            total_windows += 1
            block = "\n".join(lines[i: i + window])
            windows.setdefault(str(hash(block)), []).append(f"{rel}:{i+1}")

    for occ in windows.values():
        if len(occ) > 1:
            duplicate_windows += len(occ) - 1

    ratio = duplicate_windows / max(total_windows, 1)
    if ratio <= 0.02:   score = 95.0
    elif ratio <= 0.05: score = 85.0
    elif ratio <= 0.10: score = 70.0
    elif ratio <= 0.15: score = 55.0
    else:               score = 35.0
    return score, {
        "duplicate_ratio": round(ratio, 4),
        "duplicate_windows": duplicate_windows,
        "total_windows": total_windows,
    }


def compute_code_quality(
    snapshot: ProjectSnapshot,
    cached_lint: Optional[Tuple[float, Dict]] = None,
) -> Tuple[float, Dict]:
    """Pure-static CQ per paper: ESLint/ruff + cyclomatic complexity + duplication."""
    if cached_lint is not None:
        lint_norm, lint_details = cached_lint
    else:
        lint_norm, lint_details = run_lint_checks(snapshot)
    lint = lint_norm * 100.0
    comp, comp_details = complexity_score(snapshot)
    dup, dup_details = duplication_score(snapshot)
    cq = 0.40 * lint + 0.35 * comp + 0.25 * dup
    return cq, {
        "static_cq": round(cq, 2),
        "lint_score": round(lint, 2),
        "complexity_score": round(comp, 2),
        "duplication_score": round(dup, 2),
        "lint_details": lint_details,
        "complexity_details": comp_details,
        "duplication_details": dup_details,
    }


def _build_cq_judge_prompt(source_context: str) -> str:
    return f"""\
You are a senior software engineer grading the architectural and implementation quality \
of a rental-platform submission. You will score four dimensions that static tools cannot \
measure. Be strict — this is a hard task and most submissions are incomplete demos.

## SCORING DIMENSIONS

1. **architecture** (0–100): Is the codebase well-structured?
   - 90–100: Clear separation of concerns, layered architecture (models/services/API/agents), \
dependency injection, no god objects
   - 70–89: Reasonable structure with some coupling issues
   - 50–69: Mostly flat, some structure but mixed concerns
   - 30–49: Minimal structure, logic scattered across files
   - 0–29: Single file or chaotic layout

2. **error_handling** (0–100): Are failures handled gracefully?
   - 90–100: Try/except with specific errors, meaningful messages, recovery paths, \
no swallowed exceptions
   - 70–89: Most error paths handled, some gaps
   - 50–69: Basic try/catch present but many paths unhandled or silently ignored
   - 30–49: Mostly missing, empty except blocks, or bare `pass`
   - 0–29: No error handling at all

3. **agent_logic_authenticity** (0–100): Are the agents real or fake?
   - 90–100: Agents use LLM API calls with structured prompts, real decision logic that \
varies by context, dynamic proposals based on actual state
   - 70–89: Real LLM integration but logic is partially hardcoded or templated
   - 50–69: Template-based responses or simple rule engine — no LLM, but logic branches \
on real state
   - 30–49: Decisions are hardcoded strings, static proposals, or random values \
(random.randint, Math.random, hardcoded arrays)
   - 0–29: No agent logic at all — just UI labels or empty functions

4. **production_readiness** (0–100): Could this run in production?
   - 90–100: Real database, environment config, authentication, input validation, \
logging, graceful startup
   - 70–89: Most production concerns addressed, one or two gaps
   - 50–69: Works as a demo but missing several production requirements
   - 30–49: Proof of concept only — hardcoded credentials, no auth, in-memory state
   - 0–29: Barely runnable prototype

## CODEBASE
{source_context}

## OUTPUT FORMAT
Return ONLY a valid JSON object — no markdown fences, no extra text:
{{
  "architecture": <0-100>,
  "error_handling": <0-100>,
  "agent_logic_authenticity": <0-100>,
  "production_readiness": <0-100>,
  "architecture_reasoning": "<2 sentences>",
  "error_handling_reasoning": "<2 sentences>",
  "agent_logic_reasoning": "<2 sentences>",
  "production_readiness_reasoning": "<2 sentences>"
}}
"""


def compute_code_quality_hybrid(
    snapshot: ProjectSnapshot,
    model: str = "gpt-4o-mini",
    dotenv_path: Optional[str] = None,
) -> Tuple[float, Dict]:
    """
    Hybrid CQ: 60% static (lint + complexity + duplication) + 40% LLM qualitative.
    The LLM evaluates architecture, error handling, agent logic authenticity,
    and production readiness — dimensions that static tools cannot measure.
    """
    # --- Static component (60% of final CQ) ---
    lint_norm, lint_details = run_lint_checks(snapshot)
    lint = lint_norm * 100.0
    comp, comp_details = complexity_score(snapshot)
    dup, dup_details = duplication_score(snapshot)
    static_cq = 0.40 * lint + 0.35 * comp + 0.25 * dup

    # --- LLM component (40% of final CQ) ---
    print(f"  → CQ LLM judge ({model}): evaluating architecture & agent logic...", flush=True)
    source_context = _build_source_context(snapshot)
    prompt = _build_cq_judge_prompt(source_context)
    raw, cost = _call_openai_judge(prompt, model=model, dotenv_path=dotenv_path)
    print(f"  → CQ LLM judge done. cost ≈ ${cost:.4f}", flush=True)

    llm_details: Dict = {}
    llm_cq = 50.0  # fallback if parse fails
    try:
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
        data = json.loads(cleaned)
        arch = float(data.get("architecture", 50))
        err  = float(data.get("error_handling", 50))
        agent = float(data.get("agent_logic_authenticity", 50))
        prod = float(data.get("production_readiness", 50))
        # Equal weight across the four LLM dimensions
        llm_cq = (arch + err + agent + prod) / 4.0
        llm_details = {
            "architecture":            round(arch, 1),
            "error_handling":          round(err, 1),
            "agent_logic_authenticity": round(agent, 1),
            "production_readiness":    round(prod, 1),
            "architecture_reasoning":  data.get("architecture_reasoning", ""),
            "error_handling_reasoning": data.get("error_handling_reasoning", ""),
            "agent_logic_reasoning":   data.get("agent_logic_reasoning", ""),
            "production_readiness_reasoning": data.get("production_readiness_reasoning", ""),
        }
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"  [warn] CQ LLM parse error: {e}", file=sys.stderr)
        llm_details = {"parse_error": str(e), "raw": raw[:300]}

    # --- Combined ---
    cq = 0.60 * static_cq + 0.40 * llm_cq
    return round(cq, 2), {
        "static_cq": round(static_cq, 2),
        "llm_cq": round(llm_cq, 2),
        "combined_cq": round(cq, 2),
        "static_details": {
            "lint_score": round(lint, 2),
            "complexity_score": round(comp, 2),
            "duplication_score": round(dup, 2),
            "lint_details": lint_details,
            "complexity_details": comp_details,
            "duplication_details": dup_details,
        },
        "llm_details": llm_details,
        "llm_cost_usd": round(cost, 5),
    }


# ---------------------------------------------------------------------------
# Top-level evaluation
# ---------------------------------------------------------------------------

def evaluate_project(
    root: Path,
    features: List[dict],
    llm_model: str = "gpt-4o-mini",
    dotenv_path: Optional[str] = None,
) -> ProjectResult:
    snapshot = build_snapshot(root)

    # Run lint ONCE and share result across SV and CQ (avoids double execution)
    cached_lint = run_lint_checks(snapshot)

    # Feature Completeness — LLM judge performing structured static-style checks
    # (file detection + import analysis + schema inspection + route checking)
    feature_scores, fc_cost = evaluate_features_llm(
        snapshot, features, model=llm_model, dotenv_path=dotenv_path
    )
    # FC = mean of continuous scores * 100 (preserves gradient, no cliff at 0.7)
    fc = statistics.mean(f.score for f in feature_scores) * 100.0

    # Structural Validity — static, reuses cached lint
    sv, sv_details = compute_structural_validity(snapshot, cached_lint=cached_lint)

    # Build Success — static
    bs, bs_details = compute_build_success(snapshot)

    # Code Quality — pure static per paper (ESLint/ruff + complexity + duplication)
    cq, cq_details = compute_code_quality(snapshot, cached_lint=cached_lint)

    return ProjectResult(
        project=str(root),
        fc=round(fc, 2),
        sv=round(sv, 2),
        bs=bool(bs),
        cq=round(cq, 2),
        feature_breakdown=feature_scores,
        structural_details=sv_details,
        build_details=bs_details,
        quality_details=cq_details,
        llm_judge_model=llm_model,
        llm_judge_cost_usd=round(fc_cost, 5),
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def write_reports(results: List[ProjectResult], output_dir: Path) -> Tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "evaluation_report.json"
    md_path = output_dir / "evaluation_report.md"

    json_payload = {
        "projects": [
            {
                "project": r.project,
                "metrics": {
                    "FC_percent": r.fc,
                    "SV_percent": r.sv,
                    "BS": r.bs,
                    "CQ_score": r.cq,
                    "llm_judge_model": r.llm_judge_model,
                    "llm_judge_cost_usd": r.llm_judge_cost_usd,
                },
                "features": [
                    {
                        "id": f.id,
                        "name": f.name,
                        "score": round(f.score, 3),
                        "implemented": f.implemented,
                        "reasoning": f.reasoning,
                        "evidence": f.evidence,
                    }
                    for f in r.feature_breakdown
                ],
                "structural_details": r.structural_details,
                "build_details": r.build_details,
                "quality_details": r.quality_details,
            }
            for r in results
        ]
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines: List[str] = ["# Evaluation Report", ""]
    lines.append("| Project | FC (%) | SV (%) | BS | CQ | Lint | Complexity | Duplication | Cost |")
    lines.append("|---|---:|---:|:---:|---:|---:|---:|---:|---:|")
    for r in results:
        name = Path(r.project).name
        lint_s   = r.quality_details.get("lint_score", "-")
        comp_s   = r.quality_details.get("complexity_score", "-")
        dup_s    = r.quality_details.get("duplication_score", "-")
        def _fmt(v: object) -> str:
            return f"{v:.1f}" if isinstance(v, float) else str(v)
        lines.append(
            f"| `{name}` | {r.fc:.2f} | {r.sv:.2f} | "
            f"{'PASS' if r.bs else 'FAIL'} | {r.cq:.2f} | "
            f"{_fmt(lint_s)} | {_fmt(comp_s)} | {_fmt(dup_s)} | "
            f"${r.llm_judge_cost_usd:.4f} |"
        )
    lines.append("")
    lines.append("## Feature Breakdown")
    for r in results:
        name = Path(r.project).name
        lines.extend(["", f"### `{name}`", ""])
        lines.append("| Feature | Impl | Score | Reasoning |")
        lines.append("|---|:---:|---:|---|")
        for f in r.feature_breakdown:
            impl = "Y" if f.implemented else "N"
            reasoning = f.reasoning.replace("|", "\\|")[:120]
            lines.append(f"| {f.name} | {impl} | {f.score:.1f} | {reasoning} |")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Sequence) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score rental-platform projects. "
            "FC: LLM judge performing structured static-style checks (file/import/schema/route). "
            "SV/BS/CQ: purely static analysis."
        )
    )
    parser.add_argument("--projects", nargs="+", required=True,
                        help="Paths to project roots.")
    parser.add_argument("--checklist",
                        default=str(Path(__file__).with_name("feature_checklist.json")),
                        help="Path to feature checklist JSON.")
    parser.add_argument("--output-dir",
                        default=str(Path(__file__).with_name("reports")),
                        help="Output directory for reports.")
    parser.add_argument("--llm-model", default="gpt-4o-mini",
                        help="OpenAI model for FC LLM judge (default: gpt-4o-mini).")
    parser.add_argument("--dotenv",
                        default=str(Path(__file__).parent / "MassGen" / ".env"),
                        help="Path to .env file containing OPENAI_API_KEY.")
    return parser.parse_args(argv)


def main(argv: Sequence) -> int:
    args = parse_args(argv)
    checklist_path = Path(args.checklist).resolve()
    output_dir = Path(args.output_dir).resolve()
    dotenv_path = args.dotenv if Path(args.dotenv).exists() else None

    if not checklist_path.exists():
        print(f"Checklist not found: {checklist_path}", file=sys.stderr)
        return 2
    features = json.loads(checklist_path.read_text(encoding="utf-8"))
    if not isinstance(features, list):
        print("Checklist must be a JSON array.", file=sys.stderr)
        return 2

    results: List[ProjectResult] = []
    total_cost = 0.0
    for p in args.projects:
        root = Path(p).resolve()
        if not root.exists() or not root.is_dir():
            print(f"Skipping invalid path: {root}", file=sys.stderr)
            continue
        print(f"\nEvaluating: {root.name}")
        result = evaluate_project(
            root, features,
            llm_model=args.llm_model,
            dotenv_path=dotenv_path,
        )
        results.append(result)
        total_cost += result.llm_judge_cost_usd

    if not results:
        print("No valid projects evaluated.", file=sys.stderr)
        return 2

    json_path, md_path = write_reports(results, output_dir)
    print(f"\nSaved JSON: {json_path}")
    print(f"Saved MD:   {md_path}")
    print(f"\nSummary (total LLM cost ≈ ${total_cost:.4f}):")
    for r in results:
        name = Path(r.project).name
        print(
            f"  {name:20s}  FC={r.fc:.1f}%  SV={r.sv:.1f}%  "
            f"BS={'PASS' if r.bs else 'FAIL'}  CQ={r.cq:.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
