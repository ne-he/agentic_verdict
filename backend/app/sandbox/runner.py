"""Sandbox runner — eksekusi kode hasil LLM secara TERISOLASI.

Aturan #6: kode LLM HANYA jalan di sini, JANGAN pernah exec()/eval() di proses backend.

Mode utama: Docker (--network none, limit mem/cpu/timeout, non-root, auto-remove).
Fallback (USE_DOCKER=false): subprocess + timeout (+ resource limit di POSIX) — untuk dev cepat,
TIDAK seaman Docker (ada network). Target portfolio tetap Docker.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.config import PROJECT_ROOT, get_settings

# Direktori kerja sementara per-run (di-gitignore: backend/sandbox/tmp/).
TMP_ROOT = PROJECT_ROOT / "backend" / "sandbox" / "tmp"
# Chart PNG dipindah ke sini agar tetap ada setelah run_dir dibersihkan (di-gitignore).
ARTIFACTS_ROOT = PROJECT_ROOT / "backend" / "sandbox" / "artifacts"

# Path konvensi di dalam container.
CONTAINER_DATASET_PATH = "/data/dataset.csv"
CONTAINER_WORKDIR = "/work"

# Preamble yang disuntik ke depan kode user: sediakan DATASET_PATH + backend headless.
_PREAMBLE = """\
import os as _os
import matplotlib as _mpl
_mpl.use("Agg")
DATASET_PATH = _os.environ.get("DATASET_PATH", "{dataset_path}")
"""


class SandboxResult(BaseModel):
    """Hasil satu eksekusi sandbox (internal — bukan kontrak API)."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    duration_ms: int = 0
    chart_paths: list[str] = Field(default_factory=list)
    backend: str = "docker"  # "docker" | "subprocess"

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def _prepare_run_dir(code: str, dataset_path_in_container: str) -> tuple[Path, Path]:
    """Buat dir kerja unik, tulis script.py (preamble + kode user). Return (run_dir, script)."""
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = TMP_ROOT / uuid.uuid4().hex[:12]
    run_dir.mkdir(parents=True, exist_ok=True)
    script = run_dir / "script.py"
    full = _PREAMBLE.format(dataset_path=dataset_path_in_container) + "\n" + code
    script.write_text(full, encoding="utf-8")
    return run_dir, script


def _persist_charts(run_dir: Path) -> list[str]:
    """Pindah PNG ke ARTIFACTS_ROOT/<run> agar tidak ikut terhapus saat cleanup."""
    pngs = sorted(run_dir.glob("*.png"))
    if not pngs:
        return []
    dest_dir = ARTIFACTS_ROOT / run_dir.name
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for p in pngs:
        dest = dest_dir / p.name
        shutil.copy2(p, dest)
        out.append(str(dest))
    return out


def _to_docker_path(p: Path) -> str:
    """Path host untuk bind-mount Docker Desktop (Windows pakai forward slash)."""
    return str(p).replace("\\", "/")


def run_code(code: str, dataset_path: str, timeout_sec: int | None = None) -> SandboxResult:
    """Jalankan `code` terhadap dataset di `dataset_path`. Pilih Docker / subprocess dari settings."""
    settings = get_settings()
    timeout = timeout_sec if timeout_sec is not None else settings.sandbox_timeout_sec
    if settings.use_docker:
        return _run_docker(code, dataset_path, timeout, settings)
    return _run_subprocess(code, dataset_path, timeout)


