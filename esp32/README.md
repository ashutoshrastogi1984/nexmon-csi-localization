# ESP32-C5 Probe Request Injector — Setup Guide

## What This Does

The ESP32-C5 sends continuous 802.11 probe request frames on channel 44 (5220 MHz)
every 50ms. The patched router (in monitor mode) captures these frames and generates
CSI for each one — giving ~20 CSI frames/second × 4 antenna cores = ~80 packets/second.

The probe frame uses a **fixed source MAC** (`D0:CF:13:E2:88:94`) embedded in the
802.11 SA field. Nexmon reads this SA and puts it in the CSI header — this is the
MAC you use for `--mac` in the parser and for tcpdump filtering.

---

## Hardware Required

- ESP32-C5 development board (any variant with USB)
- USB cable (data capable, not charge-only)
- Ubuntu/Windows PC with Arduino IDE

---

## Arduino IDE Setup

### Step 1 — Install Arduino IDE
Download from: https://www.arduino.cc/en/software (version 2.x recommended)

### Step 2 — Add ESP32 board support
In Arduino IDE:
- File → Preferences → Additional boards manager URLs, add:
```
https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
```
- Tools → Board → Boards Manager → search "esp32" → install **esp32 by Espressif Systems** (version **3.x or later**)

**Important:** ESP32-C5 requires esp32 core version 3.x or later. Earlier versions do not support ESP32-C5.

### Step 3 — Select board and settings
- Tools → Board → ESP32 Arduino → **ESP32C5 Dev Module**
- Tools → Port → select the COM port for your ESP32-C5
- Tools → Partition Scheme → **Default**
- All other settings: leave as default

### Step 4 — Open and configure the sketch
Open `esp32c5_probe_inject.ino` in Arduino IDE.

The only settings you may need to change are at the top of the file:

```cpp
#define WIFI_CHANNEL     44          // Must match your router channel
#define PROBE_SSID       "Asus86u_5G" // Must match your AP SSID
#define PROBE_INTERVAL   50           // ms between probes (50ms = ~20/sec)

static const uint8_t SRC_MAC[6] = { 0xD0, 0xCF, 0x13, 0xE2, 0x88, 0x94 };
// This is the MAC that appears in CSI frames — use this for --mac in parser
// Change only if you want a different identifier
```

### Step 5 — Flash
- Click **Upload** (→ button) in Arduino IDE
- Wait for "Done uploading"

### Step 6 — Verify
- Tools → Serial Monitor → set baud rate to **115200**
- Expected output:
```
=== ESP32-C5 Probe Request Injector ===
HW MAC:     xx:xx:xx:xx:xx:xx
Frame SA:   d0:cf:13:e2:88:94  ← use this for --mac
Channel:    44 (5220 MHz)
Interval:   50 ms

Probe frame built (47 bytes). Starting injection...
Sent 100 probe requests (last err: ESP_OK)
Sent 200 probe requests (last err: ESP_OK)
```

Counter must increase with `ESP_OK`. Any other error string indicates a problem.

---

## Verifying on Capture Machine

Once ESP32-C5 is running and router CSI is activated, verify on Ubuntu:

```bash
sudo cat /dev/ttyACM0
# Should show: Sent XXXX probe requests (last err: ESP_OK)
```

**DO NOT press the physical reset button on ESP32-C5** — it will restart the firmware
but the flash content is preserved. Only a full re-flash erases it.

---

## Key Notes

- The `SRC_MAC` in the code (`D0:CF:13:E2:88:94`) is what Nexmon records as the
  transmitter MAC in the CSI header — use this for `--mac d0:cf:13:e2:88:94` in the parser
- The tcpdump filter uses a different MAC: `4e:45:58:4d:4f:4e` — this is the Nexmon
  magic source MAC that identifies CSI UDP packets on the ethernet side
- `WIFI_SECOND_CHAN_ABOVE` locks the radio to 40MHz upper sideband alignment with ch44
- `WIFI_PS_NONE` disables power saving to keep USB powerbanks from cutting power

---

## Troubleshooting

### ESP32-C5 not detected (no COM port)
- Try a different USB cable — many cables are charge-only
- Install CP210x or CH340 USB-UART driver for your OS

### `last err: ESP_ERR_WIFI_IF` or similar
- Router AP on channel 44 must be on and broadcasting before ESP32 starts
- Try power cycling ESP32-C5 after router is fully up

### Counter stops increasing
- Check Serial Monitor for error messages
- Power cycle ESP32-C5

### 0 packets on capture machine despite ESP32 running
- Verify router CSI activation command was run (`wl -i eth6 monitor 1`)
- Verify channel: `ssh admin@192.168.1.1 "wl -i eth6 chanspec"` → must show `44l (0xd82e)`
- See `docs/06_troubleshooting.md` for full capture troubleshooting
