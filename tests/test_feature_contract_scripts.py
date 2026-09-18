import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "scripts" / "feature-contract.ps1"
UPDATE_INDEXES = ROOT / "scripts" / "update-doc-indexes.ps1"
READY_FOR_PR = ROOT / "scripts" / "ready-for-pr.ps1"
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


def managed_zone(content: str) -> str:
    assert content.count(START_MARKER) == 1
    assert content.count(END_MARKER) == 1
    start = content.index(START_MARKER) + len(START_MARKER)
    end = content.index(END_MARKER)
    assert start < end
    return content[start:end]


def powershell() -> str:
    candidates = ["powershell.exe", "pwsh"] if os.name == "nt" else ["pwsh", "powershell"]
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    pytest.skip("PowerShell no esta disponible")


def run_ps(command: str, cwd: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_file(script: Path, args: list[str], cwd: Path, env: dict[str, str] | None = None):
    return subprocess.run(
        [powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def git(repo: Path, *args: str, check: bool = True):
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env=git_env(),
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr + result.stdout)
    return result


def git_env(extra_path: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "NUL" if os.name == "nt" else "/dev/null"
    env["GIT_TERMINAL_PROMPT"] = "0"
    if extra_path:
        env["PATH"] = str(extra_path) + os.pathsep + env["PATH"]
    return env


def verdict_block(status: str = "approved", attempt: int = 1) -> str:
    return (
        "```yaml\n"
        f"status: {status}\n"
        f"attempt: {attempt}\n"
        "feedback:\n"
        "  - ok\n"
        "```\n"
    )


def make_contract_repo(tmp_path: Path, slug: str = "99-demo-feature", title: str = "Demo feature"):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init")
    git(repo, "checkout", "-b", "feature/99-demo-feature")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Tests")

    doc_slug = slug.split("-", 1)[1]
    for path in [
        repo / "runs" / slug,
        repo / "docs" / "tecnica",
        repo / "docs" / "usuario",
    ]:
        path.mkdir(parents=True, exist_ok=True)

    (repo / "runs" / slug / "spec.md").write_text("# Spec\n", encoding="utf-8")
    (repo / "runs" / slug / "plan.md").write_text("# Plan\n", encoding="utf-8")
    (repo / "runs" / slug / "tasks.md").write_text("# Tasks\n", encoding="utf-8")
    (repo / "runs" / slug / "audit-1.md").write_text(verdict_block(), encoding="utf-8")
    (repo / "runs" / slug / "test-report-1.md").write_text(verdict_block(), encoding="utf-8")
    (repo / "runs" / slug / "code-review-1.md").write_text(verdict_block(), encoding="utf-8")
    (repo / "docs" / "tecnica" / f"{doc_slug}.md").write_text("# Tecnica\n", encoding="utf-8")
    (repo / "docs" / "usuario" / f"{doc_slug}.md").write_text("# Usuario\n", encoding="utf-8")
    (repo / "docs" / "tecnica" / "index.md").write_text(
        index_template("Tecnica"), encoding="utf-8"
    )
    (repo / "docs" / "usuario" / "index.md").write_text(
        index_template("Usuario"), encoding="utf-8"
    )
    (repo / "ROADMAP.md").write_text(f"- [ ] {slug} - Demo\n", encoding="utf-8")
    return repo, slug, title


def test_scaffolding_decision_docs_and_index_links_are_idempotent(tmp_path: Path):
    repo, slug, title = make_contract_repo(tmp_path)

    untouched_parts = {}
    for index in [repo / "docs" / "tecnica" / "index.md", repo / "docs" / "usuario" / "index.md"]:
        content = index.read_text(encoding="utf-8")
        untouched_parts[index] = (
            content[: content.index(START_MARKER) + len(START_MARKER)],
            content[content.index(END_MARKER) :],
        )

    create_decision = (
        f". '{CONTRACT}'; "
        "New-DecisionFile -Slug '99-demo-feature' -Title 'Demo feature' "
        "-Decisions @('Decision demostrable uno', 'Decision demostrable dos')"
    )
    result = run_ps(create_decision, repo)
    assert result.returncode == 0, result.stderr

    first = run_file(UPDATE_INDEXES, [slug, title], repo)
    second = run_file(UPDATE_INDEXES, [slug, title], repo)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    decision = (repo / "runs" / slug / "decision.md").read_text(encoding="utf-8")
    assert "- Decision demostrable uno" in decision
    assert "System.Object[]" not in decision
    for index in [repo / "docs" / "tecnica" / "index.md", repo / "docs" / "usuario" / "index.md"]:
        content = index.read_text(encoding="utf-8")
        assert content.count("- [Demo feature](demo-feature.md)") == 1
        assert "Texto externo" in content
        assert managed_zone(content).count("- [Demo feature](demo-feature.md)") == 1
        assert content.startswith(untouched_parts[index][0])
        assert content.endswith(untouched_parts[index][1])


def test_decision_file_does_not_claim_merge_and_references_hitl(tmp_path: Path):
    # AC-19: New-DecisionFile ya no debe escribir "MERGE aprobado" ni
    # ninguna afirmacion de que la PR fue mergeada; debe referenciar
    # explicitamente que el merge depende del HITL/GitHub, y su seccion
    # "Evidencias revisadas" debe incluir plan.md, tasks.md y
    # code-review-1.md ademas de spec.md/audit-1.md/test-report-1.md
    # (AC-18).
    repo, slug, title = make_contract_repo(tmp_path)

    create_decision = (
        f". '{CONTRACT}'; "
        "New-DecisionFile -Slug '99-demo-feature' -Title 'Demo feature' "
        "-Decisions @('Decision demostrable uno')"
    )
    result = run_ps(create_decision, repo)
    assert result.returncode == 0, result.stderr

    decision = (repo / "runs" / slug / "decision.md").read_text(encoding="utf-8")

    assert "MERGE aprobado" not in decision
    assert "fue mergeada" not in decision.lower()
    assert "la pr fue mergeada" not in decision.lower()
    assert "hitl" in decision.lower()
    assert "github" in decision.lower()
    assert "plan.md" in decision
    assert "tasks.md" in decision
    assert "code-review-1.md" in decision
    assert "spec.md" in decision
    assert "audit-1.md" in decision
    assert "test-report-1.md" in decision


def test_index_update_fails_for_missing_destination_and_ambiguous_links(tmp_path: Path):
    repo, slug, title = make_contract_repo(tmp_path)
    missing = repo / "docs" / "tecnica" / "demo-feature.md"
    missing.unlink()

    result = run_file(UPDATE_INDEXES, [slug, title], repo)

    assert result.returncode != 0
    assert "No existe el destino" in result.stderr

    missing.write_text("# Tecnica\n", encoding="utf-8")
    index = repo / "docs" / "tecnica" / "index.md"
    content = index_template("Tecnica").replace(
        END_MARKER,
        "- [Uno](demo-feature.md)\n- [Dos](demo-feature.md)\n\n" + END_MARKER,
    )
    index.write_text(content, encoding="utf-8")

    result = run_file(UPDATE_INDEXES, [slug, title], repo)

    assert result.returncode != 0
    assert "ambigua" in result.stderr.lower()


@pytest.mark.parametrize(
    "broken_content",
    [
        index_template("Tecnica").replace(START_MARKER, ""),
        index_template("Tecnica").replace(END_MARKER, ""),
        index_template("Tecnica").replace(START_MARKER, START_MARKER + "\n" + START_MARKER),
        index_template("Tecnica").replace(END_MARKER, END_MARKER + "\n" + END_MARKER),
        index_template("Tecnica").replace(
            START_MARKER + "\n\n" + END_MARKER,
            END_MARKER + "\n\n" + START_MARKER,
        ),
    ],
)
def test_index_update_rejects_invalid_markers_without_modifying_file(
    tmp_path: Path, broken_content: str
):
    repo, slug, title = make_contract_repo(tmp_path)
    index = repo / "docs" / "tecnica" / "index.md"
    index.write_text(broken_content, encoding="utf-8")
    before = index.read_bytes()

    result = run_file(UPDATE_INDEXES, [slug, title], repo)

    assert result.returncode != 0
    assert "FEATURE_LINKS" in result.stderr
    assert index.read_bytes() == before


def test_index_update_rejects_existing_link_outside_managed_zone(tmp_path: Path):
    repo, slug, title = make_contract_repo(tmp_path)
    index = repo / "docs" / "tecnica" / "index.md"
    content = index.read_text(encoding="utf-8")
    index.write_text(content + "\n- [Demo feature](demo-feature.md)\n", encoding="utf-8")
    before = index.read_bytes()

    result = run_file(UPDATE_INDEXES, [slug, title], repo)

    assert result.returncode != 0
    assert "fuera de la zona" in result.stderr
    assert "FEATURE_LINKS" in result.stderr
    assert index.read_bytes() == before


def test_preflight_prevents_partial_update_when_second_index_is_invalid(tmp_path: Path):
    repo, slug, title = make_contract_repo(tmp_path)
    technical_index = repo / "docs" / "tecnica" / "index.md"
    user_index = repo / "docs" / "usuario" / "index.md"
    user_index.write_text(
        user_index.read_text(encoding="utf-8").replace(END_MARKER, ""),
        encoding="utf-8",
    )
    technical_before = technical_index.read_bytes()
    user_before = user_index.read_bytes()

    result = run_file(UPDATE_INDEXES, [slug, title], repo)

    assert result.returncode != 0
    assert "FEATURE_LINKS_END" in result.stderr
    assert technical_index.read_bytes() == technical_before
    assert user_index.read_bytes() == user_before


def test_contract_rejects_link_outside_managed_zone(tmp_path: Path):
    repo, slug, title = make_contract_repo(tmp_path)
    run_ps(
        f". '{CONTRACT}'; "
        "New-DecisionFile -Slug '99-demo-feature' -Title 'Demo feature' "
        "-Decisions @('Decision demostrable')",
        repo,
    )
    for index in [repo / "docs" / "tecnica" / "index.md", repo / "docs" / "usuario" / "index.md"]:
        content = index.read_text(encoding="utf-8")
        index.write_text(content + "\n- [Demo feature](demo-feature.md)\n", encoding="utf-8")

    command = (
        f". '{CONTRACT}'; "
        f"Assert-FeatureContract -Slug '{slug}' -Title '{title}'"
    )
    result = run_ps(command, repo)

    assert result.returncode != 0
    assert "zona FEATURE_LINKS" in result.stderr


def test_ready_gate_fails_when_decision_or_index_link_is_missing(tmp_path: Path):
    repo, slug, title = make_contract_repo(tmp_path)
    command = (
        f". '{CONTRACT}'; "
        f"Assert-FeatureContract -Slug '{slug}' -Title '{title}'"
    )

    result = run_ps(command, repo)

    assert result.returncode != 0
    assert "decision.md" in result.stderr


def make_passing_repo(tmp_path: Path, slug: str = "99-demo-feature", title: str = "Demo feature"):
    # Repo con todo el contrato satisfecho (decision.md creado, indices
    # enlazados, spec/plan/tasks y los tres veredictos aprobados con
    # attempt 1). Los tests de parseo de veredicto parten de esta base y
    # corrompen un unico artefacto a la vez.
    repo, slug, title = make_contract_repo(tmp_path, slug, title)
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
    command = (
        f". '{CONTRACT}'; "
        f"Assert-FeatureContract -Slug '{slug}' -Title '{title}'"
    )
    return run_ps(command, repo)


def test_contract_passes_with_full_valid_run(tmp_path: Path):
    repo, slug, title = make_passing_repo(tmp_path)

    result = assert_contract(repo, slug, title)

    assert result.returncode == 0, result.stderr


def test_contract_uses_real_numeric_order_not_lexicographic(tmp_path: Path):
    repo, slug, title = make_passing_repo(tmp_path)
    (repo / "runs" / slug / "audit-1.md").unlink()
    (repo / "runs" / slug / "audit-2.md").write_text(verdict_block("rejected", 2), encoding="utf-8")
    (repo / "runs" / slug / "audit-10.md").write_text(verdict_block("approved", 10), encoding="utf-8")

    result = assert_contract(repo, slug, title)

    assert result.returncode == 0, result.stderr


def test_contract_fails_when_latest_real_attempt_is_rejected(tmp_path: Path):
    repo, slug, title = make_passing_repo(tmp_path)
    (repo / "runs" / slug / "audit-1.md").unlink()
    (repo / "runs" / slug / "audit-2.md").write_text(verdict_block("approved", 2), encoding="utf-8")
    (repo / "runs" / slug / "audit-10.md").write_text(verdict_block("rejected", 10), encoding="utf-8")

    result = assert_contract(repo, slug, title)

    assert result.returncode != 0
    assert "audit-10.md" in result.stderr
    assert "rejected" in result.stderr.lower() or "ultimo intento" in result.stderr.lower()


def test_contract_fails_when_previous_attempt_rejected_and_no_later_attempt_exists(tmp_path: Path):
    # Reproduce el escenario exacto de la auditoria: audit-1.md rechazado
    # seguido de audit-2.md vacio/inexistente ya NO debe pasar el contrato.
    repo, slug, title = make_passing_repo(tmp_path)
    (repo / "runs" / slug / "audit-1.md").write_text(verdict_block("rejected", 1), encoding="utf-8")

    result = assert_contract(repo, slug, title)

    assert result.returncode != 0
    assert "audit-1.md" in result.stderr


def test_contract_fails_with_readable_message_when_latest_attempt_file_is_empty(tmp_path: Path):
    # Complementa el test anterior: cubre explicitamente la mitad "vacio"
    # del escenario descripto en AC-16 ("audit-2.md vacio o inexistente"),
    # no solo la mitad "inexistente". audit-2.md existe como archivo de
    # 0 bytes (mas reciente por numero real que audit-1.md rechazado): el
    # contrato debe fallar con un mensaje identificable (ruta + causa),
    # no con una excepcion .NET cruda sin diagnostico.
    repo, slug, title = make_passing_repo(tmp_path)
    (repo / "runs" / slug / "audit-1.md").write_text(verdict_block("rejected", 1), encoding="utf-8")
    (repo / "runs" / slug / "audit-2.md").write_text("", encoding="utf-8")

    result = assert_contract(repo, slug, title)

    assert result.returncode != 0
    assert "audit-2.md" in result.stderr
    assert "valor no puede ser nulo" not in result.stderr.lower()
    assert "parametername" not in result.stderr.lower().replace(" ", "")


def test_contract_fails_when_yaml_block_is_missing(tmp_path: Path):
    repo, slug, title = make_passing_repo(tmp_path)
    (repo / "runs" / slug / "test-report-1.md").write_text("status: approved\nattempt: 1\n", encoding="utf-8")

    result = assert_contract(repo, slug, title)

    assert result.returncode != 0
    assert "test-report-1.md" in result.stderr
    assert "bloque" in result.stderr.lower()


def test_contract_fails_when_attempt_does_not_match_filename(tmp_path: Path):
    repo, slug, title = make_passing_repo(tmp_path)
    (repo / "runs" / slug / "code-review-1.md").write_text(verdict_block("approved", 2), encoding="utf-8")

    result = assert_contract(repo, slug, title)

    assert result.returncode != 0
    assert "code-review-1.md" in result.stderr
    assert "no coincide" in result.stderr.lower()


def test_contract_fails_when_status_value_is_malformed(tmp_path: Path):
    repo, slug, title = make_passing_repo(tmp_path)
    (repo / "runs" / slug / "audit-1.md").write_text(verdict_block("Approved", 1), encoding="utf-8")

    result = assert_contract(repo, slug, title)

    assert result.returncode != 0
    assert "audit-1.md" in result.stderr
    assert "invalido" in result.stderr.lower()


@pytest.mark.parametrize("missing_name", ["plan.md", "tasks.md"])
def test_contract_fails_when_plan_or_tasks_is_missing(tmp_path: Path, missing_name: str):
    repo, slug, title = make_passing_repo(tmp_path)
    (repo / "runs" / slug / missing_name).unlink()

    result = assert_contract(repo, slug, title)

    assert result.returncode != 0
    assert missing_name in result.stderr


def test_contract_fails_when_code_review_is_entirely_missing(tmp_path: Path):
    repo, slug, title = make_passing_repo(tmp_path)
    (repo / "runs" / slug / "code-review-1.md").unlink()

    result = assert_contract(repo, slug, title)

    assert result.returncode != 0
    assert "code-review" in result.stderr


def make_fake_tools(bin_dir: Path, mode: str):
    bin_dir.mkdir()
    if os.name == "nt":
        gh = bin_dir / "gh.cmd"
        if mode == "missing_then_create":
            # Simula el 'gh' real: 'pr view' falla (no existe todavia) y
            # 'pr create' (sin --json, que no todas las versiones de gh
            # soportan) imprime unicamente la URL de la PR en stdout.
            gh.write_text(
                "@echo off\n"
                "echo %* | findstr /C:\"pr view\" >nul && (echo no pull requests found 1>&2 & exit /b 1)\n"
                "echo https://example.test/pull/123\n",
                encoding="utf-8",
            )
        elif mode == "existing":
            gh.write_text(
                "@echo off\n"
                "echo {\"number\":45,\"url\":\"https://example.test/pull/45\",\"baseRefName\":\"develop\",\"state\":\"OPEN\"}\n",
                encoding="utf-8",
            )
        else:
            gh.write_text("@echo off\necho auth failed 1>&2\nexit /b 2\n", encoding="utf-8")
        pwsh = bin_dir / "pwsh.cmd"
        pwsh.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
    else:
        gh = bin_dir / "gh"
        if mode == "missing_then_create":
            # Simula el 'gh' real: 'pr view' falla (no existe todavia) y
            # 'pr create' (sin --json, que no todas las versiones de gh
            # soportan) imprime unicamente la URL de la PR en stdout.
            gh.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in *'pr view'*) echo 'no pull requests found' >&2; exit 1;; esac\n"
                "echo 'https://example.test/pull/123'\n",
                encoding="utf-8",
            )
        elif mode == "existing":
            gh.write_text(
                "#!/bin/sh\n"
                "echo '{\"number\":45,\"url\":\"https://example.test/pull/45\",\"baseRefName\":\"develop\",\"state\":\"OPEN\"}'\n",
                encoding="utf-8",
            )
        else:
            gh.write_text("#!/bin/sh\necho 'auth failed' >&2\nexit 2\n", encoding="utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        pwsh = bin_dir / "pwsh"
        pwsh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        pwsh.chmod(pwsh.stat().st_mode | stat.S_IXUSR)


def prepare_ready_repo(tmp_path: Path, mode: str):
    repo, slug, title = make_contract_repo(tmp_path, "99-demo-feature", "Demo feature")
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], cwd=tmp_path, check=True)
    git(repo, "remote", "add", "origin", str(remote))
    run_ps(
        f". '{CONTRACT}'; "
        "New-DecisionFile -Slug '99-demo-feature' -Title 'Demo feature' "
        "-Decisions @('Decision demostrable')",
        repo,
    )
    run_file(UPDATE_INDEXES, [slug, title], repo)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "feature ready")
    git(repo, "push", "-u", "origin", "feature/99-demo-feature")
    bin_dir = tmp_path / "bin"
    make_fake_tools(bin_dir, mode)
    return repo, slug, title, git_env(bin_dir)


