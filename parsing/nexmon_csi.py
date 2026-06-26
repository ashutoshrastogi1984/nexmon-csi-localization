"""
nexmon_csi.py — CSI parser for bcm4366c0 (ASUS RT-AC86U)
=========================================================
Version      : v3 — correct float format confirmed empirically
               Reference: https://github.com/seemoo-lab/nexmon_csi
Chip         : bcm4366c0  (Merlin 386.14_2, commit a975a10)
Router       : ASUS RT-AC86U

Float format (confirmed for bcm4366c0):
  Official README: "80MHz → 256 times four bytes" = 256 float components
  Each 32-bit word = ONE float component (either I or Q separately)
  Components are interleaved: word[0]=I[0], word[1]=Q[0], word[2]=I[1]...
  So: 256 words → 128 complex CSI values (128 I + 128 Q)

  Per 32-bit word bit layout (bcm4366c0, nman=12, nexp=6):
    bit  31      : sign
    bits 17:12   : exponent (6-bit, 2's complement, clamped ±10)
    bits 11:0    : mantissa (12-bit unsigned)
    value = (-1)^sign × (mant / 2^12) × 2^exp

  Note: Issue #134 proposed a packed I+Q layout but empirical testing
  shows that layout produces near-zero values inconsistent with measured
  RSSI. The interleaved separate-word layout (above) is consistent with
  CSIKit's implementation and produces physically meaningful amplitudes.

Subcarrier counts (official README):
  20MHz → 64 complex values  (128 float words × 4 bytes = 512 bytes)
  40MHz → 128 complex values (256 float words × 4 bytes = 1024 bytes)
  80MHz → 256 complex values (512 float words × 4 bytes = 2048 bytes)
  BUT: our 80MHz captures have 1024-byte payloads → 128 complex values
  This is consistent with the router capturing 20MHz frames inside
  the 80MHz channel (official README FAQ explains this is normal).

Wire layout:
  Ethernet(14) + IP(20) + UDP(8) = 42 bytes before nexmon header
  Nexmon header 18 bytes:
    +00 magic    2B  0x1111
    +02 rssi     1B  signed dBm
    +03 fc       1B  frame control
    +04 src_mac  6B  transmitter WiFi MAC
    +10 seq      2B  802.11 sequence number
    +12 unk      2B  (core/spatial stream packed)
    +14 chanspec 2B  Broadcom chanspec
    +16 csiconf  2B  chip version
  CSI payload at byte 60

CSV output: one row per subcarrier per frame
  frame_idx, timestamp, src_mac, rssi_dbm, seq, n_avg,
  subcarrier, I, Q, amplitude, phase_deg, phase_san_rad

Usage:
  python3 nexmon_csi.py capture.pcap
  python3 nexmon_csi.py capture.pcap --mac 88:a2:9e:5f:7f:9b --csv out.csv
  python3 nexmon_csi.py capture.pcap --list-macs
  python3 nexmon_csi.py capture.pcap --stats
"""

import struct, sys, argparse, csv
import numpy as np
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict, Optional, Tuple

# ══════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════

NEXMON_MAGIC  = 0x1111
ETH_IP_UDP    = 42              # bytes before nexmon header
NEXMON_HDR    = 18              # nexmon header size bytes
CSI_START     = ETH_IP_UDP + NEXMON_HDR   # = 60

# Float format per 32-bit word for bcm4366c0
# sign(1) @ bit31, exp(6) @ bits17:12, mant(12) @ bits11:0
NMAN = 12                       # mantissa bits
NEXP =  6                       # exponent bits
BYTES_PER_FLOAT = 4             # each I or Q = one 32-bit word
BYTES_PER_SUB   = 8             # one complex sub = I word + Q word

# Chanspec bandwidth decode
BW_MASK = 0x3800
BW_MAP  = {0x1000: 20, 0x1800: 40, 0x2000: 80, 0x2800: 160}

# pcap structures
PCAP_GLB      = struct.Struct('<IHHiIII')
PCAP_PKT      = struct.Struct('<IIII')
PCAP_MAGIC_LE = 0xA1B2C3D4
PCAP_MAGIC_NS = 0xA1B23C4D


# ══════════════════════════════════════════════════════════════════════
#  FLOAT UNPACKING — confirmed correct for bcm4366c0
# ══════════════════════════════════════════════════════════════════════

