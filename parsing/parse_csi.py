"""
parse_csi.py — Nexmon CSI parser for bcm4366c0 (RT-AC86U)

Usage:
    python3 parse_csi.py capture.pcap [--csv] [--plot] [--max-frames N]

Outputs:
    - Per-antenna amplitude/phase statistics
    - Optional CSV files per antenna
    - Optional histogram + subcarrier profile plots
"""

import argparse
import csv
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    from scapy.all import rdpcap, UDP
except ImportError:
    print("ERROR: scapy not installed. Run: pip3 install scapy numpy matplotlib")
    sys.exit(1)

from unpack_float import unpack_float_acphy, parse_packet_header

# Antenna label — core_ss value to human-readable name
# With -C 15 -N 15, 4 antennas appear as ss=0,2,4,6 (core always 0)
ANT_LABEL = {
    (0, 0): 'Ant0',
    (0, 2): 'Ant1',
    (0, 4): 'Ant2',
    (0, 6): 'Ant3',
}


def parse_pcap(pcap_file, max_frames=None):
    """
    Parse a nexmon CSI pcap file.

    Returns
    -------
    dict: {(core, ss): list of complex numpy arrays}
    """
    packets = rdpcap(str(pcap_file))
    csi_by_antenna = defaultdict(list)
    count = 0

    for pkt in packets:
        if UDP not in pkt or pkt[UDP].dport != 5500:
            continue
        hdr = parse_packet_header(bytes(pkt[UDP].payload))
        if hdr is None:
            continue
        csi = unpack_float_acphy(hdr['csi_raw'])
        csi_by_antenna[(hdr['core'], hdr['ss'])].append(csi)
        count += 1
        if max_frames and count >= max_frames:
            break

    return dict(csi_by_antenna)


def print_stats(csi_by_antenna):
    print(f"\n{'='*60}")
    print(f"  CSI Summary — {sum(len(v) for v in csi_by_antenna.values())} total packets")
    print(f"{'='*60}")
    for (core, ss), frames in sorted(csi_by_antenna.items()):
        arr   = np.array(frames, dtype=np.complex128)
        amp   = np.abs(arr)
        phase = np.angle(arr)
        T, S  = arr.shape
        label = ANT_LABEL.get((core, ss), f'Core{core}_SS{ss}')
        print(f"\n  {label} (core={core}, ss={ss})")
        print(f"    Frames      : {T}")
        print(f"    Subcarriers : {S}")
        print(f"    Amplitude   : mean={amp.mean():.2f}  std={amp.std():.2f}  "
              f"min={amp.min():.2f}  max={amp.max():.2f}")
        print(f"    Phase (rad) : mean={phase.mean():.4f}  std={phase.std():.4f}")


def save_csv(csi_by_antenna, out_dir, max_rows=5000):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for (core, ss), frames in sorted(csi_by_antenna.items()):
        label = ANT_LABEL.get((core, ss), f'Core{core}_SS{ss}')
        arr   = np.array(frames, dtype=np.complex128)
        amp   = np.abs(arr)
        phase = np.angle(arr)
        T, S  = arr.shape
        path  = out_dir / f"csi_{label}.csv"
        with open(path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(
                ['frame'] +
                [f'amp_sub{i}'   for i in range(S)] +
                [f'phase_sub{i}' for i in range(S)]
            )
            for t in range(min(T, max_rows)):
                w.writerow([t] + amp[t].tolist() + phase[t].tolist())
        print(f"  CSV saved: {path}")


def save_plots(csi_by_antenna, out_dir):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed, skipping plots.")
        return

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_ant = len(csi_by_antenna)

    # ---- Subcarrier amplitude profile (all antennas) ----
    fig, axes = plt.subplots(n_ant, 1, figsize=(14, 4 * n_ant), sharex=True)
    if n_ant == 1:
        axes = [axes]
    fig.suptitle("Mean Amplitude per Subcarrier — All Antennas", fontsize=13)

    for ax, ((core, ss), frames) in zip(axes, sorted(csi_by_antenna.items())):
        arr = np.array(frames, dtype=np.complex128)
        amp = np.abs(arr)
        T, S = arr.shape
        label = ANT_LABEL.get((core, ss), f'Core{core}_SS{ss}')
        ax.plot(amp.mean(axis=0), lw=0.9, label=label)
        ax.fill_between(range(S),
                        amp.mean(axis=0) - amp.std(axis=0),
                        amp.mean(axis=0) + amp.std(axis=0),
                        alpha=0.25, label='±1 std')
        ax.set_ylabel("Amplitude")
        ax.set_title(f"{label} — {T} frames × {S} subcarriers")
        ax.legend(loc='upper right', fontsize=8)
    axes[-1].set_xlabel("Subcarrier Index")
    plt.tight_layout()
    p = out_dir / "csi_subcarrier_all.png"
    plt.savefig(p, dpi=150)
    plt.close()
    print(f"  Plot saved: {p}")

    # ---- Amplitude & phase histograms ----
    fig2, axes2 = plt.subplots(2, n_ant, figsize=(5 * n_ant, 8))
    if n_ant == 1:
        axes2 = axes2.reshape(2, 1)
    fig2.suptitle("Amplitude & Phase Histograms — All Antennas", fontsize=13)

    for idx, ((core, ss), frames) in enumerate(sorted(csi_by_antenna.items())):
        arr   = np.array(frames, dtype=np.complex128)
        amp   = np.abs(arr)
        phase = np.angle(arr)
        label = ANT_LABEL.get((core, ss), f'Core{core}_SS{ss}')
        axes2[0][idx].hist(amp.flatten(),   bins=80, color='steelblue', edgecolor='none', alpha=0.85)
        axes2[0][idx].set_title(f"{label}\nAmplitude")
        axes2[0][idx].set_xlabel("Amplitude")
        axes2[1][idx].hist(phase.flatten(), bins=80, color='seagreen',  edgecolor='none', alpha=0.85)
        axes2[1][idx].set_title(f"{label}\nPhase")
        axes2[1][idx].set_xlabel("Phase (rad)")
    axes2[0][0].set_ylabel("Count")
    axes2[1][0].set_ylabel("Count")
    plt.tight_layout()
    p2 = out_dir / "csi_histograms.png"
    plt.savefig(p2, dpi=150)
    plt.close()
    print(f"  Plot saved: {p2}")


def main():
    parser = argparse.ArgumentParser(description="Nexmon CSI parser for bcm4366c0")
    parser.add_argument("pcap",        help="Input .pcap file")
    parser.add_argument("--csv",       action="store_true", help="Save per-antenna CSV files")
    parser.add_argument("--plot",      action="store_true", help="Save amplitude/phase plots")
    parser.add_argument("--out",       default="output",    help="Output directory (default: output/)")
    parser.add_argument("--max-frames",type=int, default=None, help="Max frames to parse")
    args = parser.parse_args()

    print(f"Parsing: {args.pcap}")
    csi = parse_pcap(args.pcap, max_frames=args.max_frames)

    if not csi:
        print("No CSI packets found. Check the pcap file.")
        sys.exit(1)

    print_stats(csi)

    if args.csv:
        print("\nSaving CSVs...")
        save_csv(csi, args.out)

    if args.plot:
        print("\nSaving plots...")
        save_plots(csi, args.out)


if __name__ == "__main__":
    main()
