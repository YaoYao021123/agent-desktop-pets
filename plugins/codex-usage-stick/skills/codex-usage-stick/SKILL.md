---
name: codex-usage-stick
description: Start, stop, inspect, or troubleshoot the Codex Usage Stick BLE bridge that sends local Codex usage data to a StickS3 display.
---

# Codex Usage Stick

Use this skill when the user asks about the Codex Usage Stick bridge, BLE usage display, plugin startup, hook status, or StickS3 Codex usage connection.

## What This Plugin Does

- Starts one background BLE bridge for the current user.
- Sends Codex usage packets to a StickS3 running the matching firmware.
- Uses `~/.codex/codex-usage-bridge/config.json` for BLE name/address and timing.
- Writes bridge output to `~/.codex/codex-usage-bridge/bridge.log`.
- Writes hook diagnostics to `~/.codex/codex-usage-bridge/hook.log`.
- Forwards Codex PermissionRequest prompts to the StickS3 through the local `approval.sock` IPC bridge.

## Commands

Resolve the plugin root from this skill file, then use:

```sh
python3 <plugin-root>/scripts/start_bridge.py --status
python3 <plugin-root>/scripts/start_bridge.py --stop
python3 <plugin-root>/scripts/start_bridge.py
python3 <plugin-root>/scripts/start_bridge.py --foreground
```

For hook diagnostics:

```sh
tail -n 40 ~/.codex/codex-usage-bridge/hook.log
tail -n 80 ~/.codex/codex-usage-bridge/bridge.log
```

## Troubleshooting Order

1. Check `--status`.
2. Check `hook.log`; if it has no new line after a prompt is submitted, the plugin hook was not loaded or trusted by Codex.
3. Check `bridge.log`; if hook fired but bridge did not connect, inspect BLE scan/name/address config.
4. If a local marketplace was updated while Codex was already open, ask the user to restart Codex or reinstall the local marketplace entry.
