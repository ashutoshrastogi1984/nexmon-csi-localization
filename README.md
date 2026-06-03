# Nexmon CSI Localization — RT-AC86U

WiFi CSI-based indoor localization using fingerprinting, time reversal, and machine learning on the **Asus RT-AC86U** (bcm4366c0 chipset).

---

## Hardware & Software Requirements

| Item | Details |
|------|---------|
| Router | Asus RT-AC86U (bcm4366c0) |
| Router firmware | Merlin 386.14_2 |
| Build machine | Ubuntu 22.04 (x86_64) |
| Python | 3.10+ |
| Transmitter | Any WiFi device (phone, laptop) |

---

## Repository Structure

```
nexmon_csi_localization/
├── README.md                    ← You are here
├── docs/
│   ├── 01_ubuntu_setup.md       ← Build environment setup
│   ├── 02_router_setup.md       ← Merlin firmware + SSH
│   ├── 03_nexmon_build.md       ← Nexmon base framework build
│   ├── 04_nexmon_csi_build.md   ← nexmon_csi patch build & flash
│   ├── 05_csi_collection.md     ← CSI capture procedure
│   └── 06_troubleshooting.md    ← Known issues & fixes
├── scripts/
│   ├── setup_env.sh             ← One-shot environment setup
│   ├── flash_csi_firmware.sh    ← Build & flash patched firmware
│   ├── collect_csi.sh           ← Configure router & start capture
│   └── router_init.sh           ← Router startup script (/jffs)
├── parsing/
│   ├── parse_csi.py             ← Main CSI parser (bcm4366c0)
│   ├── unpack_float.py          ← Official float unpacking
│   └── requirements.txt
├── ml/
│   └── README.md                ← ML pipeline (coming soon)
└── data/
    └── sample/                  ← Sample .pcap files (gitignored)
```

---

## Quick Start

### Step 1 — Ubuntu build environment

```bash
sudo apt-get update
sudo apt-get install git libssl-dev gawk qpdf python3 bc make gcc \
     libgmp-dev autoconf automake libtool texinfo bison flex \
     g++ g++-multilib libmpc-dev python-is-python3 python2
sudo dpkg --add-architecture i386
sudo apt update
sudo apt install libc6:i386 libncurses5:i386 libstdc++6:i386 \
     libmpc3:i386 libmpfr-dev:i386
```

### Step 2 — Clone repositories

```bash
# Nexmon base
git clone https://github.com/seemoo-lab/nexmon.git
cd nexmon

# Fix library symlinks (Ubuntu 22.04)
sudo mkdir -p /usr/lib/arm-linux-gnueabihf
cd buildtools/isl-0.10 && make clean && ./configure && make && sudo make install
sudo ln -s /usr/local/lib/libisl.so /usr/lib/arm-linux-gnueabihf/libisl.so.10
cd ../mpfr-3.1.4 && autoreconf -f -i && ./configure && make && sudo make install
sudo ln -s /usr/local/lib/libmpfr.so /usr/lib/arm-linux-gnueabihf/libmpfr.so.4
sudo ln -s /usr/lib/i386-linux-gnu/libmpfr.so.6 /usr/lib/i386-linux-gnu/libmpfr.so.4
sudo ln -s /usr/lib/i386-linux-gnu/libmpc.so.3  /usr/lib/i386-linux-gnu/libmpc.so.3
cd ../..

# Build nexmon base
source setup_env.sh
make

# Clone nexmon_csi at tested commit
cd patches/bcm4366c0/10_10_122_20/
git clone https://github.com/seemoo-lab/nexmon_csi.git
cd nexmon_csi
git checkout 13f87d2   # tested working commit (pre-PR#256)

# Toolchain
cd ~/
git clone https://github.com/RMerl/am-toolchains.git
export AMCC=$(pwd)/am-toolchains/brcm-arm-hnd/crosstools-aarch64-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25/usr/bin/aarch64-buildroot-linux-gnu-
```

### Step 3 — Fix b43-v2 assembler (Ubuntu 22.04)

