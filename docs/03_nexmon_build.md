# Step 3 — Nexmon Base Framework Build

## Clone and build

```bash
git clone https://github.com/seemoo-lab/nexmon.git
cd nexmon
source setup_env.sh
make
```

Expected: extracts firmware ucodes for all supported chips including bcm4366c0.

## Clone aarch64 toolchain

```bash
cd ~
git clone https://github.com/RMerl/am-toolchains.git

export AMCC=$(pwd)/am-toolchains/brcm-arm-hnd/crosstools-aarch64-gcc-5.3-linux-4.1-glibc-2.22-binutils-2.25/usr/bin/aarch64-buildroot-linux-gnu-

# Verify
ls ${AMCC}gcc
```

## Build nexutil for router

```bash
export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:$LD_LIBRARY_PATH
cd ~/nexmon/utilities/nexutil/

${AMCC}gcc -o nexutil \
    nexutil.c bcmutils.c bcmwifi_channels.c b64-encode.c b64-decode.c \
    ../libnexio/libnexio.c \
    -I include -I ../libargp -I ../../patches/include \
    -DVERSION=\"1.0\"

file nexutil
# Should show: ELF 64-bit LSB executable, ARM aarch64

scp nexutil admin@192.168.1.1:/jffs/
```

## Fix b43-v2 assembler

The bundled b43-asm.bin needs to be rebuilt from source to support `xje` instruction:

```bash
cd ~/nexmon/buildtools/b43-v2/assembler
make clean && make

# Fix Python 2 beautifier shebang
sudo apt-get install python2 -y
sudo sed -i 's|#!/usr/bin/env python$|#!/usr/bin/env python2|' \
    ~/nexmon/buildtools/b43-v2/debug/b43-beautifier
```
