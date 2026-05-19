#!/usr/bin/env python3
"""Codex hook entry point for the Codex Usage Stick plugin.

This wrapper writes a small diagnostic record before it starts the BLE bridge.
That makes hook loading problems distinguishable from bridge startup problems.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import select
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
START_BRIDGE = PLUGIN_ROOT / "scripts" / "start_bridge.py"
STATE_DIR = Path.home() / ".codex" / "codex-usage-bridge"
HOOK_LOG_PATH = STATE_DIR / "hook.log"
APPROVAL_SOCK_PATH = STATE_DIR / "approval.sock"
APPROVAL_WAIT_SEC = 45.0
APPROVAL_CONNECT_SEC = 4.0


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def read_stdin_text() -> str:
    """Read hook stdin only when data is already available."""
    try:
        if sys.stdin is None or sys.stdin.closed or sys.stdin.isatty():
            return ""
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return ""
        return sys.stdin.read(65536)
    except Exception as exc:  # pragma: no cover - diagnostic best effort
        return f"<stdin unavailable: {exc}>"


def append_log(record: dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with HOOK_LOG_PATH.open("a", encoding="utf-8") as log:
            log.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass


def env_snapshot() -> dict[str, str | None]:
    keys = [
        "PLUGIN_ROOT",
        "PLUGIN_DATA",
        "CLAUDE_PLUGIN_ROOT",
        "CLAUDE_PLUGIN_DATA",
        "CODEX_HOME",
        "PWD",
    ]
    return {key: os.environ.get(key) for key in keys}


def permission_output(behavior: str, message: str) -> dict[str, Any]:
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": behavior,
                "message": message,
            },
        },
    }


def request_hardware_permission(hook_payload: dict[str, Any]) -> dict[str, Any] | None:
    request = {
        "type": "permission_request",
        "hook": hook_payload,
        "timeout": APPROVAL_WAIT_SEC,
    }
    encoded = (json.dumps(request, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    connect_deadline = time.monotonic() + APPROVAL_CONNECT_SEC
    last_error = ""

    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(max(0.2, min(1.0, connect_deadline - time.monotonic())))
                sock.connect(str(APPROVAL_SOCK_PATH))
                sock.sendall(encoded)
                sock.settimeout(APPROVAL_WAIT_SEC + 2.0)
                raw = sock.makefile("rb").readline(4096)
            if not raw:
                append_log({"time": now_iso(), "event": "PermissionRequest", "phase": "approval_ipc_empty"})
                return None
            response = json.loads(raw.decode("utf-8", errors="replace"))
            append_log({
                "time": now_iso(),
                "event": "PermissionRequest",
                "phase": "approval_ipc_response",
                "response": response,
            })
            if not response.get("ok"):
                return None
            decision = response.get("decision")
            if decision == "allow":
                return permission_output("allow", "Approved from StickS3")
            if decision == "deny":
                return permission_output("deny", "Denied from StickS3")
            return None
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError) as exc:
            last_error = repr(exc)
            if time.monotonic() >= connect_deadline:
                append_log({
                    "time": now_iso(),
                    "event": "PermissionRequest",
                    "phase": "approval_ipc_unavailable",
                    "socket": str(APPROVAL_SOCK_PATH),
                    "error": last_error,
                })
                return None
            time.sleep(0.2)
        except Exception as exc:  # pragma: no cover - keep hook fail-open
            append_log({
                "time": now_iso(),
                "event": "PermissionRequest",
                "phase": "approval_ipc_error",
                "error": repr(exc),
            })
            return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Codex Usage Stick hook entry point.")
    parser.add_argument("--event", default="unknown", help="Hook event name")
    args = parser.parse_args()

    stdin_text = read_stdin_text()
    append_log({
        "time": now_iso(),
        "event": args.event,
        "phase": "received",
        "argv": sys.argv,
        "cwd": os.getcwd(),
        "plugin_root": str(PLUGIN_ROOT),
        "env": env_snapshot(),
        "stdin_preview": stdin_text[:4096],
    })

    try:
        proc = subprocess.run(
            [sys.executable, str(START_BRIDGE)],
            cwd=str(PLUGIN_ROOT),
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        append_log({
            "time": now_iso(),
            "event": args.event,
            "phase": "start_bridge",
            "returncode": proc.returncode,
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        })
    except Exception as exc:  # pragma: no cover - hook must stay non-fatal
        append_log({
            "time": now_iso(),
            "event": args.event,
            "phase": "error",
            "error": repr(exc),
        })

    if args.event == "PermissionRequest":
        try:
            hook_payload = json.loads(stdin_text) if stdin_text else {}
        except json.JSONDecodeError as exc:
            append_log({
                "time": now_iso(),
                "event": args.event,
                "phase": "permission_json_error",
                "error": repr(exc),
            })
            return 0

        decision = request_hardware_permission(hook_payload)
        if decision:
            sys.stdout.write(json.dumps(decision, separators=(",", ":"), ensure_ascii=False))
            sys.stdout.write("\n")
            sys.stdout.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