# ── Docker backend ──────────────────────────────────────────────────────────
def _run_docker(code: str, dataset_path: str, timeout: int, settings) -> SandboxResult:
    import docker  # import lokal agar fallback tak butuh lib docker
    from docker.errors import ContainerError, ImageNotFound
    # Timeout dari container.wait() muncul beda per transport: TCP -> ReadTimeout,
    # Windows named pipe -> ConnectionError(ReadTimeoutError). Tangkap keduanya.
    from requests.exceptions import ConnectionError as ReqConnectionError
    from requests.exceptions import ReadTimeout

    run_dir, _ = _prepare_run_dir(code, CONTAINER_DATASET_PATH)
    ds_path = Path(dataset_path).resolve()
    client = docker.from_env()
    container = None
    started = time.perf_counter()
    timed_out = False
    exit_code: int | None = None
    try:
        container = client.containers.run(
            image=settings.sandbox_image,
            command=["python", f"{CONTAINER_WORKDIR}/script.py"],
            volumes={
                _to_docker_path(run_dir): {"bind": CONTAINER_WORKDIR, "mode": "rw"},
                _to_docker_path(ds_path): {"bind": CONTAINER_DATASET_PATH, "mode": "ro"},
            },
            environment={"DATASET_PATH": CONTAINER_DATASET_PATH, "MPLBACKEND": "Agg"},
            working_dir=CONTAINER_WORKDIR,
            network_mode="none",          # --network none
            mem_limit=f"{settings.sandbox_mem_mb}m",
            nano_cpus=int(settings.sandbox_cpus * 1_000_000_000),
            pids_limit=128,
            detach=True,
        )
        try:
            result = container.wait(timeout=timeout)
            exit_code = result.get("StatusCode")
        except (ReadTimeout, ReqConnectionError):
            timed_out = True
            try:
                container.kill()
            except Exception:
                pass
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", "replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", "replace")
        charts = _persist_charts(run_dir)
        if timed_out:
            stderr = (stderr + f"\n[sandbox] Timeout: kode melebihi {timeout}s dan dihentikan.").strip()
        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
            duration_ms=int((time.perf_counter() - started) * 1000),
            chart_paths=charts,
            backend="docker",
        )
    except ImageNotFound as e:
        raise RuntimeError(
            f"Image sandbox '{settings.sandbox_image}' belum ada. "
            f"Build: docker build -t analyst-sandbox backend/app/sandbox/image"
        ) from e
    except ContainerError as e:  # pragma: no cover - defensive
        return SandboxResult(stderr=str(e), exit_code=1, backend="docker")
    finally:
        if container is not None:
            try:
                container.remove(force=True)  # auto-cleanup
            except Exception:
                pass
        shutil.rmtree(run_dir, ignore_errors=True)


# ── Subprocess fallback (dev) ───────────────────────────────────────────────
# Var sistem yang AMAN diteruskan ke subprocess (dibutuhkan Python/matplotlib/pandas).
# Sengaja TIDAK menyertakan env aplikasi (GEMINI_API_KEY, DATABASE_URL, dll) supaya
# kode LLM tak bisa membaca secret. Whitelist, bukan blacklist.
_SAFE_ENV_KEYS = {
    "PATH", "SYSTEMROOT", "WINDIR", "PATHEXT", "TEMP", "TMP", "TMPDIR",
    "HOME", "HOMEPATH", "HOMEDRIVE", "USERPROFILE",
    "LANG", "LC_ALL", "LC_CTYPE", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
    "PYTHONHOME", "LD_LIBRARY_PATH",
}


def _run_subprocess(code: str, dataset_path: str, timeout: int) -> SandboxResult:
    import os

    ds_path = Path(dataset_path).resolve()
    run_dir, script = _prepare_run_dir(code, str(ds_path).replace("\\", "/"))
    started = time.perf_counter()
    # Env minimal-tapi-cukup: var sistem aman + yang dibutuhkan matplotlib (config dir writable).
    env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
    env["DATASET_PATH"] = str(ds_path)
    env["MPLBACKEND"] = "Agg"
    env["MPLCONFIGDIR"] = str(run_dir)  # matplotlib butuh dir cache yang bisa ditulis
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # Resource limit hanya tersedia di POSIX.
    preexec = None
    try:
        import resource  # noqa: F401 (POSIX-only)

        def _limit():  # pragma: no cover - POSIX only
            import resource as _r

            mem = get_settings().sandbox_mem_mb * 1024 * 1024
            _r.setrlimit(_r.RLIMIT_AS, (mem, mem))

        preexec = _limit
    except ImportError:
        pass  # Windows: tanpa resource limit, andalkan timeout.

    timed_out = False
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(run_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            preexec_fn=preexec,  # type: ignore[arg-type]
        )
        stdout, stderr, exit_code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")) + \
            f"\n[sandbox] Timeout: kode melebihi {timeout}s."
        exit_code = None
    # Persist PNG ke ARTIFACTS_ROOT supaya bisa dilayani GET /artifacts (sama seperti Docker).
    # Penting untuk deploy mode subprocess (USE_DOCKER=false) di Render.
    charts = _persist_charts(run_dir)
    result = SandboxResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        timed_out=timed_out,
        duration_ms=int((time.perf_counter() - started) * 1000),
        chart_paths=charts,
        backend="subprocess",
    )
    return result