def _unpack_floats(raw: bytes, n_sub: int) -> np.ndarray:
    """
    Decode n_sub complex CSI samples from bcm4366c0 payload.

    Each subcarrier = 8 bytes = two 32-bit words (I word then Q word).
    Per 32-bit word:
      bit 31     : sign
      bits 17:12 : exponent (6-bit 2's complement)
      bits 11:0  : mantissa (12-bit unsigned)
      value = (-1)^sign * (mant/4096) * 2^exp

    This layout is confirmed by:
    1. CSIKit's unpack_float_acphy(nman=12, nexp=6) implementation
    2. Physical sanity: produces amplitudes consistent with measured RSSI
    3. Empirical comparison: packed I+Q layout produces near-zero values

    Returns complex64 array of shape (n_sub,).
    """
    # Read 2*n_sub uint32 words (n_sub I words + n_sub Q words interleaved)
    vals = np.frombuffer(raw[:n_sub * BYTES_PER_SUB], dtype='<u4')

    # Extract fields — keep as uint32 throughout to prevent overflow
    sign = (vals >> np.uint32(31)) & np.uint32(1)
    exp  = ((vals >> np.uint32(NMAN)) & np.uint32((1 << NEXP) - 1)).astype(np.int32)
    mant = (vals & np.uint32((1 << NMAN) - 1)).astype(np.float64)

    # 2's complement decode for 6-bit signed exponent
    exp[exp > 31] -= 64
    exp = np.clip(exp, -10, 10)

    # Reconstruct float values
    f = ((-1.0) ** sign) * (mant / (1 << NMAN)) * (2.0 ** exp)

    # Pair interleaved I and Q into complex values
    # f[0]=I[0], f[1]=Q[0], f[2]=I[1], f[3]=Q[1], ...
    return (f[0::2][:n_sub] + 1j * f[1::2][:n_sub]).astype(np.complex64)


# ══════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ══════════════════════════════════════════════════════════════════════

class RawPacket:
    """One raw nexmon CSI packet from pcap."""
    __slots__ = ('ts', 'rssi', 'fc', 'src_mac', 'seq', 'core_id',
                 'chanspec', 'csiconf', 'n_sub', 'csi')


class CSIFrame:
    """
    One CSI measurement — retransmissions averaged for noise reduction.
    csi shape: (n_sub,) complex64
    """
    __slots__ = ('ts', 'src_mac', 'seq', 'core_id', 'rssi',
                 'chanspec', 'n_sub', 'csi', 'n_avg')

    def bw_mhz(self) -> int:
        return BW_MAP.get(self.chanspec & BW_MASK, 0)

    def channel(self) -> int:
        return self.chanspec & 0xFF

    # ── derived quantities ─────────────────────────────────────────

    def I(self) -> np.ndarray:
        """In-phase component. Shape: (n_sub,) float32."""
        return self.csi.real.astype(np.float32)

    def Q(self) -> np.ndarray:
        """Quadrature component. Shape: (n_sub,) float32."""
        return self.csi.imag.astype(np.float32)

    def amplitude(self) -> np.ndarray:
        """Magnitude |H(f)| = sqrt(I²+Q²). Shape: (n_sub,) float32."""
        return np.abs(self.csi).astype(np.float32)

    def phase_deg(self) -> np.ndarray:
        """Raw phase in degrees [-180, +180]. Shape: (n_sub,) float32."""
        return np.degrees(np.angle(self.csi)).astype(np.float32)

    def phase_sanitized(self) -> np.ndarray:
        """
        Phase unwrapped + linear trend removed.
        Removes hardware CFO/STO artifact common in nexmon captures.
        Shape: (n_sub,) float32, radians.
        """
        raw = np.angle(self.csi).astype(np.float64)
        u   = np.unwrap(raw)
        x   = np.arange(self.n_sub, dtype=np.float64)
        slope, intercept = np.polyfit(x, u, 1)
        return (u - (slope * x + intercept)).astype(np.float32)

    def __repr__(self):
        a = self.amplitude()
        return (f"<CSIFrame mac={self.src_mac} seq={self.seq:#06x} core={self.core_id} "
                f"ch={self.channel()} bw={self.bw_mhz()}MHz "
                f"n_sub={self.n_sub} rssi={self.rssi}dBm "
                f"amp={a.mean():.1f}±{a.std():.1f} n_avg={self.n_avg}>")


# ══════════════════════════════════════════════════════════════════════
#  PARSING
# ══════════════════════════════════════════════════════════════════════

