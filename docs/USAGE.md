# Codex Usage Stick Setup Guide

This guide walks through flashing the StickS3 firmware, uploading GIF assets,
installing the Codex plugin, and checking the BLE bridge.

## Requirements

- M5Stack StickS3.
- USB-C cable with data support.
- macOS with Codex installed.
- PlatformIO Core.
- Python 3.
- Python package `bleak`.

Install the Python dependency:

```bash
python3 -m pip install bleak
```

## 1. Clone The Project

```bash
git clone https://github.com/openelab-commits/codex-desktop-buddy.git
cd codex-desktop-buddy
```

If you downloaded a ZIP instead, open a terminal in the extracted project
folder.

## 2. Build The Firmware

```bash
pio run -e m5stack-sticks3
```

Expected result:

```text
m5stack-sticks3  SUCCESS
```

## 3. Flash The Firmware

Connect the StickS3 by USB-C, then run:

```bash
pio run -e m5stack-sticks3 -t upload
pio run -e m5stack-sticks3 -t uploadfs
```

If the device had unrelated firmware before, erase first:

```bash
pio run -e m5stack-sticks3 -t erase
pio run -e m5stack-sticks3 -t upload
```

After flashing, the device should advertise as:

```text
Codex-XXXX
```

## 4. Upload GIF Assets

The firmware reads GIF assets from LittleFS:

```text
/characters/<name>/manifest.json
/characters/<name>/*.gif
```

PlatformIO creates LittleFS from the local `data/` folder. This repo includes
the default Mao pet at `data/characters/Mao/`, so `uploadfs` installs Mao out
of the box.

Use your own character folder:

```bash
cd codex-desktop-buddy
mkdir -p ./data/characters
rm -rf ./data/characters/MyPet
cp -R /Users/you/Downloads/MyPet ./data/characters/MyPet
pio run -e m5stack-sticks3 -t uploadfs
```

Keep one character folder under `data/characters/` while testing. The firmware
loads the first character directory it finds.

If `uploadfs` says it cannot read the source directory, the `data/` folder is
missing or empty.

## 5. Install The Codex Plugin

In Codex, open:

```text
Settings -> Plugins -> Add plugin marketplace
```

Fill the dialog like this:

```text
Source:
openelab-commits/codex-desktop-buddy

Git ref:
main
```

If you are using a fork, replace the source with your own GitHub `owner/repo`.

The repo root contains `.agents/plugins/marketplace.json`, so Codex can load the
plugin marketplace directly from the repository root.

### CLI Fallback

If the UI flow is unavailable, use:

```bash
/Applications/Codex.app/Contents/Resources/codex plugin marketplace add openelab-commits/codex-desktop-buddy --ref main
```

For local development from a cloned repo, use the local folder path:

```bash
/Applications/Codex.app/Contents/Resources/codex plugin marketplace add /Users/you/codex-desktop-buddy
```

### Enable Plugin Hooks

Enable plugin hooks:

```bash
/Applications/Codex.app/Contents/Resources/codex features enable plugin_hooks
```

Check the feature state:

```bash
/Applications/Codex.app/Contents/Resources/codex features list | grep -E "hooks|plugin_hooks"
```

Expected:

```text
hooks          true
plugin_hooks  true
```

If the plugin is not enabled automatically, add this to `~/.codex/config.toml`:

```toml
[plugins."codex-usage-stick@codex-usage-stick-marketplace"]
enabled = true
```

Restart Codex after changing plugin settings.

## 6. Trust The Hook

Codex may show a hook trust prompt for each project or session. Approve the
hook if the path points to this plugin.

The hook runs:

```text
plugins/codex-usage-stick/scripts/hook_entry.py
```

It writes a diagnostic record and starts the local background BLE bridge. The
bridge reads local Codex usage files and sends compact usage numbers to the
StickS3 over BLE.

## 7. Trigger The Bridge

Submit a prompt in Codex. The `UserPromptSubmit` hook should run.

Check the hook log:

```bash
tail -n 20 ~/.codex/codex-usage-bridge/hook.log
```

A successful automatic trigger includes:

```text
"event": "UserPromptSubmit"
```

Check the bridge log:

```bash
tail -n 40 ~/.codex/codex-usage-bridge/bridge.log
```

A successful BLE send includes:

```text
sent {"state":"busy","tokens":...,"primary":...,"secondary":...}
```

## 8. Manual Bridge Commands

Check status:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py --status
```

Start or reuse the background bridge:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py
```

Run in the foreground:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py --foreground
```

Stop the background bridge:

```bash
python3 plugins/codex-usage-stick/scripts/start_bridge.py --stop
```

Run the raw bridge:

```bash
python3 tools/codex_usage_ble_bridge.py --verbose --no-approval-proxy
```

## Configuration

The first bridge start creates:

```text
~/.codex/codex-usage-bridge/config.json
```

Default config:

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

Use `address` if macOS keeps showing a stale cached BLE name.

## Troubleshooting

### Hook log only shows ManualTest

`ManualTest` means the hook entry was run manually. Submit a Codex prompt and
look for:

```text
"event": "UserPromptSubmit"
```

If it does not appear:

1. Confirm `plugin_hooks` is enabled.
2. Restart Codex.
3. Trust the hook when Codex asks.
4. Confirm the plugin is enabled in `~/.codex/config.toml`.

### Codex warns that async hooks are not supported

Update to this version. The plugin hooks in this repo do not use `async`.

### StickS3 stays on waiting

1. Confirm the firmware advertises as `Codex-XXXX`.
2. Confirm the bridge is running:

   ```bash
   python3 plugins/codex-usage-stick/scripts/start_bridge.py --status
   ```

3. Run the foreground bridge:

   ```bash
   python3 plugins/codex-usage-stick/scripts/start_bridge.py --foreground
   ```

4. If the device is not found, increase `scan_timeout` or set `address` in
   `~/.codex/codex-usage-bridge/config.json`.

### Bluetooth pairing fails on macOS

If the first connection does not pair correctly, or the bridge log shows:

```text
Peer removed pairing information
```

reset the macOS BLE pairing record:

1. Open macOS `System Settings -> Bluetooth`.
2. Find the `Codex-XXXX` device and choose `Forget This Device`.
3. Turn Mac Bluetooth off and on again.
4. Restart the StickS3.
5. Submit a prompt in Codex to let the plugin reconnect.

### GIF assets do not appear

Confirm the local upload folder looks like:

```text
data/
  characters/
    YourPet/
      manifest.json
      idle.gif
      busy.gif
      ...
```

Then upload LittleFS:

```bash
pio run -e m5stack-sticks3 -t uploadfs
```

### Landscape GIF looks slow

This version renders the landscape pet into a small canvas before pushing it to
the LCD. If you still see slow animation, use smaller GIFs or reduce the source
frame complexity.

## Release Checklist

Before publishing a new GitHub version:

```bash
pio run -e m5stack-sticks3
python3 -m json.tool plugins/codex-usage-stick/.codex-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/codex-usage-stick/hooks.json >/dev/null
python3 -m json.tool .agents/plugins/marketplace.json >/dev/null
python3 -m py_compile plugins/codex-usage-stick/scripts/*.py tools/codex_usage_ble_bridge.py
```

Also confirm no local-only paths are present in `plugins/codex-usage-stick/hooks.json`.
