from __future__ import annotations

import difflib
import io
import zipfile

from .db import Database


class CompileService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def compile_project(self, project_id: str, engine: str, entrypoint: str, trigger: str) -> dict:
        project = self.database.get_project(project_id)
        files = self.database.list_project_files(project_id)
        entry = next((file for file in files if file["path"] == entrypoint), None)
        if entry is None:
            entry = files[0] if files else {"path": entrypoint, "content": ""}
        warnings = lint_latex(entry["content"])
        project_dir = self.database.artifact_root / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        job_name = f"{engine}_{entrypoint.replace('/', '_').replace('.', '_')}"
        pdf_path = project_dir / f"{job_name}.pdf"
        pdf_path.write_bytes(render_simple_pdf(project["name"], entry["content"]))
        log = "\n".join(
            [
                f"[worker] trigger={trigger}",
                f"[engine] {engine} {entrypoint}",
                f"[files] {len(files)} tracked files",
                "[status] completed simulated compile pipeline",
                "[note] swap CompileService with Dockerized TeX Live worker for real engine execution",
                "[lint] " + ("; ".join(warnings) if warnings else "No major issues detected"),
            ]
        )
        return self.database.create_compile_job(project_id, engine, entrypoint, trigger, log, str(pdf_path))

    def export_project_zip(self, project_id: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            project = self.database.get_project(project_id)
            archive.writestr("README.txt", f"Export bundle for {project['name']}\n")
            for file in self.database.list_project_files(project_id):
                archive.writestr(file["path"], file["content"])
            for share in self.database.list_share_links(project_id):
                archive.writestr("sharing/share-links.json", f"{share}\n")
        return buffer.getvalue()


def lint_latex(content: str) -> list[str]:
    warnings: list[str] = []
    if content.count("\\begin{") != content.count("\\end{"):
        warnings.append("Environment counts appear unbalanced")
    if "\\cite{" in content and "refs.bib" not in content:
        warnings.append("Remember to keep bibliography entries in refs.bib")
    if "\\ref{" in content and "\\label{" not in content:
        warnings.append("Reference detected without nearby label definition")
    if len(content.strip()) < 20:
        warnings.append("Document is very short; consider expanding sections")
    return warnings


def render_simple_pdf(title: str, body: str) -> bytes:
    clean_lines = [title, "TexForge preview"] + body.splitlines()[:20]
    text = " ".join(line.replace("(", "[").replace(")", "]") for line in clean_lines)
    stream = f"BT /F1 12 Tf 50 760 Td ({text}) Tj ET"
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj\n".encode(),
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
    ]
    pdf = io.BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(pdf.tell())
        pdf.write(obj)
    xref_start = pdf.tell()
    pdf.write(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.write(f"{offset:010d} 00000 n \n".encode())
    pdf.write(f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode())
    return pdf.getvalue()


def build_diff(source: str, target: str) -> str:
    diff = difflib.unified_diff(source.splitlines(), target.splitlines(), fromfile="from", tofile="to", lineterm="")
    return "\n".join(diff)


def ai_assist(prompt: str, mode: str) -> dict[str, str]:
    prompt_lower = prompt.lower()
    if "table" in prompt_lower:
        suggestion = (
            "\\begin{table}[t]\n"
            "\\centering\n"
            "\\begin{tabular}{lcc}\n"
            "Model & Accuracy & F1 \\\\ \n"
            "\\hline\n"
            "Baseline & 0.91 & 0.89 \\\\ \n"
            "TexForge & 0.95 & 0.94 \\\\ \n"
            "\\end{tabular}\n"
            "\\caption{Experiment results.}\n"
            "\\end{table}\n"
        )
    elif "citation" in prompt_lower or "doi" in prompt_lower:
        suggestion = "@article{newref2026, title={Generated citation scaffold}, author={Author, Example}, year={2026}}"
    elif mode == "fix":
        suggestion = "Try adding missing \\end{...} statements, a \\bibliography section, and labels for every referenced figure or section."
    else:
        suggestion = "\\section{Generated Draft}\nThis paragraph was generated from your prompt and can be refined collaboratively."
    summary = "TexForge Copilot generated a deterministic offline suggestion suitable for local demo use."
    return {"suggestion": suggestion, "summary": summary}
