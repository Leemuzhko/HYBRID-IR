"""Experimental HVB2 bank ABI. Not accepted by the public HYBRID4 patcher.

One shared pair of 61-row controls, OFF plus 1..8 models. Offsets are bank
relative. Immutable for a loaded effect; changing bank means reloading ZDL.
"""
import math
import struct
import zlib

MAGIC = int.from_bytes(b'HVB2', 'little')
HEADER = struct.Struct('<16I')
MAX_BYTES = 32768  # Parser ceiling only, not a hardware allowance.
STABILITY_MARGIN = 2**-20  # Covers float32 interpolation rounding, not gain/headroom.


def stable_denominator(a1, a2):
    """Conservative float32 Jury test for z**2 + a1*z + a2.

    Stable real second-order denominators form a convex region. The margin
    leaves room for the runtime's float32 interpolation between table rows.
    Match C rounding explicitly; this is not an amplitude/overflow guarantee.
    """
    bound = struct.unpack('<f', struct.pack('<f', 1+a2))[0]
    bound = struct.unpack('<f', struct.pack('<f', bound-STABILITY_MARGIN))[0]
    return -1+STABILITY_MARGIN < a2 < 1-STABILITY_MARGIN and abs(a1) < bound


def from_legacy(bank):
    """Migrate current single-table IRB2 without requantizing any coefficients."""
    if len(bank) < 32:
        raise ValueError('Truncated legacy bank')
    h = struct.unpack_from('<IHHHHBBHHHHHII', bank)
    magic, version, size, count, taps, bq, stride, flags, nf, nq, desc, steps, total, _ = h
    if (magic, version, size, stride, flags, desc, steps) != (0x32425249, 1, 32, 8, 1, 48, 61):
        raise ValueError('Unsupported legacy ABI')
    if total != len(bank) or total != 32 + 56*count + 2*nf + 20*nq + 244 + 2440:
        raise ValueError('Expected one shared control-table pair')
    offsets = [64, 64+48*count, 64+56*count]
    offsets += [offsets[-1]+2*nf]
    offsets += [offsets[-1]+20*nq]
    offsets += [offsets[-1]+244]
    offsets += [offsets[-1]+1220]
    body = bank[32:]
    result = HEADER.pack(MAGIC, 2, 64+len(body), zlib.crc32(body), count, taps, bq,
                         *offsets, nf, nq) + body
    validate(result)
    return result


def validate(bank):
    if not 64 <= len(bank) <= MAX_BYTES:
        raise ValueError('Invalid HVB2 length')
    h = HEADER.unpack_from(bank)
    magic, version, total, stamp, count, taps, bq = h[:7]
    if (magic, version, total) != (MAGIC, 2, len(bank)):
        raise ValueError('Invalid HVB2 header')
    if not 2 <= count <= 9 or not 32 <= taps <= 4096 or taps % 4 or not 2 <= bq <= 32:
        raise ValueError('Invalid HVB2 capacities')
    nf, nq = h[14:]
    if nf > 65534 or nf % 2 or not 2 <= nq <= 65535:
        raise ValueError('Invalid HVB2 pools')
    offset = 64
    for actual, length in zip(h[7:14], (48*count, 8*count, 2*nf, 20*nq, 244, 1220, 1220)):
        if actual != offset or actual % 4 or length > total-offset:
            raise ValueError('Invalid HVB2 region')
        offset += length
    if offset != total or zlib.crc32(bank[64:]) != stamp:
        raise ValueError('Invalid HVB2 payload/stamp')
    for i in range(count):
        n, q, flags, fi, qi, *floats = struct.unpack_from('<HBBHH10f', bank, h[7]+48*i)
        if n > taps or (n and (n < 32 or n % 4)) or q < 2 or q > bq or flags:
            raise ValueError('Invalid HVB2 descriptor')
        if fi % 2 or fi+n > nf or qi+q > nq or not all(map(math.isfinite, floats)):
            raise ValueError('Invalid HVB2 descriptor bounds')
        label = bank[h[8]+8*i:h[8]+8*(i+1)]
        if not label[0] or b'\0' not in label or any(c < 32 or c > 126 for c in label.split(b'\0')[0]):
            raise ValueError('Invalid HVB2 label')
    for offset in range(h[10], total, 4):
        if not math.isfinite(struct.unpack_from('<f', bank, offset)[0]):
            raise ValueError('Non-finite HVB2 coefficient')
    for start, rows in ((h[10], nq), (h[12], 122)):
        for offset in range(start, start+20*rows, 20):
            if not stable_denominator(*struct.unpack_from('<2f', bank, offset+12)):
                raise ValueError('Unstable or insufficient-margin HVB2 denominator')
    return dict(bank_bytes=total, entry_count=count, max_fir=taps, max_bq=bq,
                fir_pool_samples=nf, bq_pool_sections=nq, stamp=stamp)


def pack(project):
    from .zoom_bank import pack_bank
    legacy, report = pack_bank(project, binary=True)
    bank = from_legacy(legacy)
    # Legacy estimates describe a different const/state layout. The repacker
    # reports actual ELF sizes; runtime computes state from its own sizeof.
    report.pop('estimated_const_bytes', None)
    report.pop('estimated_state_bytes', None)
    return bank, dict(report, **validate(bank), schema='hybridir-variable-bank/2')
