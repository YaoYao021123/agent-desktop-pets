#!/usr/bin/env python3
"""Run the BLE bridge from a macOS .app host with Bluetooth usage metadata."""

from __future__ import annotations

import atexit
import os
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PLUGIN_ROOT.parents[1]
STATE_DIR = Path.home() / ".codex" / "codex-usage-bridge"
PID_PATH = STATE_DIR / "bridge.pid"
LOG_PATH = STATE_DIR / "bridge.log"


def add_local_site_packages() -> None:
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    site_packages = REPO_ROOT / ".venv" / "lib" / version / "site-packages"
    if site_packages.exists():
        sys.path.insert(0, str(site_packages))


def clear_pid() -> None:
    try:
        if PID_PATH.read_text().strip() == str(os.getpid()):
            PID_PATH.unlink()
    except OSError:
        pass


def main() -> int:
    add_local_site_packages()
    sys.path.insert(0, str(PLUGIN_ROOT))
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(f"{os.getpid()}\n")
    atexit.register(clear_pid)

    os.chdir(PLUGIN_ROOT)
    with LOG_PATH.open("a", encoding="utf-8", buffering=1) as log:
        with redirect_stdout(log), redirect_stderr(log):
            print(f"[macos-runner] pid={os.getpid()} plugin_root={PLUGIN_ROOT}", flush=True)
            from scripts import codex_usage_ble_bridge

            bridge_argv = [str(PLUGIN_ROOT / "scripts" / "codex_usage_ble_bridge.py"), *sys.argv[1:]]
            if "--once" in bridge_argv:
                sys.argv = bridge_argv
                return codex_usage_ble_bridge.main()

            while True:
                sys.argv = list(bridge_argv)
                code = codex_usage_ble_bridge.main()
                print(f"[macos-runner] bridge exited code={code}; restarting in 5s", flush=True)
                time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
