# Codex Usage Stick Plugin

This local Codex plugin starts a BLE bridge that sends Codex usage data to a
StickS3 running the matching Codex Usage Stick firmware.

The plugin is local-first:

- It reads local Codex usage files.
- It starts one background bridge process.
- It sends compact usage packets over BLE.
- It writes diagnostics under `~/.codex/codex-usage-bridge/`.
- It does not send data to an external server.

## Hooks

The plugin registers:

```text
SessionStart
UserPromptSubmit
PermissionRequest
```

The hooks run:

```sh
python3 "$PLUGIN_ROOT/scripts/hook_entry.py"
```

The startup hooks return quickly: `hook_entry.py` writes a log line and asks
`start_bridge.py` to start or reuse the background bridge. The
`PermissionRequest` hook is synchronous and waits briefly for A/B on the
StickS3 before falling back to Codex's normal approval UI.

## Install From Codex UI

Open:

```text
Settings -> Plugins -> Add plugin marketplace
```

Fill the dialog like this:

```text
Source:
YaoYao021123/agent-desktop-pets

Git ref:
main
```

If this lives in your own fork, use that fork's `owner/repo`.

## CLI Fallback

```bash
/Applications/Codex.app/Contents/Resources/codex plugin marketplace add YaoYao021123/agent-desktop-pets --ref main
```

For local development:

```bash
/Applications/Codex.app/Contents/Resources/codex plugin marketplace add /path/to/agent-desktop-pets
```

## Enable Hooks

Enable plugin hooks:

```bash
/Applications/Codex.app/Contents/Resources/codex features enable plugin_hooks
```

If needed, enable the plugin in `~/.codex/config.toml`:

```toml
[plugins."codex-usage-stick@codex-usage-stick-marketplace"]
enabled = true
```

Restart Codex after changing plugin settings. Approve the hook trust prompt
when Codex shows it.

## Dependency

```bash
python3 -m pip install bleak
```

## Runtime Files

```text
~/.codex/codex-usage-bridge/config.json
~/.codex/codex-usage-bridge/hook.log
~/.codex/codex-usage-bridge/bridge.log
~/.codex/codex-usage-bridge/bridge.pid
```

## Config

Default `config.json`:

```json
{
  "name": "Codex-",
  "address": null,
  "interval": 5.0,
  "scan_timeout": 8.0,
  "restart_delay": 5.0,
  "verbose": true,
  "no_approval_proxy": true
}
```

Use `address` if macOS BLE name caching makes name scanning unreliable.
`no_approval_proxy` only disables the older app-server proxy experiment.
StickS3 approve/deny uses the `PermissionRequest` hook plus the local
`approval.sock` bridge and works with this value set to `true`.

## Commands

Check status:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py --status
```

Start:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py
```

Stop:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py --stop
```

Run in foreground:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py --foreground
```

Manual hook test:

```bash
python3 plugins/codex-usage-stick/scripts/hook_entry.py --event ManualTest
```

## Verify

Make sure Bluetooth is enabled on the computer.

For the first BLE pairing on a new computer, start with a foreground `busy`
test so macOS can show the pairing prompt:

```bash
python3 ~/.codex/plugins/cache/codex-usage-stick-marketplace/codex-usage-stick/0.4.0/scripts/codex_usage_ble_bridge.py --verbose --state busy
```

The StickS3 should show a pairing code. Enter that code on the computer to
finish the BLE pairing. Once the hardware starts showing usage information,
stop the foreground test with `Command-C` / `Ctrl-C`.

Then submit a Codex prompt in a project where the plugin hook is trusted:

```bash
tail -n 20 ~/.codex/codex-usage-bridge/hook.log
```

Expected:

```text
"event": "UserPromptSubmit"
```

Then check BLE packets:

```bash
tail -n 40 ~/.codex/codex-usage-bridge/bridge.log
```

Expected:

```text
sent {"state":"busy","tokens":...,"primary":...,"secondary":...}
```

## Approve / Deny

When Codex asks for a permission approval, the bridge forwards the prompt to
the StickS3 through a local `PermissionRequest` hook. Press A to allow or B to
deny. If the StickS3 is not connected or no button is pressed before timeout,
the hook returns no decision and Codex falls back to its normal local approval
flow.