def test_ready_for_pr_creates_pr_after_expected_missing_pr(tmp_path: Path):
    repo, slug, title, env = prepare_ready_repo(tmp_path, "missing_then_create")

    result = run_file(READY_FOR_PR, [slug, title], repo, env)

    assert result.returncode == 0, result.stderr
    assert "PR creada: #123" in result.stdout
    assert "- [-] 99-demo-feature" in (repo / "ROADMAP.md").read_text(encoding="utf-8")


def test_ready_for_pr_reuses_existing_pr_without_duplicate(tmp_path: Path):
    repo, slug, title, env = prepare_ready_repo(tmp_path, "existing")

    result = run_file(READY_FOR_PR, [slug, title], repo, env)

    assert result.returncode == 0, result.stderr
    assert "PR existente: #45" in result.stdout


def test_ready_for_pr_blocks_real_gh_error(tmp_path: Path):
    repo, slug, title, env = prepare_ready_repo(tmp_path, "real_error")

    result = run_file(READY_FOR_PR, [slug, title], repo, env)

    assert result.returncode != 0
    assert "auth failed" in result.stderr


def test_ready_for_pr_blocks_roadmap_mutation_when_contract_fails(tmp_path: Path):
    # AC-3, AC-9 (GAP B): si el contrato completo falla (decision.md
    # faltante), ready-for-pr.ps1 no debe mutar ni commitear ROADMAP.md.
    repo, slug, title, env = prepare_ready_repo(tmp_path, "missing_then_create")
    (repo / "runs" / slug / "decision.md").unlink()
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "romper contrato: borrar decision.md")

    roadmap_before = (repo / "ROADMAP.md").read_bytes()
    log_before = git(repo, "log", "--oneline").stdout

    result = run_file(READY_FOR_PR, [slug, title], repo, env)

    assert result.returncode != 0
    assert "decision.md" in result.stderr
    assert (repo / "ROADMAP.md").read_bytes() == roadmap_before
    assert "- [ ] 99-demo-feature" in (repo / "ROADMAP.md").read_text(encoding="utf-8")
    log_after = git(repo, "log", "--oneline").stdout
    assert log_after == log_before


