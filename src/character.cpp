#include "character.h"
#include "ble_bridge.h"
#include <M5Unified.h>
#include <LittleFS.h>
#include <AnimatedGIF.h>
#include <ArduinoJson.h>

extern M5Canvas spr;

static const char* STATE_NAMES[] = {
  "sleep", "idle", "busy", "attention", "completed", "dizzy", "heart"
};
static const uint8_t N_STATES = 7;

static JsonVariant stateVariant(JsonObject states, uint8_t idx) {
  JsonVariant v = states[STATE_NAMES[idx]];
  if (v.isNull() && idx == 4) v = states["celebrate"];
  return v;
}

// Text mode: manifest has "mode":"text", states contain {frames:[...],delay:N}.
// Frames are short strings rendered at text size 2, centered. No GIF pipeline.
struct TextState {
  char     frames[8][20];
  uint8_t  nFrames;
  uint16_t delayMs;
};
static TextState textStates[N_STATES];
static bool      textMode = false;
static uint8_t   textFrame = 0;
static uint32_t  textNext = 0;

static bool    loaded = false;
static Palette pal = { 0xC2A6, 0x0000, 0xFFFF, 0x8410, 0x0000 };
static char    basePath[48];
static const uint8_t MAX_GIFS = 32;
static char    gifPaths[MAX_GIFS][32];
static uint8_t stateStart[N_STATES];
static uint8_t stateCount[N_STATES];
static uint8_t stateRot[N_STATES];
static uint8_t gifTotal = 0;
static uint8_t curState = 0xFF;

static AnimatedGIF gif;
static File        gifFile;
static int         gifX = 0, gifY = 0, gifW = 0, gifH = 0;
static uint8_t     renderScalePct = 50;
// Peek mode pins the GIF bottom to the info-panel top (y=70) so the pet
// sits on the panel edge regardless of canvas height. Home mode centers
// in the upper 140px. No padding assumed in the source art.
static const int   PEEK_TOP = 70;
static bool        peekMode = false;
static int         peekClipH = PEEK_TOP;
static int         peekTopY = 0;
static bool        peekBottomAlign = false;
// Draw target — defaults to the sprite; characterRenderTo() retargets to
// M5.Lcd for the landscape clock (both inherit lgfx::v1::LGFXBase).
static lgfx::LGFXBase*   _tgt = &spr;
// Peek mode defaults to half scale. Direct landscape render can temporarily
// raise renderScalePct while keeping the portrait path unchanged.
static void gifPlace() {
  int outW = peekMode ? (gifW * renderScalePct) / 100 : gifW;
  int outH = peekMode ? (gifH * renderScalePct) / 100 : gifH;
  gifX = (spr.width() - outW) / 2;
  gifY = peekMode
    ? peekTopY + (peekBottomAlign ? peekClipH - outH : (peekClipH - outH) / 2)
    : (PEEK_TOP * 2 - outH) / 2;
}
static uint32_t    nextFrameAt = 0;
static uint32_t    animPauseUntil = 0;
static uint32_t    variantStartedMs = 0;
static const uint32_t VARIANT_DWELL_MS = 5000;
static const uint32_t ANIM_PAUSE_DISCONNECTED_MS = 5000;
static const uint32_t ANIM_PAUSE_CONNECTED_MS    = 3000;
static bool        gifOpen = false;
static bool        keepFrameOnNextOpen = false;

static uint16_t parseHexColor(const char* s, uint16_t fallback) {
  if (!s) return fallback;
  if (*s == '#') s++;
  uint32_t v = strtoul(s, nullptr, 16);
  return (uint16_t)(((v >> 19) & 0x1F) << 11 | ((v >> 10) & 0x3F) << 5 | ((v >> 3) & 0x1F));
}

// --- AnimatedGIF file callbacks (LittleFS) ------------------------------

static void* gifOpenCb(const char* fname, int32_t* pSize) {
  gifFile = LittleFS.open(fname, "r");
  if (!gifFile) return nullptr;
  *pSize = gifFile.size();
  return (void*)&gifFile;
}

static void gifCloseCb(void* handle) {
  File* f = (File*)handle;
  if (f) f->close();
}

