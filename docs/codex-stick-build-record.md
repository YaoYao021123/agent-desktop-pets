# Codex StickS3 Pet Build Record

Date: 2026-05-29  
Repository: `agent-desktop-pets`  
Device: M5Stack StickS3, ESP32-S3  
BLE target: discovered by name prefix, for example `Codex-XXXX`

## Goal

Turn the M5Stack StickS3 into a small Codex desktop pet and usage monitor:

- show a Codex pet on the StickS3 screen;
- display Codex quota windows, reset countdowns, and activity state;
- reuse pets from `~/.codex/pets`;
- connect from the Mac over BLE while USB-C is used for power and flashing.

The final working setup uses a fork of `anthropics/claude-desktop-buddy`, a converted `david` pet, and a local BLE bridge that reads local Codex usage data and sends compact JSON status packets to the device.

## Final Result

The firmware and assets were flashed successfully.

| Item | Result |
| --- | --- |
| Firmware build | success |
| Firmware size | `1.2M` at `.pio/build/m5stack-sticks3/firmware.bin` |
| LittleFS image | success |
| LittleFS size | `1.9M` at `.pio/build/m5stack-sticks3/littlefs.bin` |
| Active pet | `david` |
| Pet asset size | about `504K` at `characters/david` |
| Bridge status | running |
| Bridge interval | `5s` |
| Verified BLE send | yes |

Verified bridge log:

```text
sent {"state":"busy","tokens":...,"primary":...,"secondary":...}
```

This confirms the Mac bridge is sending live Codex usage data to the StickS3 over BLE.

## Hardware Connection

USB-C is required for flashing and power. Runtime data is sent over BLE.

The device was recognized by macOS as a USB CDC serial device:

```text
/dev/cu.usbmodem1101
USB product: StickS3(UiFlow2)
Vendor: M5Stack
```

For flashing, the StickS3 needs to enter ESP32-S3 download mode:

1. Keep USB-C connected.
2. Long-press the side reset button.
3. Release when the internal green LED flashes.
4. Flash with `esptool.py` or PlatformIO.

## Pet Conversion

Codex app pets live under:

```text
~/.codex/pets
```

The source pet format is an 8x9 `spritesheet.webp` atlas. The StickS3 firmware expects:

```text
/characters/<name>/manifest.json
/characters/<name>/*.gif
```

A converter was added:

```text
tools/convert_codex_pet.py
```

Converted packs:

```text
characters/david
characters/kuma
characters/lulu-capybara
characters/silverloaf
```

The active resource pack is:

```text
characters/david
```

Firmware default character was pinned to `david`:

```ini
-DDEFAULT_CHARACTER=\"david\"
```

## Dependency Workaround

PlatformIO downloads were slow, so the required large packages were installed locally instead of relying on repeated online installs.

Key local packages:

- `framework-arduinoespressif32@3.20016.0`
- `toolchain-xtensa-esp32s3@8.4.0+2021r2-patch5`
- `toolchain-riscv32-esp@8.4.0+2021r2-patch5`
- `tool-esptoolpy@1.40501.0`
- `tool-scons@4.40801.0`
- `tool-mklittlefs@1.203.210628`
- `tool-mkspiffs@2.230.0`
- `tool-mkfatfs@2.0.1`

During bring-up, Arduino libraries were temporarily vendored under `lib/` to avoid slow repeated downloads. The public repository keeps dependency declarations in `platformio.ini` instead of committing the local cache:

- `M5Unified@0.2.16`
- `M5GFX@0.2.22`
- `AnimatedGIF@2.2.2`
- `ArduinoJson@7.4.3`
- `M5PM1@1.0.6`

## Build And Flash

Build command:

```bash
PLATFORMIO_CORE_DIR=.platformio \
  .venv/bin/pio run -e m5stack-sticks3
```

Firmware build result:

```text
m5stack-sticks3  SUCCESS
RAM:   24.8%
Flash: 62.0%
```

The reliable flash path used direct `esptool.py` commands with `--before no_reset`, because PlatformIO's automatic reset flow made the USB serial port disappear at the wrong moment.

Firmware write:

```bash
.venv/bin/python .platformio/packages/tool-esptoolpy/esptool.py \
  --chip esp32s3 \
  --port /dev/cu.usbmodem1101 \
  --baud 115200 \
  --before no_reset \
  --after hard_reset \
  write_flash -z \
  --flash_mode dio \
  --flash_freq 80m \
  --flash_size 8MB \
  0x10000 .pio/build/m5stack-sticks3/firmware.bin
```

