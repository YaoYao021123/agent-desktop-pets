# Claude Desktop Buddy GIF Edition for M5Stack StickS3

This is a personal fork of Anthropic's
[`claude-desktop-buddy`](https://github.com/anthropics/claude-desktop-buddy)
reference firmware, focused on M5Stack StickS3, animated GIF pets, charging
clock layouts, and a more desk-friendly visual experience.

The upstream project is a reference implementation for the BLE protocol
described in [`REFERENCE.md`](REFERENCE.md). This fork keeps that protocol
surface, but turns the firmware into a more opinionated StickS3 GIF-pet build.

## What This Fork Adds

- BLE-friendly GIF playback pacing:
  - disconnected: play one GIF loop, then pause for 5 seconds
  - connected: play one GIF loop, then pause for 3 seconds
- Last-frame hold between GIF loops to avoid black-frame flicker.
- Landscape clock GIF playback that continues looping instead of stopping
  after one pass.
- Landscape GIF clipping fixes for StickS3.
- Portrait charging clock layout tuned for GIF pets.
- Token usage display in the charging clock, replacing the seconds display.
- Battery landscape clock support while the screen is already awake.
- Auto screen-off on battery is preserved.
- M5Stack StickS3 PlatformIO environment pinned to `espressif32@6.7.0`.

## Hardware Target

This fork is primarily tested with:

```text
M5Stack StickS3 / ESP32-S3
```

The code still comes from the original ESP32/M5Unified firmware, but this fork
is not intended to be a general board-support PR for upstream. It is a
StickS3-focused variant.

## Features

### GIF Pet Mode

The device can receive a custom GIF character pack from the Claude Desktop
Hardware Buddy window. The pack contains a `manifest.json` file and the GIFs
referenced by that manifest.

This fork tunes GIF playback to leave time for BLE advertising and data
exchange, which is especially important while the device is waiting for Claude
Desktop to connect or send permission events.

### Charging Clock

When the StickS3 is on USB power and idle, it shows a clock view.

Portrait charging clock:

- GIF pet at the top
- large time display
- today's token usage below the time
- no date line

Landscape charging clock:

- GIF pet on the left
- time, token usage, and date on the right

### Battery Landscape Clock

When running on battery, the screen-off behavior is unchanged. However, if the
screen is already awake and the device is held sideways, this fork can show the
landscape clock view.

This means:

```text
battery + screen awake + landscape = landscape clock
battery + idle timeout = screen turns off as usual
```

## Build And Flash

Install [PlatformIO Core](https://docs.platformio.org/en/latest/core/installation/),
then clone this fork:

```bash
git clone https://github.com/openelab-commits/claude-desktop-buddy-GIF.git
cd claude-desktop-buddy-GIF
```

Build the StickS3 firmware:

```bash
pio run -e m5stack-sticks3
```

Upload firmware:

```bash
pio run -e m5stack-sticks3 -t upload
```

If you are starting from a previously flashed device, erase first:

```bash
pio run -e m5stack-sticks3 -t erase
pio run -e m5stack-sticks3 -t upload
```

If you are uploading local LittleFS data over USB:

```bash
pio run -e m5stack-sticks3 -t uploadfs
```

## Pairing With Claude Desktop

1. Enable developer mode in Claude Desktop:

   ```text
   Help -> Troubleshooting -> Enable Developer Mode
   ```

2. Open:

   ```text
   Developer -> Open Hardware Buddy...
   ```

3. Click **Connect** and select the StickS3 device.

4. Grant Bluetooth permissions if macOS asks.

The device uses the same Nordic UART Service protocol as the upstream reference
implementation.

## Controls

| Button | Normal | Approval |
| --- | --- | --- |
| A | next screen | approve once |
| B | scroll / next page | deny |
| Hold A | menu | menu |
| Power short press | toggle screen off | toggle screen off |
| Power long press | hardware power off | hardware power off |

The screen auto-powers-off after idle time on battery. USB power keeps the
clock visible.

## GIF Character Pack Format

A GIF character pack is a folder containing `manifest.json` and the referenced
GIF files.

Example:

```json
{
  "name": "Mili",
  "colors": {
    "body": "#FFFFFF",
    "bg": "#000000",
    "text": "#FFFFFF",
    "textDim": "#808080",
    "ink": "#000000"
  },
  "states": {
    "sleep": "sleep.gif",
    "idle": ["idle_0.gif", "idle_1.gif"],
    "busy": "busy.gif",
    "attention": "attention.gif",
    "completed": "completed.gif",
    "celebrate": "celebrate.gif",
    "dizzy": "dizzy.gif",
    "heart": "heart.gif"
  }
}
```

Recommended GIF guidance for this fork:

- Keep the character consistent across all states.
- Use transparent backgrounds.
- Keep the sprite tightly cropped.
- Avoid shadows, speed lines, text, UI elements, and complex scenery.
- Keep animations readable on the StickS3 screen.
- Compress GIFs so the full character pack fits comfortably in LittleFS.

## State Meanings

| State | Intended use |
| --- | --- |
| `sleep` | Claude is not connected or the buddy is resting |
| `idle` | connected and calm |
| `busy` | Claude is actively working |
| `attention` | a permission prompt is waiting |
| `completed` | a task or action completed |
| `celebrate` | success or level-up style reaction |
| `dizzy` | shake / confused / error reaction |
| `heart` | quick approval or affectionate reaction |

## Project Layout

```text
src/
  main.cpp        loop, state machine, UI, clock screens
  character.cpp   GIF decode, playback pacing, rendering
  character.h     GIF character API
  ble_bridge.cpp  Nordic UART BLE bridge
  data.h          JSON protocol parsing
  xfer.h          folder push receiver
  stats.h         settings and persistent stats
characters/       example GIF character packs
tools/            helper scripts
```

## Relationship To Upstream

The upstream project is a reference implementation. This fork is a customized
firmware variant for my M5Stack StickS3 workflow.

If you are building a different device, read [`REFERENCE.md`](REFERENCE.md)
first. The protocol is the stable contract; this firmware is one implementation
of that protocol.

## Roadmap

- Add a token usage progress bar.
- Build a more targeted GIF generation workflow.
- Create an image-based pet generation skill for producing matching GIF packs.
- Improve documentation for flashing and custom character creation.

## License

This fork keeps the upstream project license. See [`LICENSE`](LICENSE).
