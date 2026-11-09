/*
 * XIAO_RP2040_Blink
 * Version: 2.5.0
 *
 * Pin map, wiring, and changelog: see README.md
 * Eyes only, full-screen roam. Boot shows pixel insightx.
 */

#include <Adafruit_NeoPixel.h>
#include <U8g2lib.h>
#include <Wire.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <avr/pgmspace.h>

#define APP_VERSION "2.5.0"
#define EMOTION_ID_FALLBACK "02"
#define EMOTION_COUNT 32

#define PIXEL_BRIGHTNESS 35

int Power = 11;
int PIN  = 12;
#define NUMPIXELS 1

int displayValue = 0;

Adafruit_NeoPixel pixels(NUMPIXELS, PIN, NEO_GRB + NEO_KHZ800);
U8G2_SSD1306_128X64_NONAME_1_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);

static const int LX0 = 38;
static const int RX0 = 90;
static const int EY0 = 32;

static char emotionId[4] = "02";
static char emotionTips[16] = "idle";
static int currentEid = 2;
static uint32_t emotionStartMs = 0;

static const char kEmoId[EMOTION_COUNT][3] PROGMEM = {
  "00", "01", "02", "03", "04", "05", "06", "07",
  "10", "11", "12", "13", "14", "15", "16", "17",
  "18", "19", "20", "21", "30", "31", "32", "33",
  "34", "35", "36", "37", "38", "39", "40", "41"
};

static const char kEmoTip[EMOTION_COUNT][11] PROGMEM = {
  "sleep", "wake", "idle", "curious",
  "daze", "boot", "dormant", "shake",
  "happy", "puzzled", "down", "surprise",
  "shy", "tired", "focus", "panic",
  "resigned", "satisfied", "confused", "angry",
  "think", "recv", "busy", "done",
  "error", "listen", "load", "recall",
  "refuse", "reply", "search", "stop"
};

enum : uint8_t {
  SH_CIRCLE = 0,
  SH_RECT = 1,
  SH_CAPSULE = 2
};

enum : uint8_t {
  MOT_NONE = 0,
  MOT_GLANCE_X,
  MOT_SINE_X,
  MOT_SINE_Y,
  MOT_SINE_XY,
  MOT_JITTER,
  MOT_SCAN,
  MOT_BLINK_ALT,
  MOT_NOD,
  MOT_DIVERGE,
  MOT_SHAKE_X,
  MOT_PULSE,
  MOT_WAKE
};

struct EyeProfile {
  uint8_t shapeL, shapeR;
  uint8_t wL, hL, wR, hR;
  int8_t oxL, oyL, oxR, oyR;
  int8_t lookX, lookY;
  int8_t angL, angR; /* 0=horizontal, 90=vertical */
  uint8_t openL, openR;
  uint8_t motion;
  uint8_t amp;
  uint16_t period;
  uint8_t blink;
  uint8_t roam;
  uint8_t invert;
};

static void truncateStr(char* dst, size_t dstSize, const char* src, size_t maxLen) {
  if (dstSize == 0) return;
  size_t n = strlen(src);
  if (n > maxLen) n = maxLen;
  if (n >= dstSize) n = dstSize - 1;
  memcpy(dst, src, n);
  dst[n] = '\0';
}

static int parseEmotionIdNum(const char* id) {
  if (id == nullptr || strlen(id) < 2) return 2;
  return (id[0] - '0') * 10 + (id[1] - '0');
}

static uint8_t findEmotionIndex(const char* id) {
  if (id == nullptr || strlen(id) < 2) return 255;
  for (uint8_t i = 0; i < EMOTION_COUNT; i++) {
    char a = (char)pgm_read_byte(&kEmoId[i][0]);
    char b = (char)pgm_read_byte(&kEmoId[i][1]);
    if (a == id[0] && b == id[1]) return i;
  }
  return 255;
}

static int scale13(int v) {
  return (v * 4) / 3;
}

