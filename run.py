from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


BACKEND_DIR = Path(__file__).resolve().parent
HEALTH_URL = os.environ.get("BACKEND_HEALTH_URL", "http://127.0.0.1:8000/health")
HEALTH_TIMEOUT_SECONDS = 120
HEALTH_POLL_SECONDS = 1


def require_docker() -> None:
    if shutil.which("docker") is None:
        raise SystemExit(
            "Docker is required. Install Docker Desktop/Engine with Compose v2, "
            "then run 'python run.py' again."
        )

    compose_check = subprocess.run(
        ["docker", "compose", "version"],
        cwd=BACKEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if compose_check.returncode != 0:
        raise SystemExit(
            "Docker Compose v2 is not available. Confirm that 'docker compose' "
            "works in a terminal, then run 'python run.py' again."
        )


def validate_compose() -> None:
    result = subprocess.run(
        ["docker", "compose", "config"],
        cwd=BACKEND_DIR,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "The backend Docker Compose configuration is invalid. "
            "Fix the Compose error above before starting the backend."
        )


def url_is_healthy(url: str) -> bool:
    try:
        with urlopen(url, timeout=2) as response:
            return 200 <= response.status < 400
    except (OSError, URLError):
        return False


def wait_for_health(
    process: subprocess.Popen[bytes],
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"Backend Docker Compose exited with code {exit_code} "
                "before the API became healthy."
            )

        if url_is_healthy(HEALTH_URL):
            print(f"[backend] API is healthy at {HEALTH_URL}", flush=True)
            return

        time.sleep(HEALTH_POLL_SECONDS)

    raise RuntimeError(
        f"Backend API did not become healthy within {timeout:.0f} seconds. "
        "Check the Docker Compose output above."
    )


def stop_compose(process: subprocess.Popen[bytes] | None) -> None:
    if process is not None and process.poll() is None:
        try:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        except OSError:
            process.terminate()

    down = subprocess.run(
        ["docker", "compose", "down"],
        cwd=BACKEND_DIR,
        check=False,
    )
    if down.returncode != 0:
        print(
            "[backend] Warning: 'docker compose down' did not complete successfully.",
            flush=True,
        )


def main() -> int:
    require_docker()
    validate_compose()

    print(
        "[backend] Starting the existing backend Compose stack: "
        "PostgreSQL + FastAPI API + scheduler worker.",
        flush=True,
    )
    print(
        "[backend] No Redis/Celery service is started because the repository "
        "does not use them.",
        flush=True,
    )

    compose_process: subprocess.Popen[bytes] | None = None

    try:
        compose_process = subprocess.Popen(
            ["docker", "compose", "up", "--build"],
            cwd=BACKEND_DIR,
        )

        wait_for_health(
            compose_process,
            timeout=HEALTH_TIMEOUT_SECONDS,
        )

        print(
            "[backend] All backend services are running. "
            "Press Ctrl+C to stop them.",
            flush=True,
        )

        while True:
            exit_code = compose_process.poll()
            if exit_code is not None:
                if exit_code == 0:
                    print("[backend] Compose stack stopped.", flush=True)
                    return 0

                raise RuntimeError(
                    f"Backend Docker Compose exited unexpectedly with code {exit_code}."
                )

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n[backend] Stopping backend services...", flush=True)
        return 0
    except RuntimeError as exc:
        print(f"[backend] ERROR: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        if compose_process is not None:
            stop_compose(compose_process)


if __name__ == "__main__":
    sys.exit(main())
