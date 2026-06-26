#!/bin/bash
# collect_csi.sh — Configure router CSI and capture on Ubuntu
# Usage: ./collect_csi.sh <output.pcap>
# Example: ./collect_csi.sh ~/captures/16pos_experiment/pos1_4ant.pcap
#
# IMPORTANT: Set channel to 44/40MHz via web UI BEFORE running this script
#   http://192.168.1.1 → Wireless → Professional → 5GHz → ch44, 40MHz → Apply

ROUTER_IP="192.168.1.1"
ROUTER_USER="admin"
OUTPUT=${1:-capture.pcap}

echo "=== Nexmon CSI Collection ==="
echo "Output: ${OUTPUT}"

# Step 1 — Restart wireless to reload Nexmon driver
echo "[1/3] Restarting wireless (reloads Nexmon driver)..."
ssh ${ROUTER_USER}@${ROUTER_IP} "service restart_wireless"
sleep 15

# Step 2 — Apply CSI params and enable monitor mode
echo "[2/3] Applying CSI params (ch44/40MHz, C15, N=1)..."
ssh ${ROUTER_USER}@${ROUTER_IP} "cd /jffs && \
    wl -i eth6 up && \
    ifconfig eth6 up && \
    PARAMS=\$(./makecsiparams -c 44/40 -C 15 -N 1) && \
    ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && \
    wl -i eth6 monitor 1 && \
    echo DONE"

# Step 3 — Verify channel
echo "[3/3] Verifying channel..."
CHANSPEC=$(ssh ${ROUTER_USER}@${ROUTER_IP} "wl -i eth6 chanspec")
echo "  Chanspec: ${CHANSPEC}"
if [[ "$CHANSPEC" != *"0xd82e"* ]]; then
    echo "  WARNING: Channel is not 44l (0xd82e) — set via web UI first!"
    exit 1
fi

echo ""
echo "CSI active. Starting capture → ${OUTPUT}"
echo "Press Ctrl+C to stop."
echo ""

mkdir -p $(dirname ${OUTPUT})
sudo tcpdump -i eno1 ether src 4e:45:58:4d:4f:4e -w ${OUTPUT}