```bash
# Install updated b43 assembler (supports xje instruction)
cd ~
git clone https://github.com/mbuesch/b43-tools.git
# Use b43-v2 source from nexmon (it has xje support)
cd ~/nexmon/buildtools/b43-v2/assembler
make clean && make

# Fix Python 2 beautifier
sudo apt-get install python2 -y
sudo sed -i 's|#!/usr/bin/env python$|#!/usr/bin/env python2|' \
    ~/nexmon/buildtools/b43-v2/debug/b43-beautifier
```

### Step 4 — Add missing include files to Makefile

The assembler needs SHM/condition/register include files. Edit line 223 of the nexmon_csi Makefile:

```bash
cd ~/nexmon/patches/bcm4366c0/10_10_122_20/nexmon_csi
sed -i 's|--cpp-args -DRXE_RXHDR_LEN=$(RXE_RXHDR_LEN) --|--cpp-args -DRXE_RXHDR_LEN=$(RXE_RXHDR_LEN) -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/shm.inc -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/cond.inc -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/regs.inc -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/spr.inc --|' Makefile
```

Also add `mov 0x86E, SPARE1` before `calls L902` in the ucode patch (line ~4332):

```bash
grep -n "calls.*L902" src/csi.ucode.bcm4366c0.10_10_122_20.asm | head -2
# Fix line number as needed:
sed -i '4332s/^\tcalls\tL902/\tmov\t0x86E, SPARE1\n\tcalls\tL902/' \
    src/csi.ucode.bcm4366c0.10_10_122_20.asm
```

### Step 5 — Build nexutil for router

```bash
export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:$LD_LIBRARY_PATH
cd ~/nexmon/utilities/nexutil/
export CC=${AMCC}gcc
${AMCC}gcc -o nexutil nexutil.c bcmutils.c bcmwifi_channels.c \
    b64-encode.c b64-decode.c \
    ../libnexio/libnexio.c \
    -I include -I ../libargp -I ../../patches/include \
    -DVERSION=\"1.0\"
scp nexutil admin@192.168.1.1:/jffs/
```

### Step 6 — Build & flash patched firmware

```bash
cd ~/nexmon/patches/bcm4366c0/10_10_122_20/nexmon_csi
source ../../../../setup_env.sh
export AMCC=~/am-toolchains/brcm-arm-hnd/crosstools-aarch64-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25/usr/bin/aarch64-buildroot-linux-gnu-
export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:$LD_LIBRARY_PATH
make install-firmware REMOTEADDR=192.168.1.1
```

### Step 7 — Build & copy makecsiparams

```bash
cd utils/makecsiparams
${AMCC}gcc -o makecsiparams makecsiparams.c bcmwifi_channels.c -I./
scp makecsiparams admin@192.168.1.1:/jffs/
```

### Step 8 — Persistent firmware load on router

SSH into the router and create startup script:

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

After reboot, verify:
```bash
ssh admin@192.168.1.1 "dmesg | grep -i nexmon"
# Should show: nexmon.org/csi: a975-...
```

### Step 9 — CSI Collection

**Check which channel your 5GHz radio is on:**
```bash
ssh admin@192.168.1.1 "wl -i eth6 channel"
# Note the channel (e.g. 44)
```

**Configure CSI extraction (on router):**
```bash
ssh admin@192.168.1.1 "service restart_wireless"
ssh admin@192.168.1.1 "cd /jffs && \
    wl -i eth6 up && ifconfig eth6 up && \
    PARAMS=\$(./makecsiparams -c 44/80 -C 15 -N 15) && \
    ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && \
    wl -i eth6 monitor 1 && echo DONE"
```

**Capture on Ubuntu:**
```bash
sudo tcpdump -i eno1 -n ether src 4e:45:58:4d:4f:4e \
    -w ~/captures/location_A.pcap
```

> `-m` flag omitted intentionally — using broadcast MAC filter causes 0 captures.
> Source MAC `4e:45:58:4d:4f:4e` = "NEXMON" in ASCII.

---

## Known Issues & Fixes

See [docs/06_troubleshooting.md](docs/06_troubleshooting.md)

---

## Citation

If you use this work please cite:
- Nexmon: https://nexmon.org
- Nexmon CSI: https://github.com/seemoo-lab/nexmon_csi
- Gringoli et al., "Free Your CSI", WiNTECH 2019
