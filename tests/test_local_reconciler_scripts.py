import ctypes
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = ROOT / "scripts" / "local-feature-reconcile.ps1"
SLUG = "99-demo"
BRANCH = f"feature/{SLUG}"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

pytestmark = pytest.mark.skipif(
    os.name != "nt"
    or shutil.which("powershell.exe") is None
    or os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1",
    reason="Requiere Windows con PowerShell 5.1 fuera del sandbox Codex",
)


def powershell() -> str:
    path = shutil.which("powershell.exe")
    if not path:
        pytest.skip("PowerShell no esta disponible")
    return path


def command_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "NUL"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["NO_COLOR"] = "1"
    env["TERM"] = "dumb"
    return env


def run(command: list[str], cwd: Path, check: bool = True):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=command_env(),
        text=True,
        capture_output=True,
        check=False,
        creationflags=CREATE_NO_WINDOW,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"Command failed: {command}\n{result.stdout}\n{result.stderr}")
    return result


def git(repo: Path, *args: str, check: bool = True):
    return run(["git", *args], repo, check=check)


def write_roadmap(repo: Path, entries: dict[str, str]) -> None:
    lines = ["# Roadmap", "", "## Features", ""]
    for slug, marker in entries.items():
        lines.append(f"- [{marker}] {slug} — Feature {slug}")
    (repo / "ROADMAP.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_repo(tmp_path: Path) -> tuple[Path, Path]:
    seed = tmp_path / "seed"
    origin = tmp_path / "origin.git"
    main = tmp_path / "main"
    run(["git", "init", "-b", "develop", str(seed)], tmp_path)
    git(seed, "config", "user.email", "test@example.com")
    git(seed, "config", "user.name", "Test")
    write_roadmap(seed, {SLUG: " "})
    git(seed, "add", "ROADMAP.md")
    git(seed, "commit", "-m", "init")
    run(["git", "clone", "--bare", str(seed), str(origin)], tmp_path)
    run(["git", "clone", str(origin), str(main)], tmp_path)
    git(main, "config", "user.email", "test@example.com")
    git(main, "config", "user.name", "Test")
    return origin, main


def push_remote_roadmap(main: Path, entries: dict[str, str]) -> None:
    write_roadmap(main, entries)
    git(main, "add", "ROADMAP.md")
    git(main, "commit", "-m", "roadmap")
    git(main, "push", "origin", "develop")


def run_capture_to_files(
    command: list[str], cwd: Path, tmp_path: Path, name: str
) -> subprocess.CompletedProcess[str]:
    """Como `run()`, pero redirige stdout/stderr del proceso lanzado a archivos
    reales en vez de PIPE (`capture_output=True`).

    Necesario para el launcher `-StartBackground`: ese proceso lanza a su vez
    un reconciliador de fondo vía `Start-Process` en PowerShell, que -- a
    diferencia de `subprocess.Popen` de Python (>=3.7, que restringe la
    herencia de handles solo a los explicitos vía
    PROC_THREAD_ATTRIBUTE_HANDLE_LIST) -- no restringe que handles hereda: con
    `capture_output=True` el nieto termina heredando tambien el extremo de
    escritura del pipe stdout/stderr que Python le paso al launcher, aunque su
    propia salida vaya a archivos. Ese duplicado mantiene el pipe sin EOF
    hasta que el nieto termina (hasta `MaxMinutes` despues), bloqueando
    innecesariamente `subprocess.run()`/`communicate()` mucho despues de que
    el launcher ya devolvio el control. Redirigiendo a archivos reales no hay
    pipe que el nieto pueda mantener abierto: Python solo espera a que el
    proceso launcher termine (via su handle de proceso), no a un EOF de pipe.
    """
    out_path = tmp_path / f"{name}.launcher.out.log"
    err_path = tmp_path / f"{name}.launcher.err.log"
    with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=command_env(),
            stdout=out_f,
            stderr=err_f,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    return subprocess.CompletedProcess(
        command,
        result.returncode,
        out_path.read_text(encoding="utf-8", errors="replace"),
        err_path.read_text(encoding="utf-8", errors="replace"),
    )


def start_reconciler(
    cwd: Path,
    slug: str,
    tmp_path: Path,
    worktree_dir: Path | None = None,
    poll_seconds: int = 1,
    max_minutes: int = 2,
) -> subprocess.CompletedProcess[str]:
    command = [
        powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(START_SCRIPT),
        "-Slug",
        slug,
        "-StartBackground",
        "-PollSeconds",
        str(poll_seconds),
        "-MaxMinutes",
        str(max_minutes),
    ]
    if worktree_dir is not None:
        command.extend(["-WorktreeDir", str(worktree_dir)])
    return run_capture_to_files(command, cwd, tmp_path, slug)


def run_reconciler_foreground(
    cwd: Path,
    slug: str,
    tmp_path: Path,
    worktree_dir: Path | None = None,
    poll_seconds: int = 1,
    max_minutes: int = 2,
) -> subprocess.CompletedProcess[str]:
    """Ejecuta el motor en primer plano para probar lifecycle.

    Los tests de arranque cubren `-StartBackground`. Los tests de limpieza
    prueban aquí el motor directamente para no hacer depender la verificación
    de ROADMAP de la supervivencia de un proceso nieto del host de pytest.
    Esa separación evita falsos timeouts sin relajar el gate Windows.
    """
    command = [
        powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(START_SCRIPT),
        "-Slug",
        slug,
        "-PollSeconds",
        str(poll_seconds),
        "-MaxMinutes",
        str(max_minutes),
    ]
    if worktree_dir is not None:
        command.extend(["-WorktreeDir", str(worktree_dir)])
    return run(command, cwd, check=False)


def state_dir(main: Path) -> Path:
    return main / ".git" / "feature-reconcilers"


def lock_path(main: Path, slug: str) -> Path:
    return state_dir(main) / f"{slug}.pid"


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def process_alive(pid: int) -> bool:
    """Comprueba si `pid` sigue vivo vía Win32 (OpenProcess/GetExitCodeProcess)
    directamente desde ctypes, en vez de lanzar `powershell.exe -Command
    "Get-Process -Id ..."` como subproceso. Lanzar un proceso PowerShell
    nuevo por cada verificacion (potencialmente decenas de veces por
    segundo durante `wait_for_reconciler_running`) demostro dar falsos
    negativos poco fiables tanto en maquinas locales como en runners
    limpios de GitHub Actions windows-latest sin ningun EDR de por medio
    (ver docs/tecnica/circuito-agentico.md, seccion "Bug real corregido"):
    el reconciliador arrancaba y corria correctamente (log con contenido
    real, proceso vivo y haciendo fetch) mientras esta comprobacion
    reportaba "no arranco". La consulta nativa vía OpenProcess no depende
    de lanzar ni parsear salida de un proceso externo.
    """
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def kill_pid(pid: int) -> None:
    run(["taskkill", "/PID", str(pid), "/T", "/F"], Path(os.getcwd()), check=False)


def wait_until(predicate, timeout_seconds: float, message: str):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1)
    raise AssertionError(message)


