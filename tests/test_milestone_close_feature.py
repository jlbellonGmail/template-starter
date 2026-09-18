import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "close-feature.ps1"
SLUG = "mi-milestone"
ITEMS = ["02-item-a", "03-item-b"]
BRANCH = f"milestone/{SLUG}"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
WHITESPACE_RE = re.compile(r"\s+")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


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
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    if extra_path:
        env["PATH"] = str(extra_path) + os.pathsep + env["PATH"]
    return env


def plain_output(output: str) -> str:
    # pwsh en Linux envuelve mensajes de error largos al ancho de terminal
    # e inserta un marcador "|" al inicio de cada linea continuada (el
    # "gutter" del formateador de errores). Se quita antes de colapsar
    # espacios para que el mensaje quede como una sola frase comparable.
    without_ansi = ANSI_ESCAPE_RE.sub("", output)
    without_pipes = without_ansi.replace("|", " ")
    return WHITESPACE_RE.sub(" ", without_pipes).strip()


def captured_output(result: subprocess.CompletedProcess[str]) -> str:
    return plain_output("\n".join(part for part in [result.stdout, result.stderr] if part))


def exception_message(result: subprocess.CompletedProcess[str]) -> str:
    return plain_output(result.stderr)


def ps_quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def run(command, cwd, env=None, check=True):
    result = subprocess.run(
        command, cwd=cwd, env=env or command_env(), text=True, capture_output=True,
        check=False, creationflags=CREATE_NO_WINDOW,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"Command failed: {command}\n{captured_output(result)}")
    return result


def git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], repo, check=check)


def write_fake_gh(bin_dir: Path, state: str = "MERGED", base: str = "develop") -> None:
    bin_dir.mkdir()
    payload = (
        f'{{"state":"{state}","mergedAt":"2026-08-17T19:00:00Z",'
        f'"baseRefName":"{base}","headRefName":"{BRANCH}"}}'
    )
    if os.name == "nt":
        gh = bin_dir / "gh.cmd"
        gh.write_text(f"@echo off\necho {payload}\n", encoding="utf-8")
    else:
        gh = bin_dir / "gh"
        gh.write_text(f"#!/bin/sh\necho '{payload}'\n", encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)


def make_case(tmp_path: Path, roadmap: str, items: list[str] = None, gh_state: str = "MERGED"):
    items = items if items is not None else ITEMS
    remote = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    worktree = tmp_path / "worktrees" / SLUG
    bin_dir = tmp_path / "bin"

    run(["git", "init", "--bare", str(remote)], tmp_path)
    run(["git", "init", str(repo)], tmp_path)
    git(repo, "checkout", "-b", "develop")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Tests")
    (repo / "ROADMAP.md").write_text(roadmap, encoding="utf-8")
    manifest_dir = repo / "runs" / f"milestone-{SLUG}"
    manifest_dir.mkdir(parents=True)
    manifest = {"schemaVersion": 1, "mode": "milestone", "slug": SLUG, "items": items}
    (manifest_dir / "work-unit.json").write_text(json.dumps(manifest), encoding="utf-8")
    git(repo, "add", "ROADMAP.md", str(manifest_dir.relative_to(repo)))
    git(repo, "commit", "-m", "initial roadmap + manifest")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-u", "origin", "develop")
    git(repo, "checkout", "-b", BRANCH)
    git(repo, "push", "-u", "origin", BRANCH)
    git(repo, "checkout", "develop")
    git(repo, "worktree", "add", str(worktree), BRANCH)
    write_fake_gh(bin_dir, gh_state)
    return repo, remote, worktree, bin_dir


def close_feature(repo: Path, worktree: Path, bin_dir: Path):
    command = (
        "$ErrorActionPreference = 'Stop'; "
        "try { "
        f"& {ps_quote(SCRIPT)} -Slug {ps_quote(SLUG)} -WorktreeDir {ps_quote(worktree)} -Mode Milestone; "
        "exit $LASTEXITCODE "
        "} catch { "
        "[Console]::Error.WriteLine($_.Exception.Message); "
        "exit 1 "
        "}"
    )
    return run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        repo, env=command_env(bin_dir), check=False,
    )


def roadmap(repo: Path, ref: str = "develop") -> str:
    return git(repo, "show", f"{ref}:ROADMAP.md").stdout


def commit_count(repo: Path) -> str:
    return git(repo, "rev-list", "--count", "develop").stdout.strip()