def capture_pr_body_bin_dir(bin_dir: Path, body_capture: Path) -> None:
    # Variante de make_fake_tools('missing_then_create') que ademas
    # vuelca el contenido del '--body-file' pasado a 'gh pr create' a un
    # archivo aparte, siguiendo el patron FAKE_GH_LOG de
    # test_complete_approved_pr_script.py (T-16).
    bin_dir.mkdir(exist_ok=True)
    if os.name == "nt":
        gh = bin_dir / "gh.cmd"
        gh.write_text(
            "@echo off\n"
            "echo %* | findstr /C:\"pr view\" >nul && (echo no pull requests found 1>&2 & exit /b 1)\n"
            f"for %%i in (%*) do (if /I \"%%~xi\"==\".md\" copy /Y \"%%~i\" \"{body_capture}\" >nul)\n"
            "echo https://example.test/pull/123\n",
            encoding="utf-8",
        )
        pwsh = bin_dir / "pwsh.cmd"
        pwsh.write_text("@echo off\nexit /b 0\n", encoding="utf-8")
    else:
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in *'pr view'*) echo 'no pull requests found' >&2; exit 1;; esac\n"
            "prev=\"\"\n"
            "for arg in \"$@\"; do\n"
            "  if [ \"$prev\" = \"--body-file\" ]; then cp \"$arg\" \"" + str(body_capture) + "\"; fi\n"
            "  prev=\"$arg\"\n"
            "done\n"
            "echo 'https://example.test/pull/123'\n",
            encoding="utf-8",
        )
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        pwsh = bin_dir / "pwsh"
        pwsh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        pwsh.chmod(pwsh.stat().st_mode | stat.S_IXUSR)


