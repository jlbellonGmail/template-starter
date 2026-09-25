import os
import shutil
import subprocess
from pathlib import Path
import pytest
import json

ROOT = Path(__file__).resolve().parents[1]
UPDATE = ROOT / "scripts" / "update-status.ps1"
CHECK = ROOT / "scripts" / "check-status.ps1"

def powershell():
    for name in ("pwsh", "powershell.exe", "powershell"):
        if path := shutil.which(name):
            return path
    pytest.skip("PowerShell no disponible")

def environment():
    result = os.environ.copy()
    result["GIT_CONFIG_GLOBAL"] = "NUL" if os.name == "nt" else "/dev/null"
    result["GIT_TERMINAL_PROMPT"] = "0"
    return result

def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True, env=environment())

def run(script, repo):
    return subprocess.run([powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], cwd=repo, text=True, capture_output=True, env=environment())

def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "checkout", "-b", "develop")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Tests")
    (repo / "STATUS.md").write_text("# Manual\n\nPreservar.\n", encoding="utf-8")
    git(repo, "add", "STATUS.md")
    git(repo, "commit", "-m", "status")
    return repo

def test_update_preserves_manual_and_is_idempotent(tmp_path):
    repo = make_repo(tmp_path)
    assert run(UPDATE, repo).returncode == 0
    first = (repo / "STATUS.md").read_text(encoding="utf-8")
    assert run(UPDATE, repo).returncode == 0
    second = (repo / "STATUS.md").read_text(encoding="utf-8")
    assert "Preservar." in second
    assert second.count("STATUS:AUTO:BEGIN") == 1
    assert first.split("- Actualizado:", 1)[0] == second.split("- Actualizado:", 1)[0]

def test_check_clean_and_dirty(tmp_path):
    repo = make_repo(tmp_path)
    assert run(UPDATE, repo).returncode == 0
    assert run(CHECK, repo).returncode == 0
    (repo / "manual.txt").write_text("dirty\n", encoding="utf-8")
    assert run(UPDATE, repo).returncode == 0
    assert run(CHECK, repo).returncode == 0

def test_check_detects_stale_branch(tmp_path):
    repo = make_repo(tmp_path)
    assert run(UPDATE, repo).returncode == 0
    status = repo / "STATUS.md"
    status.write_text(status.read_text().replace("- Rama: develop", "- Rama: old"), encoding="utf-8")
    assert run(CHECK, repo).returncode == 1

@pytest.mark.parametrize("text", ["missing\n", "<!-- STATUS:AUTO:BEGIN -->\n<!-- STATUS:AUTO:BEGIN -->\n<!-- STATUS:AUTO:END -->\n"])
def test_check_detects_bad_markers(tmp_path, text):
    repo = make_repo(tmp_path)
    (repo / "STATUS.md").write_text(text, encoding="utf-8")
    assert run(CHECK, repo).returncode == 1

def test_no_gh_is_warning(tmp_path):
    repo = make_repo(tmp_path)
    assert run(UPDATE, repo).returncode == 0
    result = run(CHECK, repo)
    assert result.returncode == 0
    assert "WARNING" in result.stdout

def test_execution_error_is_exit_two(tmp_path):
    assert run(UPDATE, tmp_path).returncode == 2


def json_snapshot(repo):
    result = subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(UPDATE), "-Json"],
        cwd=repo, text=True, capture_output=True, env=environment()
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_version_is_not_hardcoded_and_unknown_is_explicit(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "ROADMAP.md").write_text("## v2.7.3 — Roadmap activo\n", encoding="utf-8")
    git(repo, "add", "ROADMAP.md")
    git(repo, "commit", "-m", "roadmap")
    assert json_snapshot(repo)["version"] == {
        "value": "v2.7.3", "source": "ROADMAP.md", "confidence": "declared"
    }
    (repo / "VERSION").write_text("v9.1.4\n", encoding="utf-8")
    assert json_snapshot(repo)["version"]["value"] == "v9.1.4"
    (repo / "VERSION").write_text("not-a-version\n", encoding="utf-8")
    (repo / "ROADMAP.md").write_text("# Histórico\n", encoding="utf-8")
    assert json_snapshot(repo)["version"]["value"] is None


def test_historical_runs_do_not_create_active_units_and_real_worktree_does(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "ROADMAP.md").write_text(
        "## v3.0.0 — Roadmap activo\n\n- [ ] 01-demo - Demo\n", encoding="utf-8"
    )
    git(repo, "add", "ROADMAP.md")
    git(repo, "commit", "-m", "roadmap")
    (repo / "runs" / "v2.0.0" / "01-demo").mkdir(parents=True)
    assert json_snapshot(repo)["activeUnits"] == []

    linked = tmp_path / "linked"
    git(repo, "worktree", "add", "-b", "feature/v3.0.0-01-demo", str(linked), "develop")
    snapshot = json_snapshot(repo)
    assert len(snapshot["worktrees"]) == 2
    assert snapshot["worktrees"][0]["role"] == "primary"
    assert snapshot["activeUnits"][0]["source"] == "git-worktree"
    git(repo, "worktree", "remove", str(linked))
    assert json_snapshot(repo)["activeUnits"] == []
def test_ci_ignores_non_ci_workflows_for_same_head():
    source = (ROOT / "scripts" / "status-lib.ps1").read_text(encoding="utf-8")
    assert "Where-Object {$_.workflowName -eq 'CI'}" in source
