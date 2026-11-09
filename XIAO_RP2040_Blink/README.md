# XIAO_RP2040_Blink

**Version:** `2.5.0`  
**Board:** Seeed Studio XIAO RP2040  
**Wiki:** https://wiki.seeedstudio.com/XIAO-RP2040/

## Features

- Drive onboard NeoPixel RGB LED (GPIO12)
- Drive SSD1306 128×64 OLED over I2C (U8g2)
- Sci-fi boot animation via `playBootAnimation()`
- Post-boot brand animation via `playInsightxAnimation()` (`insightx`)
- emotion-ball Plan B: **eyes only** (circle or rounded-rect), no head/mouth
- Full-screen eye roam (no status bar)
- Eyes scaled about +1/3; rounded-rect corner radius steps 2→8
- Expressions from eye shape + movement (`lookX/Y`, blink, scan, jitter)
- `setEmotion(id)` / `setEmotionTips()` / `handleEmotionMessage()`
- Number mode via `driveDisplay(displayValue)`
- Tunable NeoPixel brightness via `PIXEL_BRIGHTNESS` (0–255)

## Emotion API

Inspired by [emotion-ball](https://github.com/sam70361/emotion-ball). OLED shows two eyes only.

- Shape: filled **circle** or **rounded rect**
- Motion: glance / sine / scan / jitter / nod / alternate blink / pulse
- No ball body, no mouth, no eyebrows, no status bar

```cpp
setEmotion("30");                        // thinking face
handleEmotionMessage("33", "task done"); // ID + custom tips
```

Status: ID/tips kept in API only (not drawn).

### 32 emotion IDs

| ID | Tips | ID | Tips |
|----|------|----|------|
| 00 sleep | 01 wake | 02 idle | 03 curious |
| 04 daze | 05 boot | 06 dormant | 07 shake |
| 10 happy | 11 puzzled | 12 down | 13 surprise |
| 14 shy | 15 tired | 16 focus | 17 panic |
| 18 resigned | 19 satisfied | 20 confused | 21 angry |
| 30 think | 31 recv | 32 busy | 33 done |
| 34 error | 35 listen | 36 load | 37 recall |
| 38 refuse | 39 reply | 40 search | 41 stop |

Unknown ID falls back to `"02"`.

## Changelog

### v2.5.0 — 2026-08-19

- Rotated capsule eyes (vertical / horizontal / slant), matching emotion-ball screenshots
- Angry/error invert the screen; wink is one tall + one flat capsule

### v2.4.1 — 2026-08-19

- Cut SRAM: U8g2 page buffer + PROGMEM emotion/glyph tables

### v2.4.0 — 2026-08-19

- Remove top status bar; eyes roam the full 128×64
- Scale circle/rounded-rect eyes by 4/3
- Rounded-rect radius and height step through extra increments

### v2.3.1 — 2026-08-19

- Boot `insightx` identity as 5x7 pixel blocks (cell-by-cell reveal)

### v2.3.0 — 2026-08-19

- Eyes-only renderer: circle/rect pixels, no round head
- Animate gaze, blink, scan, jitter to mimic emotion-ball eye motion

### v2.2.0 — 2026-08-19

- Redraw Plan B as emotion-ball language: filled ball + punched eye rings
- Remove cartoon mouth/brows so 32 IDs are visually distinct from v1 faces

### v2.1.0 — 2026-07-17

- Plan B: 32 unique `drawEmotionById()` pixel faces for emotion-ball IDs
- Loop cycles all 32 emotions; no ribbons/confetti

### v2.0.0 — 2026-07-17

- Plan A: emotion-ball ID mapping to shared face enum

### v1.9.3 — 2026-07-17

- Move status bar to top first line (above face)

### v1.7.1 — 2026-07-17

- Remove face frame and ear bolts; keep eyes + mouth
- Scale eyes to ~2× previous size

### v1.8.0 — 2026-07-17 (reverted)

- Redesign `driveFace` after FluxGarage RoboEyes (eyes only, no head frame/mouth)
- Moods use rounded-rect eyes + background triangle/box lid overlays
- Reverted back to v1.7.0 by request

### v1.7.0 — 2026-07-17

- Add `driveFace()` robot expression API (开心/难过/生气/平静/惊讶/困倦)
- `loop` demos cycling through faces

### v1.6.0 — 2026-07-17

- `driveDisplay(int value)` shows a number only (no color binding)
- Add global `displayValue`; set it then call `driveDisplay(displayValue)`

### v1.5.2 — 2026-07-17

- OLED first line uses fixed text `XIAO RP2040`

### v1.5.1 — 2026-07-17

- Large data font switched to `u8g2_font_inb16_mn`

### v1.5.0 — 2026-07-17

- Implement `driveDisplay`: title shows `R G B`, big 7-segment line shows R (`000`–`255`)
- Use `u8g2_font_7Segments_26x42_mn` for digital readout

### v1.4.1 — 2026-07-17

- Remove OLED border
- Line 1 uses `u8g2_font_6x12_tr`; remaining text uses `u8g2_font_inb16_mr`

### v1.4.0 — 2026-07-17

- Draw SSD1306 full-screen frame `128×64`

### v1.3.1 — 2026-07-17

- Add `#define PIXEL_BRIGHTNESS` and `pixels.setBrightness()` for debug tuning

### v1.3.0 — 2026-07-17

- Add `driveLed(r, g, b, holdMs)` wrapping pixels + display + delay
- Simplify `loop` to sequential `driveLed(...)` calls

### v1.2.0 — 2026-07-17

- Extract NeoPixel control into `drivePixels(r, g, b)`
- Add reserved `driveDisplay(r, g, b)` interface for OLED sync (no-op for now)
- `loop` drives color table and calls both functions each step

### v1.1.0 — 2026-07-17

- Add SSD1306 OLED display via U8g2 (HW I2C)
- Show fixed text: `XIAO RP2040` / `Hello`
- Move pin map and usage notes from sketch header into this README
- Add version number and changelog

### v1.0.0 — initial

- NeoPixel power enable on pin 11
- Cycle 5 RGB colors on onboard NeoPixel (GPIO12)

## Dependencies

| Library | Purpose |
|---------|---------|
| Adafruit NeoPixel | Onboard RGB LED |
| U8g2 | SSD1306 OLED |

Recommended board package: Seeed XIAO RP2040 **≥ 2.7.2** (Wire on D4/D5).

## Wiring

### NeoPixel (onboard)

| Signal | Pin |
|--------|-----|
| Data   | GPIO12 |
| Power enable | pin 11 (HIGH) |

### SSD1306 OLED (I2C)

| OLED | XIAO RP2040 |
|------|-------------|
| VCC  | 3V3 |
| GND  | GND |
| SDA  | D4 (GPIO6) |
| SCL  | D5 (GPIO7) |

## Pin Map

| XIAO Pin   | Function | Chip Pin    | Description                        |
|------------|----------|-------------|------------------------------------|
| 5V         | VBUS     | —           | Power Input/Output                 |
| GND        | —        | —           | Ground                             |
| 3V3        | 3V3_OUT  | —           | Power Output                       |
| D0         | Analog   | GPIO26      | GPIO, ADC                          |
| D1         | Analog   | GPIO27      | GPIO, ADC                          |
| D2         | Analog   | GPIO28      | GPIO, ADC                          |
| D3         | Analog   | GPIO29      | GPIO, ADC                          |
| D4         | SDA      | GPIO6       | GPIO, I2C Data                     |
| D5         | SCL      | GPIO7       | GPIO, I2C Clock                    |
| D6         | TX       | GPIO0       | GPIO, UART Transmit                |
| D7         | RX, CSn  | GPIO1       | GPIO, UART Receive, CSn            |
| D8         | SCK      | GPIO2       | GPIO, SPI Clock                    |
| D9         | MISO     | GPIO4       | GPIO, SPI Data                     |
| D10        | MOSI     | GPIO3       | GPIO, SPI Data                     |
| Reset      | RUN      | RUN         | Reset                              |
| Boot       | BOOT     | RP2040_BOOT | Enter Boot Mode                    |
| CHARGE_LED | VCC_3V3  | —           | CHG-LED Red                        |
| RGB LED    | —        | GPIO12      | Onboard NeoPixel RGB LED           |
| USER_LED_R | —        | GPIO17      | User red LED (active LOW)          |
| USER_LED_G | —        | GPIO16      | User green LED (active LOW)        |
| USER_LED_B | —        | GPIO25      | User blue LED (active LOW)         |

## Notes

- I/O working voltage is 3.3V; >3.3V on GPIO may damage the chip.
- Onboard single-color LEDs are active LOW (pull pin LOW to turn on).
