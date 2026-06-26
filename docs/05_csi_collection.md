# Step 5 — CSI Collection Procedure

## Hardware Required

| Item | Details |
|------|---------|
| Patched router | ASUS RT-AC86U, Nexmon CSI firmware, IP: 192.168.1.1 |
| Unpatched router | ASUS RT-AC86U, AP mode, ch44/40MHz, IP: 192.168.2.1 |
| Transmitter | ESP32-C5 (MAC: D0:CF:13:E2:88:94), probe request firmware |
| Capture machine | Ubuntu, ethernet connected to patched router via eno1 |

---

## CRITICAL NOTES (learned from experiments)

- **Never use `-N 15`** — use `-N 1` (1 spatial stream from ESP32-C5 transmitter)
- **Never use `44/80`** — use `44/40` (40MHz). At 80MHz only core 0 is active
- **`service restart_wireless` resets eth6 channel to 149/20MHz** — must fix via web UI afterward
- **`wl -i eth6 monitor 1` is mandatory** — without it, 0 CSI packets flow
- **`-m` flag must be omitted** — using `-m ff:ff:ff:ff:ff:ff` causes 0 captures
- **Write pcap files to `~/captures/`** — sudo tcpdump cannot write to `/tmp/`
- **Tools are in `/jffs/`** — always use full path `/jffs/makecsiparams` etc.
- **`wl chanspec` set command does not work on eth6** — channel is set by nexutil via makecsiparams

---

## Step 1 — Verify network connectivity

```bash
# Verify eno1 has IP in 192.168.1.x range
ip a show eno1
# Expected: inet 192.168.1.xx/24

# Verify patched router reachable
ping -c 3 192.168.1.1
```

---

## Step 2 — Verify ESP32-C5 is transmitting

```bash
sudo cat /dev/ttyACM0
```
Expected output (counter increasing with ESP_OK):
```
Sent 100 probe requests (last err: ESP_OK)
Sent 200 probe requests (last err: ESP_OK)
```
**DO NOT press the reset button on ESP32** — it will erase the firmware.

---

## Step 3 — Set channel via web UI (MANDATORY after every reboot)

Open browser: `http://192.168.1.1`
Navigate to: **Wireless → Professional → 5GHz**
- Control Channel: **44**
- Channel Bandwidth: **40 MHz**

Click **Apply** and wait ~10 seconds.

Verify from terminal:
```bash
ssh admin@192.168.1.1 "wl -i eth6 chanspec"
# Expected: 44l (0xd82e)
```

---

## Step 4 — Activate CSI extraction (run ONCE per session)

```bash
ssh admin@192.168.1.1 "service restart_wireless"
```
Wait 15 seconds, then:
```bash
ssh admin@192.168.1.1 "cd /jffs && wl -i eth6 up && ifconfig eth6 up && PARAMS=\$(./makecsiparams -c 44/40 -C 15 -N 1) && ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && wl -i eth6 monitor 1 && echo DONE"
```
Expected output: `DONE`

### makecsiparams flags

| Flag | Value | Meaning |
|------|-------|---------|
| `-c` | `44/40` | Channel 44, **40MHz** bandwidth |
| `-C` | `15` (0b1111) | Enable all 4 Rx cores (antennas) |
| `-N` | `1` | 1 spatial stream (matches ESP32-C5 single antenna) |

---

## Step 5 — Verify CSI packets flowing

```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -c 20
```
Expected: 20 packets captured within 1-2 seconds.

Verify 4 cores with parser:
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -c 80 -w ~/captures/test_verify.pcap
python parsing/nexmon_csi.py ~/captures/test_verify.pcap --stats --mac d0:cf:13:e2:88:94
```
Expected:
- `chanspec: 0xd82e` ✓
- `bandwidth: 40 MHz` ✓
- `subcarriers: 64` ✓
- `Mean amplitude: ~400-500` ✓
- Frame count divisible by 4 (4 cores per probe request) ✓

---

## Step 6 — Capture per position

```bash
mkdir -p ~/captures/16pos_experiment

# For each position (replace N with position number 1-16):
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/posN_4ant.pcap
# Wait 3 minutes → Ctrl+C → move to next position
```

See `docs/07_data_capture_pipeline.md` for the complete 16-position procedure with all checks.

---

## What to expect

- ~77-80 CSI frames/second at 40MHz
- 4 CSI packets per probe request (one per router antenna core)
- ~14,000 CSI frames per 3-minute capture
- Source MAC in pcap: `4e:45:58:4d:4f:4e` (NEXMON in ASCII)
- Transmitter MAC in CSI header: `d0:cf:13:e2:88:94` (ESP32-C5)

---

## Subcarrier mapping (40MHz, 64 subcarriers)

At 40MHz channel 44, each core produces 64 subcarriers:
- Subcarrier 0: DC component — low amplitude, typically excluded
- Subcarrier 63: DC artifact spike — exclude from ML features
- Subcarriers 1-62: valid data subcarriers — use for localization
- Total valid subcarriers used in ML: 61 (indices 2-62 after removing 0, 1, 63)
