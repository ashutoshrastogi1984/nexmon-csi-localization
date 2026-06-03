#!/bin/bash
# setup_env.sh — One-shot build environment setup for Ubuntu 22.04
# Run once after cloning this repo and nexmon.
# Usage: bash scripts/setup_env.sh

set -e

NEXMON_ROOT="${HOME}/nexmon"
TOOLCHAIN_ROOT="${HOME}/am-toolchains"

echo "=== Nexmon CSI Build Environment Setup ==="

# --- System packages ---
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y git libssl-dev gawk qpdf python3 bc make gcc \
    libgmp-dev autoconf automake libtool texinfo bison flex \
    g++ g++-multilib libmpc-dev python-is-python3 python2

sudo dpkg --add-architecture i386
sudo apt-get update -qq
sudo apt-get install -y libc6:i386 libncurses5:i386 libstdc++6:i386 \
    libmpc3:i386 libmpfr-dev:i386

# --- 32-bit lib symlinks ---
echo "[2/6] Creating 32-bit library symlinks..."
[ ! -f /usr/lib/i386-linux-gnu/libmpfr.so.4 ] && \
    sudo ln -s /usr/lib/i386-linux-gnu/libmpfr.so.6 /usr/lib/i386-linux-gnu/libmpfr.so.4 && \
    echo "  Created libmpfr.so.4 symlink"

export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:$LD_LIBRARY_PATH

# --- Clone nexmon ---
echo "[3/6] Cloning nexmon..."
if [ ! -d "$NEXMON_ROOT" ]; then
    git clone https://github.com/seemoo-lab/nexmon.git "$NEXMON_ROOT"
fi

# --- Build nexmon libs ---
echo "[4/6] Building libisl and libmpfr..."
sudo mkdir -p /usr/lib/arm-linux-gnueabihf

cd "${NEXMON_ROOT}/buildtools/isl-0.10"
make clean -s && ./configure -q && make -s && sudo make install -s
sudo ln -sf /usr/local/lib/libisl.so /usr/lib/arm-linux-gnueabihf/libisl.so.10

cd "${NEXMON_ROOT}/buildtools/mpfr-3.1.4"
autoreconf -f -i -q && ./configure -q && make -s && sudo make install -s
sudo ln -sf /usr/local/lib/libmpfr.so /usr/lib/arm-linux-gnueabihf/libmpfr.so.4

# --- Nexmon base make ---
echo "[5/6] Building nexmon base..."
cd "$NEXMON_ROOT"
source setup_env.sh
make -s
apt-get install -y bison flex
make -s

# --- Clone toolchain ---
echo "[6/6] Cloning aarch64 toolchain..."
if [ ! -d "$TOOLCHAIN_ROOT" ]; then
    git clone https://github.com/RMerl/am-toolchains.git "$TOOLCHAIN_ROOT"
fi

# --- Fix b43-v2 assembler ---
echo "[+] Rebuilding b43-v2 assembler..."
cd "${NEXMON_ROOT}/buildtools/b43-v2/assembler"
make clean -s && make -s

echo "[+] Fixing b43-beautifier Python shebang..."
sudo sed -i 's|#!/usr/bin/env python$|#!/usr/bin/env python2|' \
    "${NEXMON_ROOT}/buildtools/b43-v2/debug/b43-beautifier"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Export these in every new terminal (or add to ~/.bashrc):"
echo ""
echo "  export NEXMON_ROOT=${NEXMON_ROOT}"
echo "  export AMCC=${TOOLCHAIN_ROOT}/brcm-arm-hnd/crosstools-aarch64-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25/usr/bin/aarch64-buildroot-linux-gnu-"
echo "  export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:\$LD_LIBRARY_PATH"
echo "  source \${NEXMON_ROOT}/setup_env.sh"
