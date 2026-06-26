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
Use tested commit `13f87d2`:
```bash
cd ~/nexmon/patches/bcm4366c0/10_10_122_20/nexmon_csi
git checkout 13f87d2
make clean && rm -f src/csi.ucode.bcm4366c0.10_10_122_20.asm
make
```

### `b43-beautifier: SyntaxError: Missing parentheses in call to 'print'`
```bash
sudo apt-get install python2 -y
sudo sed -i 's|#!/usr/bin/env python$|#!/usr/bin/env python2|' \
    ~/nexmon/buildtools/b43-v2/debug/b43-beautifier
```

---

## Router Issues

### `nexutil: error ret=-1 errno=19` (No such device)
eth6 is not up or Nexmon driver not active. Run full activation sequence:
```bash
ssh admin@192.168.1.1 "service restart_wireless"
# Wait 15 seconds
ssh admin@192.168.1.1 "cd /jffs && wl -i eth6 up && ifconfig eth6 up && PARAMS=\$(./makecsiparams -c 44/40 -C 15 -N 1) && ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && wl -i eth6 monitor 1 && echo DONE"
```

### `nexutil -g500` returns all zeros after setting
Nexmon patch not active on eth6. Run `service restart_wireless` first, then reapply CSI params. The `wl eth6 down/up` alone is insufficient — `restart_wireless` is required.

### Channel resets to 149/20MHz after `service restart_wireless`
This always happens. Fix via web UI:
- Open `http://192.168.1.1` → Wireless → Professional → 5GHz
- Set channel=44, bandwidth=40MHz → Apply
- Verify: `ssh admin@192.168.1.1 "wl -i eth6 chanspec"` → must show `44l (0xd82e)`
- Then reapply CSI params

### `wl -i eth6 chanspec 44/40l` returns error
The `wl chanspec` set command does not work on eth6 on this router. Channel is set by `makecsiparams -c 44/40` command via nexutil — NOT by wl chanspec. Use web UI to set channel, then nexutil applies it correctly.

### `makecsiparams: not found` or `nexutil: not found`
Tools are in `/jffs/`, not in system PATH. Always use full path:
```bash
/jffs/makecsiparams -c 44/40 -C 15 -N 1
/jffs/nexutil -Ieth6 -s500 -b -l34 -v $PARAMS
```
Or `cd /jffs` first.

### SSID not visible after flashing
```bash
ssh admin@192.168.1.1 "service restart_wireless"
```

### Router crashes when running `rmmod dhd`
Never run `rmmod dhd` interactively over SSH — it drops the connection and may corrupt state. Use the `init-start` script approach which runs safely at boot.

### `dmesg | grep nexmon` shows nothing after reboot
The init-start script waits 30 seconds then reloads Nexmon driver. Wait at least 45 seconds after reboot before checking. Verify script exists:
```bash
cat /jffs/scripts/init-start
```
Should contain:
```
#!/bin/sh
sleep 30
/sbin/rmmod dhd
/sbin/insmod /jffs/dhd.ko
```

---

## Capture Issues

### `0 packets captured` with MAC filter
Check in order:
1. Is ESP32-C5 powered and transmitting? `sudo cat /dev/ttyACM0` — counter must increase with ESP_OK
2. Is `wl -i eth6 monitor 1` active? Rerun full CSI activation command
3. Is channel correct? `ssh admin@192.168.1.1 "wl -i eth6 chanspec"` → must show `44l (0xd82e)`
4. Is ethernet cable connected between patched router LAN port and laptop eno1?
5. Does eno1 have IP in 192.168.1.x? `ip a show eno1`

### Permission denied writing to `/tmp/`
sudo tcpdump cannot write to /tmp on Ubuntu. Always write to home directory:
```bash
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ~/captures/test.pcap
```

### UDP packets on port 7788 appearing but parser rejects them
Port 7788 is used by the ASUS router's own service — not Nexmon CSI. Nexmon CSI packets are identified by source MAC `4e:45:58:4d:4f:4e`, not by port number.

### Very low packet count at some positions (~30k vs ~55k)
Normal variation due to distance and multipath. Acceptable if:
- Duration ≥ 180 seconds (check with parser `--list-macs`)
- fps ≥ 70
- All 4 cores present

If duration < 180 seconds → recapture that position for the full 3 minutes.

### `No CSI frames assembled` in parser output
Raw packets captured but Nexmon header invalid — router lost monitor mode mid-capture. Reactivate CSI and recapture that position from scratch:
```bash
ssh admin@192.168.1.1 "service restart_wireless"
# Wait 15 seconds, then reapply CSI params
ssh admin@192.168.1.1 "cd /jffs && wl -i eth6 up && ifconfig eth6 up && PARAMS=\$(./makecsiparams -c 44/40 -C 15 -N 1) && ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && wl -i eth6 monitor 1 && echo DONE"
```

---

## Parsing Issues

### Core separation is critical
Parser must group by `(src_mac, seq, core_id)` — NOT by `(src_mac, seq)`.
Grouping without core_id averages all 4 cores together producing garbage CSI.

### Only 1 core appearing instead of 4
Verify C15 parameter was used: `makecsiparams -c 44/40 -C 15 -N 1`
C15 = binary 1111 = all 4 cores enabled.
At 80MHz only core 0 is active regardless of C value — must use 40MHz.

### Subcarrier count: 64 per core at 40MHz
At 40MHz: 512 bytes payload ÷ 8 bytes per complex sample = 64 subcarriers per core.
Total features for 4-core MIMO at 40MHz: 64 × 4 = 256 raw, or 61 × 4 = 244 after removing subs 0, 1, 63.

### Subcarriers to remove before ML
- Sub 0: DC component — always zero or near-zero
- Sub 1: low amplitude artifact
- Sub 63: DC spike artifact identified from diagnostic plot
- Valid subcarriers: indices 2-62 = 61 subcarriers per core

### Amplitude near-zero warning (~22%)
Expected at 40MHz due to null/guard subcarriers and pilot tones.
Near-zero ~22% is normal and not a problem for the ML pipeline.

### `uint32` to `int32` casting bug
Earlier parser versions cast raw bytes as uint32 before converting to int32,
corrupting ~50% of subcarrier values. The current `nexmon_csi.py` in `parsing/`
uses correct signed casting. Always use the version from this repo.
