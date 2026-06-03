# Step 1 — Ubuntu 22.04 Build Environment Setup

## Install all dependencies

```bash
sudo apt-get update
sudo apt-get install -y git libssl-dev gawk qpdf python3 bc make gcc \
     libgmp-dev autoconf automake libtool texinfo bison flex \
     g++ g++-multilib libmpc-dev python-is-python3 python2

sudo dpkg --add-architecture i386
sudo apt update
sudo apt install -y libc6:i386 libncurses5:i386 libstdc++6:i386 \
     libmpc3:i386 libmpfr-dev:i386
```

## Fix 32-bit library symlinks

The aarch64 cross-compiler is 32-bit and needs 32-bit system libs:

```bash
# libmpc (may already exist — check first)
find /usr -name "libmpc.so*" 2>/dev/null
# If /usr/lib/i386-linux-gnu/libmpc.so.3 missing:
sudo ln -s /usr/lib/i386-linux-gnu/libmpc.so.3.2.1 /usr/lib/i386-linux-gnu/libmpc.so.3

# libmpfr 32-bit (system has .so.6, compiler needs .so.4)
sudo ln -s /usr/lib/i386-linux-gnu/libmpfr.so.6 /usr/lib/i386-linux-gnu/libmpfr.so.4

# Export for current session (add to ~/.bashrc for persistence)
export LD_LIBRARY_PATH=/usr/lib/i386-linux-gnu:$LD_LIBRARY_PATH
```

## Build libisl and libmpfr from source (nexmon buildtools)

```bash
cd ~/nexmon/buildtools/isl-0.10
make clean
./configure && make && sudo make install
sudo mkdir -p /usr/lib/arm-linux-gnueabihf
sudo ln -s /usr/local/lib/libisl.so /usr/lib/arm-linux-gnueabihf/libisl.so.10

cd ~/nexmon/buildtools/mpfr-3.1.4
autoreconf -f -i
./configure && make && sudo make install
sudo ln -s /usr/local/lib/libmpfr.so /usr/lib/arm-linux-gnueabihf/libmpfr.so.4
```

## Verify

```bash
ls /usr/lib/arm-linux-gnueabihf/libisl.so.10
ls /usr/lib/arm-linux-gnueabihf/libmpfr.so.4
ls /usr/lib/i386-linux-gnu/libmpfr.so.4
ls /usr/lib/i386-linux-gnu/libmpc.so.3
```

All four should show symlinks.
