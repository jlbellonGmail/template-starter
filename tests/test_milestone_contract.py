import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "feature-contract.ps1"

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
WHITESPACE_RE = re.compile(r"\s+")


def plain_output(output: str) -> str:
    # pwsh en Linux envuelve mensajes de error largos al ancho de terminal
    # e inserta un marcador "|" al inicio de cada linea continuada (el
    # "gutter" del formateador de errores). Se quita antes de colapsar
    # espacios para que el mensaje quede como una sola frase comparable.
    without_ansi = ANSI_ESCAPE_RE.sub("", output)
    without_pipes = without_ansi.replace("|", " ")
    return WHITESPACE_RE.sub(" ", without_pipes).strip()


START_MARKER = "<!-- FEATURE_LINKS_START -->"
END_MARKER = "<!-- FEATURE_LINKS_END -->"


def index_template(label: str) -> str:
    return f"""---
hide:
  - navigation
  - toc
---

<section class="page-hero page-hero--{label.lower()}">
  <div class="page-hero__content">Hero {label}</div>
</section>

<section class="documentation-directory" markdown="1">
  <div class="documentation-directory__header">
    <h2>{label}</h2>
    <p>Texto externo</p>
  </div>

  <div class="documentation-directory__grid" markdown="1">

{START_MARKER}

{END_MARKER}

  </div>
</section>
"""


def powershell() -> str:
    candidates = ["powershell.exe", "pwsh"] if os.name == "nt" else ["pwsh", "powershell"]
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    pytest.skip("PowerShell no esta disponible")


def run_ps(command: str, cwd: Path):
    return subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


ITEMS = ["02-item-a", "03-item-b"]


def verdict_block(status: str = "approved", attempt: int = 1) -> str:
    return (
        "```yaml\n"
        f"status: {status}\n"
        f"attempt: {attempt}\n"
        "feedback:\n"
        "  - ok\n"
        "```\n"
    )


