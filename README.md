# Nexmon CSI Localization — RT-AC86U

WiFi CSI-based indoor localization using **MIMO fingerprinting** and machine learning on the **ASUS RT-AC86U** (bcm4366c0 chipset).

This repo supports a complete end-to-end pipeline:
- Router patching (from scratch OR pre-compiled binaries)
- ESP32-C5 probe request transmitter
- 16-position 4×4 grid CSI data capture
- Parser with 4-core MIMO separation
- Classification and regression ML pipelines (1-antenna vs 4-antenna comparison)

---

## Hardware Used

| Item | Details |
|------|---------|
| Patched router | ASUS RT-AC86U (bcm4366c0), Merlin 386.14_2, Nexmon CSI firmware |
| Unpatched router | ASUS RT-AC86U, AP mode, ch44/40MHz |
| Transmitter | ESP32-C5 (MAC: D0:CF:13:E2:88:94), probe requests via `esp_wifi_80211_tx()` |
| Capture machine | Ubuntu 22.04 (x86_64), ethernet connected to patched router |

---

## Repository Structure

```
nexmon-csi-localization/
├── README.md                         ← You are here
├── docs/
│   ├── 01_ubuntu_setup.md            ← Build environment setup (Ubuntu 22.04)
│   ├── 02_router_setup.md            ← Merlin firmware flash + SSH setup
│   ├── 03_nexmon_build.md            ← Nexmon base framework build
│   ├── 04_nexmon_csi_build.md        ← nexmon_csi patch build and flash
│   ├── 05_csi_collection.md          ← CSI capture procedure (verified working)
│   ├── 06_troubleshooting.md         ← All known issues and fixes
│   └── 07_data_capture_pipeline.md   ← Complete foolproof 16-position pipeline
├── firmware/                         ← Pre-compiled binaries (Path B)
│   ├── dhd.ko                        ← Nexmon patched kernel module
│   ├── nexutil                       ← CSI configuration utility
│   └── makecsiparams                 ← CSI parameter generator
├── scripts/
│   ├── setup_env.sh                  ← Build environment setup script
│   ├── flash_csi_firmware.sh         ← Build and flash patched firmware
│   ├── collect_csi.sh                ← Router CSI activation + capture
│   └── router_init.sh                ← Router /jffs startup script
├── parsing/
│   ├── nexmon_csi.py                 ← Main parser (bcm4366c0, v3, core separation)
│   ├── parse_csi.py                  ← Original parser reference
│   ├── unpack_float.py               ← Official Broadcom float unpacking
│   └── requirements.txt              ← Python dependencies
├── ml/
│   ├── README.md                     ← ML pipeline overview
│   ├── CSI_MIMO_Classification_Final_1.ipynb  ← 16-pos classification (1-ant vs 4-ant)
│   └── CSI_MIMO_Regression_Final_1.ipynb      ← 16-pos regression (1-ant vs 4-ant)
└── data/
    └── sample/                       ← Sample .pcap files (gitignored)
```

---

## Two Paths to Get Started

### Path A — Pre-compiled Binaries (Recommended for identical hardware)

If you have the **exact same hardware** (ASUS RT-AC86U, bcm4366c0, Merlin 386.14_2), use the pre-compiled binaries in `firmware/`. No build environment needed.

**Step 1 — Flash Merlin 386.14_2 firmware**

Download Merlin firmware from: https://sourceforge.net/projects/asuswrt-merlin/files/RT-AC86U/

Flash via router web UI: `http://192.168.1.1` → Administration → Firmware Upgrade

**Step 2 — Enable SSH and JFFS on router**

In router web UI:
- Administration → System → Enable SSH → Apply
- Administration → System → Enable JFFS custom scripts → Apply

**Step 3 — Copy pre-compiled binaries to router**

```bash
scp firmware/dhd.ko admin@192.168.1.1:/jffs/
scp firmware/nexutil admin@192.168.1.1:/jffs/
scp firmware/makecsiparams admin@192.168.1.1:/jffs/
```

**Step 4 — Create persistent startup script on router**

```bash
ssh admin@192.168.1.1
cat > /jffs/scripts/init-start << 'SCRIPT'
#!/bin/sh
sleep 30
/sbin/rmmod dhd
/sbin/insmod /jffs/dhd.ko
SCRIPT
chmod +x /jffs/scripts/init-start
reboot
```

