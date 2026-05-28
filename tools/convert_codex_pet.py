#!/usr/bin/env python3
"""Convert a Codex app pet atlas into a StickS3 GIF character pack."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image


CODEX_CELL = (192, 208)
STICK_FRAME = (144, 156)

CODEX_ROWS = {
    "idle": {"row": 0, "frames": 6, "durations": [280, 110, 110, 140, 140, 320]},
    "running-right": {"row": 1, "frames": 8, "durations": [120, 120, 120, 120, 120, 120, 120, 220]},
    "running-left": {"row": 2, "frames": 8, "durations": [120, 120, 120, 120, 120, 120, 120, 220]},
    "waving": {"row": 3, "frames": 4, "durations": [140, 140, 140, 280]},
    "jumping": {"row": 4, "frames": 5, "durations": [140, 140, 140, 140, 280]},
    "failed": {"row": 5, "frames": 8, "durations": [140, 140, 140, 140, 140, 140, 140, 240]},
    "waiting": {"row": 6, "frames": 6, "durations": [150, 150, 150, 150, 150, 260]},
    "running": {"row": 7, "frames": 6, "durations": [120, 120, 120, 120, 120, 220]},
    "review": {"row": 8, "frames": 6, "durations": [150, 150, 150, 150, 150, 280]},
}

STICK_STATE_MAP = {
    "sleep": "waiting",
    "idle": "idle",
    "busy": "running",
    "attention": "waving",
    "completed": "jumping",
    "celebrate": "jumping",
    "dizzy": "failed",
    "heart": "waving",
}


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-") or "pet"


def load_pet_manifest(pet_dir: Path) -> dict[str, Any]:
    manifest_path = pet_dir / "pet.json"
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid {manifest_path}: {exc}") from exc


def resolve_spritesheet(pet_dir: Path, manifest: dict[str, Any]) -> Path:
    raw = manifest.get("spritesheetPath") or "spritesheet.webp"
    path = Path(raw)
    if not path.is_absolute():
        path = pet_dir / path
    if not path.exists():
        raise SystemExit(f"spritesheet not found: {path}")
    return path


def public_path(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(Path.home().resolve())
    except ValueError:
        return str(path)
    return str(Path("~") / rel)


def crop_frame(sheet: Image.Image, row: int, col: int) -> Image.Image:
    x = col * CODEX_CELL[0]
    y = row * CODEX_CELL[1]
    frame = sheet.crop((x, y, x + CODEX_CELL[0], y + CODEX_CELL[1])).convert("RGBA")
    return frame.resize(STICK_FRAME, Image.Resampling.LANCZOS)


def rgba_to_gif_frame(frame: Image.Image) -> Image.Image:
    rgba = frame.convert("RGBA")
    alpha = rgba.getchannel("A")

    # GIF has one transparent palette index. Quantize only opaque RGB data,
    # then force low-alpha pixels onto an unused final palette slot.
    flattened = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    flattened.alpha_composite(rgba)
    paletted = flattened.convert("RGB").convert("P", palette=Image.Palette.ADAPTIVE, colors=255)
    palette = paletted.getpalette() or []
    palette.extend([0] * (768 - len(palette)))
    palette[255 * 3:255 * 3 + 3] = [0, 0, 0]
    paletted.putpalette(palette)

    transparent_mask = alpha.point(lambda value: 255 if value <= 8 else 0)
    paletted.paste(255, mask=transparent_mask)
    paletted.info["transparency"] = 255
    return paletted


def save_gif(sheet: Image.Image, output: Path, source_state: str) -> None:
    spec = CODEX_ROWS[source_state]
    frames = [
        rgba_to_gif_frame(crop_frame(sheet, int(spec["row"]), col))
        for col in range(int(spec["frames"]))
    ]
    durations = list(spec["durations"])
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
        transparency=255,
    )


def write_character_pack(pet_dir: Path, output_dir: Path, force: bool) -> dict[str, Any]:
    manifest = load_pet_manifest(pet_dir)
    display_name = str(manifest.get("displayName") or pet_dir.name)
    sheet_path = resolve_spritesheet(pet_dir, manifest)

    with Image.open(sheet_path) as image:
        sheet = image.convert("RGBA")
        expected = (CODEX_CELL[0] * 8, CODEX_CELL[1] * 9)
        if sheet.size != expected:
            raise SystemExit(f"expected {expected[0]}x{expected[1]} atlas, got {sheet.width}x{sheet.height}")

        if output_dir.exists():
            if not force:
                raise SystemExit(f"{output_dir} exists; pass --force to overwrite")
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        state_files: dict[str, Any] = {}
        for stick_state, source_state in STICK_STATE_MAP.items():
            filename = f"{stick_state}.gif"
            save_gif(sheet, output_dir / filename, source_state)
            state_files[stick_state] = filename

    character_manifest = {
        "name": display_name,
        "colors": {
            "body": "#FFFFFF",
            "bg": "#000000",
            "text": "#FFFFFF",
            "textDim": "#808080",
            "ink": "#000000",
        },
        "states": state_files,
        "source": {
            "format": "codex-pet-atlas",
            "petDir": public_path(pet_dir),
            "spritesheet": public_path(sheet_path),
            "mapping": STICK_STATE_MAP,
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(character_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return character_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pet", help="Pet name under ~/.codex/pets or an absolute pet directory")
    parser.add_argument(
        "--codex-pets-dir",
        type=Path,
        default=Path.home() / ".codex" / "pets",
        help="Directory containing Codex app pets",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("characters"),
        help="Root directory for generated StickS3 character packs",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Exact output directory. Overrides --output-root.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output directory")
    args = parser.parse_args()

    pet_arg = Path(args.pet).expanduser()
    pet_dir = pet_arg if pet_arg.is_absolute() or pet_arg.exists() else args.codex_pets_dir.expanduser() / args.pet
    pet_dir = pet_dir.resolve()
    if not pet_dir.is_dir():
        raise SystemExit(f"pet directory not found: {pet_dir}")

    manifest = load_pet_manifest(pet_dir)
    raw_name = str(manifest.get("id") or manifest.get("displayName") or pet_dir.name)
    output_dir = args.output_dir.expanduser() if args.output_dir else args.output_root.expanduser() / slugify(raw_name)
    output_dir = output_dir.resolve()

    character_manifest = write_character_pack(pet_dir, output_dir, args.force)
    print(json.dumps({
        "ok": True,
        "pet": str(pet_dir),
        "output": str(output_dir),
        "name": character_manifest["name"],
        "states": character_manifest["states"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