def _parse_raw_packet(raw: bytes, ts: float) -> Optional[RawPacket]:
    """Parse one raw pcap packet. Returns None if not a valid nexmon frame."""
    if len(raw) < CSI_START + BYTES_PER_SUB:
        return None
    if struct.unpack_from('<H', raw, ETH_IP_UDP)[0] != NEXMON_MAGIC:
        return None

    nh = raw[ETH_IP_UDP:]
    p  = RawPacket()
    p.ts       = ts
    rssi_raw   = nh[2]
    p.rssi     = rssi_raw if rssi_raw < 128 else rssi_raw - 256
    p.fc       = nh[3]
    p.src_mac  = nh[4:10].hex(':')
    p.seq      = struct.unpack_from('<H', nh, 10)[0]
    p.core_id  = nh[13]  # top byte of 4-byte seq_ext = core identifier
    p.chanspec = struct.unpack_from('<H', nh, 14)[0]
    p.csiconf  = struct.unpack_from('<H', nh, 16)[0]

    # Infer subcarrier count from payload length
    payload = raw[CSI_START:]
    p.n_sub = len(payload) // BYTES_PER_SUB
    if p.n_sub == 0:
        return None

    p.csi = _unpack_floats(payload, p.n_sub)
    return p


def _group_and_average(packets: List[RawPacket]) -> List[CSIFrame]:
    """
    Group by (src_mac, seq) to keep transmitters separate.
    Average CSI across retransmissions within each group.
    """
    buckets: Dict[Tuple[str, int, int], List[RawPacket]] = defaultdict(list)
    for p in packets:
        buckets[(p.src_mac, p.seq, p.core_id)].append(p)

    frames = []
    for (mac, seq, core_id), pkts in buckets.items():
        csi_avg = np.mean(
            np.stack([p.csi for p in pkts], axis=0), axis=0
        ).astype(np.complex64)

        f          = CSIFrame()
        f.src_mac  = mac
        f.seq      = seq
        f.core_id  = core_id
        f.n_sub    = pkts[0].n_sub
        f.chanspec = pkts[0].chanspec
        f.rssi     = pkts[0].rssi
        f.ts       = pkts[0].ts
        f.csi      = csi_avg
        f.n_avg    = len(pkts)
        frames.append(f)

    frames.sort(key=lambda f: f.ts)
    return frames


def parse_pcap(path: str,
               mac_filter: str = None,
               verbose: bool = True) -> List[CSIFrame]:
    """
    Parse a nexmon_csi pcap file into CSIFrame objects.

    Args:
        path       : path to .pcap file
        mac_filter : if set, keep only frames from this WiFi MAC
        verbose    : print summary to stdout

    Returns:
        List of CSIFrame sorted by timestamp
    """
    packets: List[RawPacket] = []
    total = bad = 0

    with open(path, 'rb') as fh:
        glb_raw = fh.read(PCAP_GLB.size)
        pcap_mg = struct.unpack_from('<I', glb_raw, 0)[0]
        if pcap_mg not in (PCAP_MAGIC_LE, PCAP_MAGIC_NS):
            raise ValueError(
                f"\n  CORRUPTED pcap (magic={pcap_mg:#010x})\n"
                f"  Always transfer with: scp admin@router:/tmp/cap.pcap ./cap.pcap")
        ts_div = 1e9 if pcap_mg == PCAP_MAGIC_NS else 1e6

        while True:
            hdr = fh.read(PCAP_PKT.size)
            if len(hdr) < PCAP_PKT.size:
                break
            ts_sec, ts_frac, incl_len, _ = PCAP_PKT.unpack(hdr)
            raw    = fh.read(incl_len)
            total += 1
            pkt    = _parse_raw_packet(raw, ts_sec + ts_frac / ts_div)
            if pkt is None:
                bad += 1
            else:
                packets.append(pkt)

    frames = _group_and_average(packets)

    if mac_filter:
        frames = [f for f in frames
                  if f.src_mac.lower() == mac_filter.lower()]

    if verbose:
        _print_summary(path, total, bad, packets, frames)

    return frames


def filter_mac(frames: List[CSIFrame], mac: str) -> List[CSIFrame]:
    """Filter frames by transmitter MAC address."""
    return [f for f in frames if f.src_mac.lower() == mac.lower()]


# ══════════════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════════════

