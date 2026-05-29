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