static int clmpi(int v, int lo, int hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

static int pingPongStep(uint32_t t, uint16_t stepMs, uint8_t lo, uint8_t hi) {
  if (hi <= lo || stepMs == 0) return lo;
  int span = (int)hi - (int)lo;
  int cycle = span * 2;
  int idx = (int)((t / stepMs) % (uint32_t)cycle);
  if (idx > span) idx = cycle - idx;
  return (int)lo + idx;
}

static EyeProfile profileFor(int eid) {
  EyeProfile p;
  memset(&p, 0, sizeof(p));
  p.shapeL = p.shapeR = SH_CAPSULE;
  p.wL = p.wR = 6;
  p.hL = p.hR = 14;
  p.angL = 82;
  p.angR = 98;
  p.openL = p.openR = 100;
  p.period = 2800;
  p.amp = 6;
  p.roam = 1;

  switch (eid) {
    case 0:  /* sleep: both horizontal */
      p.wL = p.wR = 4;
      p.hL = p.hR = 13;
      p.angL = p.angR = 8;
      p.openL = p.openR = 100;
      p.oyL = p.oyR = 6;
      p.motion = MOT_SINE_Y;
      p.amp = 1;
      p.period = 3600;
      p.blink = 0;
      p.roam = 0;
      break;
    case 1:  /* wake / wink: left vertical, right horizontal */
      p.wL = 6;
      p.hL = 16;
      p.angL = 84;
      p.wR = 5;
      p.hR = 11;
      p.angR = 6;
      p.oyR = 3;
      p.motion = MOT_SINE_Y;
      p.amp = 2;
      p.period = 1800;
      p.blink = 0;
      break;
    case 2:  /* idle: two vertical capsules, slight tilt */
      p.wL = 6;
      p.hL = 15;
      p.angL = 78;
      p.wR = 5;
      p.hR = 13;
      p.angR = 102;
      p.motion = MOT_GLANCE_X;
      p.amp = 16;
      p.period = 4800;
      p.blink = 1;
      p.roam = 2;
      break;
    case 3:  /* curious: left \, right / */
      p.wL = 6;
      p.hL = 14;
      p.angL = -42;
      p.wR = 5;
      p.hR = 12;
      p.angR = 28;
      p.oyL = p.oyR = -2;
      p.motion = MOT_SINE_X;
      p.amp = 3;
      p.period = 2800;
      p.blink = 1;
      break;
    case 4:  /* daze */
      p.angL = 70;
      p.angR = 110;
      p.oxL = -3;
      p.oxR = 4;
      p.motion = MOT_DIVERGE;
      p.amp = 4;
      p.period = 6800;
      p.blink = 1;
      break;
    case 5:  /* boot alt blink: wink cycle */
      p.angL = 88;
      p.angR = 10;
      p.hR = 10;
      p.motion = MOT_BLINK_ALT;
      p.period = 1600;
      p.blink = 2;
      break;
    case 6:  /* dormant */
      p.wL = p.wR = 5;
      p.hL = p.hR = 12;
      p.angL = 12;
      p.angR = -8;
      p.oyL = p.oyR = 5;
      p.motion = MOT_SINE_Y;
      p.amp = 1;
      p.period = 5000;
      p.blink = 0;
      p.roam = 0;
      break;
    case 7:  /* shake */
      p.angL = 55;
      p.angR = 120;
      p.hL = 12;
      p.hR = 10;
      p.motion = MOT_JITTER;
      p.amp = 5;
      p.period = 80;
      p.blink = 0;
      break;
    case 10: /* happy squint \ / */
      p.wL = p.wR = 6;
      p.hL = p.hR = 13;
      p.angL = -40;
      p.angR = 40;
      p.oyL = p.oyR = -2;
      p.motion = MOT_SINE_Y;
      p.amp = 3;
      p.period = 1400;
      p.blink = 0;
      break;
    case 11: /* puzzled: left tall vertical, right short horizontal */
      p.wL = 6;
      p.hL = 17;
      p.angL = 86;
      p.wR = 5;
      p.hR = 12;
      p.angR = 8;
      p.oyR = 4;
      p.motion = MOT_SINE_Y;
      p.amp = 2;
      p.period = 3200;
      p.blink = 0;
      break;
    case 12: /* down */
      p.angL = 20;
      p.angR = -18;
      p.oyL = p.oyR = 6;
      p.hL = p.hR = 12;
      p.motion = MOT_SINE_Y;
      p.amp = 2;
      p.period = 3600;
      p.blink = 1;
      break;
    case 13: /* surprise round */
      p.shapeL = p.shapeR = SH_CIRCLE;
      p.wL = p.wR = 16;
      p.hL = p.hR = 16;
      p.oyL = p.oyR = -4;
      p.motion = MOT_PULSE;
      p.amp = 3;
      p.period = 420;
      p.blink = 1;
      break;
    case 14: /* shy wink */
      p.wL = 5;
      p.hL = 14;
      p.angL = 80;
      p.wR = 4;
      p.hR = 10;
      p.angR = 12;
      p.oxL = p.oxR = 6;
      p.oyL = p.oyR = 3;
      p.motion = MOT_SINE_X;
      p.amp = 2;
      p.period = 2600;
      p.blink = 0;
      break;
    case 15: /* tired */
      p.wL = p.wR = 5;
      p.hL = p.hR = 12;
      p.angL = 18;
      p.angR = -16;
      p.oyL = p.oyR = 5;
      p.motion = MOT_SINE_Y;
      p.amp = 1;
      p.period = 3400;
      p.blink = 0;
      break;
    case 16: /* focus vertical closer */
      p.angL = 90;
      p.angR = 90;
      p.oxL = 5;
      p.oxR = -5;
      p.wL = p.wR = 5;
      p.hL = p.hR = 14;
      p.motion = MOT_NONE;
      p.blink = 1;
      break;
    case 17: /* panic */
      p.angL = -30;
      p.angR = 55;
      p.hL = p.hR = 16;
      p.motion = MOT_JITTER;
      p.amp = 6;
      p.period = 50;
      p.blink = 1;
      p.roam = 2;
      break;
    case 18: /* resigned */
      p.angL = 55;
      p.angR = 125;
      p.oxL = p.oxR = 5;
      p.oyL = p.oyR = -5;
      p.motion = MOT_SINE_Y;
      p.amp = 2;
      p.period = 3000;
      p.blink = 1;
      break;
    case 19: /* satisfied \ / nod */
      p.angL = -36;
      p.angR = 36;
      p.wL = p.wR = 6;
      p.hL = p.hR = 12;
      p.motion = MOT_NOD;
      p.amp = 5;
      p.period = 1050;
      p.blink = 0;
      break;
    case 20: /* confused: left vertical, right horizontal, mismatch */
      p.wL = 7;
      p.hL = 16;
      p.angL = 92;
      p.wR = 4;
      p.hR = 10;
      p.angR = -12;
      p.oyL = -3;
      p.oyR = 5;
      p.motion = MOT_DIVERGE;
      p.amp = 3;
      p.period = 3200;
      p.blink = 0;
      break;
    case 21: /* angry: inward slants + filled screen */
      p.wL = p.wR = 6;
      p.hL = 14;
      p.hR = 15;
      p.angL = 48;
      p.angR = 78;
      p.oxL = 2;
      p.oxR = -2;
      p.invert = 1;
      p.motion = MOT_JITTER;
      p.amp = 2;
      p.period = 70;
      p.blink = 0;
      p.roam = 0;
      break;
    case 30: /* think */
      p.angL = 70;
      p.angR = 110;
      p.lookY = -6;
      p.oyL = p.oyR = -3;
      p.motion = MOT_SINE_X;
      p.amp = 14;
      p.period = 2600;
      p.blink = 1;
      break;
    case 31: /* recv */
      p.angL = 88;
      p.angR = 12;
      p.hR = 11;
      p.motion = MOT_NOD;
      p.amp = 3;
      p.period = 700;
      p.blink = 0;
      break;
    case 32: /* busy */
      p.angL = 60;
      p.angR = 120;
      p.motion = MOT_SINE_XY;
      p.amp = 8;
      p.period = 1200;
      p.blink = 1;
      p.roam = 2;
      break;
    case 33: /* done smile \ / */
      p.angL = -42;
      p.angR = 42;
      p.wL = p.wR = 6;
      p.hL = p.hR = 13;
      p.oyL = p.oyR = -3;
      p.motion = MOT_NOD;
      p.amp = 4;
      p.period = 700;
      p.blink = 0;
      break;
    case 34: /* error invert uneven */
      p.angL = 40;
      p.angR = 85;
      p.oyL = -3;
      p.oyR = 4;
      p.invert = 1;
      p.motion = MOT_JITTER;
      p.amp = 3;
      p.period = 60;
      p.blink = 0;
      p.roam = 0;
      break;
    case 35: /* listen tall */
      p.wL = p.wR = 5;
      p.hL = p.hR = 16;
      p.angL = 90;
      p.angR = 90;
      p.motion = MOT_SINE_Y;
      p.amp = 6;
      p.period = 2200;
      p.blink = 1;
      break;
    case 36: /* load wink alt */
      p.angL = 90;
      p.angR = 0;
      p.hR = 10;
      p.motion = MOT_BLINK_ALT;
      p.period = 1200;
      p.blink = 2;
      break;
    case 37: /* recall */
      p.angL = 75;
      p.angR = 105;
      p.lookY = -9;
      p.oyL = p.oyR = -3;
      p.motion = MOT_SINE_Y;
      p.amp = 2;
      p.period = 4000;
      p.blink = 0;
      break;
    case 38: /* refuse */
      p.angL = 35;
      p.angR = 145;
      p.hL = p.hR = 12;
      p.oyL = p.oyR = 3;
      p.motion = MOT_SHAKE_X;
      p.amp = 8;
      p.period = 800;
      p.blink = 0;
      break;
    case 39: /* reply */
      p.angL = 0;
      p.angR = 0;
      p.wL = p.wR = 5;
      p.hL = p.hR = 14;
      p.motion = MOT_PULSE;
      p.amp = 2;
      p.period = 680;
      p.blink = 0;
      break;
    case 40: /* search */
      p.angL = 8;
      p.angR = -8;
      p.wL = p.wR = 5;
      p.hL = p.hR = 15;
      p.motion = MOT_SCAN;
      p.amp = 18;
      p.period = 700;
      p.blink = 1;
      p.roam = 2;
      break;
    case 41: /* stop */
      p.angL = p.angR = 0;
      p.wL = p.wR = 3;
      p.hL = p.hR = 8;
      p.oyL = p.oyR = 4;
      p.motion = MOT_NONE;
      p.blink = 0;
      p.roam = 0;
      break;
    default:
      p.motion = MOT_GLANCE_X;
      p.blink = 1;
      break;
  }
  return p;
}

#if 0
    case 0:  /* sleep: thin rect, slow breathe */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 14;
      p.hL = p.hR = 3;
      p.openL = p.openR = 18;
      p.oyL = p.oyR = 6;
      p.motion = MOT_SINE_Y;
      p.amp = 1;
      p.period = 3600;
      p.blink = 0;
      p.roam = 0;
      break;
    case 1:  /* wake */
      p.wL = p.wR = 11;
      p.hL = p.hR = 9;
      p.motion = MOT_WAKE;
      p.period = 2100;
      p.blink = 0;
      break;
    case 2:  /* idle glance */
      p.motion = MOT_GLANCE_X;
      p.amp = 16;
      p.period = 4800;
      p.blink = 1;
      p.roam = 2;
      break;
    case 3:  /* curious wide */
      p.wL = p.wR = 15;
      p.hL = p.hR = 14;
      p.oyL = p.oyR = -3;
      p.lookY = -2;
      p.motion = MOT_SINE_X;
      p.amp = 3;
      p.period = 2800;
      p.blink = 1;
      break;
    case 4:  /* daze: each eye wanders */
      p.hL = 8;
      p.hR = 7;
      p.oxL = -3;
      p.oxR = 4;
      p.motion = MOT_DIVERGE;
      p.amp = 4;
      p.period = 6800;
      p.blink = 1;
      break;
    case 5:  /* boot: alternate blink */
      p.motion = MOT_BLINK_ALT;
      p.period = 1600;
      p.blink = 2;
      break;
    case 6:  /* dormant */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 13;
      p.hL = p.hR = 5;
      p.openL = p.openR = 40;
      p.oyL = p.oyR = 5;
      p.motion = MOT_SINE_Y;
      p.amp = 1;
      p.period = 5000;
      p.blink = 0;
      p.roam = 0;
      break;
    case 7:  /* shake */
      p.wL = 10;
      p.wR = 8;
      p.hL = 8;
      p.hR = 5;
      p.motion = MOT_JITTER;
      p.amp = 5;
      p.period = 80;
      p.blink = 0;
      break;
    case 10: /* happy: wide short rect */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 14;
      p.hL = p.hR = 6;
      p.oyL = p.oyR = -3;
      p.motion = MOT_SINE_Y;
      p.amp = 3;
      p.period = 1400;
      p.blink = 1;
      break;
    case 11: /* puzzled: size mismatch */
      p.wL = 14;
      p.hL = 12;
      p.wR = 9;
      p.hR = 8;
      p.oyL = -4;
      p.oyR = 4;
      p.lookX = 3;
      p.motion = MOT_SINE_Y;
      p.amp = 2;
      p.period = 3200;
      p.blink = 1;
      break;
    case 12: /* down */
      p.wL = p.wR = 10;
      p.hL = p.hR = 8;
      p.oyL = p.oyR = 7;
      p.lookY = 4;
      p.motion = MOT_SINE_Y;
      p.amp = 2;
      p.period = 3600;
      p.blink = 1;
      break;
    case 13: /* surprise */
      p.wL = p.wR = 16;
      p.hL = p.hR = 16;
      p.oyL = p.oyR = -4;
      p.motion = MOT_PULSE;
      p.amp = 3;
      p.period = 420;
      p.blink = 1;
      break;
    case 14: /* shy */
      p.wL = p.wR = 9;
      p.hL = p.hR = 8;
      p.oxL = p.oxR = 6;
      p.oyL = p.oyR = 4;
      p.lookX = 8;
      p.lookY = 3;
      p.motion = MOT_SINE_X;
      p.amp = 2;
      p.period = 2600;
      p.blink = 1;
      break;
    case 15: /* tired */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 14;
      p.hL = p.hR = 6;
      p.openL = p.openR = 55;
      p.oyL = p.oyR = 5;
      p.lookY = 3;
      p.motion = MOT_SINE_Y;
      p.amp = 1;
      p.period = 3400;
      p.blink = 0;
      break;
    case 16: /* focus: converge */
      p.wL = p.wR = 10;
      p.hL = p.hR = 10;
      p.oxL = 5;
      p.oxR = -5;
      p.motion = MOT_NONE;
      p.blink = 1;
      break;
    case 17: /* panic */
      p.wL = p.wR = 16;
      p.hL = p.hR = 15;
      p.motion = MOT_JITTER;
      p.amp = 6;
      p.period = 50;
      p.blink = 1;
      p.roam = 2;
      break;
    case 18: /* resigned: look up-away */
      p.oxL = p.oxR = 5;
      p.oyL = p.oyR = -5;
      p.lookX = 7;
      p.lookY = -8;
      p.motion = MOT_SINE_Y;
      p.amp = 2;
      p.period = 3000;
      p.blink = 1;
      break;
    case 19: /* satisfied nod */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 13;
      p.hL = p.hR = 8;
      p.motion = MOT_NOD;
      p.amp = 5;
      p.period = 1050;
      p.blink = 1;
      break;
    case 20: /* confused mismatch */
      p.wL = 15;
      p.hL = 13;
      p.wR = 8;
      p.hR = 7;
      p.oyL = -3;
      p.oyR = 5;
      p.motion = MOT_DIVERGE;
      p.amp = 3;
      p.period = 3200;
      p.blink = 1;
      break;
    case 21: /* angry rect */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 12;
      p.hL = p.hR = 7;
      p.oyL = -2;
      p.oyR = -2;
      p.oxL = 2;
      p.oxR = -2;
      p.motion = MOT_JITTER;
      p.amp = 2;
      p.period = 70;
      p.blink = 1;
      break;
    case 30: /* think: gaze patrol up */
      p.lookY = -6;
      p.oyL = p.oyR = -3;
      p.motion = MOT_SINE_X;
      p.amp = 14;
      p.period = 2600;
      p.blink = 1;
      break;
    case 31: /* recv */
      p.wL = p.wR = 13;
      p.hL = p.hR = 12;
      p.motion = MOT_WAKE;
      p.period = 700;
      p.blink = 0;
      break;
    case 32: /* busy */
      p.wL = p.wR = 11;
      p.hL = p.hR = 10;
      p.motion = MOT_SINE_XY;
      p.amp = 8;
      p.period = 1200;
      p.blink = 1;
      p.roam = 2;
      break;
    case 33: /* done smile rect */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 14;
      p.hL = p.hR = 6;
      p.oyL = p.oyR = -4;
      p.motion = MOT_NOD;
      p.amp = 4;
      p.period = 700;
      p.blink = 1;
      break;
    case 34: /* error uneven */
      p.wL = p.wR = 15;
      p.hL = p.hR = 14;
      p.oyL = -4;
      p.oyR = 5;
      p.motion = MOT_JITTER;
      p.amp = 3;
      p.period = 60;
      p.blink = 0;
      break;
    case 35: /* listen tall */
      p.wL = p.wR = 9;
      p.hL = p.hR = 14;
      p.motion = MOT_SINE_Y;
      p.amp = 6;
      p.period = 2200;
      p.blink = 1;
      break;
    case 36: /* load alt blink */
      p.motion = MOT_BLINK_ALT;
      p.period = 1200;
      p.blink = 2;
      break;
    case 37: /* recall look up */
      p.wL = p.wR = 10;
      p.hL = p.hR = 13;
      p.lookX = 3;
      p.lookY = -9;
      p.oyL = p.oyR = -3;
      p.motion = MOT_SINE_Y;
      p.amp = 2;
      p.period = 4000;
      p.blink = 0;
      break;
    case 38: /* refuse shake */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 12;
      p.hL = p.hR = 6;
      p.openL = p.openR = 60;
      p.oyL = p.oyR = 3;
      p.lookY = 3;
      p.motion = MOT_SHAKE_X;
      p.amp = 8;
      p.period = 800;
      p.blink = 1;
      break;
    case 39: /* reply scan pulse */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 15;
      p.hL = p.hR = 6;
      p.oyL = p.oyR = -2;
      p.motion = MOT_PULSE;
      p.amp = 2;
      p.period = 680;
      p.blink = 0;
      break;
    case 40: /* search */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 16;
      p.hL = p.hR = 5;
      p.motion = MOT_SCAN;
      p.amp = 18;
      p.period = 700;
      p.blink = 1;
      p.roam = 2;
      break;
    case 41: /* stop close */
      p.shapeL = p.shapeR = SH_RECT;
      p.wL = p.wR = 8;
      p.hL = p.hR = 3;
      p.openL = p.openR = 20;
      p.oyL = p.oyR = 4;
      p.motion = MOT_NONE;
      p.blink = 0;
      p.roam = 0;
      break;
    default:
      p.motion = MOT_GLANCE_X;
      p.blink = 1;
      break;
  }
  return p;
}