def test_closes_all_items_atomically_in_one_commit(tmp_path: Path):
    lines = "".join(f"- [-] {item} - Item\n" for item in ITEMS)
    repo, _, worktree, bin_dir = make_case(tmp_path, lines)
    before = commit_count(repo)

    result = close_feature(repo, worktree, bin_dir)

    assert result.returncode == 0, result.stdout
    remote_roadmap = roadmap(repo, "origin/develop")
    for item in ITEMS:
        assert f"- [x] {item}" in remote_roadmap
        assert f"- [-] {item}" not in remote_roadmap
    # Un unico commit adicional para cerrar TODOS los items.
    assert int(commit_count(repo)) == int(before) + 1
    assert not worktree.exists()


def test_idempotent_rerun_when_all_already_closed(tmp_path: Path):
    lines = "".join(f"- [x] {item} - Item\n" for item in ITEMS)
    repo, _, worktree, bin_dir = make_case(tmp_path, lines)
    before = commit_count(repo)

    result = close_feature(repo, worktree, bin_dir)

    assert result.returncode == 0, result.stdout
    assert commit_count(repo) == before
    assert "sin commit vacio" in captured_output(result)


def test_partial_close_state_is_rejected_as_unrecoverable(tmp_path: Path):
    # Estado mezclado que en teoria no deberia ocurrir con escritura
    # atomica, pero se defiende igual: un item ya [x], otro sigue [-].
    lines = f"- [x] {ITEMS[0]} - Item\n- [-] {ITEMS[1]} - Item\n"
    repo, _, worktree, bin_dir = make_case(tmp_path, lines)

    result = close_feature(repo, worktree, bin_dir)

    assert result.returncode != 0
    message = exception_message(result)
    assert "irrecuperable" in message or "intervencion manual" in message
    assert worktree.exists()


def test_retry_after_failed_push_completes_on_rerun(tmp_path: Path):
    # Version Milestone del escenario de AC-21: commit local de cierre para
    # TODOS los items ya se creo, pero el push subsiguiente fallo. Una
    # segunda ejecucion con el mismo estado local detecta el remoto todavia
    # sin el cierre y completa el push pendiente, sin reintentar el commit.
    lines = "".join(f"- [-] {item} - Item\n" for item in ITEMS)
    repo, remote, worktree, bin_dir = make_case(tmp_path, lines)
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)

    first = close_feature(repo, worktree, bin_dir)

    assert first.returncode != 0
    assert "Command failed: git push origin develop" in exception_message(first)
    local_roadmap = (repo / "ROADMAP.md").read_text(encoding="utf-8")
    for item in ITEMS:
        assert f"- [x] {item}" in local_roadmap
    remote_roadmap_before = roadmap(repo, "origin/develop")
    for item in ITEMS:
        assert f"- [-] {item}" in remote_roadmap_before
    assert worktree.exists()
    commits_after_failed_push = commit_count(repo)

    hook.unlink()

    second = close_feature(repo, worktree, bin_dir)

    assert second.returncode == 0, second.stdout
    output = captured_output(second)
    assert "Reejecucion segura, sin commit vacio" in output
    assert "Pusheando commit local pendiente" in output
    assert commit_count(repo) == commits_after_failed_push
    remote_roadmap_after = roadmap(repo, "origin/develop")
    for item in ITEMS:
        assert f"- [x] {item}" in remote_roadmap_after
        assert f"- [-] {item}" not in remote_roadmap_after
    assert not worktree.exists()


def test_rerun_after_success_does_not_create_commit(tmp_path: Path):
    lines = "".join(f"- [-] {item} - Item\n" for item in ITEMS)
    repo, _, worktree, bin_dir = make_case(tmp_path, lines)
    first = close_feature(repo, worktree, bin_dir)
    assert first.returncode == 0, first.stdout

    # El primer run ya limpio el worktree; para la reejecucion ese
    # directorio ya no existe, lo cual replica el escenario real de
    # cierre remoto detectado sin necesidad de limpieza local otra vez.
    before = commit_count(repo)
    second = run(
        [
            powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            "$ErrorActionPreference = 'Stop'; try { "
            f"& {ps_quote(SCRIPT)} -Slug {ps_quote(SLUG)} -Mode Milestone -SkipLocalCleanup; "
            "exit $LASTEXITCODE } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }",
        ],
        repo, env=command_env(bin_dir), check=False,
    )

    assert second.returncode == 0, second.stdout
    assert commit_count(repo) == before
