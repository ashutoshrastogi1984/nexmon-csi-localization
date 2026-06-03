# Step 5 — CSI Collection Procedure

## Check which channel the 5GHz radio is on

```bash
ssh admin@192.168.1.1 "wl -i eth6 channel"
# Example output: current mac channel  44
```

## Configure CSI extraction on router

Replace `44` and `80` with your actual channel and bandwidth:

```bash
ssh admin@192.168.1.1 "
  cd /jffs
  wl -i eth6 up
  ifconfig eth6 up
  PARAMS=\$(./makecsiparams -c 44/80 -C 15 -N 15)
  ./nexutil -Ieth6 -s500 -b -l34 -v \$PARAMS && echo OK
  wl -i eth6 monitor 1
"
```

### makecsiparams flags

| Flag | Value | Meaning |
|------|-------|---------|
| `-c` | `44/80` | Channel 44, 80MHz bandwidth |
| `-C` | `15` (0b1111) | Enable all 4 Rx cores |
| `-N` | `15` (0b1111) | Enable all 4 spatial streams |
| `-m` | *(omit)* | Capture from ALL devices |

> **Important:** Do NOT use `-m ff:ff:ff:ff:ff:ff`. This sets `n_mac_addr=1`
> filtering for broadcast source MAC — no real device uses this. Result: 0 packets.

## Capture on Ubuntu

CSI UDP packets have source MAC `4e:45:58:4d:4f:4e` ("NEXMON" in ASCII).

```bash
# Basic capture
sudo tcpdump -i eno1 -n ether src 4e:45:58:4d:4f:4e \
    -w ~/captures/location_A.pcap

# Or use the collection script (handles setup + capture + summary):
chmod +x scripts/collect_csi.sh
./scripts/collect_csi.sh 44 80 ~/captures/location_A.pcap 30
```

## What to expect

With a phone transmitting on the same channel:
- ~1000+ packets/second
- 4 UDP packets per WiFi frame (one per router antenna)
- Antenna streams: `core=0 ss=0`, `core=0 ss=2`, `core=0 ss=4`, `core=0 ss=6`
- Each packet: 18-byte header + 256×4 = 1024 bytes CSI (80MHz)

## Parse captured data

```bash
cd parsing
pip3 install -r requirements.txt
python3 parse_csi.py ~/captures/location_A.pcap --csv --plot --out output/
```

## Data collection for localization

For fingerprinting-based localization:

1. Mark physical locations (e.g. L1, L2, ... L20) in your environment
2. At each location, run:
```bash
./scripts/collect_csi.sh 44 80 data/location_L1.pcap 30
./scripts/collect_csi.sh 44 80 data/location_L2.pcap 30
# ... repeat for all locations
```
3. Parse all captures to CSV for ML pipeline

## Subcarrier mapping (80MHz, 256 subcarriers)

For 80MHz channel 44, the 256 subcarriers map to:
- Subcarriers 0-5: guard/null (near DC) — typically low amplitude
- Subcarriers 6-250: data subcarriers — use these for localization
- Subcarriers 251-255: guard — typically low amplitude

Filter out guard subcarriers before ML processing.
