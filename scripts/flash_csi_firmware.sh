#!/bin/bash
# flash_csi_firmware.sh — Build and flash nexmon_csi patched firmware
# Usage: bash scripts/flash_csi_firmware.sh <router_ip>
# Example: bash scripts/flash_csi_firmware.sh 192.168.1.1

set -e

ROUTER_IP=${1:-192.168.1.1}
NEXMON_ROOT="${HOME}/nexmon"
TOOLCHAIN="${HOME}/am-toolchains/brcm-arm-hnd/crosstools-aarch64-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25/usr/bin/aarch64-buildroot-linux-gnu-"
CSI_DIR="${NEXMON_ROOT}/patches/bcm4366c0/10_10_122_20/nexmon_csi"

export AMCC="$TOOLCHAIN"
export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:$LD_LIBRARY_PATH

echo "=== Nexmon CSI Firmware Flash ==="
echo "Router: ${ROUTER_IP}"

# Clone nexmon_csi if not present
if [ ! -d "$CSI_DIR" ]; then
    echo "[1/4] Cloning nexmon_csi..."
    cd "${NEXMON_ROOT}/patches/bcm4366c0/10_10_122_20/"
    git clone https://github.com/seemoo-lab/nexmon_csi.git
    cd nexmon_csi
    git checkout 13f87d2
else
    echo "[1/4] nexmon_csi already cloned."
fi

# Apply Makefile fix
echo "[2/4] Applying Makefile include fix..."
cd "$CSI_DIR"
if ! grep -q "shm.inc" Makefile; then
    sed -i 's|--cpp-args -DRXE_RXHDR_LEN=$(RXE_RXHDR_LEN) --|--cpp-args -DRXE_RXHDR_LEN=$(RXE_RXHDR_LEN) -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/shm.inc -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/cond.inc -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/regs.inc -include $(NEXMON_ROOT)/buildtools/$(B43VERSION)/debug/include/spr.inc --|' Makefile
    echo "  Makefile patched."
else
    echo "  Makefile already patched."
fi

# Apply ucode SPARE1 fix
echo "[3/4] Applying ucode SPARE1 fix..."
source "${NEXMON_ROOT}/setup_env.sh"
# Regenerate asm if needed
if [ ! -f "src/csi.ucode.bcm4366c0.10_10_122_20.asm" ]; then
    make gen/ucode.asm 2>/dev/null || true
fi
LINE=$(grep -n "^	calls	L902" src/csi.ucode.bcm4366c0.10_10_122_20.asm 2>/dev/null | head -1 | cut -d: -f1)
if [ -n "$LINE" ]; then
    PREV=$(sed -n "$((LINE-1))p" src/csi.ucode.bcm4366c0.10_10_122_20.asm)
    if ! echo "$PREV" | grep -q "0x86E"; then
        sed -i "${LINE}s/^\tcalls\tL902/\tmov\t0x86E, SPARE1\n\tcalls\tL902/" \
            src/csi.ucode.bcm4366c0.10_10_122_20.asm
        echo "  SPARE1 fix applied at line $LINE."
    else
        echo "  SPARE1 fix already present."
    fi
fi

# Build and flash
echo "[4/4] Building and flashing (enter router password when prompted)..."
make install-firmware REMOTEADDR="${ROUTER_IP}"

# Build makecsiparams
echo "[+] Building makecsiparams for router..."
cd utils/makecsiparams
${AMCC}gcc -o makecsiparams makecsiparams.c bcmwifi_channels.c -I./ 2>/dev/null
scp makecsiparams admin@${ROUTER_IP}:/jffs/
echo "  makecsiparams copied to router."

echo ""
echo "=== Done. Reboot router to load patched firmware ==="
echo "  ssh admin@${ROUTER_IP} 'reboot'"
