# Complete Data Capture Pipeline — 16-Position CSI Experiment
## ASUS RT-AC86U | Nexmon CSI | 40MHz | C15 | Single AP (AP0)

---

## LESSONS LEARNED (from previous session — read before starting)

| Problem encountered | Root cause | Fix applied in this pipeline |
|---|---|---|
| 0 packets captured | `wl eth6 monitor 1` missing | Added as mandatory step |
| Wrong channel 149/20MHz | `service restart_wireless` resets channel | Fix via web UI before applying CSI params |
| nexutil returning all zeros | CSI params applied before eth6 fully up | Added sleep delays |
| `/tmp/` permission denied | sudo tcpdump can't write to /tmp | Always write to `~/captures/` |
| makecsiparams not found | Tools in `/jffs/`, not in PATH | Always use full path `/jffs/` |

---

## HARDWARE CHECKLIST (verify before starting)

- [ ] Patched router (192.168.1.1) powered on and ethernet cable connected to laptop
- [ ] Unpatched router (192.168.2.1) powered on and broadcasting SSID on ch44/40MHz
- [ ] ESP32-C5 powered on and USB connected to laptop
- [ ] Laptop ethernet interface `eno1` showing IP in 192.168.1.x range
- [ ] Mobile hotspot active for internet (Claude communication)

---

## PHASE 1 — VERIFY NETWORK CONNECTIVITY

Open Terminal 1 on capture machine.

### Step 1.1 — Verify eno1 has correct IP
```bash
ip a show eno1
```
**Expected output:** `inet 192.168.1.xx/24` — any IP in 192.168.1.x range is correct.
If eno1 has no IP → ethernet cable is not connected properly to patched router.

### Step 1.2 — Verify patched router is reachable
```bash
ping -c 3 192.168.1.1
```
**Expected:** 0% packet loss. If fails → ethernet cable issue.

### Step 1.3 — Verify virtual environment
```bash
cd ~/localization
source .venv/bin/activate
```
Prompt should show `(.venv)` prefix.

### Step 1.4 — Create capture directory
```bash
mkdir -p ~/captures/16pos_experiment
ls ~/captures/16pos_experiment/
```
Directory should exist and be empty (or contain only old files you moved away).

---

## PHASE 2 — VERIFY ESP32-C5 IS TRANSMITTING

### Step 2.1 — Check ESP32 serial output
Open Terminal 2:
```bash
sudo cat /dev/ttyACM0
```
**Expected output:**
```
Sent 100 probe requests (last err: ESP_OK)
Sent 200 probe requests (last err: ESP_OK)
...
```
Counter must be increasing with `ESP_OK`. If device not found:
```bash
ls /dev/ttyACM*
ls /dev/ttyUSB*
```
Use whichever device appears. If nothing appears → ESP32 not connected via USB.

**IMPORTANT:** Keep this terminal open to monitor ESP32 throughout capture.
**DO NOT press reset button on ESP32** — it will erase the firmware.

---

## PHASE 3 — SET PATCHED ROUTER CHANNEL VIA WEB UI

**This step is MANDATORY after every router reboot.**
`service restart_wireless` resets channel to 149/20MHz.
The `wl chanspec` command does not work reliably on this router.
Web UI is the only reliable way to set the channel.

### Step 3.1 — Open patched router web UI
In browser: `http://192.168.1.1`
Login: admin / (your password)

### Step 3.2 — Set 5GHz channel
Navigate to:
**Wireless → Professional → 5GHz band**
- Control Channel: **44**
- Channel Bandwidth: **40 MHz**

Click **Apply** and wait for router to apply settings (~10 seconds).

### Step 3.3 — Verify channel from terminal
```bash
ssh admin@192.168.1.1 "wl -i eth6 chanspec"
```
**Expected output:** `44l (0xd82e)`
If it shows `149` or anything else → repeat Step 3.2.

---

## PHASE 4 — ACTIVATE CSI EXTRACTION ON PATCHED ROUTER

**Run this command ONCE before starting all 16 captures.**
Do NOT repeat between positions unless router reboots.

### Step 4.1 — Apply CSI parameters and enable monitor mode
```bash
ssh admin@192.168.1.1 "cd /jffs && wl -i eth6 up && ifconfig eth6 up && PARAMS=\$(./makecsiparams -c 44/40 -C 15 -N 1) && ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && wl -i eth6 monitor 1 && echo DONE"
```
**Expected output:** `DONE` (no errors)