def wait_for_reconciler_running(main: Path, slug: str, timeout_seconds: float = 60.0) -> int:
    lock = lock_path(main, slug)

    def started() -> bool:
        if not lock.exists():
            return False
        raw = lock.read_text(encoding="ascii", errors="replace").strip()
        return raw.isdigit() and process_alive(int(raw))

    wait_until(
        started,
        timeout_seconds,
        f"El reconciliador de {slug} no arranco en {timeout_seconds}s (log/lock ausentes).",
    )
    return int(lock.read_text(encoding="ascii", errors="replace").strip())


def wait_for_reconciler_finished(main: Path, slug: str, timeout_seconds: float = 90.0) -> None:
    lock = lock_path(main, slug)
    wait_until(
        lambda: not lock.exists(),
        timeout_seconds,
        f"El reconciliador de {slug} no termino en {timeout_seconds}s.",
    )


def find_lock_pids(tmp_path: Path) -> list[int]:
    pids: list[int] = []
    for lock in tmp_path.glob("*/main/.git/feature-reconcilers/*.pid"):
        raw = lock.read_text(encoding="ascii", errors="replace").strip()
        if raw.isdigit():
            pids.append(int(raw))
    return pids


@pytest.fixture
def cleanup_reconcilers(tmp_path):
    try:
        yield
    finally:
        for pid in find_lock_pids(tmp_path):
            kill_pid(pid)


def make_worktree(main: Path, tmp_path: Path, name: str, slug: str) -> Path:
    worktree = tmp_path / name
    git(main, "worktree", "add", str(worktree), "-b", f"feature/{slug}")
    return worktree


def branch_exists(main: Path, branch: str) -> bool:
    return git(main, "branch", "--list", branch).stdout.strip() != ""


