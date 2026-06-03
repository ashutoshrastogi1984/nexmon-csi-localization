"""
unpack_float.py
Python port of nexmon_csi utils/matlab/unpack_float.c
For bcm4366c0: format=1, nman=12, nexp=6, nbits=10
"""
import numpy as np


def unpack_float_acphy(H, nman=12, nexp=6, nbits=10):
    """
    Unpack bcm4366c0 CSI float format.

    Each 32-bit word encodes one complex CSI subcarrier value:
        bits[nexp-1 : 0]              = exponent (signed, nexp bits)
        bits[nexp+nman-1 : nexp]      = imag mantissa (nman-1 bits + sign)
        bits[nexp+2*nman-1 : nexp+nman] = real mantissa (nman-1 bits + sign)

    For bcm4366c0: nman=12, nexp=6
        bits[5:0]   exponent
        bits[17:6]  imag (bit17=sign, bits[16:6]=magnitude)
        bits[29:18] real (bit29=sign, bits[28:18]=magnitude)

    Parameters
    ----------
    H      : array-like of uint32
    nman   : mantissa bits (12 for bcm4366c0)
    nexp   : exponent bits (6 for bcm4366c0)
    nbits  : output normalization bits (10)

    Returns
    -------
    numpy complex128 array of length len(H)
    """
    H = np.asarray(H, dtype=np.uint32)
    nfft = len(H)

    e_p       = 1 << (nexp - 1)
    iq_mask   = (1 << (nman - 1)) - 1
    e_mask    = (1 << nexp) - 1
    sgnr_mask = 1 << (nexp + 2 * nman - 1)
    sgni_mask = sgnr_mask >> nman
    e_zero    = -nman
    SGN_MASK  = 1 << 31

    He     = np.zeros(nfft, dtype=np.int32)
    vi_arr = np.zeros(nfft, dtype=np.int64)
    vq_arr = np.zeros(nfft, dtype=np.int64)

    for i in range(nfft):
        x  = int(H[i])
        vi = (x >> (nexp + nman)) & iq_mask
        vq = (x >> nexp) & iq_mask
        e  = x & e_mask
        if e >= e_p:
            e -= (e_p << 1)
        He[i] = e
        if x & sgnr_mask:
            vi |= SGN_MASK
        if x & sgni_mask:
            vq |= SGN_MASK
        vi_arr[i] = vi
        vq_arr[i] = vq

    maxbit = -e_p   # autoscale=0, so maxbit stays at initial value
    shft   = nbits - maxbit

    result = np.zeros(nfft, dtype=np.complex128)
    for i in range(nfft):
        e = int(He[i]) + shft
        for is_imag, v in enumerate([int(vi_arr[i]), int(vq_arr[i])]):
            sgn = -1 if (v & SGN_MASK) else 1
            v  &= ~SGN_MASK
            if e < e_zero:
                v = 0
            elif e < 0:
                v = v >> (-e)
            else:
                v = v << e
            if is_imag == 0:
                result[i] = sgn * v
            else:
                result[i] += 1j * sgn * v
    return result


def parse_packet_header(payload):
    """
    Parse nexmon CSI UDP packet header (post-PR#256 / commit 13f87d2).

    Header layout:
        0-1   : magic (0x1111)
        2-7   : source MAC
        8-9   : sequence number
        10-11 : core_ss  (core=bits[2:0], ss=bits[5:3])
        12-13 : chanspec (may be 0 in some builds)
        14-15 : chip version / actual chanspec
        16-17 : padding
        18+   : CSI data (uint32 array)

    Returns dict or None if not a valid CSI packet.
    """
    import struct
    if len(payload) < 18:
        return None
    magic = struct.unpack_from('<H', payload, 0)[0]
    if magic != 0x1111:
        return None
    src_mac  = ':'.join(f'{b:02x}' for b in payload[2:8])
    seq_num  = struct.unpack_from('<H', payload, 8)[0]
    core_ss  = struct.unpack_from('<H', payload, 10)[0]
    chanspec = struct.unpack_from('<H', payload, 14)[0]   # offset 14, not 12
    chip_ver = struct.unpack_from('<H', payload, 14)[0]
    core     = core_ss & 0x07
    ss       = (core_ss >> 3) & 0x07
    csi_raw  = np.frombuffer(payload[18:], dtype='<u4')
    return {
        'src_mac' : src_mac,
        'seq_num' : seq_num,
        'core'    : core,
        'ss'      : ss,
        'chanspec': chanspec,
        'csi_raw' : csi_raw,
    }