What each part does:
- `wl -i eth6 up` → brings wireless interface up
- `ifconfig eth6 up` → brings ethernet side up
- `makecsiparams -c 44/40 -C 15 -N 1` → generates CSI parameter string for ch44/40MHz, all 4 cores (C15=binary 1111), 1 spatial stream
- `nexutil -Ieth6 -s500 -b -l34 -v $PARAMS` → applies CSI parameters to driver
- `wl -i eth6 monitor 1` → puts eth6 into monitor mode (CRITICAL — without this no CSI packets flow)

### Step 4.2 — Verify channel is still correct after CSI activation
```bash
ssh admin@192.168.1.1 "wl -i eth6 chanspec"
```
**Expected:** `44l (0xd82e)` — if it changed, repeat Phase 3 then Phase 4.

### Step 4.3 — Verify CSI packets are flowing (test capture)
In Terminal 1:
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -c 20
```
**Expected:** 20 packets captured almost instantly (within 1-2 seconds).

If 0 packets after 10 seconds:
1. Check ESP32 is transmitting (Terminal 2)
2. Rerun Step 4.1
3. Verify channel (Step 4.2)

### Step 4.4 — Parse test capture to verify 4 cores
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -c 80 -w ~/captures/test_verify.pcap
python ~/parser_check/nexmon_csi.py ~/captures/test_verify.pcap --stats --mac d0:cf:13:e2:88:94
```
**Expected in parser output:**
- `chanspec: 0xd82e` ✓
- `bandwidth: 40 MHz` ✓
- `subcarriers: 64` ✓
- `d0:cf:13:e2:88:94  XX frames (100%)` ✓
- `Mean amplitude: ~400-500` ✓
- Frame count = multiple of 4 (one per core per probe request) ✓

Only proceed to Phase 5 when all checks pass.

---

## PHASE 5 — DATA CAPTURE (16 POSITIONS)

**IMPORTANT RULES:**
- Capture exactly **3 minutes per position** — use a timer on your phone
- Press **Ctrl+C** to stop capture, then immediately move to next position
- Do NOT restart the router between positions
- Do NOT re-run the CSI activation command between positions (unless router reboots)
- Keep ESP32-C5 powered and transmitting throughout all 16 positions
- Filenames must match EXACTLY: `pos1_4ant.pcap` through `pos16_4ant.pcap`

### Position coordinate reference

| File | X (m) | Y (m) | Notes |
|------|--------|--------|-------|
| pos1_4ant.pcap  | 0.00 | 0.00 | Corner |
| pos2_4ant.pcap  | 0.00 | 1.43 | |
| pos3_4ant.pcap  | 0.00 | 2.86 | |
| pos4_4ant.pcap  | 0.00 | 4.29 | Corner |
| pos5_4ant.pcap  | 1.43 | 0.00 | |
| pos6_4ant.pcap  | 1.43 | 1.43 | Inner |
| pos7_4ant.pcap  | 1.43 | 2.86 | Inner |
| pos8_4ant.pcap  | 1.43 | 4.29 | |
| pos9_4ant.pcap  | 2.86 | 0.00 | |
| pos10_4ant.pcap | 2.86 | 1.43 | Inner |
| pos11_4ant.pcap | 2.86 | 2.86 | Inner |
| pos12_4ant.pcap | 2.86 | 4.29 | |
| pos13_4ant.pcap | 4.29 | 0.00 | Corner |
| pos14_4ant.pcap | 4.29 | 1.43 | |
| pos15_4ant.pcap | 4.29 | 2.86 | |
| pos16_4ant.pcap | 4.29 | 4.29 | Corner |

### Capture commands — run one at a time

**Position 1 (x=0.00, y=0.00):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos1_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 2.

**Position 2 (x=0.00, y=1.43):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos2_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 3.

**Position 3 (x=0.00, y=2.86):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos3_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 4.

**Position 4 (x=0.00, y=4.29):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos4_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 5.

**Position 5 (x=1.43, y=0.00):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos5_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 6.

**Position 6 (x=1.43, y=1.43):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos6_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 7.

**Position 7 (x=1.43, y=2.86):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos7_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 8.

**Position 8 (x=1.43, y=4.29):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos8_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 9.

**Position 9 (x=2.86, y=0.00):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos9_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 10.

**Position 10 (x=2.86, y=1.43):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos10_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 11.

**Position 11 (x=2.86, y=2.86):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos11_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 12.

**Position 12 (x=2.86, y=4.29):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos12_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 13.

**Position 13 (x=4.29, y=0.00):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos13_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 14.

**Position 14 (x=4.29, y=1.43):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos14_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 15.

