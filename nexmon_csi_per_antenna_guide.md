# Nexmon CSI: Per-Antenna CSI Extraction Guide
### Based on the official seemoo-lab/nexmon_csi documentation & arXiv:2206.09532 (Hands-on Wi-Fi Sensing Tutorial)

---

## Overview

**Nexmon CSI** extracts Channel State Information (CSI) per Wi-Fi frame from Broadcom chipsets.
As explained in the paper (Section 3), CSI is a 4-D tensor `[T × S × A × L]`:

| Dimension | Meaning |
|-----------|---------|
| **T** | Number of CSI packets (time) |
| **S** | Number of subcarriers (e.g., 64/128/256 for 20/40/80 MHz) |
| **A** | Number of antennas / cores / spatial streams |
| **L** | Number of HT-LTFs per PPDU (usually 1) |

Per-antenna extraction is controlled via the `-C` (core bitmask) and `-N` (spatial stream bitmask) flags of `makecsiparams`.

---

## Supported Platforms

| Router / Device | Chip | Max MIMO | Firmware |
|----------------|------|----------|----------|
| Asus RT-AC86U | bcm4366c0 | 4×4 | 10.10.122.20 |
| Asus GT-AC5300 | bcm4366c0 | 4×4 | 10.10.122.20 |
| Raspberry Pi 4B | bcm43455c0 | 1×1 | varies |
| Raspberry Pi 3B+ | bcm43455c0 | 1×1 | varies |
| Nexus 5 | bcm4339 | 1×1 | varies |

This guide focuses on the **Asus RT-AC86U (bcm4366c0)** — the most capable platform for multi-antenna CSI.

---

## Prerequisites

- Linux build machine (Ubuntu 18.04/20.04 recommended)
- SSH access to the router with Merlin firmware enabled
- `git`, `make`, `gcc`, `libssl-dev`, `gawk` installed
- Router connected to local network (e.g., `192.168.50.1`)

```bash
sudo apt-get install git libssl-dev gawk qpdf python3 bc
```

---

## Step 1 — Clone the Nexmon Base Framework

```bash
git clone https://github.com/seemoo-lab/nexmon.git
cd nexmon
```

Check and install build dependencies (libisl and libmpfr):

```bash
# Check if these exist; if not, build from source
ls /usr/lib/arm-linux-gnueabihf/libisl.so.10
ls /usr/lib/arm-linux-gnueabihf/libmpfr.so.4

# If missing, build libisl
cd buildtools/isl-0.10
./configure && make && sudo make install
sudo ln -s /usr/local/lib/libisl.so /usr/lib/arm-linux-gnueabihf/libisl.so.10
cd ../..

# If missing, build libmpfr
cd buildtools/mpfr-3.1.4
autoreconf -f -i && ./configure && make && sudo make install
sudo ln -s /usr/local/lib/libmpfr.so /usr/lib/arm-linux-gnueabihf/libmpfr.so.4
cd ../..
```

---

## Step 2 — Set Up Environment & Extract Firmware

```bash
# From the nexmon root directory
source setup_env.sh

# Extract ucode, templateram, flashpatches from original firmware files
make
```

---

## Step 3 — Clone nexmon_csi Into the Correct Patch Directory

```bash
# Navigate to the bcm4366c0 patch directory
cd patches/bcm4366c0/10_10_122_20/

# Clone nexmon_csi as a sub-project here
git clone https://github.com/seemoo-lab/nexmon_csi.git

cd nexmon_csi
```

---

## Step 4 — Clone the aarch64 Toolchain

The RT-AC86U runs an aarch64 (ARM64) processor, so you need the cross-compiler:

```bash
# Go back to your working directory (alongside nexmon/)
cd ../../../../..
git clone https://github.com/RMerl/am-toolchains.git

# Export the cross-compiler path
export AMCC=$(pwd)/am-toolchains/brcm-arm-hnd/crosstools-aarch64-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25/usr/bin/aarch64-buildroot-linux-gnu-
```

---

## Step 5 — Enable SSH on the Router

On the Asus RT-AC86U web UI:
1. Go to **Administration → System**
2. Enable **SSH Daemon**
3. Note the router's IP (e.g., `192.168.50.1`)

---

## Step 6 — Build nexutil for the Router

`nexutil` is the userspace tool that communicates with the patched firmware via IOCTLs.

```bash
cd nexmon/utilities/nexutil/

# Set cross-compiler and build for aarch64
export CC=${AMCC}gcc
make

# Copy to router
scp nexutil admin@192.168.50.1:/jffs/
```

---

## Step 7 — Compile and Flash the Patched Firmware

```bash
cd nexmon/patches/bcm4366c0/10_10_122_20/nexmon_csi

# Make sure env vars are still set
source ../../../../setup_env.sh
export AMCC=<path-to-toolchain>/aarch64-buildroot-linux-gnu-

# Compile & install (this SSHes into the router and loads the firmware)
make install-firmware REMOTEADDR=192.168.50.1
```