#endif

static int sineOff(uint32_t t, uint16_t period, int amp) {
  if (period == 0 || amp == 0) return 0;
  float ph = (float)(t % period) * 6.2831853f / (float)period;
  return (int)(sinf(ph) * (float)amp);
}

static int glanceOff(uint32_t t, uint16_t period, int amp) {
  if (period == 0) return 0;
  uint32_t p = t % period;
  uint32_t q = period / 5;
  if (p < q) return -amp;
  if (p < q * 2) return 0;
  if (p < q * 3) return amp;
  if (p < q * 4) return 0;
  return 0;
}

static int scanOff(uint32_t t, uint16_t period, int amp) {
  if (period < 2) return 0;
  uint32_t p = t % period;
  uint32_t h = period / 2;
  if (p < h) return -amp + (int)(2L * amp * (long)p / (long)h);
  return amp - (int)(2L * amp * (long)(p - h) / (long)h);
}

static int jitterOff(int amp) {
  if (amp <= 0) return 0;
  return (int)(random(amp * 2 + 1)) - amp;
}

static uint8_t blinkOpen(uint32_t t, uint8_t baseOpen, uint8_t mode, uint16_t phaseMs) {
  if (mode == 0) return baseOpen;
  uint32_t interval = (mode == 2) ? 1200 : 3200;
  uint32_t local = (t + phaseMs) % interval;
  if (local < 90) return 8;
  return baseOpen;
}

