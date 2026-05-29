# Animation Rows

The Codex Usage Stick pet atlas uses 8 columns, 7 rows, and 192x208 pixels per cell.

| Row | State | Used columns | Durations |
| --- | --- | ---: | --- |
| 0 | sleep | 0-5 | 260, 180, 180, 180, 180, 420 ms |
| 1 | idle | 0-5 | 280, 110, 110, 140, 140, 320 ms |
| 2 | busy | 0-7 | 110 ms each, final 180 ms |
| 3 | attention | 0-5 | 120, 120, 140, 160, 140, 260 ms |
| 4 | completed | 0-7 | 120 ms each, final 260 ms |
| 5 | dizzy | 0-5 | 130 ms each, final 260 ms |
| 6 | heart | 0-5 | 150 ms each, final 280 ms |

Unused cells after each row's final used column must be fully transparent.

## Row Purposes

- `sleep`: quiet low-power loop with closed eyes and gentle breathing.
- `idle`: calm baseline loop with a complete blink motion.
- `busy`: energetic running or in-progress loop, centered in the slot.
- `attention`: jump up, alert pose, and settle, with a small nearby exclamation mark allowed.
- `completed`: joyful celebration with compact confetti close to the pet.
- `dizzy`: wobble, spiral or unfocused eyes, and tiny close stars if useful.
- `heart`: affectionate happy loop with small hearts rising close to the pet.