def test_ready_for_pr_pr_body_references_real_latest_attempt(tmp_path: Path):
    # AC-6, AC-10 (GAP C): con audit-1.md (rejected) + audit-2.md
    # (approved), el body de la PR debe referenciar audit-2.md (el
    # intento real aprobado vigente) y no el literal generico audit-N.md.
    repo, slug, title = make_contract_repo(tmp_path, "99-demo-feature", "Demo feature")
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(remote)], cwd=tmp_path, check=True)
    git(repo, "remote", "add", "origin", str(remote))
    (repo / "runs" / slug / "audit-1.md").write_text(verdict_block("rejected", 1), encoding="utf-8")
    (repo / "runs" / slug / "audit-2.md").write_text(verdict_block("approved", 2), encoding="utf-8")
    run_ps(
        f". '{CONTRACT}'; "
        "New-DecisionFile -Slug '99-demo-feature' -Title 'Demo feature' "
        "-Decisions @('Decision demostrable')",
        repo,
    )
    run_file(UPDATE_INDEXES, [slug, title], repo)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "feature ready")
    git(repo, "push", "-u", "origin", "feature/99-demo-feature")

    bin_dir = tmp_path / "bin"
    body_capture = tmp_path / "captured-body.md"
    if os.name != "nt":
        pytest.skip("Captura de body de PR solo implementada para Windows en este entorno")
    capture_pr_body_bin_dir(bin_dir, body_capture)
    env = git_env(bin_dir)

    result = run_file(READY_FOR_PR, [slug, title], repo, env)

    assert result.returncode == 0, result.stderr
    assert body_capture.exists()
    body = body_capture.read_text(encoding="utf-8")
    # Debe referenciar la ruta relativa exacta (runs/<slug>/audit-2.md),
    # no solo la subcadena "audit-2.md" (esa subcadena tambien aparece al
    # final de una ruta absoluta, asi que por si sola no detectaria una
    # regresion del bug de GAP C donde Get-LatestVerdictArtifact.Path
    # -- System.IO.FileInfo.FullName, siempre absoluto -- se filtraba al
    # body publico de la PR). El repo de este test vive bajo tmp_path, asi
    # que si el bug reaparece el path absoluto real de ese repo temporal
    # (con separador de unidad de disco Windows) aparece en el body.
    assert f"runs/{slug}/audit-2.md" in body
    assert "audit-N.md" not in body
    assert ":\\" not in body
    assert str(repo) not in body
    assert str(repo).replace("\\", "/") not in body


def test_workflow_yaml_is_valid():
    workflow = ROOT / ".github" / "workflows" / "post-merge-close-feature.yml"
    content = workflow.read_text(encoding="utf-8")
    assert "pull_request_target:" in content
    assert "contents: write" in content
    assert "pull-requests: read" in content
    assert "group: close-feature-develop" in content
    assert "-SkipLocalCleanup" in content

    gate = ROOT / ".github" / "workflows" / "post-hitl-merge-gate.yml"
    gate_content = gate.read_text(encoding="utf-8")
    assert "pull_request_review:" in gate_content
    assert "github.event.review.state == 'approved'" in gate_content
    assert "scripts/complete-approved-pr.ps1" in gate_content
    assert "-CommentOnFailure" in gate_content