def make_milestone_repo(tmp_path: Path, slug: str = "mi-milestone", items: list[str] = None):
    items = items if items is not None else ITEMS
    repo = tmp_path / "repo"
    run_dir = repo / "runs" / f"milestone-{slug}"
    for path in [run_dir, repo / "docs" / "tecnica", repo / "docs" / "usuario"]:
        path.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schemaVersion": 1,
        "mode": "milestone",
        "slug": slug,
        "items": items,
    }
    (run_dir / "work-unit.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run_dir / "spec.md").write_text("# Spec milestone\n", encoding="utf-8")
    (run_dir / "plan.md").write_text("# Plan milestone\n", encoding="utf-8")
    (run_dir / "tasks.md").write_text("# Tasks milestone\n", encoding="utf-8")
    (run_dir / "audit-1.md").write_text(verdict_block(), encoding="utf-8")
    (run_dir / "test-report-1.md").write_text(verdict_block(), encoding="utf-8")
    (run_dir / "code-review-1.md").write_text(verdict_block(), encoding="utf-8")
    (run_dir / "decision.md").write_text("# Decision\n", encoding="utf-8")

    (repo / "docs" / "tecnica" / "index.md").write_text(index_template("Tecnica"), encoding="utf-8")
    (repo / "docs" / "usuario" / "index.md").write_text(index_template("Usuario"), encoding="utf-8")

    for item in items:
        doc_slug = item.split("-", 1)[1]
        title = " ".join(w.capitalize() for w in doc_slug.split("-"))
        (repo / "docs" / "tecnica" / f"{doc_slug}.md").write_text(f"# {title}\n", encoding="utf-8")
        (repo / "docs" / "usuario" / f"{doc_slug}.md").write_text(f"# {title}\n", encoding="utf-8")
        for section in ["tecnica", "usuario"]:
            index_path = repo / "docs" / section / "index.md"
            content = index_path.read_text(encoding="utf-8")
            content = content.replace(END_MARKER, f"- [{title}]({doc_slug}.md)\n\n{END_MARKER}")
            index_path.write_text(content, encoding="utf-8")

    return repo


def test_milestone_contract_happy_path(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone",
        repo,
    )
    assert result.returncode == 0, result.stderr


def test_milestone_contract_missing_manifest_is_rejected(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    (repo / "runs" / "milestone-mi-milestone" / "work-unit.json").unlink()

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone",
        repo,
    )
    assert result.returncode != 0
    assert "No existe el manifest" in plain_output(result.stderr)


def test_milestone_contract_missing_one_item_tech_doc_is_rejected(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    (repo / "docs" / "tecnica" / "item-b.md").unlink()

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone",
        repo,
    )
    assert result.returncode != 0
    assert "item-b.md" in plain_output(result.stderr)


def test_milestone_contract_missing_decision_is_rejected(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    (repo / "runs" / "milestone-mi-milestone" / "decision.md").unlink()

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone",
        repo,
    )
    assert result.returncode != 0
    assert "decision.md" in plain_output(result.stderr)


def test_milestone_contract_require_ready_roadmap(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    (repo / "ROADMAP.md").write_text(
        "- [-] 02-item-a - Uno\n- [-] 03-item-b - Dos\n", encoding="utf-8"
    )

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone -RequireReadyRoadmap",
        repo,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("missing_name", ["plan.md", "tasks.md"])
def test_milestone_contract_missing_plan_or_tasks_is_rejected(tmp_path: Path, missing_name: str):
    repo = make_milestone_repo(tmp_path)
    (repo / "runs" / "milestone-mi-milestone" / missing_name).unlink()

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone",
        repo,
    )
    assert result.returncode != 0
    assert missing_name in plain_output(result.stderr)


def test_milestone_contract_missing_code_review_is_rejected(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    (repo / "runs" / "milestone-mi-milestone" / "code-review-1.md").unlink()

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone",
        repo,
    )
    assert result.returncode != 0
    assert "code-review" in plain_output(result.stderr)


def test_milestone_contract_uses_real_numeric_order_not_lexicographic(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    run_dir = repo / "runs" / "milestone-mi-milestone"
    (run_dir / "test-report-1.md").unlink()
    (run_dir / "test-report-2.md").write_text(verdict_block("rejected", 2), encoding="utf-8")
    (run_dir / "test-report-10.md").write_text(verdict_block("approved", 10), encoding="utf-8")

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone",
        repo,
    )
    assert result.returncode == 0, result.stderr


def test_milestone_contract_fails_when_latest_real_attempt_is_rejected(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    run_dir = repo / "runs" / "milestone-mi-milestone"
    (run_dir / "test-report-1.md").unlink()
    (run_dir / "test-report-2.md").write_text(verdict_block("approved", 2), encoding="utf-8")
    (run_dir / "test-report-10.md").write_text(verdict_block("rejected", 10), encoding="utf-8")

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone",
        repo,
    )
    assert result.returncode != 0
    assert "test-report-10.md" in plain_output(result.stderr)


def test_milestone_contract_fails_when_yaml_block_is_missing(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    run_dir = repo / "runs" / "milestone-mi-milestone"
    (run_dir / "audit-1.md").write_text("status: approved\nattempt: 1\n", encoding="utf-8")

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone",
        repo,
    )
    assert result.returncode != 0
    output = plain_output(result.stderr)
    assert "audit-1.md" in output
    assert "bloque" in output.lower()


def test_milestone_contract_require_ready_roadmap_fails_if_one_item_pending(tmp_path: Path):
    repo = make_milestone_repo(tmp_path)
    (repo / "ROADMAP.md").write_text(
        "- [-] 02-item-a - Uno\n- [ ] 03-item-b - Dos\n", encoding="utf-8"
    )

    result = run_ps(
        f". '{CONTRACT}'; Assert-WorkUnitContract -Slug 'mi-milestone' -Mode Milestone -RequireReadyRoadmap",
        repo,
    )
    assert result.returncode != 0
    assert "Ningun item fue modificado" in plain_output(result.stderr) or "invalida" in plain_output(result.stderr)
