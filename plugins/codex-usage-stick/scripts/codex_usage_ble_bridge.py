#!/usr/bin/env python3
"""
Send local Codex usage to the StickS3 Codex usage firmware over BLE.

The firmware exposes a Nordic UART Service-compatible BLE endpoint. This
script reads the latest Codex token_count event from ~/.codex, builds the
small JSON packet the firmware expects, then writes it to the NUS RX
characteristic.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import shutil
import sqlite3
import sys
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # pragma: no cover - user-facing dependency path
    BleakClient = None
    BleakScanner = None


NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
DEFAULT_CODEX_HOME = Path.home() / ".codex"
DEFAULT_CODEX_APP_CLI = Path("/Applications/Codex.app/Contents/Resources/codex")
STATE_DIR = Path.home() / ".codex" / "codex-usage-bridge"
DEFAULT_HOOK_APPROVAL_SOCK = STATE_DIR / "approval.sock"
SNAPSHOT_CACHE_PATH = STATE_DIR / "last_usage_snapshot.json"
PRIMARY_RESET_WINDOW_SEC = 5 * 60 * 60
SECONDARY_RESET_WINDOW_SEC = 7 * 24 * 60 * 60

INTERESTING_LINE_MARKERS = (
    "token_count",
    "task_started",
    "task_complete",
    "approval",
    "permission",
    "confirm",
    "rate_limit",
    "rate limit",
    "error",
    "failed",
    "exception",
    "traceback",
    "timed out",
)

ATTENTION_EVENT_TYPES = {
    "approval_request",
    "approval_requested",
    "apply_patch_approval_request",
    "permission_request",
    "permission_requested",
    "user_approval_request",
    "tool_approval_request",
}

DIZZY_EVENT_TYPES = {
    "error",
    "fatal_error",
    "task_failed",
    "rate_limit",
    "rate_limit_reached",
}


def newer_ts(left: float | None, right: float | None) -> float | None:
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def is_recent(ts: float | None, window: float, now: float | None = None) -> bool:
    if ts is None:
        return False
    now = time.time() if now is None else now
    return 0 <= now - ts <= window


class ActivityTracker:
    def __init__(self) -> None:
        self.last_tokens: int | None = None
        self.last_event_ts: float | None = None
        self.last_growth_at: float | None = None

    def state_for(self, snapshot: "UsageSnapshot", busy_window: float) -> str:
        now = time.time()

        if self.last_tokens is None:
            self.last_tokens = snapshot.tokens
            self.last_event_ts = snapshot.event_ts
            if snapshot.event_ts and now - snapshot.event_ts <= busy_window:
                self.last_growth_at = now
                return "busy"
            return "idle"

        if snapshot.tokens > self.last_tokens:
            self.last_tokens = snapshot.tokens
            self.last_event_ts = snapshot.event_ts
            self.last_growth_at = now
            return "busy"

        if snapshot.tokens < self.last_tokens:
            self.last_tokens = snapshot.tokens
            self.last_event_ts = snapshot.event_ts
            self.last_growth_at = now
            return "busy"

        if snapshot.event_ts and snapshot.event_ts != self.last_event_ts:
            self.last_event_ts = snapshot.event_ts
            if now - snapshot.event_ts <= busy_window:
                self.last_growth_at = now
                return "busy"

        if self.last_growth_at and now - self.last_growth_at <= busy_window:
            return "busy"
        return "idle"


@dataclass
class UsageSnapshot:
    tokens: int
    primary: int
    secondary: int
    primary_resets_at: int
    secondary_resets_at: int
    source: Path
    event_ts: float | None
    limit_id: str | None
    limit_name: str | None
    task_started_at: float | None = None
    task_complete_at: float | None = None
    attention_at: float | None = None
    dizzy_at: float | None = None
    last_activity_at: float | None = None

    def packet(self, state: str) -> dict[str, Any]:
        now = int(time.time())
        return {
            "state": state,
            "tokens": self.tokens,
            "primary": self.primary,
            "secondary": self.secondary,
            "primary_resets_at": roll_reset_at(self.primary_resets_at, PRIMARY_RESET_WINDOW_SEC, now),
            "secondary_resets_at": roll_reset_at(self.secondary_resets_at, SECONDARY_RESET_WINDOW_SEC, now),
            "now": now,
        }


def roll_reset_at(reset_at: int, window_sec: int, now: int) -> int:
    if reset_at <= 0 or window_sec <= 0 or reset_at > now:
        return reset_at
    windows_elapsed = (now - reset_at) // window_sec + 1
    return reset_at + windows_elapsed * window_sec


def limit_matches(limit_id: str | None, preferred_limit_id: str) -> bool:
    value = str(limit_id or "")
    preferred = str(preferred_limit_id or "")
    if not value:
        return False
    if value == preferred:
        return True
    return bool(preferred) and value.startswith(f"{preferred}_")


def snapshot_has_rate_limit(snapshot: UsageSnapshot, preferred_limit_id: str) -> bool:
    return (
        limit_matches(snapshot.limit_id, preferred_limit_id)
        and snapshot.primary_resets_at > 0
        and snapshot.secondary_resets_at > 0
    )


def snapshot_event_key(snapshot: UsageSnapshot) -> float:
    return snapshot.event_ts or 0.0


def attach_activity(snapshot: UsageSnapshot, activity: UsageSnapshot) -> UsageSnapshot:
    return replace(
        snapshot,
        task_started_at=activity.task_started_at,
        task_complete_at=activity.task_complete_at,
        attention_at=activity.attention_at,
        dizzy_at=activity.dizzy_at,
        last_activity_at=activity.last_activity_at,
    )


def merge_latest_tokens(snapshot: UsageSnapshot, latest: UsageSnapshot | None) -> UsageSnapshot:
    if not latest or snapshot_event_key(latest) <= snapshot_event_key(snapshot):
        return snapshot
    return replace(
        snapshot,
        tokens=latest.tokens,
        source=latest.source,
        event_ts=latest.event_ts,
        task_started_at=latest.task_started_at,
        task_complete_at=latest.task_complete_at,
        attention_at=latest.attention_at,
        dizzy_at=latest.dizzy_at,
        last_activity_at=latest.last_activity_at,
    )


def snapshot_to_cache(snapshot: UsageSnapshot) -> dict[str, Any]:
    return {
        "tokens": snapshot.tokens,
        "primary": snapshot.primary,
        "secondary": snapshot.secondary,
        "primary_resets_at": snapshot.primary_resets_at,
        "secondary_resets_at": snapshot.secondary_resets_at,
        "source": str(snapshot.source),
        "event_ts": snapshot.event_ts,
        "limit_id": snapshot.limit_id,
        "limit_name": snapshot.limit_name,
        "saved_at": time.time(),
    }


def snapshot_from_cache(path: Path) -> UsageSnapshot | None:
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    try:
        return UsageSnapshot(
            tokens=int(data.get("tokens") or 0),
            primary=clamp_percent(data.get("primary")),
            secondary=clamp_percent(data.get("secondary")),
            primary_resets_at=int(data.get("primary_resets_at") or 0),
            secondary_resets_at=int(data.get("secondary_resets_at") or 0),
            source=Path(data.get("source") or path),
            event_ts=float(data["event_ts"]) if data.get("event_ts") is not None else None,
            limit_id=data.get("limit_id"),
            limit_name=data.get("limit_name"),
        )
    except (TypeError, ValueError):
        return None


def save_snapshot_cache(snapshot: UsageSnapshot) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_CACHE_PATH.write_text(json.dumps(snapshot_to_cache(snapshot), separators=(",", ":")))
    except OSError:
        pass


def clamp_percent(value: Any) -> int:
    try:
        n = round(float(value))
    except (TypeError, ValueError):
        n = 0
    return max(0, min(100, n))


def parse_timestamp(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def tail_lines(path: Path, max_bytes: int) -> list[str]:
    size = path.stat().st_size
    with path.open("rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
            f.readline()  # drop partial first line
        data = f.read()
    return data.decode("utf-8", errors="replace").splitlines()


def latest_rollout_paths(codex_home: Path, thread_id: str | None, limit: int) -> list[Path]:
    db = codex_home / "state_5.sqlite"
    if not db.exists():
        raise FileNotFoundError(f"Codex state database not found: {db}")

    con = sqlite3.connect(db)
    try:
        if thread_id:
            rows = con.execute(
                "select rollout_path from threads where id = ? limit 1",
                (thread_id,),
            ).fetchall()
        else:
            rows = con.execute(
                """
                select rollout_path
                from threads
                where rollout_path is not null and rollout_path != ''
                order by coalesce(updated_at_ms, updated_at * 1000) desc
                limit ?
                """,
                (limit,),
            ).fetchall()
    finally:
        con.close()

    paths: list[Path] = []
    for (raw,) in rows:
        p = Path(raw).expanduser()
        if p.exists():
            paths.append(p)
    return paths


def event_payload_text(payload: dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, default=str).lower()
    except (TypeError, ValueError):
        return str(payload).lower()


def payload_wants_attention(payload: dict[str, Any]) -> bool:
    payload_type = str(payload.get("type") or "").lower()
    if payload_type in ATTENTION_EVENT_TYPES:
        return True
    return (
        any(word in payload_type for word in ("approval", "permission", "confirm"))
        and "request" in payload_type
    )


def payload_looks_dizzy(payload: dict[str, Any]) -> bool:
    payload_type = str(payload.get("type") or "").lower()
    if payload_type in DIZZY_EVENT_TYPES:
        return True
    if payload.get("rate_limit_reached_type"):
        return True
    if payload_type != "function_call_output":
        return False

    output = str(payload.get("output") or "").lower()
    if "process exited with code 0" in output[:300]:
        return False
    return any(
        word in output
        for word in ("rate_limit_reached", "rate limit", "fatal error", "traceback", "exception", "timed out")
    )


def extract_token_counts(path: Path, max_bytes: int) -> list[UsageSnapshot]:
    snapshots: list[UsageSnapshot] = []
    task_started_at: float | None = None
    task_complete_at: float | None = None
    attention_at: float | None = None
    dizzy_at: float | None = None
    last_activity_at: float | None = None

    for line in tail_lines(path, max_bytes):
        lower_line = line.lower()
        if not any(marker in lower_line for marker in INTERESTING_LINE_MARKERS):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        payload = event.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get("type")
        event_ts = parse_timestamp(event.get("timestamp"))

        if payload_type in {"token_count", "task_started", "task_complete"}:
            last_activity_at = newer_ts(last_activity_at, event_ts)
        if payload_type == "task_started":
            task_started_at = newer_ts(task_started_at, event_ts)
        elif payload_type == "task_complete":
            task_complete_at = newer_ts(task_complete_at, event_ts)

        if payload_wants_attention(payload):
            attention_at = newer_ts(attention_at, event_ts)
        if payload_looks_dizzy(payload):
            dizzy_at = newer_ts(dizzy_at, event_ts)

        if payload_type != "token_count":
            continue

        info = payload.get("info") or {}
        total_usage = info.get("total_token_usage") or {}
        rate_limits = payload.get("rate_limits") or {}
        primary = rate_limits.get("primary") or {}
        secondary = rate_limits.get("secondary") or {}

        snapshot = UsageSnapshot(
            tokens=int(total_usage.get("total_tokens") or 0),
            primary=clamp_percent(primary.get("used_percent")),
            secondary=clamp_percent(secondary.get("used_percent")),
            primary_resets_at=int(primary.get("resets_at") or 0),
            secondary_resets_at=int(secondary.get("resets_at") or 0),
            source=path,
            event_ts=event_ts,
            limit_id=rate_limits.get("limit_id"),
            limit_name=rate_limits.get("limit_name"),
        )
        snapshots.append(snapshot)

    for snapshot in snapshots:
        snapshot.task_started_at = task_started_at
        snapshot.task_complete_at = task_complete_at
        snapshot.attention_at = attention_at
        snapshot.dizzy_at = dizzy_at
        snapshot.last_activity_at = last_activity_at
    return snapshots


def choose_best_rate_limit_snapshot(
    snapshots: list[UsageSnapshot],
    preferred_limit_id: str,
    preferred_fresh_window: float = 180.0,
) -> UsageSnapshot | None:
    valid = [s for s in snapshots if snapshot_has_rate_limit(s, preferred_limit_id)]
    if not valid:
        return None

    latest_ts = max(snapshot_event_key(s) for s in valid)
    fresh = [s for s in valid if latest_ts - snapshot_event_key(s) <= preferred_fresh_window]
    exact = [s for s in fresh if s.limit_id == preferred_limit_id]
    return max(exact or fresh, key=snapshot_event_key)


def read_usage(args: argparse.Namespace) -> UsageSnapshot:
    paths = latest_rollout_paths(args.codex_home, args.thread_id, args.thread_scan_limit)
    if args.rollout:
        paths.insert(0, args.rollout)

    snapshots: list[UsageSnapshot] = []
    seen: set[Path] = set()
    for path in paths:
        path = path.expanduser().resolve()
        if path in seen or not path.exists():
            continue
        seen.add(path)
        snapshots.extend(extract_token_counts(path, args.tail_bytes))

    latest_any = max(snapshots, key=snapshot_event_key) if snapshots else None
    best = choose_best_rate_limit_snapshot(snapshots, args.limit_id)
    cached = getattr(read_usage, "_last_valid_snapshot", None)
    if cached is None:
        cached = snapshot_from_cache(SNAPSHOT_CACHE_PATH)
    if cached and not snapshot_has_rate_limit(cached, args.limit_id):
        cached = None

    if best and (not cached or snapshot_event_key(best) >= snapshot_event_key(cached)):
        if latest_any:
            best = attach_activity(best, latest_any)
        setattr(read_usage, "_last_valid_snapshot", best)
        save_snapshot_cache(best)
        return best

    if cached:
        return merge_latest_tokens(cached, latest_any)

    if best:
        setattr(read_usage, "_last_valid_snapshot", best)
        save_snapshot_cache(best)
        return best

    if latest_any:
        return latest_any

    raise RuntimeError("No Codex token_count event found in recent rollout files")


def choose_state(args: argparse.Namespace, snapshot: UsageSnapshot, tracker: ActivityTracker) -> str:
    if args.state != "auto":
        return args.state

    now = time.time()
    latest_start = snapshot.task_started_at or 0
    if is_recent(snapshot.attention_at, args.attention_window, now):
        return "attention"
    if (
        snapshot.task_complete_at
        and snapshot.task_complete_at >= latest_start
        and is_recent(snapshot.task_complete_at, args.completed_window, now)
    ):
        return "completed"
    # Dizzy is owned by the StickS3 IMU shake gesture, not by Codex logs.

    state = tracker.state_for(snapshot, args.busy_window)
    last_activity_at = snapshot.last_activity_at or snapshot.event_ts
    if state == "idle" and last_activity_at and now - last_activity_at >= args.sleep_window:
        return "sleep"
    return state


def short_text(value: Any, fallback: str, limit: int) -> str:
    text = str(value or fallback).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "..."


class BleSession:
    def __init__(self, args: argparse.Namespace, client: BleakClient) -> None:
        self.args = args
        self.client = client
        self.incoming: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._notify_buffer = ""
        self._loop = asyncio.get_running_loop()
        self._write_lock = asyncio.Lock()

    async def start_notify(self) -> None:
        try:
            await self.client.start_notify(NUS_TX_UUID, self._on_notify)
        except Exception as exc:
            print(f"[ble] notifications unavailable: {exc}", file=sys.stderr)

    def _on_notify(self, _sender: Any, data: bytearray) -> None:
        self._notify_buffer += bytes(data).decode("utf-8", errors="replace")
        while "\n" in self._notify_buffer:
            raw, self._notify_buffer = self._notify_buffer.split("\n", 1)
            line = raw.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                if self.args.verbose:
                    print(f"[ble] ignoring non-json notify: {line}", file=sys.stderr)
                continue
            self._loop.call_soon_threadsafe(self.incoming.put_nowait, msg)

    async def write_json(self, packet: dict[str, Any]) -> str:
        payload = (json.dumps(packet, separators=(",", ":")) + "\n").encode("utf-8")
        async with self._write_lock:
            for i in range(0, len(payload), self.args.chunk_size):
                chunk = payload[i:i + self.args.chunk_size]
                await self.client.write_gatt_char(NUS_RX_UUID, chunk, response=not self.args.no_response)
                await asyncio.sleep(self.args.chunk_delay)
        return payload.decode("utf-8").strip()


APPROVAL_METHODS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "item/permissions/requestApproval",
    "execCommandApproval",
    "applyPatchApproval",
}


class CodexApprovalProxy:
    def __init__(self, args: argparse.Namespace, ble: BleSession) -> None:
        self.args = args
        self.ble = ble
        self.proc: asyncio.subprocess.Process | None = None
        self.pending: dict[str, dict[str, Any]] = {}
        self.pending_order: list[str] = []
        self.active_prompt_id: str | None = None
        self.next_prompt_num = 1
        self.enabled = False
        self.ipc_server: asyncio.AbstractServer | None = None

    def has_pending(self) -> bool:
        return bool(self.pending)

    async def start_ipc_server(self) -> None:
        sock = self.args.hook_approval_sock
        if not sock:
            return
        sock.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(FileNotFoundError):
            sock.unlink()
        try:
            self.ipc_server = await asyncio.start_unix_server(
                self._handle_ipc_client,
                path=str(sock),
            )
            with contextlib.suppress(OSError):
                sock.chmod(0o600)
            if self.args.verbose:
                print(f"[approval] hook IPC listening at {sock}", file=sys.stderr)
        except Exception as exc:
            print(f"[approval] hook IPC unavailable: {exc}", file=sys.stderr)

    async def close_ipc_server(self) -> None:
        if self.ipc_server:
            self.ipc_server.close()
            await self.ipc_server.wait_closed()
            self.ipc_server = None
        sock = self.args.hook_approval_sock
        if sock:
            with contextlib.suppress(FileNotFoundError):
                sock.unlink()

    async def _handle_ipc_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        response: dict[str, Any]
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=2.0)
            request = json.loads(raw.decode("utf-8", errors="replace"))
            if request.get("type") != "permission_request":
                response = {"ok": False, "reason": "unsupported request"}
            else:
                timeout = float(request.get("timeout") or self.args.hook_approval_timeout)
                hook_payload = request.get("hook") or {}
                decision = await self.request_hook_permission(hook_payload, timeout)
                if decision:
                    response = {"ok": True, "decision": decision}
                else:
                    response = {"ok": False, "reason": "timeout"}
        except Exception as exc:
            response = {"ok": False, "reason": repr(exc)}

        writer.write((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))
        with contextlib.suppress(Exception):
            await writer.drain()
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()

    async def inject_test_request(self) -> None:
        prompt_id = f"test{self.next_prompt_num}"
        self.next_prompt_num += 1
        self.pending[prompt_id] = {
            "method": "testApproval",
            "rpc_id": None,
            "params": {"reason": "A accept / B cancel"},
        }
        self.pending_order.append(prompt_id)
        if self.args.verbose:
            print(f"[approval] injected test request {prompt_id}", file=sys.stderr)
        if not self.active_prompt_id:
            await self._show_next_prompt()

    async def request_hook_permission(self, hook_payload: dict[str, Any], timeout: float) -> str | None:
        prompt_id = f"h{self.next_prompt_num}"
        self.next_prompt_num += 1
        future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
        self.pending[prompt_id] = {
            "method": "hookPermissionRequest",
            "rpc_id": None,
            "params": hook_payload,
            "future": future,
        }
        self.pending_order.append(prompt_id)
        if self.args.verbose:
            tool = hook_payload.get("tool_name") if isinstance(hook_payload, dict) else None
            print(f"[approval] hook request {prompt_id}: {tool or 'permission'}", file=sys.stderr)
        if not self.active_prompt_id:
            await self._show_next_prompt()

        try:
            raw_decision = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._remove_pending(prompt_id)
            if self.active_prompt_id == prompt_id:
                self.active_prompt_id = None
                await self._show_next_prompt()
            if self.args.verbose:
                print(f"[approval] hook request {prompt_id} timed out", file=sys.stderr)
            return None

        if raw_decision == "accept":
            return "allow"
        if raw_decision == "cancel":
            return "deny"
        return None

    async def start(self) -> None:
        if self.args.no_approval_proxy:
            return

        codex_cli = self.args.codex_cli
        if not codex_cli:
            found = shutil.which("codex")
            codex_cli = Path(found) if found else DEFAULT_CODEX_APP_CLI
        if not codex_cli.exists():
            print(
                f"[approval] codex CLI not found at {codex_cli}; approval proxy disabled",
                file=sys.stderr,
            )
            return

        cmd = [str(codex_cli), "app-server", "proxy"]
        if self.args.approval_sock:
            cmd.extend(["--sock", str(self.args.approval_sock)])

        try:
            self.proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            print("[approval] codex CLI not found; approval proxy disabled", file=sys.stderr)
            return
        except Exception as exc:
            print(f"[approval] could not start proxy: {exc}", file=sys.stderr)
            return

        self.enabled = True
        asyncio.create_task(self._read_stdout())
        asyncio.create_task(self._read_stderr())
        await self._send_rpc(
            {
                "jsonrpc": "2.0",
                "id": "codex-usage-bridge-init",
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "codex-usage-ble-bridge",
                        "title": "Codex Usage BLE Bridge",
                        "version": "0.1",
                    },
                    "capabilities": {
                        "experimentalApi": True,
                        "optOutNotificationMethods": [],
                    },
                },
            }
        )

    async def _read_stdout(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                self.enabled = False
                return
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                if self.args.verbose:
                    print(f"[approval] non-json proxy output: {text}", file=sys.stderr)
                continue
            await self._handle_server_message(msg)

    async def _read_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", errors="replace").strip()
            if self.args.verbose or "Error:" in text or "failed" in text.lower():
                print(f"[approval] {text}", file=sys.stderr)

    async def _send_rpc(self, msg: dict[str, Any]) -> bool:
        if not self.proc or not self.proc.stdin or self.proc.returncode is not None:
            self.enabled = False
            return False
        try:
            self.proc.stdin.write((json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()
            return True
        except (BrokenPipeError, ConnectionResetError):
            self.enabled = False
            return False

    async def _handle_server_message(self, msg: dict[str, Any]) -> None:
        method = msg.get("method")
        if method not in APPROVAL_METHODS or "id" not in msg:
            return

        prompt_id = f"a{self.next_prompt_num}"
        self.next_prompt_num += 1
        params = msg.get("params") or {}
        self.pending[prompt_id] = {
            "method": method,
            "rpc_id": msg["id"],
            "params": params,
        }
        self.pending_order.append(prompt_id)
        if self.args.verbose:
            print(f"[approval] request {prompt_id}: {method}", file=sys.stderr)
        if not self.active_prompt_id:
            await self._show_next_prompt()

    def _prompt_text(self, req: dict[str, Any]) -> tuple[str, str]:
        method = req["method"]
        params = req["params"]

        if method == "hookPermissionRequest":
            if not isinstance(params, dict):
                return "PERMISSION", "Codex permission request"
            tool = short_text(params.get("tool_name"), "PERMISSION", 19).upper()
            tool_input = params.get("tool_input")
            if isinstance(tool_input, dict):
                hint = (
                    tool_input.get("command")
                    or tool_input.get("cmd")
                    or tool_input.get("path")
                    or tool_input.get("file")
                    or tool_input.get("justification")
                    or tool_input.get("reason")
                )
                if isinstance(hint, list):
                    hint = " ".join(str(x) for x in hint)
            else:
                hint = tool_input
            if not hint:
                hint = params.get("cwd") or "Codex permission request"
            return tool, short_text(hint, "Codex permission request", 43)

        if method in {"item/commandExecution/requestApproval", "execCommandApproval"}:
            command = params.get("command") or ""
            if isinstance(command, list):
                command = " ".join(str(x) for x in command)
            return "COMMAND", short_text(params.get("reason") or command, "command approval", 43)

        if method in {"item/fileChange/requestApproval", "applyPatchApproval"}:
            hint = params.get("reason") or params.get("grantRoot") or "file change approval"
            return "FILE CHANGE", short_text(hint, "file change approval", 43)

        if method == "item/permissions/requestApproval":
            hint = params.get("reason") or "extra permissions"
            return "PERMISSIONS", short_text(hint, "extra permissions", 43)

        if method == "testApproval":
            return "TEST", short_text(params.get("reason"), "A accept / B cancel", 43)

        return "APPROVAL", "Codex approval"

    async def _show_next_prompt(self) -> None:
        if not self.pending_order:
            self.active_prompt_id = None
            await self.ble.write_json({"prompt": None})
            return

        prompt_id = self.pending_order[0]
        self.active_prompt_id = prompt_id
        tool, hint = self._prompt_text(self.pending[prompt_id])
        await self.ble.write_json(
            {
                "prompt": {
                    "id": prompt_id,
                    "tool": short_text(tool, "APPROVAL", 19),
                    "hint": short_text(hint, "Codex approval", 43),
                },
                "msg": "Codex approval",
            }
        )

    async def handle_device_message(self, msg: dict[str, Any]) -> None:
        if msg.get("cmd") != "permission":
            if self.args.verbose:
                print(f"[ble] notify {msg}", file=sys.stderr)
            return

        prompt_id = str(msg.get("id") or "")
        raw_decision = str(msg.get("decision") or "").lower()
        if raw_decision in {"accept", "approve", "approved", "once"}:
            decision = "accept"
        elif raw_decision in {"cancel", "deny", "denied", "decline", "abort"}:
            decision = "cancel"
        else:
            print(f"[approval] unknown decision from StickS3: {raw_decision}", file=sys.stderr)
            return

        req = self._remove_pending(prompt_id)
        if self.active_prompt_id == prompt_id:
            self.active_prompt_id = None

        if not req:
            print(f"[approval] no pending request for {prompt_id}", file=sys.stderr)
            await self._show_next_prompt()
            return

        if req["method"] == "testApproval":
            print(f"[approval] test decision from StickS3: {decision}", file=sys.stderr)
            await self._show_next_prompt()
            return

        if req["method"] == "hookPermissionRequest":
            future = req.get("future")
            if future and not future.done():
                future.set_result(decision)
            if self.args.verbose:
                print(f"[approval] hook decision {decision} for {prompt_id}", file=sys.stderr)
            await self._show_next_prompt()
            return

        response = self._response_for(req, decision)
        ok = await self._send_rpc(response)
        if self.args.verbose:
            status = "sent" if ok else "failed"
            print(f"[approval] {status} {decision} for {prompt_id}", file=sys.stderr)
        await self._show_next_prompt()

    def _remove_pending(self, prompt_id: str) -> dict[str, Any] | None:
        req = self.pending.pop(prompt_id, None)
        if prompt_id in self.pending_order:
            self.pending_order.remove(prompt_id)
        return req

    def _response_for(self, req: dict[str, Any], decision: str) -> dict[str, Any]:
        method = req["method"]
        rpc_id = req["rpc_id"]
        params = req["params"]

        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"decision": decision}}

        if method in {"execCommandApproval", "applyPatchApproval"}:
            legacy_decision = "approved" if decision == "accept" else "abort"
            return {"jsonrpc": "2.0", "id": rpc_id, "result": {"decision": legacy_decision}}

        if method == "item/permissions/requestApproval" and decision == "accept":
            requested = params.get("permissions") or {}
            granted = {
                key: requested[key]
                for key in ("network", "fileSystem")
                if requested.get(key) is not None
            }
            return {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": {
                    "permissions": granted,
                    "scope": "turn",
                    "strictAutoReview": False,
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": {
                "code": -32000,
                "message": "cancelled from StickS3",
            },
        }


async def find_device(name_filter: str, address: str | None, timeout: float):
    assert BleakScanner is not None
    devices = await BleakScanner.discover(
        timeout=timeout,
        service_uuids=[NUS_SERVICE_UUID],
    )
    service_filtered = bool(devices)
    if not devices:
        devices = await BleakScanner.discover(timeout=timeout)
    if getattr(find_device, "debug_scan", False):
        mode = "NUS" if service_filtered else "fallback"
        print(f"[scan] {mode} scan saw {len(devices)} device(s):", file=sys.stderr)
        for dev in devices:
            print(f"[scan]   {dev.name or '-'}  {dev.address}", file=sys.stderr)
    for dev in devices:
        dev_name = dev.name or ""
        if address and dev.address.lower() == address.lower():
            return dev
        if name_filter and name_filter in dev_name:
            return dev
        if name_filter.startswith("Codex") and "Claude" in dev_name:
            print(f"[scan] using cached old name: {dev_name}", file=sys.stderr)
            return dev
    if not address and name_filter and len(devices) == 1:
        dev = devices[0]
        print(
            f"[scan] using only NUS device despite cached name: {dev.name or dev.address}",
            file=sys.stderr,
        )
        return dev
    interesting = [
        d.name or d.address
        for d in devices
        if any(key in (d.name or "") for key in ("Codex", "Claude"))
    ]
    names = ", ".join(sorted(interesting)) or "none"
    raise RuntimeError(f"Codex BLE device not found. Saw: {names}")


async def send_packet(args: argparse.Namespace, packet: dict[str, Any]) -> None:
    assert BleakClient is not None
    dev = await find_device(args.name, args.address, args.scan_timeout)
    payload = (json.dumps(packet, separators=(",", ":")) + "\n").encode("utf-8")

    async with BleakClient(dev, timeout=args.connect_timeout) as client:
        if args.pair and hasattr(client, "pair"):
            try:
                await client.pair()
            except Exception as exc:  # macOS often pairs on encrypted write
                print(f"[pair] continuing after pair attempt failed: {exc}", file=sys.stderr)
        for i in range(0, len(payload), args.chunk_size):
            chunk = payload[i:i + args.chunk_size]
            await client.write_gatt_char(NUS_RX_UUID, chunk, response=not args.no_response)
            await asyncio.sleep(args.chunk_delay)


async def send_usage_update(
    args: argparse.Namespace,
    tracker: ActivityTracker,
    ble: BleSession | None = None,
    approvals: CodexApprovalProxy | None = None,
) -> None:
    snapshot = read_usage(args)
    state = choose_state(args, snapshot, tracker)
    if approvals and approvals.has_pending():
        state = "attention"
    packet = snapshot.packet(state)
    line = json.dumps(packet, separators=(",", ":"))

    if args.dry_run:
        print(line)
    elif ble:
        await ble.write_json(packet)
        if args.verbose:
            age = "?"
            if snapshot.event_ts is not None:
                age = f"{int(time.time() - snapshot.event_ts)}s"
            print(
                f"sent {line} from {snapshot.source.name} "
                f"limit={snapshot.limit_id or '-'} age={age}",
                flush=True,
            )


async def bridge_loop(args: argparse.Namespace) -> None:
    setattr(find_device, "debug_scan", args.debug_scan)
    tracker = ActivityTracker()
    if args.dry_run:
        while True:
            await send_usage_update(args, tracker)
            if args.once:
                return
            await asyncio.sleep(args.interval)

    assert BleakClient is not None
    dev = await find_device(args.name, args.address, args.scan_timeout)
    async with BleakClient(dev, timeout=args.connect_timeout) as client:
        if args.pair and hasattr(client, "pair"):
            try:
                await client.pair()
            except Exception as exc:  # macOS often pairs on encrypted write
                print(f"[pair] continuing after pair attempt failed: {exc}", file=sys.stderr)

        ble = BleSession(args, client)
        await ble.start_notify()
        approvals = CodexApprovalProxy(args, ble)
        await approvals.start_ipc_server()
        await approvals.start()
        if args.test_approval:
            await approvals.inject_test_request()

        async def usage_runner() -> None:
            while True:
                await send_usage_update(args, tracker, ble, approvals)
                if args.once:
                    return
                await asyncio.sleep(args.interval)

        async def device_runner() -> None:
            while True:
                msg = await ble.incoming.get()
                await approvals.handle_device_message(msg)

        try:
            if args.once:
                await usage_runner()
                return
            await asyncio.gather(usage_runner(), device_runner())
        finally:
            await approvals.close_ipc_server()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bridge Codex usage to a StickS3 over BLE.",
    )
    p.add_argument("--codex-home", type=Path, default=DEFAULT_CODEX_HOME)
    p.add_argument("--rollout", type=Path, help="Read a specific Codex rollout JSONL")
    p.add_argument("--thread-id", help="Read a specific Codex thread from state_5.sqlite")
    p.add_argument("--thread-scan-limit", type=int, default=12)
    p.add_argument("--tail-bytes", type=int, default=8 * 1024 * 1024)
    p.add_argument("--limit-id", default="codex", help="Prefer this rate_limits.limit_id")

    p.add_argument("--name", default="Codex-", help="BLE device name substring")
    p.add_argument("--address", help="BLE address/UUID if name scan is not enough")
    p.add_argument("--scan-timeout", type=float, default=8.0)
    p.add_argument("--debug-scan", action="store_true", help="Print raw BLE scan results")
    p.add_argument("--connect-timeout", type=float, default=20.0)
    p.add_argument("--no-response", action="store_true", help="Use write-without-response")
    p.add_argument("--pair", action="store_true", help="Try explicit BLE pairing first")
    p.add_argument("--chunk-size", type=int, default=20, help="BLE write chunk size")
    p.add_argument("--chunk-delay", type=float, default=0.02, help="Delay between BLE chunks")
    p.add_argument(
        "--no-approval-proxy",
        action="store_true",
        help="Disable Codex app-server approval proxy integration",
    )
    p.add_argument(
        "--approval-sock",
        type=Path,
        help="Optional Codex app-server control socket for approval proxy",
    )
    p.add_argument(
        "--codex-cli",
        type=Path,
        help="Path to the Codex CLI used for app-server proxy",
    )
    p.add_argument(
        "--test-approval",
        action="store_true",
        help="Send a fake approval prompt to the StickS3 and print the A/B decision",
    )
    p.add_argument(
        "--hook-approval-sock",
        type=Path,
        default=DEFAULT_HOOK_APPROVAL_SOCK,
        help="Unix socket used by PermissionRequest hooks to ask the StickS3",
    )
    p.add_argument(
        "--hook-approval-timeout",
        type=float,
        default=45.0,
        help="Seconds to wait for A/B on hardware approval requests",
    )

    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument(
        "--state",
        default="auto",
        choices=["auto", "idle", "busy", "attention", "completed", "celebrate", "dizzy", "heart", "sleep"],
    )
    p.add_argument("--busy-window", type=float, default=60.0)
    p.add_argument("--completed-window", type=float, default=25.0)
    p.add_argument("--attention-window", type=float, default=120.0)
    p.add_argument("--dizzy-window", type=float, default=60.0)
    p.add_argument("--sleep-window", type=float, default=20 * 60.0)
    return p


def main() -> int:
    args = build_parser().parse_args()
    args.codex_home = args.codex_home.expanduser()
    if args.rollout:
        args.rollout = args.rollout.expanduser()
    if args.approval_sock:
        args.approval_sock = args.approval_sock.expanduser()
    if args.hook_approval_sock:
        args.hook_approval_sock = args.hook_approval_sock.expanduser()
    if args.codex_cli:
        args.codex_cli = args.codex_cli.expanduser()

    if not args.dry_run and (BleakClient is None or BleakScanner is None):
        print("Missing dependency: bleak. Install with `python3 -m pip install bleak`.", file=sys.stderr)
        return 2

    try:
        asyncio.run(bridge_loop(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"codex_usage_ble_bridge: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
