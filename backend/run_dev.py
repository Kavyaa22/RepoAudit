"""Dev server entrypoint — reloads only app/ + src/, never workspace/."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent
_SRC = _BACKEND_ROOT / "src"
sys.path.insert(0, str(_SRC))

import uvicorn


def _port_in_use(host: str, port: int) -> bool:
    """Return True if something is already accepting connections on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            return sock.connect_ex((host, port)) == 0
        except OSError:
            return False


def _kill_zombies_on_port(port: int) -> None:
    """Terminate lingering zombie processes listening on specified port."""
    if sys.platform == "win32":
        try:
            res = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                check=False,
            )
            current_pid = str(os.getpid())
            for line in res.stdout.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid = parts[-1]
                    if pid and pid != "0" and pid != current_pid:
                        subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True, check=False)
        except Exception:
            pass


if __name__ == "__main__":
    host = "0.0.0.0"
    port = 8001
    if _port_in_use("127.0.0.1", port):
        _kill_zombies_on_port(port)

    if _port_in_use("127.0.0.1", port):
        print(
            f"ERROR: port {port} is already in use.\n"
            "Stop every old backend first (Ctrl+C in each terminal running\n"
            "uvicorn / run_dev), then retry.\n"
            "  Get-NetTCPConnection -LocalPort 8000 -State Listen\n"
            "  Stop-Process -Id <OwningProcess> -Force",
            file=sys.stderr,
        )
        raise SystemExit(1)

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=True,
        reload_dirs=[
            str(_BACKEND_ROOT / "app"),
            str(_BACKEND_ROOT / "src"),
        ],
        reload_excludes=[
            "*.pyc",
            "*__pycache__*",
            "*workspace*",
            "*snapshots*",
            "*.json",
            "*.tmp",
        ],
    )