static void drawCapsule(int cx, int cy, int halfLen, int halfThick, int angleDeg) {
  if (halfThick < 2) halfThick = 2;
  if (halfLen < halfThick) halfLen = halfThick;
  float rad = (float)angleDeg * 0.017453292f;
  float c = cosf(rad);
  float s = sinf(rad);
  int span = halfLen - halfThick;
  if (span < 0) span = 0;
  int step = (halfThick >= 4) ? 2 : 1;
  for (int d = -span; d <= span; d += step) {
    u8g2.drawDisc(cx + (int)(c * (float)d), cy + (int)(s * (float)d), halfThick);
  }
}

static void drawOneEye(int cx, int cy, int hw, int hh, uint8_t shape, uint8_t openPct, int radius, int ang) {
  if (hw < 1) hw = 1;
  int h = (int)hh * (int)openPct / 100;
  if (h < 1) h = 1;
  if (shape == SH_CAPSULE) {
    int halfLen = hh;
    int halfThick = hw;
    if (openPct < 18) {
      halfLen = hw + 6;
      halfThick = 3;
      ang = 0;
    } else if (openPct < 60) {
      halfLen = h;
      if (halfLen < halfThick + 2) halfLen = halfThick + 2;
    }
    drawCapsule(cx, cy, halfLen, halfThick, ang);
    return;
  }
  if (openPct < 14) {
    u8g2.drawBox(cx - hw, cy - 1, hw * 2, 2);
    return;
  }
  if (shape == SH_RECT) {
    int maxR = (hw < h) ? hw : h;
    if (radius < 2) radius = 2;
    if (radius > maxR) radius = maxR;
    if (radius < 1) radius = 1;
    u8g2.drawRBox(cx - hw, cy - h, hw * 2, h * 2, radius);
  } else {
    u8g2.drawFilledEllipse(cx, cy, hw, h, U8G2_DRAW_ALL);
  }
}