def _print_summary(path, total, bad, packets, frames):
    W = 60
    print(f"\n{'═'*W}")
    print(f"  FILE : {Path(path).name}")
    print(f"{'─'*W}")
    print(f"  Raw packets parsed   : {total}")
    print(f"  Valid nexmon packets : {len(packets)}")
    print(f"  Rejected             : {bad}")

    if not frames:
        print("  No CSI frames assembled.")
        print(f"{'═'*W}")
        return

    dur = frames[-1].ts - frames[0].ts
    fps = len(frames) / dur if dur > 0 else 0
    f0  = frames[0]

    print(f"\n  CSI frames total     : {len(frames)}")
    print(f"  Duration             : {dur:.2f} s")
    print(f"  Frame rate           : {fps:.1f} fps")
    print(f"\n  Channel info:")
    print(f"    chanspec           : {f0.chanspec:#06x}")
    print(f"    center channel     : {f0.channel()}")
    print(f"    bandwidth          : {f0.bw_mhz()} MHz")
    print(f"    subcarriers        : {f0.n_sub}")

    mac_counts = Counter(f.src_mac for f in frames)
    print(f"\n  Transmitters (MAC)   :")
    for mac, cnt in mac_counts.most_common(8):
        print(f"    {mac}   {cnt:5d} frames ({cnt/len(frames)*100:.0f}%)")
    if len(mac_counts) > 8:
        print(f"    ... {len(mac_counts)-8} more")

    print(f"\n  RSSI range           : "
          f"{min(f.rssi for f in frames)} to "
          f"{max(f.rssi for f in frames)} dBm")

    sample  = frames[:200]
    all_amp = np.concatenate([f.amplitude() for f in sample])
    flat    = np.mean(all_amp < 0.01) * 100

    print(f"\n  CSI amplitude check  :")
    print(f"    Mean               : {all_amp.mean():.4f}")
    print(f"    Std                : {all_amp.std():.4f}")
    print(f"    Near-zero (<0.01)  : {flat:.1f}%  "
          f"{'⚠' if flat > 20 else '✓'}")
    print(f"    NaN fraction       : {np.mean(np.isnan(all_amp)):.5f}")

    # Subcarrier amplitude profile every 16th
    amp_mean = all_amp.reshape(len(sample), f0.n_sub).mean(axis=0)
    max_amp  = amp_mean.max() if amp_mean.max() > 0 else 1
    print(f"\n  Subcarrier amplitude profile (every 16th):")
    print(f"   {'Sub':>4}   {'Mean':>8}  Bar")
    for i in range(0, f0.n_sub, 16):
        bar = '█' * int(amp_mean[i] / max_amp * 30)
        print(f"   {i:4d}   {amp_mean[i]:8.2f}  {bar}")

    print(f"{'═'*W}\n")


# ══════════════════════════════════════════════════════════════════════
#  CSV EXPORT
# ══════════════════════════════════════════════════════════════════════

def export_csv(frames: List[CSIFrame], out_path: str) -> None:
    """
    Export all CSI data to CSV — one row per subcarrier per frame.

    Columns:
      frame_idx    : frame index (0-based)
      timestamp    : Unix timestamp (seconds)
      src_mac      : transmitter WiFi MAC
      rssi_dbm     : received signal strength in dBm
      seq          : 802.11 sequence number
      n_avg        : number of retransmissions averaged
      subcarrier   : subcarrier index (0-based)
      I            : in-phase component
      Q            : quadrature component
      amplitude    : |H(f)| = sqrt(I²+Q²)
      phase_deg    : raw phase in degrees [-180, +180]
      phase_san_rad: sanitized phase in radians (unwrapped, trend removed)
    """
    if not frames:
        print("  No frames to export.")
        return

    n_sub      = frames[0].n_sub
    total_rows = len(frames) * n_sub
    print(f"\n  Exporting {len(frames)} frames × {n_sub} subcarriers"
          f" = {total_rows:,} rows")
    print(f"  Output: {out_path}")

    with open(out_path, 'w', newline='') as fh:
        writer = csv.writer(fh)
        # Header
        writer.writerow([
            'frame_idx', 'timestamp', 'src_mac', 'rssi_dbm',
            'seq', 'n_avg', 'subcarrier',
            'I', 'Q', 'amplitude', 'phase_deg', 'phase_san_rad'
        ])
        # Data
        for idx, f in enumerate(frames):
            I_arr   = f.I()
            Q_arr   = f.Q()
            amp_arr = f.amplitude()
            ph_arr  = f.phase_deg()
            san_arr = f.phase_sanitized()

            for sub in range(n_sub):
                writer.writerow([
                    idx,
                    f"{f.ts:.6f}",
                    f.src_mac,
                    f.rssi,
                    f.seq,
                    f.n_avg,
                    sub,
                    f"{I_arr[sub]:.6f}",
                    f"{Q_arr[sub]:.6f}",
                    f"{amp_arr[sub]:.6f}",
                    f"{ph_arr[sub]:.4f}",
                    f"{san_arr[sub]:.6f}",
                ])

    print(f"  Done. ✓")


