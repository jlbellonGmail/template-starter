"""Regresion de compatibilidad para el contexto de producto (Cambios 1-12):

- Un bloque `Referencias:` opcional debajo de un item de ROADMAP.md no
  debe alterar la deteccion de estado (`Pending`/`Ready`/`Done`).
- La ausencia de `docs/producto/contexto-producto.md` no debe romper
  `Assert-FeatureContract` (repos legacy o este mismo template).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "scripts" / "workunit-lib.ps1"
CONTRACT = ROOT / "scripts" / "feature-contract.ps1"
UPDATE_INDEXES = ROOT / "scripts" / "update-doc-indexes.ps1"
START_MARKER = "<!-- FEATURE_LINKS_START -->"
END_MARKER = "<!-- FEATURE_LINKS_END -->"


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


def run_file(script: Path, args: list[str], cwd: Path):
    return subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def dot_source(cwd: Path, tail: str):
    return run_ps(f". '{LIB}'; {tail}", cwd)


def git(repo: Path, *args: str, check: bool = True):
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "NUL" if os.name == "nt" else "/dev/null"
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        env=env,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr + result.stdout)
    return result


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


def verdict_block(status: str = "approved", attempt: int = 1) -> str:
    return (
        "```yaml\n"
        f"status: {status}\n"
        f"attempt: {attempt}\n"
        "feedback:\n"
        "  - ok\n"
        "```\n"
    )


def make_passing_repo(tmp_path: Path, slug: str = "99-demo-feature", title: str = "Demo feature"):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "checkout", "-b", f"feature/{slug}")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Tests")

    doc_slug = slug.split("-", 1)[1]
    for path in [repo / "runs" / slug, repo / "docs" / "tecnica", repo / "docs" / "usuario"]:
        path.mkdir(parents=True, exist_ok=True)

    (repo / "runs" / slug / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (repo / "runs" / slug / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "runs" / slug / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
    (repo / "runs" / slug / "audit-1.md").write_text(verdict_block(), encoding="utf-8")
    (repo / "runs" / slug / "test-report-1.md").write_text(verdict_block(), encoding="utf-8")
    (repo / "runs" / slug / "code-review-1.md").write_text(verdict_block(), encoding="utf-8")
    (repo / "docs" / "tecnica" / f"{doc_slug}.md").write_text("# Tecnica\n", encoding="utf-8")
    (repo / "docs" / "usuario" / f"{doc_slug}.md").write_text("# Usuario\n", encoding="utf-8")
    (repo / "docs" / "tecnica" / "index.md").write_text(index_template("Tecnica"), encoding="utf-8")
    (repo / "docs" / "usuario" / "index.md").write_text(index_template("Usuario"), encoding="utf-8")
    (repo / "ROADMAP.md").write_text(f"- [ ] {slug} - Demo\n", encoding="utf-8")

    run_ps(
        f". '{CONTRACT}'; "
        f"New-DecisionFile -Slug '{slug}' -Title '{title}' "
        "-Decisions @('Decision demostrable')",
        repo,
    )
    result = run_file(UPDATE_INDEXES, [slug, title], repo)
    assert result.returncode == 0, result.stderr
    return repo, slug, title


def assert_contract(repo: Path, slug: str, title: str):
    command = f". '{CONTRACT}'; Assert-FeatureContract -Slug '{slug}' -Title '{title}'"
    return run_ps(command, repo)


# --------------------------------------------------------------------------
# docs/producto/contexto-producto.md es opcional para el contrato
# --------------------------------------------------------------------------


def test_contract_passes_without_docs_producto_directory(tmp_path: Path):
    repo, slug, title = make_passing_repo(tmp_path)
    assert not (repo / "docs" / "producto").exists()

    result = assert_contract(repo, slug, title)

    assert result.returncode == 0, result.stderr


def test_contract_still_passes_when_docs_producto_exists(tmp_path: Path):
    repo, slug, title = make_passing_repo(tmp_path)
    producto_dir = repo / "docs" / "producto"
    producto_dir.mkdir(parents=True)
    (producto_dir / "contexto-producto.md").write_text(
        "# Contexto de producto\n\nPor definir.\n", encoding="utf-8"
    )

    result = assert_contract(repo, slug, title)

    assert result.returncode == 0, result.stderr


# --------------------------------------------------------------------------
# Bloque `Referencias:` opcional en ROADMAP.md no rompe la deteccion de
# estado de un item (Cambio 7/8).
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("marker", "expected_state"),
    [
        ("[ ]", "Pending"),
        ("[-]", "Ready"),
        ("[x]", "Done"),
    ],
)
def test_roadmap_item_state_ignores_trailing_referencias_block(tmp_path, marker, expected_state):
    content = (
        f"- {marker} 15-accesibilidad-ux-mobile - Descripcion corta y verificable.\n"
        "\n"
        "      Referencias:\n"
        "      - docs/tecnica/algo-relacionado.md\n"
        "      - docs/usuario/algo-relacionado.md\n"
        "\n"
        "- [ ] 16-otro-item - Otra descripcion.\n"
    )
    (tmp_path / "r.md").write_text(content, encoding="utf-8")
    result = dot_source(
        tmp_path,
        "$c = Get-Content r.md -Raw; "
        "Get-RoadmapItemStateName -Content $c -ItemSlug '15-accesibilidad-ux-mobile'",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == expected_state


def test_roadmap_item_state_of_following_item_unaffected_by_referencias_block(tmp_path):
    content = (
        "- [ ] 15-accesibilidad-ux-mobile - Descripcion corta y verificable.\n"
        "\n"
        "      Referencias:\n"
        "      - docs/tecnica/algo-relacionado.md\n"
        "\n"
        "- [-] 16-otro-item - Otra descripcion.\n"
    )
    (tmp_path / "r.md").write_text(content, encoding="utf-8")
    result = dot_source(
        tmp_path,
        "$c = Get-Content r.md -Raw; "
        "Get-RoadmapItemStateName -Content $c -ItemSlug '16-otro-item'",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Ready"


def test_roadmap_transition_with_referencias_block_still_succeeds(tmp_path):
    content = (
        "- [ ] 15-accesibilidad-ux-mobile - Descripcion corta y verificable.\n"
        "\n"
        "      Referencias:\n"
        "      - docs/tecnica/algo-relacionado.md\n"
    )
    result = dot_source(
        tmp_path,
        f"Assert-RoadmapItemsTransition -Content '{content}' -Items @('15-accesibilidad-ux-mobile') "
        "-FromStates @('Pending') -ToState 'Ready'; Write-Host DONE",
    )
    assert result.returncode == 0, result.stderr
    assert "DONE" in result.stdout