static void tickEmotion(uint32_t now) {
  EyeProfile p = profileFor(currentEid);
  uint32_t t = now - emotionStartMs;

  int lookX = p.lookX;
  int lookY = p.lookY;
  int extraL = 0;
  int extraR = 0;
  int extraY = 0;
  int scaleAdd = 0;
  uint8_t openL = p.openL;
  uint8_t openR = p.openR;

  switch (p.motion) {
    case MOT_GLANCE_X:
      lookX += glanceOff(t, p.period, p.amp);
      break;
    case MOT_SINE_X:
      lookX += sineOff(t, p.period, p.amp);
      break;
    case MOT_SINE_Y:
      lookY += sineOff(t, p.period, p.amp);
      break;
    case MOT_SINE_XY:
      lookX += sineOff(t, p.period, p.amp);
      lookY += sineOff(t, (p.period * 3) / 4, (p.amp * 2) / 3);
      break;
    case MOT_JITTER:
      lookX += jitterOff(p.amp);
      lookY += jitterOff(p.amp / 2 + 1);
      break;
    case MOT_SCAN:
      lookX += scanOff(t, p.period, p.amp);
      break;
    case MOT_BLINK_ALT:
      openL = blinkOpen(t, p.openL, 2, 0);
      openR = blinkOpen(t, p.openR, 2, p.period / 2);
      break;
    case MOT_NOD:
      extraY = sineOff(t, p.period, p.amp);
      break;
    case MOT_DIVERGE:
      extraL = sineOff(t, p.period, p.amp);
      extraR = sineOff(t, p.period, p.amp);
      extraR = -extraR;
      lookX += extraL / 2;
      break;
    case MOT_SHAKE_X:
      if (t < 800) {
        lookX += sineOff(t, 160, p.amp);
      }
      break;
    case MOT_PULSE:
      scaleAdd = (sineOff(t, p.period, p.amp) + p.amp) / 2;
      break;
    case MOT_WAKE: {
      if (t < 420) {
        openL = 12;
        openR = 12;
      } else if (t < 820) {
        openL = 55;
        openR = 14;
      } else if (t < 1400) {
        openL = 30;
        openR = 30;
      } else {
        openL = 100;
        openR = 100;
        scaleAdd = (t < 2100) ? 2 : 0;
      }
      break;
    }
    default:
      break;
  }

  if (p.blink == 1) {
    openL = blinkOpen(t, openL, 1, 0);
    openR = blinkOpen(t, openR, 1, 0);
  }

  int pairX = 0;
  int pairY = 0;
  if (p.roam == 1) {
    pairX = sineOff(t, 5200, 26);
    pairY = sineOff(t, 4300, 14);
  } else if (p.roam == 2) {
    pairX = sineOff(t, 3800, 38);
    pairY = sineOff(t, 3100, 18);
  }

  int rectStep = pingPongStep(t, 130, 0, 5);
  int radius = 2 + rectStep;
  int hBump = (rectStep > 0) ? (rectStep - 2) : 0;

  int hwL = scale13(p.wL) + scaleAdd;
  int hhL = scale13(p.hL) + scaleAdd;
  int hwR = scale13(p.wR) + scaleAdd;
  int hhR = scale13(p.hR) + scaleAdd;
  if (p.shapeL == SH_CAPSULE || p.shapeL == SH_RECT) hhL += hBump / 2;
  if (p.shapeR == SH_CAPSULE || p.shapeR == SH_RECT) hhR += hBump / 2;
  if (hhL < 1) hhL = 1;
  if (hhR < 1) hhR = 1;

  int angL = p.angL;
  int angR = p.angR;
  if (p.motion == MOT_JITTER) {
    angL += jitterOff(8);
    angR += jitterOff(8);
  }

  int lx = LX0 + scale13(p.oxL) + lookX + extraL + pairX;
  int ly = EY0 + scale13(p.oyL) + lookY + extraY + pairY;
  int rx = RX0 + scale13(p.oxR) + lookX + extraR + pairX;
  int ry = EY0 + scale13(p.oyR) + lookY + extraY + pairY;

  int boundL = (hhL > hwL) ? hhL : hwL;
  int boundR = (hhR > hwR) ? hhR : hwR;
  lx = clmpi(lx, boundL, 127 - boundL);
  ly = clmpi(ly, boundL, 63 - boundL);
  rx = clmpi(rx, boundR, 127 - boundR);
  ry = clmpi(ry, boundR, 63 - boundR);

  u8g2.firstPage();
  do {
    if (p.invert) {
      u8g2.drawBox(0, 0, 128, 64);
      u8g2.setDrawColor(0);
    } else {
      u8g2.setDrawColor(1);
    }
    drawOneEye(lx, ly, hwL, hhL, p.shapeL, openL, radius, angL);
    drawOneEye(rx, ry, hwR, hhR, p.shapeR, openR, radius, angR);
    u8g2.setDrawColor(1);
  } while (u8g2.nextPage());
}

