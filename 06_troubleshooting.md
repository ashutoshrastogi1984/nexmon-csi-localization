# Troubleshooting Guide

## Build Issues (Ubuntu 22.04)

### `gmp.h: No such file or directory`
```bash
sudo apt-get install libgmp-dev
```

### `bison: not found`
```bash
sudo apt-get install bison flex
```

### `makeinfo: command not found`
```bash
sudo apt-get install texinfo
```

### `libmpc.so.3: wrong ELF class: ELFCLASS64`
The cross-compiler needs 32-bit libmpc:
```bash
sudo apt-get install libmpc3:i386
export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:$LD_LIBRARY_PATH
```

### `libmpfr.so.4: cannot open shared object file`
```bash
sudo apt-get install libmpfr-dev:i386
sudo ln -s /usr/lib/i386-linux-gnu/libmpfr.so.6 /usr/lib/i386-linux-gnu/libmpfr.so.4
```

### `xje ... syntax error` in assembler
The default b43-asm doesn't support `xje`. Use b43-v2 assembler from nexmon:
```bash
cd ~/nexmon/buildtools/b43-v2/assembler
make clean && make
```

### `SHM(0x1724): syntax error` or `COND_RX_COMPLETE: syntax error`
Add include files to Makefile assembler call (see Step 4 in README).

### `enable_carrier_search does not exist`
Two patch hunks fail to apply due to line number mismatch. Use commit `13f87d2`:
```bash
cd ~/nexmon/patches/bcm4366c0/10_10_122_20/nexmon_csi
git checkout 13f87d2
make clean && rm -f src/csi.ucode.bcm4366c0.10_10_122_20.asm
make
```

### `b43-beautifier: SyntaxError: Missing parentheses in call to 'print'`
Fix Python 2 shebang:
```bash
sudo apt-get install python2 -y
sudo sed -i 's|#!/usr/bin/env python$|#!/usr/bin/env python2|' \
    ~/nexmon/buildtools/b43-v2/debug/b43-beautifier
```

---

## Router Issues

### `nexutil: error ret=-1 errno=95`
The radio hardware is not up. Run:
```bash
wl -i eth6 up
ifconfig eth6 up
wl -i eth6 radio on
```
Then retry nexutil.

### SSID not visible after flashing
```bash
ssh admin@192.168.1.1 "service restart_wireless"
```

### Router crashes when running `rmmod dhd`
This is normal — use the `init-start` script approach instead of manual rmmod.
Never run `rmmod dhd` interactively over SSH.

### `dmesg | grep nexmon` shows nothing
The stock dhd module is loaded. The init-start script runs `rmmod dhd && insmod /jffs/dhd.ko` at boot. Verify the script exists:
```bash
cat /jffs/scripts/init-start
```

---

## Capture Issues

### `0 packets captured` with `-m ff:ff:ff:ff:ff:ff`
Do NOT use `-m ff:ff:ff:ff:ff:ff`. This sets `n_mac_addr=1` which filters for broadcast source MAC — no real device uses this. Simply omit `-m`:
```bash
PARAMS=$(./makecsiparams -c 44/80 -C 15 -N 15)
```

### CSI packets not reaching Ubuntu machine
The CSI packets are broadcast UDP from source IP `10.10.10.10` with source MAC `4e:45:58:4d:4f:4e` (NEXMON in ASCII). Capture by MAC:
```bash
sudo tcpdump -i eno1 -n ether src 4e:45:58:4d:4f:4e -w capture.pcap
```

### Only Core 0 SS 0 in captures
With a 1×1 transmitter (phone), only one core/SS combination appears per frame. Use `-C 15 -N 15` to capture on all router antennas. The four antenna streams appear as `core_ss` values `0x0000, 0x0010, 0x0020, 0x0030` (core=0, ss=0/2/4/6).

---

## Parsing Issues

### Magic bytes
Pre-PR#256 format uses 4-byte magic `0x11111111`.
Post-PR#256 (commit `13f87d2`) uses 2-byte magic `0x1111`.
Always check first 2 bytes: if `== 0x1111`, use 2-byte offset.

### Header layout (commit 13f87d2)
```
Offset  Size  Field
0       2     Magic (0x1111)
2       6     Source MAC
8       2     Sequence number
10      2     Core & SS (core=bits[2:0], ss=bits[5:3])
12      2     Chanspec (may be 0x0000 in this commit — bug)
14      2     Chip version (0xE22A = bcm4366c0 = also encodes chanspec)
16      2     Padding
18      N*4   CSI data (N=64/128/256 for 20/40/80 MHz)
```

### CSI data format (bcm4366c0)
Use the official `unpack_float_acphy` with `nman=12, nexp=6, nbits=10`.
See `parsing/unpack_float.py`.
