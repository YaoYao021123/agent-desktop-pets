# Mao

Default GIF character pack for Codex Usage Stick.

This folder contains the character `manifest.json` and the GIF states used by
the StickS3 firmware:

- `sleep`
- `idle`
- `busy`
- `attention`
- `completed`
- `celebrate`
- `dizzy`
- `heart`

To upload this pack to the device, copy it into `data/characters/Mao/` and run
`pio run -e m5stack-sticks3 -t uploadfs`.