**Step 5 — Verify Nexmon is active after reboot**

Wait 45 seconds after reboot, then:
```bash
ssh admin@192.168.1.1 "dmesg | grep -i nexmon"
# Expected: nexmon.org/csi: a975...
```

**Proceed to CSI Collection section below.**

---

### Path B — Build From Scratch

Use this path if pre-compiled binaries don't work (firmware version mismatch or different hardware revision).

See full step-by-step instructions in:
- `docs/01_ubuntu_setup.md` — Ubuntu build environment
- `docs/02_router_setup.md` — Router setup
- `docs/03_nexmon_build.md` — Nexmon base build
- `docs/04_nexmon_csi_build.md` — nexmon_csi patch build and flash

**Quick summary of build steps:**

```bash
# 1. Install dependencies
sudo apt-get update
sudo apt-get install git libssl-dev gawk qpdf python3 bc make gcc \
     libgmp-dev autoconf automake libtool texinfo bison flex \
     g++ g++-multilib libmpc-dev python-is-python3 python2
sudo dpkg --add-architecture i386
sudo apt install libc6:i386 libncurses5:i386 libstdc++6:i386 \
     libmpc3:i386 libmpfr-dev:i386

# 2. Clone nexmon and fix symlinks (Ubuntu 22.04)
git clone https://github.com/seemoo-lab/nexmon.git
cd nexmon
sudo mkdir -p /usr/lib/arm-linux-gnueabihf
cd buildtools/isl-0.10 && make clean && ./configure && make && sudo make install
sudo ln -s /usr/local/lib/libisl.so /usr/lib/arm-linux-gnueabihf/libisl.so.10
cd ../mpfr-3.1.4 && autoreconf -f -i && ./configure && make && sudo make install
sudo ln -s /usr/local/lib/libmpfr.so /usr/lib/arm-linux-gnueabihf/libmpfr.so.4
sudo ln -s /usr/lib/i386-linux-gnu/libmpfr.so.6 /usr/lib/i386-linux-gnu/libmpfr.so.4
cd ../..

# 3. Build nexmon base
source setup_env.sh && make

# 4. Clone nexmon_csi at tested commit
cd patches/bcm4366c0/10_10_122_20/
git clone https://github.com/seemoo-lab/nexmon_csi.git
cd nexmon_csi
git checkout 13f87d2    # tested working commit (pre-PR#256)

# 5. Get toolchain
cd ~/
git clone https://github.com/RMerl/am-toolchains.git
export AMCC=$(pwd)/am-toolchains/brcm-arm-hnd/crosstools-aarch64-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25/usr/bin/aarch64-buildroot-linux-gnu-

# 6. Fix b43-v2 assembler
cd ~/nexmon/buildtools/b43-v2/assembler && make clean && make
sudo apt-get install python2 -y
sudo sed -i 's|#!/usr/bin/env python$|#!/usr/bin/env python2|' \
    ~/nexmon/buildtools/b43-v2/debug/b43-beautifier

# 7. Build and flash
cd ~/nexmon/patches/bcm4366c0/10_10_122_20/nexmon_csi
source ../../../../setup_env.sh
export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:$LD_LIBRARY_PATH
make install-firmware REMOTEADDR=192.168.1.1

# 8. Build and copy tools
cd utils/makecsiparams
${AMCC}gcc -o makecsiparams makecsiparams.c bcmwifi_channels.c -I./
scp makecsiparams admin@192.168.1.1:/jffs/

cd ~/nexmon/utilities/nexutil/
${AMCC}gcc -o nexutil nexutil.c bcmutils.c bcmwifi_channels.c \
    b64-encode.c b64-decode.c ../libnexio/libnexio.c \
    -I include -I ../libargp -I ../../patches/include -DVERSION=\"1.0\"
scp nexutil admin@192.168.1.1:/jffs/
```

See `docs/06_troubleshooting.md` for all known build errors and fixes.

---

## CSI Collection

Once router is patched (via either path), follow this procedure every session.

### CRITICAL parameters (verified working)

```bash
# CORRECT — use these exact parameters
makecsiparams -c 44/40 -C 15 -N 1

# WRONG — do not use these
makecsiparams -c 44/80 -C 15 -N 15   # 80MHz gives only 1 core, N=15 is wrong
```

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `-c` | `44/40` | Channel 44, **40MHz** bandwidth |
| `-C` | `15` (0b1111) | All 4 antenna cores enabled |
| `-N` | `1` | 1 spatial stream (matches ESP32-C5 single antenna) |