static int32_t gifReadCb(GIFFILE* pFile, uint8_t* pBuf, int32_t iLen) {
  File* f = (File*)pFile->fHandle;
  int32_t n = f->read(pBuf, iLen);
  pFile->iPos = f->position();
  return n;
}

static int32_t gifSeekCb(GIFFILE* pFile, int32_t iPosition) {
  File* f = (File*)pFile->fHandle;
  f->seek(iPosition);
  pFile->iPos = (int32_t)f->position();
  return pFile->iPos;
}

// --- Draw callback: one scanline → line buffer → pushImage ------------
// Transparent pixels get the character's bg color so each frame fully
// paints its region — no ghosting from prior frames.

static void gifDrawCb(GIFDRAW* d) {
  uint16_t* pal16 = d->pPalette;
  uint8_t*  src   = d->pPixels;
  uint8_t   t     = d->ucTransparent;
  bool      hasT  = d->ucHasTransparency;
  int       srcY  = d->iY + d->y;
  // GIFs are unoptimized full-frame (gifsicle --unoptimize --lossy) so
  // transparent always means background — no disposal/delta handling.
  // The -O2/-O3 sub-rect + delta-transparency path was tried and reverted:
  // disposal semantics are encoder-dependent and don't compose with the
  // 2:1 peek downscale's sample alignment.
  auto put = [&](int x, int y, uint8_t idx) {
    _tgt->drawPixel(x, y, (hasT && idx == t) ? pal.bg : pal16[idx]);
  };

  if (peekMode) {
    int y = gifY + (srcY * renderScalePct) / 100;
    if (y < peekTopY || y >= peekTopY + peekClipH) return;
    int x0 = gifX + (d->iX * renderScalePct) / 100;
    int w  = ((d->iX + d->iWidth) * renderScalePct) / 100
           - (d->iX * renderScalePct) / 100;
    if (w <= 0) return;
    for (int i = 0; i < w; i++) {
      int srcX = (i * 100) / renderScalePct;
      if (srcX >= d->iWidth) srcX = d->iWidth - 1;
      put(x0 + i, y, src[srcX]);
    }
    return;
  }

  int y = gifY + srcY;
  if (y < 0 || y >= spr.height()) return;
  int x0 = gifX + d->iX;
  int w  = d->iWidth;
  if (w > 256) w = 256;
  if (x0 < 0) { src -= x0; w += x0; x0 = 0; }
  if (x0 + w > spr.width()) w = spr.width() - x0;
  if (w <= 0) return;
  for (int i = 0; i < w; i++) put(x0 + i, y, src[i]);
}

// --- Public -------------------------------------------------------------

