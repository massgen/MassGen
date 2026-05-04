from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import yaml

README_TEMPLATES = {
    "python": "# {name}\n\nA Python project hosted on GitVault.\n",
    "default": "# {name}\n\nBuilt with GitVault.\n",
}

LICENSE_TEMPLATES = {
    "mit": "MIT License\n\nCopyright (c) {year} {owner}\n",
    "apache-2.0": "Apache License 2.0\n",
}

GITIGNORE_TEMPLATES = {
    "python": "__pycache__/\n.venv/\n*.pyc\n",
    "node": "node_modules/\ndist/\n",
    "default": ".DS_Store\n",
}


def run_git(repo_path: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_path,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class GitService:
    def __init__(self, repos_dir: Path):
        self.repos_dir = repos_dir
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def repo_path(self, owner_slug: str, repo_slug: str) -> Path:
        return self.repos_dir / owner_slug / repo_slug

    def init_repo(
        self,
        owner_slug: str,
        repo_name: str,
        description: str,
        readme_template: str,
        license_template: str,
        gitignore_template: str,
    ) -> Path:
        path = self.repo_path(owner_slug, repo_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.mkdir(parents=True, exist_ok=True)
        run_git(path, "init", "-b", "main")
        (path / ".github").mkdir(exist_ok=True)
        (path / ".github" / "PULL_REQUEST_TEMPLATE.md").write_text("## Summary\n\n- Describe your change\n", encoding="utf-8")
        (path / "CODEOWNERS").write_text("* @maintainers\n", encoding="utf-8")
        readme = README_TEMPLATES.get(readme_template, README_TEMPLATES["default"]).format(name=repo_name)
        (path / "README.md").write_text(readme + f"\n{description}\n", encoding="utf-8")
        (path / ".gitignore").write_text(GITIGNORE_TEMPLATES.get(gitignore_template, GITIGNORE_TEMPLATES["default"]), encoding="utf-8")
        if license_template:
            (path / "LICENSE").write_text(LICENSE_TEMPLATES.get(license_template, LICENSE_TEMPLATES["mit"]).format(year=2026, owner=owner_slug), encoding="utf-8")
        self._commit_all(path, "Initial scaffold commit")
        return path

    def _commit_all(self, path: Path, message: str, author_name: str = "GitVault", author_email: str = "system@gitvault.local") -> None:
        run_git(path, "add", ".")
        subprocess.run(
            ["git", "-c", f"user.name={author_name}", "-c", f"user.email={author_email}", "commit", "-m", message],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        )

    def create_branch(self, path: Path, branch_name: str, from_ref: str = "main") -> None:
        run_git(path, "branch", branch_name, from_ref)

    def list_branches(self, path: Path) -> list[str]:
        return [line.strip().lstrip("*").strip() for line in run_git(path, "branch", "--list").splitlines() if line.strip()]

    def list_tags(self, path: Path) -> list[str]:
        output = run_git(path, "tag", "--list")
        return [line.strip() for line in output.splitlines() if line.strip()]

    def create_tag(self, path: Path, tag_name: str, message: str) -> None:
        run_git(path, "tag", "-a", tag_name, "-m", message)

    def get_tree(self, path: Path, ref: str, subpath: str = "") -> list[dict[str, str]]:
        target = f"{ref}:{subpath}" if subpath else ref
        output = run_git(path, "ls-tree", target)
        entries = []
        for line in output.splitlines():
            meta, name = line.split("\t", 1)
            _, kind, sha = meta.split()
            entries.append({"kind": kind, "sha": sha, "name": name})
        return entries

    def get_file(self, path: Path, ref: str, file_path: str) -> str:
        return run_git(path, "show", f"{ref}:{file_path}")

    def commit_file(self, path: Path, branch: str, file_path: str, content: str, message: str, author_name: str, author_email: str) -> None:
        run_git(path, "checkout", branch)
        target = path / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self._commit_all(path, message, author_name=author_name, author_email=author_email)
        run_git(path, "checkout", "main")

    def history_for_path(self, path: Path, ref: str, file_path: str) -> list[dict[str, str]]:
        output = run_git(path, "log", "--pretty=format:%H|%an|%ad|%s", ref, "--", file_path)
        items = []
        for line in output.splitlines():
            sha, author, date, subject = line.split("|", 3)
            items.append({"sha": sha, "author": author, "date": date, "subject": subject})
        return items

    def blame(self, path: Path, ref: str, file_path: str) -> list[str]:
        output = run_git(path, "blame", ref, "--", file_path)
        return output.splitlines()

    def commit_history(self, path: Path, limit: int = 30) -> list[dict[str, str]]:
        output = run_git(path, "log", f"--max-count={limit}", "--pretty=format:%H|%an|%ad|%s")
        items = []
        for line in output.splitlines():
            sha, author, date, subject = line.split("|", 3)
            items.append({"sha": sha, "author": author, "date": date, "subject": subject})
        return items

    def compare(self, path: Path, base: str, head: str) -> str:
        return run_git(path, "diff", f"{base}..{head}")

    def changed_files(self, path: Path, base: str, head: str) -> list[str]:
        output = run_git(path, "diff", "--name-only", f"{base}..{head}")
        return [line.strip() for line in output.splitlines() if line.strip()]

    def required_codeowners(self, path: Path, base: str, head: str, codeowners_ref: str = "main") -> set[str]:
        try:
            codeowners = self.get_file(path, codeowners_ref, "CODEOWNERS")
        except subprocess.CalledProcessError:
            return set()
        changed = self.changed_files(path, base, head)
        owners: set[str] = set()
        rules: list[tuple[str, list[str]]] = []
        for raw_line in codeowners.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            pattern = parts[0]
            rule_owners = [part.lstrip("@") for part in parts[1:] if part.startswith("@")]
            rules.append((pattern, rule_owners))
        for file_path in changed:
            matched: list[str] = []
            for pattern, rule_owners in rules:
                normalized = pattern.lstrip("/")
                if pattern == "*" or fnmatch(file_path, normalized) or fnmatch(Path(file_path).name, normalized):
                    matched = rule_owners
            owners.update(matched)
        return owners

    def merge_conflicts(self, path: Path, source: str, target: str) -> bool:
        with tempfile.TemporaryDirectory() as tmpdir:
            clone = Path(tmpdir) / "clone"
            subprocess.run(["git", "clone", "--no-single-branch", str(path), str(clone)], check=True, capture_output=True, text=True)
            subprocess.run(["git", "checkout", target], cwd=clone, check=True, capture_output=True, text=True)
            verify = subprocess.run(["git", "rev-parse", "--verify", source], cwd=clone, capture_output=True, text=True)
            source_ref = source if verify.returncode == 0 else f"origin/{source}"
            result = subprocess.run(["git", "merge", "--no-commit", "--no-ff", source_ref], cwd=clone, capture_output=True, text=True)
            return result.returncode != 0

    def merge_pr(self, path: Path, source: str, target: str, strategy: str) -> None:
        run_git(path, "checkout", target)
        if strategy == "squash":
            run_git(path, "merge", "--squash", source)
            self._commit_all(path, f"Squash merge {source} into {target}")
        elif strategy == "rebase":
            run_git(path, "checkout", source)
            run_git(path, "rebase", target)
            run_git(path, "checkout", target)
            run_git(path, "merge", "--ff-only", source)
        else:
            run_git(path, "merge", "--no-ff", source, "-m", f"Merge branch '{source}' into {target}")
        run_git(path, "checkout", "main")

    def archive_zip(self, path: Path, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            export = Path(tmpdir) / "export"
            shutil.copytree(path, export, ignore=shutil.ignore_patterns(".git"))
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
                for file in export.rglob("*"):
                    if file.is_file():
                        zf.write(file, arcname=file.relative_to(export))
        return destination

    def fork_repo(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", str(source), str(destination)], check=True, capture_output=True, text=True)

    def delete_repo(self, path: Path) -> None:
        shutil.rmtree(path, ignore_errors=True)

    def insights(self, path: Path) -> dict[str, Any]:
        languages = Counter()
        dependencies: list[str] = []
        files = []
        for root, _, filenames in os.walk(path):
            if ".git" in root.split(os.sep):
                continue
            for name in filenames:
                file = Path(root) / name
                rel = file.relative_to(path)
                files.append(str(rel))
                suffix = file.suffix.lower() or "[no extension]"
                languages[suffix] += len(file.read_text(encoding="utf-8", errors="ignore"))
                if name in {"package.json", "requirements.txt", "pyproject.toml", "pom.xml"}:
                    dependencies.append(str(rel))
        contributors_output = run_git(path, "shortlog", "-sne", "HEAD")
        contributors = [line.strip() for line in contributors_output.splitlines() if line.strip()]
        return {
            "languages": dict(languages.most_common()),
            "dependencies": dependencies,
            "contributors": contributors,
            "files": files,
        }

    def parse_workflows(self, path: Path) -> list[dict[str, Any]]:
        workflows_dir = path / ".github" / "workflows"
        if not workflows_dir.exists():
            return []
        workflows = []
        for file in workflows_dir.glob("*.y*ml"):
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
            workflows.append(
                {
                    "name": data.get("name", file.stem),
                    "on": data.get("on", {}),
                    "jobs": list((data.get("jobs") or {}).keys()),
                    "steps": [
                        step.get("run", step.get("uses", "step"))
                        for job in (data.get("jobs") or {}).values()
                        for step in (job.get("steps") or [])
                    ],
                }
            )
        return workflows

    def pages_content(self, path: Path) -> str:
        for candidate in [path / "docs" / "index.md", path / "docs" / "index.html", path / "README.md"]:
            if candidate.exists():
                return candidate.read_text(encoding="utf-8", errors="ignore")
        return "No Pages site configured yet."