### Activation command (run once per session)

```bash
# Step 1 — Set channel via web UI: http://192.168.1.1
# Wireless → Professional → 5GHz → Channel=44, Bandwidth=40MHz → Apply

# Step 2 — Restart wireless
ssh admin@192.168.1.1 "service restart_wireless"
# Wait 15 seconds

# Step 3 — Apply CSI params and enable monitor mode
ssh admin@192.168.1.1 "cd /jffs && wl -i eth6 up && ifconfig eth6 up && PARAMS=\$(./makecsiparams -c 44/40 -C 15 -N 1) && ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && wl -i eth6 monitor 1 && echo DONE"

# Step 4 — Verify channel
ssh admin@192.168.1.1 "wl -i eth6 chanspec"
# Expected: 44l (0xd82e)

# Step 5 — Verify packets flowing
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -c 20
# Expected: 20 packets captured within 1-2 seconds
```

### Capture per position

```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e \
    -w ~/captures/16pos_experiment/posN_4ant.pcap
# Wait 3 minutes → Ctrl+C → move to next position
```

See `docs/07_data_capture_pipeline.md` for the complete verified 16-position procedure.

---

## Parser

```bash
cd parsing
pip install -r requirements.txt

# Basic stats
python nexmon_csi.py ~/captures/16pos_experiment/pos1_4ant.pcap --stats

# Filter to ESP32-C5 only
python nexmon_csi.py ~/captures/16pos_experiment/pos1_4ant.pcap \
    --stats --mac d0:cf:13:e2:88:94

# List all transmitters
python nexmon_csi.py ~/captures/16pos_experiment/pos1_4ant.pcap --list-macs
```

Expected output at 40MHz with C15:
- `chanspec: 0xd82e` (ch44/40MHz)
- `bandwidth: 40 MHz`
- `subcarriers: 64` per core
- ~77 fps
- 4 packets per probe request (one per antenna core)

---

## ML Pipeline

Both notebooks are in `ml/` and support toggles for all experiment configurations:

| Notebook | Task | Toggles |
|----------|------|---------|
| `CSI_MIMO_Classification_Final_1.ipynb` | 16-class position classification | `FEATURE_TYPE`, `ENABLE_MRC`, `ENABLE_RF` |
| `CSI_MIMO_Regression_Final_1.ipynb` | XY coordinate regression | `SPLIT_TYPE`, `FEATURE_TYPE`, `ENABLE_MRC`, `ENABLE_RF` |

### Feature strategies

| Strategy | Features | Description |
|----------|----------|-------------|
| 1-Antenna | 61 | Core 0 only, 61 valid subcarrier amp² (subs 0,1,63 removed) |
| 4-Antenna | 244 | All 4 cores concatenated, 61 subcarriers each |
| MRC (optional) | 61 | Sum of amp² across all 4 cores |

### Setup

```bash
cd ~/localization
python -m venv .venv
source .venv/bin/activate
pip install -r parsing/requirements.txt
jupyter notebook
```

Open `ml/CSI_MIMO_Classification_Final_1.ipynb` or `ml/CSI_MIMO_Regression_Final_1.ipynb`.

---

## Updating ML Scripts

When you modify a notebook and want to save it to the repo:

```bash
cd ~/nexmon-csi-localization/nexmon-csi-localization
cp ~/localization/CSI_MIMO_Classification_Final_1.ipynb ml/
cp ~/localization/CSI_MIMO_Regression_Final_1.ipynb ml/
git add ml/
git commit -m "Update ML notebooks with new results"
git push origin main
```

---

## Known Issues

See `docs/06_troubleshooting.md` for all known issues including:
- Channel resetting to 149/20MHz after `service restart_wireless`
- `nexutil errno=19` — Nexmon patch not active
- `0 packets captured` — monitor mode not enabled
- Core separation bugs in parser
- Build errors on Ubuntu 22.04

---

## Citation

If you use this work please cite:
- Nexmon: https://nexmon.org
- Nexmon CSI: https://github.com/seemoo-lab/nexmon_csi
- Gringoli et al., "Free Your CSI", WiNTECH 2019