void setEmotion(const char* id) {
  uint8_t idx = findEmotionIndex(id);
  if (idx == 255) {
    id = EMOTION_ID_FALLBACK;
    idx = findEmotionIndex(id);
  }
  truncateStr(emotionId, sizeof(emotionId), id, 2);
  if (idx != 255) {
    char tip[12];
    strcpy_P(tip, kEmoTip[idx]);
    truncateStr(emotionTips, sizeof(emotionTips), tip, 14);
  }
  currentEid = parseEmotionIdNum(emotionId);
  emotionStartMs = millis();
  tickEmotion(emotionStartMs);
}

void setEmotionTips(const char* tips) {
  if (tips == nullptr || tips[0] == '\0') return;
  truncateStr(emotionTips, sizeof(emotionTips), tips, 14);
  tickEmotion(millis());
}

void handleEmotionMessage(const char* id, const char* tips) {
  setEmotion(id);
  if (tips != nullptr && tips[0] != '\0') {
    setEmotionTips(tips);
  }
}

void driveFace(uint8_t face) {
  static const char legacyIds[][3] PROGMEM = {
    "10", "12", "21", "02", "13", "00", "14", "01",
    "16", "20", "34", "12", "02", "40"
  };
  if (face < 14) {
    char id[3];
    strcpy_P(id, legacyIds[face]);
    setEmotion(id);
  } else {
    setEmotion(EMOTION_ID_FALLBACK);
  }
}

