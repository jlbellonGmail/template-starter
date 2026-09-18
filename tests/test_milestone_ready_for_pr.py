import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READY_FOR_PR = ROOT / "scripts" / "ready-for-pr.ps1"
START_MARKER = "<!-- FEATURE_LINKS_START -->"
END_MARKER = "<!-- FEATURE_LINKS_END -->"

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


SLUG = "mi-milestone"
ITEMS = ["02-item-a", "03-item-b"]
BRANCH = f"milestone/{SLUG}"


def index_template(label: str) -> str:
    return f"""---
hide:
  - navigation
---

<section markdown="1">

{START_MARKER}

{END_MARKER}

</section>
"""


def powershell() -> str:
    candidates = ["powershell.exe", "pwsh"] if os.name == "nt" else ["pwsh", "powershell"]
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    pytest.skip("PowerShell no esta disponible")


def command_env(extra_path: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "NUL" if os.name == "nt" else "/dev/null"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if extra_path:
        env["PATH"] = str(extra_path) + os.pathsep + env["PATH"]
    return env


def git(repo: Path, *args: str, check: bool = True):
    result = subprocess.run(
        ["git", *args], cwd=repo, text=True, capture_output=True, check=False, env=command_env()
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr + result.stdout)
    return result


def run_file(args: list[str], cwd: Path, env: dict[str, str]):
    return subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(READY_FOR_PR), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def make_fake_gh(bin_dir: Path, mode: str = "missing_then_create") -> None:
    bin_dir.mkdir(exist_ok=True)
    if os.name == "nt":
        gh = bin_dir / "gh.cmd"
        gh.write_text(
            "@echo off\n"
            "echo %* | findstr /C:\"pr view\" >nul && (echo no pull requests found 1>&2 & exit /b 1)\n"
            "echo https://example.test/pull/321\n",
            encoding="utf-8",
        )
        pwsh = bin_dir / "pwsh.cmd"
        pwsh.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
    else:
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in *'pr view'*) echo 'no pull requests found' >&2; exit 1;; esac\n"
            "echo 'https://example.test/pull/321'\n",
            encoding="utf-8",
        )
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        pwsh = bin_dir / "pwsh"
        pwsh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        pwsh.chmod(pwsh.stat().st_mode | stat.S_IXUSR)


