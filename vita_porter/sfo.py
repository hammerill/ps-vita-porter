"""param.sfo (PSF) reader and writer. The writer exists for test fixtures and mirrors vita-mksfoex's layout:
header, index table, key table (4-byte aligned), data table."""
from __future__ import annotations

import struct

MAGIC = b"\0PSF"
FMT_UTF8S, FMT_UTF8, FMT_INT = 0x0004, 0x0204, 0x0404


def parse(data: bytes) -> dict:
    if data[:4] != MAGIC:
        raise ValueError("not a param.sfo (no \\0PSF magic)")
    _ver, key_start, data_start, count = struct.unpack("<IIII", data[4:20])
    out = {}
    for i in range(count):
        koff, fmt, length, _maxlen, doff = struct.unpack("<HHIII", data[20 + 16 * i:36 + 16 * i])
        k0 = key_start + koff
        key = data[k0:data.index(b"\0", k0)].decode("utf-8", "replace")
        raw = data[data_start + doff:data_start + doff + length]
        if fmt == FMT_INT:
            out[key] = struct.unpack("<I", raw[:4])[0]
        else:
            out[key] = raw.split(b"\0", 1)[0].decode("utf-8", "replace")
    return out


def build(values: dict) -> bytes:
    keys = sorted(values)
    kt = b""
    koffs = []
    for k in keys:
        koffs.append(len(kt))
        kt += k.encode() + b"\0"
    kt += b"\0" * (-len(kt) % 4)
    dt = b""
    idx = b""
    for k, ko in zip(keys, koffs, strict=True):
        v = values[k]
        if isinstance(v, int):
            body, fmt, length, maxlen = struct.pack("<I", v), FMT_INT, 4, 4
        else:
            enc = str(v).encode() + b"\0"
            maxlen = max(len(enc), 8)
            maxlen += -maxlen % 4
            body, fmt, length = enc + b"\0" * (maxlen - len(enc)), FMT_UTF8, len(enc)
        idx += struct.pack("<HHIII", ko, fmt, length, maxlen, len(dt))
        dt += body
    key_start = 20 + len(idx)
    data_start = key_start + len(kt)
    return MAGIC + struct.pack("<IIII", 0x0101, key_start, data_start, len(keys)) + idx + kt + dt