void drivePixels(uint8_t r, uint8_t g, uint8_t b) {
  pixels.clear();
  pixels.setPixelColor(0, pixels.Color(r, g, b));
  pixels.show();
}

void driveDisplay(int value) {
  char data[12];
  snprintf(data, sizeof(data), "%d", value);
  u8g2.firstPage();
  do {
    u8g2.setFont(u8g2_font_6x12_tr);
    u8g2.setCursor(0, 10);
    u8g2.print(F("XIAO RP2040"));
    u8g2.setFont(u8g2_font_logisoso42_tn);
    u8g2.drawStr(0, 60, data);
  } while (u8g2.nextPage());
}

/* 5x7 pixel glyphs (LSB = left). Order: i n s g h t x */
static const uint8_t kPixGlyph[][7] PROGMEM = {
  {0x04, 0x00, 0x0E, 0x04, 0x04, 0x04, 0x0E}, /* i */
  {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11}, /* n */
  {0x0E, 0x11, 0x10, 0x0E, 0x01, 0x11, 0x0E}, /* s */
  {0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0E}, /* g */
  {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11}, /* h */
  {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x06}, /* t */
  {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11}, /* x */
};

static int pixGlyphIndex(char c) {
  switch (c) {
    case 'i': return 0;
    case 'n': return 1;
    case 's': return 2;
    case 'g': return 3;
    case 'h': return 4;
    case 't': return 5;
    case 'x': return 6;
    default: return -1;
  }
}

static const int PIX_SCALE = 2;
static const int PIX_GAP = 2;
static const int PIX_COLS = 5;
static const int PIX_ROWS = 7;

static void drawPixCell(int x, int y) {
  u8g2.drawBox(x, y, PIX_SCALE, PIX_SCALE);
}

static void drawInsightxWord(int originX, int originY, int maxOn, int* totalOut) {
  const char* word = "insightx";
  int on = 0;
  int x = originX;
  for (uint8_t i = 0; i < 8; i++) {
    int gi = pixGlyphIndex(word[i]);
    if (gi >= 0) {
      for (uint8_t row = 0; row < PIX_ROWS; row++) {
        uint8_t bits = pgm_read_byte(&kPixGlyph[gi][row]);
        for (uint8_t col = 0; col < PIX_COLS; col++) {
          if (bits & (1 << (PIX_COLS - 1 - col))) {
            if (maxOn < 0 || on < maxOn) {
              drawPixCell(x + col * PIX_SCALE, originY + row * PIX_SCALE);
            }
            on++;
          }
        }
      }
    }
    x += PIX_COLS * PIX_SCALE + PIX_GAP;
  }
  if (totalOut) *totalOut = on;
}

static int insightxOriginX() {
  int w = 8 * PIX_COLS * PIX_SCALE + 7 * PIX_GAP;
  return (128 - w) / 2;
}

static void drawPixMark(int x, int y) {
  static const uint8_t mark[8] PROGMEM = {
    0b00111100,
    0b01000010,
    0b10100101,
    0b10000001,
    0b10100101,
    0b10011001,
    0b01000010,
    0b00111100
  };
  for (uint8_t r = 0; r < 8; r++) {
    uint8_t row = pgm_read_byte(&mark[r]);
    for (uint8_t c = 0; c < 8; c++) {
      if (row & (0x80 >> c)) {
        u8g2.drawBox(x + c * 2, y + r * 2, 2, 2);
      }
    }
  }
}