This command:
1. Compiles the patched firmware (`dlarray_4366c0.bin`)
2. SCPs the patched `dhd.ko` kernel module to `/jffs/` on the router
3. Unloads the stock `dhd` module: `/sbin/rmmod dhd`
4. Loads the patched module: `/sbin/insmod /jffs/dhd.ko`

Verify successful load via SSH on the router:

```bash
ssh admin@192.168.50.1
dmesg | grep nexmon
# Should show: "nexmon.org/csi"
```

---

## Step 8 — Install makecsiparams

`makecsiparams` (or `mcp`) generates the base64-encoded config string for the CSI extractor.

```bash
cd nexmon/patches/bcm4366c0/10_10_122_20/nexmon_csi/utils/makecsiparams
make
scp makecsiparams admin@192.168.50.1:/jffs/
```

---

## Step 9 — Configure Per-Antenna CSI Collection

This is the key step for **per-antenna extraction**.

### Understanding -C and -N Flags

```
makecsiparams -c <channel>/<bw> -C <core_bitmask> -N <spatial_stream_bitmask> [-m <MAC>]
```

| Flag | Meaning | Example |
|------|---------|---------|
| `-c` | Channel and bandwidth | `36/20`, `157/80` |
| `-C` | Core bitmask (which Rx core/antenna) | `1` = core 0 only; `15` = all 4 cores |
| `-N` | Spatial stream bitmask | `1` = SS0 only; `15` = all 4 streams |
| `-m` | MAC address filter (source of frames) | `00:11:22:33:44:55` |

The RT-AC86U has **4 cores** (antennas). To collect from all 4 simultaneously:

```bash
# On the router — collect on channel 36, 20MHz, all 4 cores, all 4 spatial streams
PARAMS=$(./makecsiparams -c 36/20 -C 15 -N 15 -m ff:ff:ff:ff:ff:ff)
echo $PARAMS
# Outputs a base64 string like: m+IBEQ...

# Apply the config via nexutil
./nexutil -Ieth6 -s500 -b -l 34 -v $PARAMS
```

> **Interface name**: On RT-AC86U the 5GHz radio is typically `eth6`. Verify with `wl -i eth6 status`.

### Per-Antenna (Core) Configuration Examples

```bash
# Antenna 0 only (core 0, spatial stream 0)
PARAMS=$(./makecsiparams -c 36/20 -C 1 -N 1)

# Antenna 1 only (core 1, spatial stream 0)
PARAMS=$(./makecsiparams -c 36/20 -C 2 -N 1)

# Antenna 2 only (core 2)
PARAMS=$(./makecsiparams -c 36/20 -C 4 -N 1)

# Antenna 3 only (core 3)
PARAMS=$(./makecsiparams -c 36/20 -C 8 -N 1)

# All 4 antennas simultaneously (one UDP packet per antenna per frame)
PARAMS=$(./makecsiparams -c 36/20 -C 15 -N 15)
```

Apply each config:
```bash
./nexutil -Ieth6 -s500 -b -l 34 -v $PARAMS
```

---

## Step 10 — Enable Monitor Mode and Start Capture

```bash
# On the router via SSH
# Set the channel
./nexutil -Ieth6 -k 36/20

# Enable monitor mode
./nexutil -Ieth6 -m1

# Capture CSI UDP packets (port 5500)
tcpdump -i eth6 dst port 5500 -w /tmp/csi_capture.pcap
```

> **Note**: On Raspberry Pi, listen on `wlan0` instead of the monitor interface.

Copy the capture back to your machine:
```bash
scp admin@192.168.50.1:/tmp/csi_capture.pcap ./
```

---

## Step 11 — Parsing the Per-Antenna CSI UDP Payload

Each UDP packet captured at port 5500 has the following payload structure:

```
[ 4 bytes ]  Magic: 0x11111111
[ 2 bytes ]  Source MAC (bytes 1–2)
[ 4 bytes ]  Source MAC (bytes 3–6)
[ 2 bytes ]  Frame sequence number
[ 2 bytes ]  Core & Spatial Stream number ← ANTENNA IDENTIFIER
[ 2 bytes ]  Chanspec
[ 2 bytes ]  Chip version
[ N×4 bytes] CSI data (64/128/256 complex values for 20/40/80 MHz)
```

### Decoding the Core & Spatial Stream Byte

```
core_and_ss = <2-byte value>
core_number  = core_and_ss & 0x07        # lowest 3 bits
spatial_stream = (core_and_ss >> 3) & 0x07  # next 3 bits
```

Example: `0x0019` = `0b00011001` → core 0, spatial stream 3.

### Python Parser