bool characterInit(const char* name) {
  if (!LittleFS.begin(false)) {
    // begin() fails if already mounted — that's fine on reload
    if (!LittleFS.open("/")) {
      // Can't open root → not mounted → try formatting. If that fails, give up
      if (!LittleFS.begin(true)) {
        Serial.println("[char] LittleFS format/mount failed");
        return false;
      }
    }
  }

  // No name → scan /characters/ for the first directory present.
  // Makes the boot character whatever you last installed.
  static char scanned[24];
  if (!name) {
    File d = LittleFS.open("/characters");
    if (d && d.isDirectory()) {
      File e = d.openNextFile();
      while (e) {
        if (e.isDirectory()) {
          const char* n = strrchr(e.name(), '/');
          strncpy(scanned, n ? n + 1 : e.name(), sizeof(scanned) - 1);
          scanned[sizeof(scanned) - 1] = 0;
          name = scanned;
          break;
        }
        e = d.openNextFile();
      }
      d.close();
    }
    if (!name) { Serial.println("[char] no characters installed"); return false; }
  }

  snprintf(basePath, sizeof(basePath), "/characters/%s", name);
  char mpath[64];
  snprintf(mpath, sizeof(mpath), "%s/manifest.json", basePath);

  File mf = LittleFS.open(mpath, "r");
  if (!mf) {
    Serial.printf("[char] manifest not found: %s\n", mpath);
    return false;
  }

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, mf);
  mf.close();
  if (err) {
    Serial.printf("[char] manifest parse: %s\n", err.c_str());
    return false;
  }

  JsonObject colors = doc["colors"];
  pal.body    = parseHexColor(colors["body"],    pal.body);
  pal.bg      = parseHexColor(colors["bg"],      pal.bg);
  pal.text    = parseHexColor(colors["text"],    pal.text);
  pal.textDim = parseHexColor(colors["textDim"], pal.textDim);
  pal.ink     = parseHexColor(colors["ink"],     pal.ink);

  const char* mode = doc["mode"];
  textMode = (mode && strcmp(mode, "text") == 0);

  JsonObject states = doc["states"];

  if (textMode) {
    for (uint8_t i = 0; i < N_STATES; i++) {
      TextState& ts = textStates[i];
      ts.nFrames = 0;
      ts.delayMs = 200;
      JsonObject st = stateVariant(states, i).as<JsonObject>();
      if (st.isNull()) continue;
      ts.delayMs = st["delay"] | 200;
      JsonArray fr = st["frames"];
      for (JsonVariant v : fr) {
        if (ts.nFrames >= 8) break;
        const char* s = v.as<const char*>();
        strncpy(ts.frames[ts.nFrames], s ? s : "", 19);
        ts.frames[ts.nFrames][19] = 0;
        ts.nFrames++;
      }
    }
    loaded = true;
    Serial.printf("[char] loaded '%s' (text mode, %d states)\n", name, N_STATES);
    return true;
  }

  gifTotal = 0;
  for (uint8_t i = 0; i < N_STATES; i++) {
    stateStart[i] = gifTotal;
    stateCount[i] = 0;
    stateRot[i]   = 0;
    JsonVariant v = stateVariant(states, i);
    if (v.is<JsonArray>()) {
      for (JsonVariant e : v.as<JsonArray>()) {
        if (gifTotal >= MAX_GIFS) break;
        const char* fn = e.as<const char*>();
        if (fn) { snprintf(gifPaths[gifTotal], 32, "%s", fn); gifTotal++; stateCount[i]++; }
      }
    } else {
      const char* fn = v.as<const char*>();
      if (fn) { snprintf(gifPaths[gifTotal], 32, "%s", fn); gifTotal++; stateCount[i] = 1; }
    }
  }

  gif.begin(LITTLE_ENDIAN_PIXELS);
  loaded = true;
  Serial.printf("[char] loaded '%s' from %s\n", (const char*)doc["name"], basePath);
  return true;
}

bool characterLoaded() { return loaded; }
const Palette& characterPalette() { return pal; }

// One-shot half-scale render to an arbitrary surface (M5.Lcd for the
// landscape clock). Caller owns clearing. Advances frame timing so
// animation runs even when characterTick() is bypassed.
bool characterRenderTo(lgfx::v1::LGFXBase* tgt, int cx, int cy) {
  uint32_t now = millis();
  if (!gifOpen) {
    if (animPauseUntil && now >= animPauseUntil && curState < N_STATES) {
      animPauseUntil = 0;
      keepFrameOnNextOpen = true;
      uint8_t s = curState; curState = 0xFF;
      characterSetState(s);
    }
    if (!gifOpen) return false;
  }

  lgfx::v1::LGFXBase* prevT = _tgt; bool prevP = peekMode; int px = gifX, py = gifY, pc = peekClipH, pt = peekTopY;
  uint8_t prevScale = renderScalePct;
  _tgt = tgt; peekMode = true;
  renderScalePct = 50;
  peekTopY = 0;
  peekClipH = tgt->height();
  gifX = cx - gifW / 4;
  gifY = cy - gifH / 4;
  bool drewFrame = false;
  if (now >= nextFrameAt) {
    int delayMs = 0;
    if (!gif.playFrame(false, &delayMs)) {
      // BLE-safe renderTo loop: stop decoding after one pass, then let the
      // landscape clock reopen after the same non-blocking pause as home.
      gif.close();
      gifOpen = false;
      animPauseUntil = now + (bleConnected() ? ANIM_PAUSE_CONNECTED_MS : ANIM_PAUSE_DISCONNECTED_MS);
      _tgt = prevT; peekMode = prevP; renderScalePct = prevScale; peekClipH = pc; peekTopY = pt; gifX = px; gifY = py;
      return true;
    }
    drewFrame = true;
    delay(1);  // yield to BLE / FreeRTOS tasks after a GIF decode burst
    nextFrameAt = now + (delayMs > 0 ? delayMs : 100);
  }
  _tgt = prevT; peekMode = prevP; renderScalePct = prevScale; peekClipH = pc; peekTopY = pt; gifX = px; gifY = py;
  return drewFrame;
}

