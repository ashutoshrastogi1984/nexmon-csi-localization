# Step 4 — nexmon_csi Patch Build & Flash

## Clone nexmon_csi at tested commit

```bash
cd ~/nexmon/patches/bcm4366c0/10_10_122_20/
git clone https://github.com/seemoo-lab/nexmon_csi.git
cd nexmon_csi
git checkout 13f87d2   # last tested working commit (pre-PR#256)
```

> **Why this commit?** PR#256 introduced backwards-incompatible changes.
> Commit `13f87d2` builds cleanly on Ubuntu 22.04 with all 8 patch hunks applying.

## Apply Makefile fix (include files for assembler)

```bash
sed -i 's|--cpp-args -DRXE_RXHDR_LEN=$(RXE_RXHDR_LEN) --|--cpp-args -DRXE_RXHDR_LEN=$(RXE_RXHDR_LEN) -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/shm.inc -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/cond.inc -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/regs.inc -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/spr.inc --|' Makefile
```

## Apply ucode fix (SPARE1 before calls L902)

Find the exact line number of the first `calls L902`:
```bash
grep -n "calls.*L902" src/csi.ucode.bcm4366c0.10_10_122_20.asm | head -2
```

Then insert `mov 0x86E, SPARE1` before it (replace 4332 with your line number):
```bash
sed -i '4332s/^\tcalls\tL902/\tmov\t0x86E, SPARE1\n\tcalls\tL902/' \
    src/csi.ucode.bcm4366c0.10_10_122_20.asm
```

## Build and flash

```bash
source ../../../../setup_env.sh
export AMCC=~/am-toolchains/brcm-arm-hnd/crosstools-aarch64-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25/usr/bin/aarch64-buildroot-linux-gnu-
export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:$LD_LIBRARY_PATH

make install-firmware REMOTEADDR=192.168.1.1
```

Expected output ends with:
```
COPYING TO ROUTER dhd.ko => /jffs/dhd.ko
LOADING /jffs/dhd.ko
```

## Build and copy makecsiparams

```bash
cd utils/makecsiparams
${AMCC}gcc -o makecsiparams makecsiparams.c bcmwifi_channels.c -I./
scp makecsiparams admin@192.168.1.1:/jffs/
```

## Set up persistent firmware load on router

```bash
ssh admin@192.168.1.1
cat > /jffs/scripts/init-start << 'EOF'
#!/bin/sh
sleep 30
/sbin/rmmod dhd
/sbin/insmod /jffs/dhd.ko
EOF
chmod +x /jffs/scripts/init-start
reboot
```

## Verify after reboot

```bash
# Wait ~45 seconds then:
ssh admin@192.168.1.1 "dmesg | grep -i nexmon"
# Expected: CONSOLE: ... 10.10.122.20 (nexmon.org/csi: a975-...)

ssh admin@192.168.1.1 "service restart_wireless"
```
