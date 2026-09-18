import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "scripts" / "resolve-agentic-model.ps1"


def powershell() -> str:
    candidates = ["powershell.exe", "pwsh"] if os.name == "nt" else ["pwsh", "powershell"]
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    pytest.skip("PowerShell no esta disponible")


def command_env(**updates: str) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "NUL" if os.name == "nt" else "/dev/null"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    for key in [
        "AGENTIC_OPENCODE_GO_READY",
        "AGENTIC_OPENCODE_ZEN_READY",
        "AGENTIC_OPENROUTER_READY",
        "OPENROUTER_API_KEY",
        "AGENTIC_TEST_MODE",
    ]:
        env.pop(key, None)
    env.update(updates)
    return env


def make_router_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(ROOT / ".agentic", repo / ".agentic")
    subprocess.run(["git", "init"], cwd=repo, env=command_env(), check=True, capture_output=True)
    return repo


def run_router(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROUTER),
            *args,
        ],
        cwd=repo,
        env=env or command_env(),
        text=True,
        capture_output=True,
        check=False,
    )


def output_json(result: subprocess.CompletedProcess[str]) -> dict:
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_explicit_valid_model_is_resolved_and_evidenced(tmp_path: Path):
    repo = make_router_repo(tmp_path)
    evidence = repo / "evidence.jsonl"

    result = run_router(
        repo,
        "-Role",
        "analyst-agent",
        "-Model",
        "opencode-go/kimi-k2.7-code",
        "-Variant",
        "high",
        "-EvidencePath",
        str(evidence),
        env=command_env(AGENTIC_OPENCODE_GO_READY="1"),
    )
    payload = output_json(result)

    assert payload["model_ref"] == "opencode-go/kimi-k2.7-code"
    assert payload["model_selection_origin"] == "explicit-parameter"
    assert payload["variant"] == "high"
    assert payload["fallback_applied"] is False
    assert json.loads(evidence.read_text(encoding="utf-8").splitlines()[0])["result"] == "resolved"


def test_default_model_uses_role_default(tmp_path: Path):
    repo = make_router_repo(tmp_path)

    result = run_router(
        repo,
        "-Role",
        "reviewer",
        "-EvidencePath",
        str(repo / "evidence.jsonl"),
        env=command_env(AGENTIC_OPENCODE_GO_READY="1"),
    )
    payload = output_json(result)

    assert payload["model_ref"] == "opencode-go/kimi-k2.7-code"
    assert payload["variant"] == "high"
    assert payload["model_selection_origin"] == "role-default"


def test_run_yaml_can_select_model_before_spec_exists(tmp_path: Path):
    repo = make_router_repo(tmp_path)
    run_dir = repo / "runs" / "01-demo"
    run_dir.mkdir(parents=True)
    (run_dir / "run.yaml").write_text(
        "execution:\n"
        "  model: opencode/mimo-v2.5-pro\n"
        "  variant: medium\n"
        "  fallback:\n"
        "    - zen\n",
        encoding="utf-8",
    )

    result = run_router(
        repo,
        "-Role",
        "qa-agent",
        "-Feature",
        "01-demo",
        env=command_env(AGENTIC_OPENCODE_ZEN_READY="1"),
    )
    payload = output_json(result)

    assert payload["model_ref"] == "opencode/mimo-v2.5-pro"
    assert payload["model_selection_origin"] == "run-yaml"
    assert (run_dir / "model-routing.jsonl").exists()


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["-Model", "unknown-provider/model", "-Variant", "high"], "Proveedor desconocido"),
        (["-Model", "opencode-go/no-such-model", "-Variant", "high"], "Modelo no autorizado"),
        (["-Model", "opencode-go/kimi-k2.7-code", "-Variant", "turbo"], "Variante invalida"),
    ],
)
def test_invalid_selection_is_rejected(tmp_path: Path, args: list[str], expected: str):
    repo = make_router_repo(tmp_path)

    result = run_router(repo, "-Role", "analyst-agent", "-NoEvidence", *args)

    assert result.returncode != 0
    assert expected in result.stderr


def test_missing_credentials_stop_execution_without_fallback(tmp_path: Path):
    repo = make_router_repo(tmp_path)

    result = run_router(
        repo,
        "-Role",
        "analyst-agent",
        "-Fallback",
        "go",
        "-EvidencePath",
        str(repo / "evidence.jsonl"),
    )

    assert result.returncode != 0
    assert "faltan credenciales" in result.stderr
    event = json.loads((repo / "evidence.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert event["result"] == "failed"
    assert event["cost"] is None


def test_go_quota_failure_falls_back_to_authorized_zen(tmp_path: Path):
    repo = make_router_repo(tmp_path)

    result = run_router(
        repo,
        "-Role",
        "builder-agent",
        "-FailedModel",
        "opencode-go/kimi-k2.7-code",
        "-FailureReason",
        "quota_exhausted",
        "-Fallback",
        "go,zen",
        "-EvidencePath",
        str(repo / "evidence.jsonl"),
        env=command_env(AGENTIC_OPENCODE_ZEN_READY="1"),
    )
    payload = output_json(result)

    assert payload["model_ref"] == "opencode/kimi-k2.7-code"
    assert payload["fallback_applied"] is True
    assert payload["fallback_reason"] == "quota_exhausted"


def test_fallback_not_authorized_stops_after_go_failure(tmp_path: Path):
    repo = make_router_repo(tmp_path)

    result = run_router(
        repo,
        "-Role",
        "builder-agent",
        "-FailedModel",
        "opencode-go/kimi-k2.7-code",
        "-FailureReason",
        "quota_exhausted",
        "-Fallback",
        "go",
        "-EvidencePath",
        str(repo / "evidence.jsonl"),
        env=command_env(AGENTIC_OPENCODE_ZEN_READY="1"),
    )

    assert result.returncode != 0
    assert "No hay modelos disponibles" in result.stderr


def test_openrouter_fallback_requires_explicit_authorization(tmp_path: Path):
    repo = make_router_repo(tmp_path)

    result = run_router(
        repo,
        "-Role",
        "analyst-agent",
        "-FailedModel",
        "opencode-go/kimi-k2.7-code",
        "-FailureReason",
        "unavailable",
        "-Fallback",
        "go,zen,openrouter-free",
        "-EvidencePath",
        str(repo / "evidence.jsonl"),
        env=command_env(OPENROUTER_API_KEY="test-key"),
    )
    payload = output_json(result)

    assert payload["provider"] == "openrouter"
    assert payload["model_ref"] == "openrouter/qwen/qwen3-coder:free"
    assert payload["fallback_applied"] is True


def test_absence_of_all_models_available_fails(tmp_path: Path):
    repo = make_router_repo(tmp_path)

    result = run_router(
        repo,
        "-Role",
        "qa-agent",
        "-Fallback",
        "go,zen",
        "-EvidencePath",
        str(repo / "evidence.jsonl"),
    )

    assert result.returncode != 0
    assert "No hay modelos disponibles" in result.stderr


def test_live_catalog_is_blocked_in_test_mode(tmp_path: Path):
    repo = make_router_repo(tmp_path)

    result = run_router(
        repo,
        "-Role",
        "analyst-agent",
        "-UseLiveCatalog",
        "-NoEvidence",
        env=command_env(AGENTIC_TEST_MODE="1"),
    )

    assert result.returncode != 0
    assert "creditos reales" in result.stderr