bool characterRenderTo(lgfx::v1::LGFXBase* tgt, int cx, int cy, uint8_t scalePct,
                       int minX, int minY, int maxX, int maxY) {
  uint32_t now = millis();
  if (!gifOpen) {
    if (animPauseUntil && now >= animPauseUntil && curState < N_STATES) {
      animPauseUntil = 0;
      keepFrameOnNextOpen = true;
      uint8_t s = curState; curState = 0xFF;
      characterSetState(s);
    }
    if (!gifOpen) return false;
  }

  if (scalePct < 25) scalePct = 25;
  if (scalePct > 100) scalePct = 100;
  if (maxX <= minX) maxX = minX + 1;
  if (maxY <= minY) maxY = minY + 1;

  int outW = (gifW * scalePct) / 100;
  int outH = (gifH * scalePct) / 100;
  int boundW = maxX - minX;
  int boundH = maxY - minY;
  if (outW > boundW || outH > boundH) {
    uint8_t sx = (uint8_t)((uint32_t)boundW * 100 / gifW);
    uint8_t sy = (uint8_t)((uint32_t)boundH * 100 / gifH);
    scalePct = sx < sy ? sx : sy;
    if (scalePct < 25) scalePct = 25;
    outW = (gifW * scalePct) / 100;
    outH = (gifH * scalePct) / 100;
  }

  int x = cx - outW / 2;
  int y = cy - outH / 2;
  if (x < minX) x = minX;
  if (y < minY) y = minY;
  if (x + outW > maxX) x = maxX - outW;
  if (y + outH > maxY) y = maxY - outH;

  lgfx::v1::LGFXBase* prevT = _tgt; bool prevP = peekMode; int px = gifX, py = gifY, pc = peekClipH, pt = peekTopY;
  uint8_t prevScale = renderScalePct;
  _tgt = tgt; peekMode = true; renderScalePct = scalePct;
  peekTopY = minY;
  peekClipH = maxY - minY;
  gifX = x;
  gifY = y;
  bool drewFrame = false;
  if (now >= nextFrameAt) {
    int delayMs = 0;
    if (!gif.playFrame(false, &delayMs)) {
      gif.close();
      gifOpen = false;
      animPauseUntil = now + (bleConnected() ? ANIM_PAUSE_CONNECTED_MS : ANIM_PAUSE_DISCONNECTED_MS);
      _tgt = prevT; peekMode = prevP; renderScalePct = prevScale; peekClipH = pc; peekTopY = pt; gifX = px; gifY = py;
      return true;
    }
    drewFrame = true;
    delay(1);
    nextFrameAt = now + (delayMs > 0 ? delayMs : 100);
  }
  _tgt = prevT; peekMode = prevP; renderScalePct = prevScale; peekClipH = pc; peekTopY = pt; gifX = px; gifY = py;
  return drewFrame;
}

void characterSetPeek(bool peek) {
  if (peekMode == peek) return;
  peekMode = peek;
  characterInvalidate();
}

void characterSetPeekWindow(int topY, int height) {
  if (topY < 0) topY = 0;
  if (height < PEEK_TOP) height = PEEK_TOP;
  if (peekTopY == topY && peekClipH == height) return;
  peekTopY = topY;
  peekClipH = height;
  characterInvalidate();
}

void characterSetPeekBottomAlign(bool bottomAlign) {
  if (peekBottomAlign == bottomAlign) return;
  peekBottomAlign = bottomAlign;
  characterInvalidate();
}

