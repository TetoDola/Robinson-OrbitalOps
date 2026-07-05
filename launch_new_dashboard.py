from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
PORT = int(os.getenv("ORBITOPS_PORT", "8010"))
URL = f"http://127.0.0.1:{PORT}"


def port_is_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def open_browser_later() -> None:
    time.sleep(1.4)
    webbrowser.open(URL)


def main() -> int:
    os.environ.setdefault("MOCK_CRUSOE", "true")
    os.environ.setdefault("CRUSOE_MODEL", "nvidia/Nemotron-3-Nano-Omni-Reasoning-30B-A3B")

    if port_is_busy(PORT):
        print(f"Port {PORT} is already in use.")
        print("Close the old server window or set ORBITOPS_PORT to another port.")
        print(f"Then open {URL}")
        return 1

    sys.path.insert(0, str(BACKEND))
    print("OrbitOps single-file agent backend")
    print(f"URL: {URL}")
    print("API: /api/simulation/* and /api/agents/*")
    print("Keep this window open while testing.")

    if os.getenv("ORBITOPS_OPEN_BROWSER", "true").lower() in {"1", "true", "yes", "on"}:
        threading.Thread(target=open_browser_later, daemon=True).start()

    uvicorn.run("orbitops_backend:app", host="127.0.0.1", port=PORT, app_dir=str(BACKEND), log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
