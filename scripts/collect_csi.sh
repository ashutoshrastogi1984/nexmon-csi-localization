#!/bin/bash
# collect_csi.sh — Configure router and capture CSI on Ubuntu
# Usage: ./collect_csi.sh <channel> <bw> <output.pcap> [duration_seconds]
# Example: ./collect_csi.sh 44 80 location_A.pcap 30

ROUTER_IP="192.168.1.1"
ROUTER_USER="admin"
CHANNEL=${1:-44}
BW=${2:-80}
OUTPUT=${3:-capture.pcap}
DURATION=${4:-30}

echo "=== Nexmon CSI Collection ==="
echo "Channel: ${CHANNEL}/${BW}MHz  Output: ${OUTPUT}  Duration: ${DURATION}s"

# Configure router
echo "[1/3] Configuring router..."
ssh ${ROUTER_USER}@${ROUTER_IP} "
  cd /jffs
  wl -i eth6 up
  ifconfig eth6 up
  PARAMS=\$(./makecsiparams -c ${CHANNEL}/${BW} -C 15 -N 15)
  ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS
  wl -i eth6 monitor 1
  echo Router configured on channel ${CHANNEL}/${BW}
"

# Start capture
echo "[2/3] Capturing for ${DURATION}s..."
mkdir -p $(dirname ${OUTPUT})
sudo timeout ${DURATION} tcpdump -i eno1 -n \
    ether src 4e:45:58:4d:4f:4e \
    -w ${OUTPUT}

# Summary
echo "[3/3] Capture complete."
python3 -c "
from scapy.all import rdpcap, UDP
import struct
pkts = rdpcap('${OUTPUT}')
count = sum(1 for p in pkts if UDP in p and p[UDP].dport==5500)
print(f'  Packets captured: {count}')
from collections import Counter
c = Counter()
for p in pkts:
    if UDP not in p or p[UDP].dport!=5500: continue
    pay = bytes(p[UDP].payload)
    if len(pay)<12: continue
    if struct.unpack_from('<H',pay,0)[0]!=0x1111: continue
    cs = struct.unpack_from('<H',pay,10)[0]
    c[(cs&7,(cs>>3)&7)] += 1
for (core,ss),n in sorted(c.items()):
    print(f'  Core {core} SS {ss}: {n} packets')
" 2>/dev/null || echo "  (install scapy for summary)"
