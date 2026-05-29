# Codex Usage Pet Contract

## Sprite Atlas

- Format: PNG or WebP.
- Dimensions: `1536x1456`.
- Grid: 8 columns x 7 rows.
- Cell: `192x208`.
- Background: transparent.
- Unused cells: fully transparent.

Do not add labels, gutters, borders, grid lines, shadows outside the cell, or extra frames.

## Local Package

Place files under:

```text
${CODEX_HOME:-$HOME/.codex}/pets/<pet-name>/
├── pet.json
└── spritesheet.webp
```

Manifest shape:

```json
{
  "id": "pet-name",
  "displayName": "Pet Name",
  "description": "One short sentence.",
  "spritesheetPath": "spritesheet.webp",
  "layout": {
    "columns": 8,
    "rows": 7,
    "cellWidth": 192,
    "cellHeight": 208
  },
  "animations": [
    { "state": "sleep", "row": 0, "frames": 6 },
    { "state": "idle", "row": 1, "frames": 6 },
    { "state": "busy", "row": 2, "frames": 8 },
    { "state": "attention", "row": 3, "frames": 6 },
    { "state": "completed", "row": 4, "frames": 8 },
    { "state": "dizzy", "row": 5, "frames": 6 },
    { "state": "heart", "row": 6, "frames": 6 }
  ]
}
```
