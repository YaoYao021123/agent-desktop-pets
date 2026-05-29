# Agent Desktop Pets Simulator

Static browser simulator for the StickS3 dashboard UI.

Run from the repository root:

```bash
python3 -m http.server 8787
```

Open:

```text
http://127.0.0.1:8787/simulator/
```

The simulator loads pet packs from `characters/<name>/manifest.json` and GIF
assets from the same folder. It accepts the same compact bridge packet shape
used by the firmware:

```json
{"state":"busy","tokens":159297887,"primary":98,"secondary":44}
```

The packet fields `primary` and `secondary` are Codex used percentages. The
dashboard displays remaining quota, so the example above renders as `2%` left
for the 5-hour window and `56%` left for the 7-day window.

Device imagery is based on official M5Stack StickS3 documentation assets:

- `assets/sticks3-front-crop.png` from `K150-stickS3_main-products_07.webp`
- `assets/sticks3-buttons.jpg` from `K150-stickS3_main-products_13.jpg`
- `assets/sticks3-size.png` from `K150-sticks3_page_01.png`