void playInsightxAnimation() {
  const int ox = insightxOriginX();
  const int oy = 26;
  int total = 0;
  u8g2.setDrawColor(1);
  drawInsightxWord(ox, oy, -1, &total);

  for (int n = 1; n <= total; n++) {
    u8g2.firstPage();
    do {
      drawPixMark(4, 4);
      u8g2.setFont(u8g2_font_4x6_tr);
      u8g2.setCursor(24, 12);
      u8g2.print(F("BOOT"));
      drawInsightxWord(ox, oy, n, nullptr);
      u8g2.drawBox(ox + 8 * (PIX_COLS * PIX_SCALE + PIX_GAP) - PIX_GAP, oy, 2, PIX_ROWS * PIX_SCALE);
    } while (u8g2.nextPage());
    drivePixels(8, 20, 40 + (n * 6) % 180);
    delay(18);
  }

  int wordW = 8 * PIX_COLS * PIX_SCALE + 7 * PIX_GAP;
  for (int sx = 0; sx <= wordW; sx += 3) {
    u8g2.firstPage();
    do {
      drawPixMark(4, 4);
      drawInsightxWord(ox, oy, -1, nullptr);
      u8g2.setDrawColor(2);
      u8g2.drawBox(ox + sx, oy - 2, 6, PIX_ROWS * PIX_SCALE + 4);
      u8g2.setDrawColor(1);
    } while (u8g2.nextPage());
    delay(20);
  }

  for (int i = 0; i < 3; i++) {
    u8g2.firstPage();
    do {
      drawPixMark(4, 4);
      drawInsightxWord(ox, oy, -1, nullptr);
      u8g2.drawBox(ox, oy + PIX_ROWS * PIX_SCALE + 3, wordW, 2);
    } while (u8g2.nextPage());
    drivePixels(20, 60, 200);
    delay(160);
    u8g2.firstPage();
    do {
      drawPixMark(4, 4);
    } while (u8g2.nextPage());
    drivePixels(5, 20, 80);
    delay(90);
  }

  u8g2.firstPage();
  do {
    drawPixMark(4, 4);
    drawInsightxWord(ox, oy, -1, nullptr);
  } while (u8g2.nextPage());
  delay(400);
}

void playBootAnimation() {
  for (int i = 0; i < 2; i++) {
    u8g2.firstPage();
    do {
      u8g2.drawBox(0, 0, 128, 64);
    } while (u8g2.nextPage());
    drivePixels(0, 40, 80);
    delay(80);
    u8g2.firstPage();
    do {
    } while (u8g2.nextPage());
    drivePixels(0, 0, 0);
    delay(80);
  }
  for (int y = 0; y < 64; y += 2) {
    u8g2.firstPage();
    do {
      u8g2.drawHLine(0, y, 128);
      u8g2.drawHLine(0, y + 1, 128);
      u8g2.setFont(u8g2_font_6x12_tr);
      u8g2.setCursor(8, 12);
      u8g2.print(F("SYSTEM BOOT"));
    } while (u8g2.nextPage());
    drivePixels(0, 20, min(y * 3, 200));
    delay(18);
  }
  for (uint8_t s = 0; s < 4; s++) {
    for (int p = 0; p <= 100; p += 5) {
      u8g2.firstPage();
      do {
        u8g2.setFont(u8g2_font_6x12_tr);
        u8g2.setCursor(8, 14);
        u8g2.print(F("XIAO RP2040"));
        u8g2.setCursor(8, 30);
        if (s == 0) u8g2.print(F("INIT CORE..."));
        else if (s == 1) u8g2.print(F("LOAD VISION..."));
        else if (s == 2) u8g2.print(F("CALIB MOTORS..."));
        else u8g2.print(F("LINK READY..."));
        u8g2.drawFrame(8, 44, 112, 10);
        u8g2.drawBox(10, 46, (108 * p) / 100, 6);
        char pct[8];
        snprintf(pct, sizeof(pct), "%d%%", p);
        u8g2.drawStr(96, 40, pct);
      } while (u8g2.nextPage());
      drivePixels(p / 2, 25, 180 - p);
      delay(12);
    }
  }
  for (int h = 4; h <= 14; h += 2) {
    u8g2.firstPage();
    do {
      u8g2.setDrawColor(1);
      drawCapsule(LX0, EY0, h, 6, 84);
      drawCapsule(RX0, EY0, h - 2, 5, 8);
    } while (u8g2.nextPage());
    delay(40);
  }
  u8g2.setDrawColor(1);
  playInsightxAnimation();
  drivePixels(15, 25, 205);
  setEmotion("11");
  delay(400);
}

void driveLed(uint8_t r, uint8_t g, uint8_t b, uint16_t holdMs) {
  drivePixels(r, g, b);
  delay(holdMs);
}

void setup() {
  pixels.begin();
  pixels.setBrightness(PIXEL_BRIGHTNESS);
  pinMode(Power, OUTPUT);
  digitalWrite(Power, HIGH);
  u8g2.begin();
  randomSeed(analogRead(A0));
  playBootAnimation();
}

void loop() {
  static uint8_t demoIndex = 0;
  static uint32_t nextSwitch = 0;
  uint32_t now = millis();

  if (now >= nextSwitch) {
    char id[3];
    strcpy_P(id, kEmoId[demoIndex]);
    setEmotion(id);
    demoIndex++;
    if (demoIndex >= EMOTION_COUNT) demoIndex = 0;
    nextSwitch = now + 2800;
    drivePixels(15, 25, 205);
  }

  tickEmotion(now);
  delay(33);
}
