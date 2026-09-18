import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "complete-approved-pr.ps1"
SLUG = "06-patente"
BRANCH = f"feature/{SLUG}"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def powershell() -> str:
    candidates = ["powershell.exe", "pwsh"] if os.name == "nt" else ["pwsh", "powershell"]
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    pytest.skip("PowerShell no esta disponible")


def command_env(bin_dir: Path, mode: str, log_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    env["FAKE_GH_MODE"] = mode
    env["FAKE_GH_LOG"] = str(log_path)
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    return env


def write_fake_gh(bin_dir: Path) -> None:
    # 'headRefOid' se agrega a la respuesta de 'pr view' para todos los
    # modos (GAP A / AC-1, AC-2). La consulta a 'gh api .../reviews
    # --paginate --slurp' responde un array de "paginas" (cada pagina, a
    # su vez, un array de reviews), reflejando el comportamiento real de
    # 'gh api --paginate --slurp' contra un endpoint que devuelve un
    # array JSON (ver docs/tecnica/integridad-post-hitl-y-ready-for-pr.md).
    bin_dir.mkdir()
    if os.name == "nt":
        gh = bin_dir / "gh.cmd"
        gh.write_text(
            "@echo off\n"
            "echo %*>>\"%FAKE_GH_LOG%\"\n"
            "echo %* | findstr /C:\"pr view\" >nul && (\n"
            "  if \"%FAKE_GH_MODE%\"==\"review_required\" echo {\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"develop\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"REVIEW_REQUIRED\",\"headRefOid\":\"commitA\"} & exit /b 0\n"
            "  if \"%FAKE_GH_MODE%\"==\"wrong_base\" echo {\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"main\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"APPROVED\",\"headRefOid\":\"commitA\"} & exit /b 0\n"
            "  if \"%FAKE_GH_MODE%\"==\"stale_approval\" echo {\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"develop\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"APPROVED\",\"headRefOid\":\"commitB\"} & exit /b 0\n"
            "  if \"%FAKE_GH_MODE%\"==\"multi_review_recent_matches\" echo {\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"develop\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"APPROVED\",\"headRefOid\":\"commitC\"} & exit /b 0\n"
            "  echo {\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"develop\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"APPROVED\",\"headRefOid\":\"commitA\"}\n"
            "  exit /b 0\n"
            ")\n"
            "echo %* | findstr /C:\"reviews\" >nul && (\n"
            "  if \"%FAKE_GH_MODE%\"==\"stale_approval\" echo [[{\"commit_id\":\"commitA\",\"state\":\"APPROVED\",\"submitted_at\":\"2026-08-20T00:00:00Z\"}]] & exit /b 0\n"
            "  if \"%FAKE_GH_MODE%\"==\"multi_review_recent_matches\" echo [[{\"commit_id\":\"commitOld\",\"state\":\"APPROVED\",\"submitted_at\":\"2026-08-19T00:00:00Z\"},{\"commit_id\":\"commitC\",\"state\":\"APPROVED\",\"submitted_at\":\"2026-08-21T00:00:00Z\"}]] & exit /b 0\n"
            "  echo [[{\"commit_id\":\"commitA\",\"state\":\"APPROVED\",\"submitted_at\":\"2026-08-20T00:00:00Z\"}]]\n"
            "  exit /b 0\n"
            ")\n"
            "echo %* | findstr /C:\"pr checks\" >nul && (\n"
            "  if \"%FAKE_GH_MODE%\"==\"checks_fail\" echo [{\"bucket\":\"fail\",\"completedAt\":\"2026-08-21T01:00:00Z\",\"description\":\"\",\"event\":\"pull_request\",\"link\":\"https://example.test/check\",\"name\":\"pytest\",\"startedAt\":\"2026-08-21T00:59:00Z\",\"state\":\"FAILURE\",\"workflow\":\"CI\"}] & exit /b 1\n"
            "  echo [{\"bucket\":\"pass\",\"completedAt\":\"2026-08-21T01:00:00Z\",\"description\":\"\",\"event\":\"pull_request\",\"link\":\"https://example.test/check\",\"name\":\"pytest\",\"startedAt\":\"2026-08-21T00:59:00Z\",\"state\":\"SUCCESS\",\"workflow\":\"CI\"}]\n"
            "  exit /b 0\n"
            ")\n"
            "echo %* | findstr /C:\"pr merge\" >nul && (echo merged & exit /b 0)\n"
            "echo %* | findstr /C:\"pr comment\" >nul && (echo commented & exit /b 0)\n"
            "echo unexpected gh args: %* 1>&2\n"
            "exit /b 2\n",
            encoding="utf-8",
        )
    else:
        gh = bin_dir / "gh"
        gh.write_text(
            "#!/bin/sh\n"
            "echo \"$*\" >> \"$FAKE_GH_LOG\"\n"
            "case \"$*\" in\n"
            "  *'pr view'*)\n"
            "    if [ \"$FAKE_GH_MODE\" = 'review_required' ]; then echo '{\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"develop\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"REVIEW_REQUIRED\",\"headRefOid\":\"commitA\"}'; exit 0; fi\n"
            "    if [ \"$FAKE_GH_MODE\" = 'wrong_base' ]; then echo '{\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"main\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"APPROVED\",\"headRefOid\":\"commitA\"}'; exit 0; fi\n"
            "    if [ \"$FAKE_GH_MODE\" = 'stale_approval' ]; then echo '{\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"develop\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"APPROVED\",\"headRefOid\":\"commitB\"}'; exit 0; fi\n"
            "    if [ \"$FAKE_GH_MODE\" = 'multi_review_recent_matches' ]; then echo '{\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"develop\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"APPROVED\",\"headRefOid\":\"commitC\"}'; exit 0; fi\n"
            "    echo '{\"number\":123,\"state\":\"OPEN\",\"baseRefName\":\"develop\",\"headRefName\":\"feature/06-patente\",\"url\":\"https://example.test/pull/123\",\"reviewDecision\":\"APPROVED\",\"headRefOid\":\"commitA\"}'; exit 0;;\n"
            "  *'reviews'*)\n"
            "    if [ \"$FAKE_GH_MODE\" = 'stale_approval' ]; then echo '[[{\"commit_id\":\"commitA\",\"state\":\"APPROVED\",\"submitted_at\":\"2026-08-20T00:00:00Z\"}]]'; exit 0; fi\n"
            "    if [ \"$FAKE_GH_MODE\" = 'multi_review_recent_matches' ]; then echo '[[{\"commit_id\":\"commitOld\",\"state\":\"APPROVED\",\"submitted_at\":\"2026-08-19T00:00:00Z\"},{\"commit_id\":\"commitC\",\"state\":\"APPROVED\",\"submitted_at\":\"2026-08-21T00:00:00Z\"}]]'; exit 0; fi\n"
            "    echo '[[{\"commit_id\":\"commitA\",\"state\":\"APPROVED\",\"submitted_at\":\"2026-08-20T00:00:00Z\"}]]'; exit 0;;\n"
            "  *'pr checks'*)\n"
            "    if [ \"$FAKE_GH_MODE\" = 'checks_fail' ]; then echo '[{\"bucket\":\"fail\",\"completedAt\":\"2026-08-21T01:00:00Z\",\"description\":\"\",\"event\":\"pull_request\",\"link\":\"https://example.test/check\",\"name\":\"pytest\",\"startedAt\":\"2026-08-21T00:59:00Z\",\"state\":\"FAILURE\",\"workflow\":\"CI\"}]'; exit 1; fi\n"
            "    echo '[{\"bucket\":\"pass\",\"completedAt\":\"2026-08-21T01:00:00Z\",\"description\":\"\",\"event\":\"pull_request\",\"link\":\"https://example.test/check\",\"name\":\"pytest\",\"startedAt\":\"2026-08-21T00:59:00Z\",\"state\":\"SUCCESS\",\"workflow\":\"CI\"}]'; exit 0;;\n"
            "  *'pr merge'*) echo merged; exit 0;;\n"
            "  *'pr comment'*) echo commented; exit 0;;\n"
            "esac\n"
            "echo \"unexpected gh args: $*\" >&2\n"
            "exit 2\n",
            encoding="utf-8",
        )
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)