def test_start_reconciler_from_linked_worktree(tmp_path, cleanup_reconcilers):
    _, main = make_repo(tmp_path)
    worktree = make_worktree(main, tmp_path, "wt-demo", SLUG)
    assert (worktree / ".git").is_file()
    result = start_reconciler(worktree, SLUG, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    wait_for_reconciler_running(main, SLUG)
    assert (state_dir(main) / f"{SLUG}.log").exists()
    assert not (worktree / ".git" / "feature-reconcilers").exists()


def test_start_reconciler_does_not_duplicate_while_running(tmp_path, cleanup_reconcilers):
    _, main = make_repo(tmp_path)
    sleeper = subprocess.Popen(
        [powershell(), "-NoProfile", "-Command", "Start-Sleep -Seconds 120"],
        env=command_env(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )
    try:
        lock = lock_path(main, SLUG)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(sleeper.pid), encoding="ascii")
        result = start_reconciler(main, SLUG, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "Ya existe un reconciliador local" in result.stdout
        assert lock.read_text(encoding="ascii").strip() == str(sleeper.pid)
    finally:
        sleeper.terminate()
        sleeper.wait(timeout=30)


def test_start_reconciler_replaces_stale_lock(tmp_path, cleanup_reconcilers):
    _, main = make_repo(tmp_path)
    lock = lock_path(main, SLUG)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("400000001", encoding="ascii")
    result = start_reconciler(main, SLUG, tmp_path, worktree_dir=tmp_path / "no-matter")
    assert result.returncode == 0, result.stdout + result.stderr
    pid = wait_for_reconciler_running(main, SLUG)
    assert int(lock.read_text(encoding="ascii").strip()) == pid


def test_reconciler_cleans_worktree_and_branch_when_remote_closed(tmp_path, cleanup_reconcilers):
    _, main = make_repo(tmp_path)
    worktree = make_worktree(main, tmp_path, "wt-demo", SLUG)
    push_remote_roadmap(main, {SLUG: "x"})
    result = run_reconciler_foreground(main, SLUG, tmp_path, worktree_dir=worktree)
    assert result.returncode == 0, result.stdout + result.stderr
    wait_for_reconciler_finished(main, SLUG)
    assert not worktree.exists()
    assert not branch_exists(main, BRANCH)
    assert "Reconciliacion local completa" in result.stdout
    assert main.exists()
    assert (main / "ROADMAP.md").exists()


def test_reconciler_cleans_only_target_worktree_and_branch(tmp_path, cleanup_reconcilers):
    _, main = make_repo(tmp_path)
    alpha = make_worktree(main, tmp_path, "wt-alpha", "98-alpha")
    beta = make_worktree(main, tmp_path, "wt-beta", "97-beta")
    push_remote_roadmap(main, {"98-alpha": "x", "97-beta": " "})
    result = run_reconciler_foreground(main, "98-alpha", tmp_path, worktree_dir=alpha)
    assert result.returncode == 0, result.stdout + result.stderr
    wait_for_reconciler_finished(main, "98-alpha")
    assert not alpha.exists()
    assert not branch_exists(main, "feature/98-alpha")
    assert beta.exists()
    assert branch_exists(main, "feature/97-beta")


def test_reconciler_never_removes_dirty_worktree(tmp_path, cleanup_reconcilers):
    _, main = make_repo(tmp_path)
    worktree = make_worktree(main, tmp_path, "wt-demo", SLUG)
    (worktree / "draft.txt").write_text("trabajo no confirmado", encoding="utf-8")
    push_remote_roadmap(main, {SLUG: "x"})
    result = run_reconciler_foreground(main, SLUG, tmp_path, worktree_dir=worktree)
    assert result.returncode != 0, result.stdout + result.stderr
    wait_for_reconciler_finished(main, SLUG)
    assert worktree.exists()
    assert (worktree / "draft.txt").read_text(encoding="utf-8") == "trabajo no confirmado"
    assert branch_exists(main, BRANCH)
    assert (result.stdout + result.stderr).strip() != ""


def test_start_reconciler_returns_quickly(tmp_path, cleanup_reconcilers):
    """Regresion: start_reconciler() debe retornar en cuanto el launcher
    confirma el arranque del reconciliador de fondo (~2s), no quedar
    bloqueado hasta que ese reconciliador de fondo termine (hasta
    max_minutes despues). Ver run_capture_to_files() para el mecanismo:
    con capture_output=True (PIPE) el reconciliador de fondo hereda el
    extremo de escritura del pipe stdout/stderr del launcher y lo mantiene
    abierto hasta que el termina, bloqueando subprocess.run() de forma
    artificial.
    """
    _, main = make_repo(tmp_path)
    start = time.monotonic()
    result = start_reconciler(main, SLUG, tmp_path, worktree_dir=tmp_path / "no-matter", max_minutes=2)
    elapsed = time.monotonic() - start
    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed < 10, (
        f"start_reconciler() tardo {elapsed:.1f}s en retornar (limite 10s); "
        "esto indica que quedo bloqueado esperando al reconciliador de "
        "fondo en vez de retornar en cuanto el launcher confirmo el arranque."
    )