LittleFS image:

```bash
PLATFORMIO_CORE_DIR=.platformio \
  .venv/bin/pio run -e m5stack-sticks3 -t buildfs
```

LittleFS write:

```bash
.venv/bin/python .platformio/packages/tool-esptoolpy/esptool.py \
  --chip esp32s3 \
  --port /dev/cu.usbmodem1101 \
  --baud 115200 \
  --before no_reset \
  --after hard_reset \
  write_flash -z \
  --flash_mode dio \
  --flash_freq 80m \
  --flash_size 8MB \
  0x210000 .pio/build/m5stack-sticks3/littlefs.bin
```

Both firmware and LittleFS writes ended with:

```text
Hash of data verified.
```

## BLE Bridge

The bridge reads local Codex usage and sends JSON packets over BLE.

Bridge status command:

```bash
.venv/bin/python plugins/codex-usage-stick/scripts/start_bridge.py --status
```

Current bridge command:

```text
codex_usage_ble_bridge.py
  --name Codex-
  --name Codex-
  --interval 5.0
  --scan-timeout 20.0
  --connect-timeout 30.0
  --debug-scan
  --verbose
  --no-approval-proxy
```

Log path:

```text
~/.codex/codex-usage-bridge/bridge.log
```

Example packet:

```json
{
  "state": "busy",
  "tokens": 123456,
  "primary": 42,
  "secondary": 17,
  "primary_resets_at": 1700000000,
  "secondary_resets_at": 1700000000
}
```

## macOS Bluetooth Fix

macOS terminated raw Python BLE scans because Python did not have the right Bluetooth app metadata. A local `.app` wrapper was added:

```text
.macos/CodexUsageBridgePython.app
```

It includes:

```xml
<key>NSBluetoothAlwaysUsageDescription</key>
<string>Codex Usage Stick uses Bluetooth to send local Codex usage status to the paired M5Stack StickS3.</string>
```

A runner was added:

```text
plugins/codex-usage-stick/scripts/macos_bridge_app_runner.py
```

The runner:

- launches through the `.app` so macOS grants Bluetooth access;
- writes `bridge.pid` and `bridge.log`;
- imports the project virtualenv packages;
- automatically restarts the bridge after transient BLE connection failures.

## BLE Pairing Decision

The original firmware required encrypted BLE pairing with a passkey. On this Mac, Python CoreBluetooth repeatedly hung during passkey pairing. For the current working monitor, BLE encryption was disabled in the firmware.

Reasoning:

- the bridge only sends local quota percentages and state strings;
- no external server is involved;
- device-side hardware approval is disabled with `--no-approval-proxy`;
- stable display was the priority for this build.

The modified firmware uses open NUS writes for the local usage monitor. Hardware approval over encrypted BLE can be reintroduced later as a separate pass.

## Files Changed Or Added

Important files:

- `src/main.cpp` - default character set to `david`.
- `src/ble_bridge.cpp` - BLE NUS write path made pairing-free for stability.
- `platformio.ini` - StickS3 environment adjusted for local build behavior.
- `tools/convert_codex_pet.py` - Codex pet atlas to StickS3 GIF converter.
- `plugins/codex-usage-stick/scripts/start_bridge.py` - macOS `.app` runner support.
- `plugins/codex-usage-stick/scripts/macos_bridge_app_runner.py` - Bluetooth-safe macOS runner.
- `characters/david` - active StickS3 pet assets generated from the Codex pet atlas.

## Operating Commands

Check bridge:

```bash
.venv/bin/python plugins/codex-usage-stick/scripts/start_bridge.py --status
tail -n 40 ~/.codex/codex-usage-bridge/bridge.log
```

Start bridge:

```bash
.venv/bin/python plugins/codex-usage-stick/scripts/start_bridge.py
```

Stop bridge:

```bash
.venv/bin/python plugins/codex-usage-stick/scripts/start_bridge.py --stop
```

Rebuild firmware:

```bash
PLATFORMIO_CORE_DIR=.platformio \
  .venv/bin/pio run -e m5stack-sticks3
```

Rebuild filesystem:

```bash
PLATFORMIO_CORE_DIR=.platformio \
  .venv/bin/pio run -e m5stack-sticks3 -t buildfs
```

## Current Status

The StickS3 has been flashed with the Codex usage monitor firmware, the David pet assets are installed, and the Mac bridge is actively sending Codex usage packets over BLE.

The working outcome is a USB-powered StickS3 desk pet that reflects Codex activity and quota state from the local Mac.