def run_gate(repo: Path, bin_dir: Path, log_path: Path, mode: str, preauthorized: bool = False):
    authorization = repo / "authorization.md"
    if preauthorized:
        authorization.write_text(
            "decision: MERGE\nscope: 06-patente\nphase: 02\nauthorizedBy: user-instruction\n",
            encoding="utf-8",
        )
    return subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-Slug",
            SLUG,
            "-Branch",
            BRANCH,
            "-PrNumber",
            "123",
            "-SkipLocalCleanup",
            "-CheckPollSeconds",
            "1",
            "-CheckMaxMinutes",
            "1",
        ] + (["-PreAuthorizedHumanMerge", "-AuthorizationPath", str(authorization)] if preauthorized else []),
        cwd=repo,
        env=command_env(bin_dir, mode, log_path),
        text=True,
        capture_output=True,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )


def make_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    log_path = tmp_path / "gh.log"
    (repo / "runs" / SLUG).mkdir(parents=True)
    write_fake_gh(bin_dir)
    return repo, bin_dir, log_path


def reports(repo: Path) -> list[Path]:
    return sorted((repo / "runs" / SLUG).glob("post-hitl-gate-*.md"))


def test_complete_approved_pr_merges_after_green_checks(tmp_path: Path):
    repo, bin_dir, log_path = make_repo(tmp_path)

    result = run_gate(repo, bin_dir, log_path, "success")

    assert result.returncode == 0, result.stderr + result.stdout
    log = log_path.read_text(encoding="utf-8")
    assert "pr checks" in log
    assert "pr merge 123 --merge --delete-branch" in log
    report = reports(repo)[0].read_text(encoding="utf-8")
    assert report.startswith("status: approved")
    assert "[pass] CI / pytest" in report