# ══════════════════════════════════════════════════════════════════════
#  STATS PRINTOUT
# ══════════════════════════════════════════════════════════════════════

def print_stats(frames: List[CSIFrame], n_sample: int = 5) -> None:
    """Print amplitude stats and first few frame values."""
    if not frames:
        return
    n_sub   = frames[0].n_sub
    amp_all = np.stack([f.amplitude() for f in frames[:200]])

    print(f"\n{'─'*60}")
    print(f"  AMPLITUDE STATS  ({len(frames)} frames, {n_sub} subcarriers)")
    print(f"{'─'*60}")
    print(f"  Mean: {amp_all.mean():.4f}   Std: {amp_all.std():.4f}   "
          f"Min: {amp_all.min():.4f}   Max: {amp_all.max():.4f}")

    print(f"\n  First {n_sample} frames — subs 0-7  (amplitude):")
    hdr = '  ' + '  '.join(f'sub{i:03d}' for i in range(8))
    print(hdr)
    print('  ' + '─' * (len(hdr)-2))
    for f in frames[:n_sample]:
        a = f.amplitude()
        print('  ' + '  '.join(f'{a[i]:7.2f}' for i in range(min(8, n_sub))))

    print(f"\n  First {n_sample} frames — subs 0-7  (I values):")
    print(hdr)
    print('  ' + '─' * (len(hdr)-2))
    for f in frames[:n_sample]:
        iv = f.I()
        print('  ' + '  '.join(f'{iv[i]:7.2f}' for i in range(min(8, n_sub))))

    print(f"\n  First {n_sample} frames — subs 0-7  (Q values):")
    print(hdr)
    print('  ' + '─' * (len(hdr)-2))
    for f in frames[:n_sample]:
        qv = f.Q()
        print('  ' + '  '.join(f'{qv[i]:7.2f}' for i in range(min(8, n_sub))))
    print(f"{'─'*60}")


# ══════════════════════════════════════════════════════════════════════
#  LIST-MACS
# ══════════════════════════════════════════════════════════════════════

def print_mac_list(frames: List[CSIFrame]) -> None:
    """Print per-MAC statistics table."""
    mac_data: Dict[str, List[CSIFrame]] = defaultdict(list)
    for f in frames:
        mac_data[f.src_mac].append(f)

    print(f"\n{'─'*66}")
    print(f"  {'MAC':<20} {'Frames':>7}  {'fps':>6}  {'RSSI':>6}  {'Subs':>5}")
    print(f"{'─'*66}")
    for mac, flist in sorted(mac_data.items(), key=lambda x: -len(x[1])):
        dur  = flist[-1].ts - flist[0].ts
        fps  = len(flist) / dur if dur > 0 else 0
        rssi = np.mean([f.rssi for f in flist])
        subs = flist[0].n_sub
        print(f"  {mac:<20}  {len(flist):>6}  {fps:>6.1f}  "
              f"{rssi:>6.1f}  {subs:>5}")
    print(f"{'─'*66}")


# ══════════════════════════════════════════════════════════════════════
#  COMMAND LINE
# ══════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description='nexmon_csi v3 parser — bcm4366c0 (ASUS RT-AC86U)')
    ap.add_argument('pcap',
                    help='Input .pcap file')
    ap.add_argument('--mac',
                    help='Filter by transmitter MAC (e.g. 88:a2:9e:5f:7f:9b)')
    ap.add_argument('--csv', metavar='OUT',
                    help='Export CSV with I, Q, amplitude, phase per subcarrier')
    ap.add_argument('--stats',     action='store_true',
                    help='Print detailed amplitude/I/Q statistics')
    ap.add_argument('--list-macs', action='store_true',
                    help='List all transmitter MACs with frame counts')
    args = ap.parse_args()

    frames = parse_pcap(args.pcap,
                        mac_filter=args.mac,
                        verbose=True)

    if args.list_macs:
        print_mac_list(frames)

    if args.stats:
        print_stats(frames)

    if args.csv:
        export_csv(frames, args.csv)
    elif not args.list_macs and not args.stats:
        print("  Tip: add --csv output.csv to export I, Q, amplitude, phase")
        print("       add --stats to see amplitude detail")
        print("       add --list-macs to see all transmitters")


if __name__ == '__main__':
    main()
