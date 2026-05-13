## Summary
<img width="1280" height="909" alt="20260513-175515" src="https://github.com/user-attachments/assets/d0ac10a8-12dd-4871-af1d-88e1d7359830" />

This PR improves the M5Stack StickS3 GIF character and clock experience.

Main changes:

- Add BLE-friendly GIF playback pacing:
  - disconnected: play one GIF loop, then pause for 5 seconds
  - connected: play one GIF loop, then pause for 3 seconds
- Preserve the last GIF frame between loops to avoid black-frame flicker.
- Make GIF playback in landscape clock mode loop again instead of stopping after one pass.
- Fix landscape GIF clipping by using the target display height instead of the portrait peek height.
- Adjust landscape GIF placement for the StickS3 clock layout.
- Improve portrait charging clock layout:
  - shift the GIF display window to better fit the character
  - avoid clearing over the lower part of the GIF
  - replace seconds/date with today’s token usage
- Replace the seconds display with today’s token count in both portrait and landscape clock modes.
- Add landscape clock support while on battery, only when the screen is already awake.
  - Auto screen-off behavior on battery is preserved.
- Pin the StickS3 PlatformIO environment to `espressif32@6.7.0` for reproducible builds.
## How to use this firmware

This branch targets the M5Stack StickS3 build.

1. Clone this fork/branch:

```bash
git clone -b sticks3-support-GIF GitHub - openelab-commits/claude-desktop-buddy-GIF: Improve M5Stack StickS3 GIF playback and clock d
cd claude-desktop-buddy-GIF
pio run -e m5stack-sticks3
pio run -e m5stack-sticks3 -t upload
pio run -e m5stack-sticks3 -t uploadfs
```
## Testing

Built successfully with:

```bash
pio run -e m5stack-sticks3
```
I’m also working on adding a token usage progress bar and an image-based pet generation skill. Stay tuned.