def test_complete_approved_pr_returns_builder_feedback_when_checks_fail(tmp_path: Path):
    repo, bin_dir, log_path = make_repo(tmp_path)

    result = run_gate(repo, bin_dir, log_path, "checks_fail")

    assert result.returncode != 0
    log = log_path.read_text(encoding="utf-8")
    assert "pr checks" in log
    assert "pr merge" not in log
    report = reports(repo)[0].read_text(encoding="utf-8")
    assert report.startswith("status: rejected")
    assert "Builder-agent debe corregir" in report
    assert "[fail] CI / pytest" in report


def test_complete_approved_pr_requires_hitl_approval_before_checks(tmp_path: Path):
    repo, bin_dir, log_path = make_repo(tmp_path)

    result = run_gate(repo, bin_dir, log_path, "review_required")

    assert result.returncode != 0
    assert "todavia no tiene aprobacion HITL" in result.stderr
    log = log_path.read_text(encoding="utf-8")
    assert "pr view" in log
    assert "pr checks" not in log
    assert reports(repo) == []


def test_complete_approved_pr_accepts_explicit_scoped_preauthorization(tmp_path: Path):
    repo, bin_dir, log_path = make_repo(tmp_path)

    result = run_gate(repo, bin_dir, log_path, "review_required", preauthorized=True)

    assert result.returncode == 0, result.stderr + result.stdout
    log = log_path.read_text(encoding="utf-8")
    assert "pr merge 123 --merge --delete-branch" in log
    assert "pr checks" in log


def test_complete_approved_pr_blocks_wrong_base_branch(tmp_path: Path):
    repo, bin_dir, log_path = make_repo(tmp_path)

    result = run_gate(repo, bin_dir, log_path, "wrong_base")

    assert result.returncode != 0
    assert "no a 'develop'" in result.stderr
    log = log_path.read_text(encoding="utf-8")
    assert "pr checks" not in log
    assert "pr merge" not in log


def test_complete_approved_pr_rejects_stale_approval(tmp_path: Path):
    # AC-1, AC-8: la ultima review APPROVED fue emitida sobre 'commitA',
    # pero el head vigente de la PR es 'commitB' (push posterior a la
    # aprobacion). El gate debe rechazar sin mergear.
    repo, bin_dir, log_path = make_repo(tmp_path)

    result = run_gate(repo, bin_dir, log_path, "stale_approval")

    assert result.returncode != 0
    log = log_path.read_text(encoding="utf-8")
    assert "pr merge" not in log
    report = reports(repo)[0].read_text(encoding="utf-8")
    assert report.startswith("status: rejected")
    assert "obsoleta" in report.lower()
    assert "nueva" in report.lower() or "vuelva a aprobar" in report.lower()


def test_complete_approved_pr_uses_most_recent_approved_review(tmp_path: Path):
    # AC-2, AC-8: dos reviews APPROVED con commit_id y submitted_at
    # distintos; la mas reciente por submitted_at coincide con el head
    # vigente. El gate debe proceder (no rechazar) usando esa mas reciente,
    # ignorando la mas vieja que no coincide.
    repo, bin_dir, log_path = make_repo(tmp_path)

    result = run_gate(repo, bin_dir, log_path, "multi_review_recent_matches")

    assert result.returncode == 0, result.stderr + result.stdout
    log = log_path.read_text(encoding="utf-8")
    assert "pr merge 123 --merge --delete-branch" in log
    report = reports(repo)[0].read_text(encoding="utf-8")
    assert report.startswith("status: approved")


def test_complete_approved_pr_is_rerunnable_after_checks_turn_green(tmp_path: Path):
    # Regresion para el riesgo conocido: el gate post-HITL solo dispara con
    # 'pull_request_review: submitted'. Si Builder pushea commits que
    # arreglan CI despues de un rechazo, nada volvia a disparar el
    # workflow -- pedir otra aprobacion humana violaria el "unico HITL".
    # La correccion real vive en el trigger de
    # post-hitl-merge-gate.yml (agregado 'pull_request: synchronize'),
    # pero eso no se puede probar con pytest; lo que SI se prueba aca es
    # que el script en si es re-ejecutable de forma segura: la misma PR
    # (misma reviewDecision=APPROVED, sin pedir otra aprobacion) puede
    # reintentarse cuantas veces haga falta hasta que los checks esten en
    # verde, y solo entonces mergea.
    repo, bin_dir, log_path = make_repo(tmp_path)

    first = run_gate(repo, bin_dir, log_path, "checks_fail")
    assert first.returncode != 0
    first_log = log_path.read_text(encoding="utf-8")
    assert "pr merge" not in first_log
    assert len(reports(repo)) == 1

    log_path.write_text("", encoding="utf-8")
    second = run_gate(repo, bin_dir, log_path, "success")

    assert second.returncode == 0, second.stderr + second.stdout
    second_log = log_path.read_text(encoding="utf-8")
    assert "pr merge 123 --merge --delete-branch" in second_log
    # 'pr view' se volvio a consultar en vivo (no se reutilizo un estado
    # de aprobacion cacheado de la primera corrida): la reviewDecision
    # segui APPROVED sin que nadie la re-aprobara.
    assert "pr view" in second_log
    assert len(reports(repo)) == 2
    assert reports(repo)[-1].read_text(encoding="utf-8").startswith("status: approved")