**Position 15 (x=4.29, y=2.86):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos15_4ant.pcap
```
Wait 3 minutes → Ctrl+C → move to position 16.

**Position 16 (x=4.29, y=4.29):**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/pos16_4ant.pcap
```
Wait 3 minutes → Ctrl+C → DONE.

---

## PHASE 6 — IF ROUTER REBOOTS MID-EXPERIMENT

If the patched router reboots at any point during capture:

### Step 6.1 — Fix channel via web UI first
Open `http://192.168.1.1` → Wireless → Professional → 5GHz
Set channel=44, bandwidth=40MHz → Apply

### Step 6.2 — Verify channel
```bash
ssh admin@192.168.1.1 "wl -i eth6 chanspec"
```
Must show `44l (0xd82e)`

### Step 6.3 — Reactivate CSI
```bash
ssh admin@192.168.1.1 "cd /jffs && wl -i eth6 up && ifconfig eth6 up && PARAMS=\$(./makecsiparams -c 44/40 -C 15 -N 1) && ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && wl -i eth6 monitor 1 && echo DONE"
```

### Step 6.4 — Verify packets flowing
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -c 20
```
Must capture 20 packets quickly. Then resume from the position you were on.

**NOTE:** If router rebooted mid-capture for a position, delete that partial pcap file and recapture that position from scratch for the full 3 minutes.

---

## PHASE 7 — POST-CAPTURE VERIFICATION

### Step 7.1 — Check all 16 files exist and sizes
```bash
ls -lh ~/captures/16pos_experiment/
```
Should see 16 files, each several MB in size.

### Step 7.2 — Packet count per position
```bash
for i in $(seq 1 16); do
    echo -n "pos${i}: "
    tcpdump -r ~/captures/16pos_experiment/pos${i}_4ant.pcap 2>/dev/null | wc -l
done
```
**Expected:** All positions roughly 35,000–60,000 packets. Any position below 20,000 should be recaptured.

### Step 7.3 — Parse and verify 3 representative positions
```bash
python ~/parser_check/nexmon_csi.py ~/captures/16pos_experiment/pos1_4ant.pcap --mac d0:cf:13:e2:88:94 --list-macs
python ~/parser_check/nexmon_csi.py ~/captures/16pos_experiment/pos8_4ant.pcap --mac d0:cf:13:e2:88:94 --list-macs
python ~/parser_check/nexmon_csi.py ~/captures/16pos_experiment/pos16_4ant.pcap --mac d0:cf:13:e2:88:94 --list-macs
```

**Expected for each:**
- 100% frames from `d0:cf:13:e2:88:94`
- ~77 fps
- 64 subcarriers
- chanspec `0xd82e`
- Frame count divisible by 4 (4 cores per probe request)

---

## PHASE 8 — RUN ANALYSIS

Once all 16 positions verified, copy scripts to localization directory and run:

```bash
cd ~/localization
source .venv/bin/activate

# Delete old CSV cache if it exists from previous experiment
rm -f ~/data/regression_16pos_4ant.csv
rm -f ~/data/regression_16pos_1ant.csv
rm -f ~/data/csi_16pos_4ant_40mhz.csv

# Run classification
python3 csi_classification_16pos.py

# Run regression
python3 csi_regression_16pos.py
```

Results saved to `~/localization/`:
- `classification_16pos_confusion_matrix.png/.eps`
- `classification_16pos_accuracy_grid.png/.eps`
- `classification_16pos_loss_curves.png/.eps`
- `classification_16pos_amplitude_profiles.png`
- `regression_16pos_true_vs_predicted.png/.eps`
- `regression_16pos_arena_heatmap.png/.eps`
- `regression_16pos_loss_curves.png`

---

## QUICK REFERENCE — SINGLE COMMANDS

**Start of experiment (run once):**
```bash
# 1. Fix channel via web UI http://192.168.1.1 → ch44/40MHz → Apply
# 2. Verify channel
ssh admin@192.168.1.1 "wl -i eth6 chanspec"
# Must show: 44l (0xd82e)

# 3. Activate CSI
ssh admin@192.168.1.1 "cd /jffs && wl -i eth6 up && ifconfig eth6 up && PARAMS=\$(./makecsiparams -c 44/40 -C 15 -N 1) && ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && wl -i eth6 monitor 1 && echo DONE"

# 4. Verify packets flowing
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -c 20
```

**Each position capture:**
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/16pos_experiment/posN_4ant.pcap
# Wait 3 minutes → Ctrl+C → change N → repeat
```

**Post-capture check:**
```bash
for i in $(seq 1 16); do echo -n "pos${i}: "; tcpdump -r ~/captures/16pos_experiment/pos${i}_4ant.pcap 2>/dev/null | wc -l; done
```
