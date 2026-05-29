---
name: codex-usage-pet
description: Create, validate, preview, and package Codex Usage Stick pet spritesheets with seven hardware states: busy, idle, completed, attention, dizzy, heart, and sleep. Use when the user wants a StickS3/Codex Usage pet that outputs pet.json and spritesheet.webp instead of separate GIF files.
---

# Codex Usage Pet

## Overview

Create a Codex Usage Stick compatible animated pet from a concept, reference image, screenshot, generated image, or visual description.

This skill is based on `hatch-pet`, but it targets the StickS3 usage display states instead of the Codex app's default nine animation rows. The final package is:

```text
${CODEX_HOME:-$HOME/.codex}/pets/<pet-name>/
  pet.json
  spritesheet.webp
```

The spritesheet atlas is `1536x1456`, with 8 columns, 7 rows, and 192x208 cells.

## Animation Rows

Use this exact row order:

| Row | State | Frames | Action |
| --- | --- | ---: | --- |
| 0 | `sleep` | 6 | quiet low-power sleep, eyes closed, gentle breathing |
| 1 | `idle` | 6 | calm baseline with a complete blink motion |
| 2 | `busy` | 8 | running or energetic in-progress loop |
| 3 | `attention` | 6 | jump up, alert pose, and settle, with small exclamation mark allowed |
| 4 | `completed` | 8 | celebration, joy, and compact falling confetti |
| 5 | `dizzy` | 6 | spiral/unfocused eyes and wobbling body |
| 6 | `heart` | 6 | happy affectionate pose with small hearts close to the pet |

Unused cells after each state's final frame must be fully transparent.

## Visual Style

Match the Codex app's built-in digital pets:

- small pixel-art-adjacent mascot
- compact chibi proportions
- chunky readable silhouette
- thick dark 1-2 px outlines
- visible stepped or pixel edges
- limited palette
- flat cel shading
- simple expressive face
- tiny limbs

Avoid polished illustration, painterly rendering, anime key art, 3D rendering, glossy app-icon treatment, realistic fur/material texture, soft gradients, high-detail antialiasing, and tiny accessories that disappear at 192x208.

## Transparency And Effects

Keep the hatch-pet cleanup standard: flat chroma-key background for row strips, transparent final atlas, no shadows or scene backgrounds.

Effects are allowed only when they are state-relevant, opaque, hard-edged, pixel-style, fully inside the same frame slot, and small enough to remain readable:

- `attention`: a small exclamation mark near the pet during alert frames.
- `completed`: compact confetti falling close around or overlapping the pet.
- `dizzy`: tiny stars touching or overlapping the pet.
- `heart`: small hearts rising close around the pet.

Do not draw large detached sprite components, distant symbols, loose sparkles, glow, aura, shadows, dust, landing marks, motion arcs, speed lines, smears, labels, UI, speech bubbles, scenery, checkerboards, white backgrounds, black backgrounds, or visible guide marks.

## State Prompts

- `sleep`: relaxed closed-eye sleep loop, gentle breathing, compact posture, no bed/moon/Z text/scenery unless already part of the identity.
- `idle`: neutral low-distraction loop with a full blink cycle. Keep first and last frames visually close.
- `busy`: running or quick-trotting loop, centered in the slot, with clear limb/body cycling but no speed lines or dust.
- `attention`: anticipation, jump up, alert pose, return, settle. Expression should clearly read as "pay attention".
- `completed`: delighted celebration, raised limbs or bounce, sparse compact confetti, no checkmarks or banners.
- `dizzy`: wobble, spiral or unfocused eyes, head tilt, tiny close stars if useful, no large rings or loose effects far away.
- `heart`: warm happy pose, blush or heart eyes if fitting, small hearts rising close to the pet, no glow or icon cloud.

## Workflow

1. Prepare the run:

```bash
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/plugins/cache/codex-usage-stick-marketplace/codex-usage-stick/0.4.0/skills/codex-usage-pet"
python "$SKILL_DIR/scripts/prepare_pet_run.py" \
  --pet-name "<Name>" \
  --description "<one sentence>" \
  --reference /absolute/path/to/reference.png \
  --output-dir /absolute/path/to/run \
  --pet-notes "<stable pet identity>" \
  --style-notes "<optional style notes>" \
  --force
```

If the skill is being used from a source checkout instead of an installed plugin, set `SKILL_DIR` to the checkout path:

```bash
SKILL_DIR="/absolute/path/to/plugins/codex-usage-stick/skills/codex-usage-pet"
```

2. Check which image jobs are ready:

```bash
python "$SKILL_DIR/scripts/pet_job_status.py" --run-dir /absolute/path/to/run
```

3. Generate the base and row-strip images with `$imagegen`.

Use the prompt files listed in `imagegen-jobs.json`. Row jobs must attach the canonical base image, any user references, and the matching layout guide from `references/layout-guides/`.

4. Record each selected image output:

```bash
python "$SKILL_DIR/scripts/record_imagegen_result.py" \
  --run-dir /absolute/path/to/run \
  --job-id <job-id> \
  --source /absolute/path/to/generated-output.png
```

5. Finalize:

```bash
python "$SKILL_DIR/scripts/finalize_pet_run.py" \
  --run-dir /absolute/path/to/run
```

Expected final output:

```text
run/
  final/spritesheet.webp
  final/validation.json
  qa/contact-sheet.png
  qa/review.json
  qa/videos/*.mp4

${CODEX_HOME:-$HOME/.codex}/pets/<pet-name>/
  pet.json
  spritesheet.webp
```

## QA

Before accepting the pet, inspect:

- `qa/contact-sheet.png`
- `qa/review.json`
- `final/validation.json`
- `qa/videos/`

Reject and repair rows if identity drifts, frames are clipped, the background is not transparent after extraction, effects become large detached components, row actions are hard to distinguish, or the first/last frame creates a harsh loop pop.

## Rules

- Generate visual content with `$imagegen`; do not draw or synthesize pet art locally.
- Use local scripts only for prompts, manifests, extraction, validation, atlas composition, previews, and packaging.
- Keep every row recognizably the same individual pet.
- Preserve the same silhouette, face, markings, palette, prop design, outline weight, and body proportions across rows.
- Do not accept outputs that copy guide pixels, include visible grids, contain text labels, or show cropped reference fragments.
- The final package must contain both `pet.json` and `spritesheet.webp`.