void characterClose() {
  if (gifOpen) { gif.close(); gifOpen = false; }
  loaded = false;
  textMode = false;
  curState = 0xFF;
}

void characterInvalidate() {
  if (!loaded) return;
  if (textMode) {
    spr.fillSprite(pal.bg);
    uint8_t s = curState; curState = 0xFF;
    characterSetState(s);
    return;
  }
  if (gifOpen) { gif.close(); gifOpen = false; }
  animPauseUntil = 0;
  uint8_t s = curState; curState = 0xFF;
  characterSetState(s);
}

void characterSetState(uint8_t s) {
  if (!loaded || s >= N_STATES || s == curState) return;

  if (textMode) {
    curState = s;
    textFrame = 0;
    textNext = 0;
    spr.fillSprite(pal.bg);
    return;
  }

  if (gifOpen) { gif.close(); gifOpen = false; }
  animPauseUntil = 0;
  curState = s;

  if (stateCount[s] == 0) {
    keepFrameOnNextOpen = false;
    Serial.printf("[char] no gif for state %d\n", s);
    return;
  }

  uint8_t idx = stateStart[s] + stateRot[s];
  char full[80];
  snprintf(full, sizeof(full), "%s/%s", basePath, gifPaths[idx]);
  if (gif.open(full, gifOpenCb, gifCloseCb, gifReadCb, gifSeekCb, gifDrawCb)) {
    gifOpen = true;
    gifW = gif.getCanvasWidth();
    gifH = gif.getCanvasHeight();
    gifPlace();
    if (!keepFrameOnNextOpen) {
      spr.fillSprite(pal.bg);   // bias upward, leave room for HUD
    }
    keepFrameOnNextOpen = false;
    nextFrameAt = 0;
    variantStartedMs = millis();
    Serial.printf("[char] %s: %dx%d @ (%d,%d) heap=%u\n",
      gifPaths[idx], gifW, gifH, gifX, gifY, ESP.getFreeHeap());
  } else {
    keepFrameOnNextOpen = false;
    Serial.printf("[char] open failed: %s (err %d)\n", full, gif.getLastError());
  }
}

void characterTick() {
  if (!loaded) return;

  if (textMode) {
    TextState& ts = textStates[curState];
    if (ts.nFrames == 0) return;
    uint32_t now = millis();
    if (now < textNext) return;
    textNext = now + ts.delayMs;

    // Clear a band around the text, not the whole sprite — keeps overlays
    // like the approval panel and the HUD untouched.
    int cy = peekMode ? 35 : 60;
    spr.fillRect(0, cy - 14, spr.width(), 28, pal.bg);

    const char* line = ts.frames[textFrame];
    int len = strlen(line);
    int tw = len * 12;                                    // size-2 glyph width
    spr.setTextColor(pal.body, pal.bg);
    spr.setTextSize(2);
    spr.setCursor((spr.width() - tw) / 2, cy - 8);
    spr.print(line);

    textFrame = (textFrame + 1) % ts.nFrames;
    return;
  }

  uint32_t now = millis();

  if (!gifOpen) {
    // BLE-friendly loop: hold the last frame after one full GIF pass, then
    // reopen after the pause without blocking the main loop.
    if (animPauseUntil && now >= animPauseUntil) {
      animPauseUntil = 0;
      keepFrameOnNextOpen = true;
      uint8_t s = curState; curState = 0xFF;
      characterSetState(s);
    }
    return;
  }
  if (now < nextFrameAt) return;

  int delayMs = 0;
  if (!gif.playFrame(false, &delayMs)) {
    // BLE-safe mode:
    // Play every GIF only once, then keep the last frame on screen for a
    // non-blocking pause so BLE advertising/connection handling gets a clean
    // window between GIF decode bursts.
    gif.close();
    gifOpen = false;
    animPauseUntil = now + (bleConnected() ? ANIM_PAUSE_CONNECTED_MS : ANIM_PAUSE_DISCONNECTED_MS);
    return;
  }
  delay(1);  // yield to BLE / FreeRTOS tasks after a GIF decode burst
  nextFrameAt = now + (delayMs > 0 ? delayMs : 100);
}
