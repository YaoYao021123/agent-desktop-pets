#pragma once
#include <stdint.h>

struct Palette {
  uint16_t body, bg, text, textDim, ink;
};

// Call after M5.begin() and spr.createSprite(). Mounts LittleFS, reads
// /characters/<name>/manifest.json, parses colors, caches GIF paths.
bool characterInit(const char* name);
bool characterLoaded();

// 0..6: sleep, idle, busy, attention, completed, dizzy, heart.
// Closes current GIF, opens the one for this state. No-op if same state.
void characterSetState(uint8_t state);

// Advances timing; if it's time for the next frame, decodes it into the
// sprite. Call every loop iteration. Does nothing if not loaded.
void characterTick();
void characterInvalidate();
void characterClose();   // close GIF + clear loaded flag; FS stays mounted   // full clear + reopen current — call when an overlay closes

// Peek mode renders the GIF at half scale, centered in the info-panel
// header strip; off renders full-size centered in the upper home area.
// Adaptive to actual canvas height — no padding required in source art.
void characterSetPeek(bool peek);
void characterSetPeekWindow(int topY, int height);
void characterSetPeekBottomAlign(bool bottomAlign);
namespace lgfx { inline namespace v1 { class LGFXBase; } }
// Renders one GIF frame to an arbitrary target when frame timing allows it.
// Returns true only when a new frame was drawn.
bool characterRenderTo(lgfx::v1::LGFXBase* tgt, int cx, int cy);
bool characterRenderTo(lgfx::v1::LGFXBase* tgt, int cx, int cy, uint8_t scalePct,
                       int minX, int minY, int maxX, int maxY);

const Palette& characterPalette();