def make_milestone_repo(tmp_path: Path, roadmap_lines: list[str], items: list[str] = None) -> Path:
    items = items if items is not None else ITEMS
    repo = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], cwd=tmp_path, check=True)
    subprocess.run(["git", "init", str(repo)], cwd=tmp_path, check=True)
    git(repo, "checkout", "-b", "develop")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Tests")
    (repo / "ROADMAP.md").write_text("\n".join(roadmap_lines) + "\n", encoding="utf-8")
    git(repo, "add", "ROADMAP.md")
    git(repo, "commit", "-m", "roadmap inicial")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "develop")
    git(repo, "checkout", "-b", BRANCH)

    run_dir = repo / "runs" / f"milestone-{SLUG}"
    for path in [run_dir, repo / "docs" / "tecnica", repo / "docs" / "usuario"]:
        path.mkdir(parents=True, exist_ok=True)

    manifest = {"schemaVersion": 1, "mode": "milestone", "slug": SLUG, "items": items}
    (run_dir / "work-unit.json").write_text(json.dumps(manifest), encoding="utf-8")
    verdict = "```yaml\nstatus: approved\nattempt: 1\nfeedback:\n  - ok\n```\n"
    (run_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (run_dir / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (run_dir / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
    (run_dir / "audit-1.md").write_text(verdict, encoding="utf-8")
    (run_dir / "test-report-1.md").write_text(verdict, encoding="utf-8")
    (run_dir / "code-review-1.md").write_text(verdict, encoding="utf-8")
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

    git(repo, "add", ".")
    git(repo, "commit", "-m", "milestone en progreso")
    return repo


def test_milestone_ready_for_pr_transitions_all_items_atomically(tmp_path: Path):
    repo = make_milestone_repo(tmp_path, [f"- [ ] {item} - Item" for item in ITEMS])
    bin_dir = tmp_path / "bin"
    make_fake_gh(bin_dir)
    env = command_env(bin_dir)

    result = run_file(["-Mode", "Milestone", "-Slug", SLUG], repo, env)

    assert result.returncode == 0, result.stdout + result.stderr
    roadmap = (repo / "ROADMAP.md").read_text(encoding="utf-8")
    for item in ITEMS:
        assert f"- [-] {item}" in roadmap
    assert "PR creada: #321" in result.stdout


def test_milestone_ready_for_pr_blocks_when_one_item_not_pending(tmp_path: Path):
    lines = ["- [ ] 02-item-a - Item", "- [-] 03-item-b - Item"]
    repo = make_milestone_repo(tmp_path, lines)
    bin_dir = tmp_path / "bin"
    make_fake_gh(bin_dir)
    env = command_env(bin_dir)
    before = (repo / "ROADMAP.md").read_text(encoding="utf-8")

    result = run_file(["-Mode", "Milestone", "-Slug", SLUG], repo, env)

    assert result.returncode != 0
    after = (repo / "ROADMAP.md").read_text(encoding="utf-8")
    # Estado mezclado: no es "todos ready" (no habria op) ni "todos pending"
    # (transicion valida); Assert-RoadmapItemsTransition debe rechazar
    # sin mutar nada.
    assert after == before
    combined = plain_output(result.stdout + result.stderr)
    assert "invalida" in combined or "Ningun item fue modificado" in combined


def test_milestone_ready_for_pr_blocks_roadmap_mutation_when_contract_fails(tmp_path: Path):
    # AC-4, AC-9 (GAP B): si falta la doc tecnica de un solo item del
    # manifest, ready-for-pr.ps1 -Mode Milestone no debe mutar ni
    # commitear ROADMAP.md para NINGUN item, ni siquiera para el item
    # cuyo contrato individual si estaria completo.
    repo = make_milestone_repo(tmp_path, [f"- [ ] {item} - Item" for item in ITEMS])
    (repo / "docs" / "tecnica" / "item-b.md").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "romper contrato: borrar doc tecnica de item-b")
    bin_dir = tmp_path / "bin"
    make_fake_gh(bin_dir)
    env = command_env(bin_dir)
    roadmap_before = (repo / "ROADMAP.md").read_bytes()
    log_before = git(repo, "log", "--oneline").stdout

    result = run_file(["-Mode", "Milestone", "-Slug", SLUG], repo, env)

    assert result.returncode != 0
    combined = plain_output(result.stdout + result.stderr)
    assert "item-b.md" in combined
    assert (repo / "ROADMAP.md").read_bytes() == roadmap_before
    for item in ITEMS:
        assert f"- [ ] {item}" in (repo / "ROADMAP.md").read_text(encoding="utf-8")
    log_after = git(repo, "log", "--oneline").stdout
    assert log_after == log_before


def test_milestone_pr_body_references_real_latest_attempt(tmp_path: Path):
    # AC-7, AC-10 (GAP C): con audit-1.md (rejected) + audit-2.md
    # (approved), el body de la PR debe referenciar audit-2.md (el
    # intento real aprobado vigente) y no el literal generico audit-N.md.
    repo = make_milestone_repo(tmp_path, [f"- [ ] {item} - Item" for item in ITEMS])
    run_dir = repo / "runs" / f"milestone-{SLUG}"
    (run_dir / "audit-1.md").write_text(
        "```yaml\nstatus: rejected\nattempt: 1\nfeedback:\n  - no\n```\n", encoding="utf-8"
    )
    (run_dir / "audit-2.md").write_text(
        "```yaml\nstatus: approved\nattempt: 2\nfeedback:\n  - ok\n```\n", encoding="utf-8"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "agregar audit-2 aprobado")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    body_capture = tmp_path / "captured-body.md"
    if os.name != "nt":
        pytest.skip("Captura de body de PR solo implementada para Windows en este entorno")
    gh = bin_dir / "gh.cmd"
    gh.write_text(
        "@echo off\n"
        "echo %* | findstr /C:\"pr view\" >nul && (echo no pull requests found 1>&2 & exit /b 1)\n"
        f"for %%i in (%*) do (if /I \"%%~xi\"==\".md\" copy /Y \"%%~i\" \"{body_capture}\" >nul)\n"
        "echo https://example.test/pull/321\n",
        encoding="utf-8",
    )
    pwsh = bin_dir / "pwsh.cmd"
    pwsh.write_text("@echo off\nexit /b 0\n", encoding="utf-8")

    env = command_env(bin_dir)
    result = run_file(["-Mode", "Milestone", "-Slug", SLUG], repo, env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert body_capture.exists()
    body = body_capture.read_text(encoding="utf-8")
    # Debe referenciar la ruta relativa exacta
    # (runs/milestone-<slug>/audit-2.md), no solo la subcadena
    # "audit-2.md" (esa subcadena tambien aparece al final de una ruta
    # absoluta, asi que por si sola no detectaria una regresion del bug
    # de GAP C donde Get-LatestVerdictArtifact.Path -- siempre absoluto,
    # via System.IO.FileInfo.FullName -- se filtraba al body publico de
    # la PR). El repo de este test vive bajo tmp_path, asi que si el bug
    # reaparece el path absoluto real de ese repo temporal (con
    # separador de unidad de disco Windows) aparece en el body.
    assert f"runs/milestone-{SLUG}/audit-2.md" in body
    assert "audit-N.md" not in body
    assert ":\\" not in body
    assert str(repo) not in body
    assert str(repo).replace("\\", "/") not in body


def test_milestone_pr_body_lists_every_item(tmp_path: Path):
    repo = make_milestone_repo(tmp_path, [f"- [ ] {item} - Item" for item in ITEMS])
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    body_capture = tmp_path / "captured-body.md"
    if os.name == "nt":
        gh = bin_dir / "gh.cmd"
        gh.write_text(
            "@echo off\n"
            "echo %* | findstr /C:\"pr view\" >nul && (echo no pull requests found 1>&2 & exit /b 1)\n"
            f"for %%i in (%*) do (if /I \"%%~xi\"==\".md\" copy /Y \"%%~i\" \"{body_capture}\" >nul)\n"
            "echo https://example.test/pull/321\n",
            encoding="utf-8",
        )
        pwsh = bin_dir / "pwsh.cmd"
        pwsh.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
    else:
        pytest.skip("Captura de body de PR solo implementada para Windows en este test")

    env = command_env(bin_dir)
    result = run_file(["-Mode", "Milestone", "-Slug", SLUG], repo, env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert body_capture.exists()
    body = body_capture.read_text(encoding="utf-8")
    for item in ITEMS:
        assert item in body