```python
import struct
import numpy as np
from scapy.all import rdpcap, UDP

def parse_nexmon_csi(pcap_file):
    packets = rdpcap(pcap_file)
    csi_by_antenna = {}

    for pkt in packets:
        if UDP not in pkt or pkt[UDP].dport != 5500:
            continue
        payload = bytes(pkt[UDP].payload)
        if len(payload) < 18:
            continue

        # Parse header
        magic = struct.unpack_from('<I', payload, 0)[0]
        if magic != 0x11111111:
            continue

        src_mac  = payload[4:10].hex(':')
        seq_num  = struct.unpack_from('<H', payload, 10)[0]
        core_ss  = struct.unpack_from('<H', payload, 12)[0]
        chanspec = struct.unpack_from('<H', payload, 14)[0]
        chipv    = struct.unpack_from('<H', payload, 16)[0]

        core   = core_ss & 0x07
        ss     = (core_ss >> 3) & 0x07
        ant_id = (core, ss)

        # Parse CSI (bcm4366c0 uses float format — 1-bit sign + 9-bit mantissa)
        csi_bytes = payload[18:]
        num_tones = len(csi_bytes) // 4
        csi_raw   = struct.unpack_from(f'<{num_tones*2}h', csi_bytes)
        csi_complex = np.array(csi_raw[0::2], dtype=float) + 1j * np.array(csi_raw[1::2], dtype=float)

        if ant_id not in csi_by_antenna:
            csi_by_antenna[ant_id] = []
        csi_by_antenna[ant_id].append(csi_complex)

    return csi_by_antenna

# Usage
csi = parse_nexmon_csi("csi_capture.pcap")
for (core, ss), frames in csi.items():
    print(f"Core {core}, Spatial Stream {ss}: {len(frames)} frames, {len(frames[0])} subcarriers")
    # frames is a list of np.arrays, shape: [num_frames, num_subcarriers]
```

---

## Step 12 — Aligning with the Paper's CSI Tensor Format

As described in the paper (Section 3, page 9), the expected tensor shape is `[T, S, A, L]`.
To reconstruct this from parsed captures:

```python
import numpy as np

def build_csi_tensor(csi_by_antenna, num_subcarriers=64):
    """
    Build a [T, S, A, 1] tensor from parsed per-antenna CSI.
    Assumes all antennas captured the same number of frames.
    """
    antenna_keys = sorted(csi_by_antenna.keys())  # sorted by (core, ss)
    A = len(antenna_keys)
    T = min(len(csi_by_antenna[k]) for k in antenna_keys)

    csi_tensor = np.zeros((T, num_subcarriers, A, 1), dtype=complex)
    for a_idx, ant_id in enumerate(antenna_keys):
        frames = csi_by_antenna[ant_id][:T]
        for t, frame in enumerate(frames):
            csi_tensor[t, :len(frame), a_idx, 0] = frame[:num_subcarriers]

    return csi_tensor, antenna_keys

csi_by_antenna = parse_nexmon_csi("csi_capture.pcap")
tensor, ant_ids = build_csi_tensor(csi_by_antenna, num_subcarriers=64)
print(f"CSI Tensor shape: {tensor.shape}")  # [T, 64, A, 1]
print(f"Antenna IDs (core, ss): {ant_ids}")
```

---

## Persistence After Reboot

The patched firmware is **not** persistent across reboots. To reload:

```bash
# SSH into router and reload manually
ssh admin@192.168.50.1
/sbin/rmmod dhd
/sbin/insmod /jffs/dhd.ko
```

Or add to `/jffs/scripts/post-mount` (Merlin firmware):

```bash
#!/bin/sh
sleep 10
/sbin/rmmod dhd
/sbin/insmod /jffs/dhd.ko
```

---

## Quick Reference Summary

```
Step 1:  git clone nexmon → source setup_env.sh → make
Step 2:  cd patches/bcm4366c0/10_10_122_20/ → git clone nexmon_csi
Step 3:  Clone am-toolchains, export AMCC
Step 4:  Build & scp nexutil to router
Step 5:  make install-firmware REMOTEADDR=<router-ip>
Step 6:  Build & scp makecsiparams to router
Step 7:  SSH to router → mcp -c <ch/bw> -C <core_mask> -N <ss_mask>
Step 8:  nexutil -Ieth6 -s500 -b -l 34 -v <base64>
Step 9:  nexutil -Ieth6 -m1  (monitor mode)
Step 10: tcpdump -i eth6 dst port 5500 -w capture.pcap
Step 11: Parse UDP payload, decode core & SS byte for per-antenna ID
Step 12: Reshape into [T, S, A, L] tensor as in the paper
```

---

## Key Antenna Bitmask Reference

| -C value | Cores active |
|----------|-------------|
| 1 (0b0001) | Core 0 only |
| 2 (0b0010) | Core 1 only |
| 4 (0b0100) | Core 2 only |
| 8 (0b1000) | Core 3 only |
| 15 (0b1111) | All 4 cores |

| -N value | Spatial Streams |
|----------|----------------|
| 1 (0b0001) | SS 0 only |
| 15 (0b1111) | All 4 SS |

For a **4×4 MIMO** setup collecting all antenna combinations: use `-C 15 -N 15`.
You will receive **4 UDP packets per Wi-Fi frame** (one per core), each identifiable by the `core_ss` field.
