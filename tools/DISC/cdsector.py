"""CD-ROM Mode 2 Form 1 sector EDC/ECC 계산.

EDC: CRC32 (다항식 0xD8018001, 반사, 초기값 0), subheader+data(16..2071) 대상, 2072에 LE 저장.
ECC: RS P(86x24)/Q(52x43), header(12..15)를 0으로 둔 상태로 12..2247 대상.
"""

SECTOR = 2352

_EDC = []
for _i in range(256):
    _e = _i
    for _ in range(8):
        _e = (_e >> 1) ^ (0xD8018001 if _e & 1 else 0)
    _EDC.append(_e)

_F = [0] * 256
_B = [0] * 256
for _i in range(256):
    _j = (_i << 1) ^ (0x11D if _i & 0x80 else 0)
    _F[_i] = _j & 0xFF
    _B[_i ^ _F[_i]] = _i


def edc(data):
    e = 0
    for b in data:
        e = _EDC[(e ^ b) & 0xFF] ^ (e >> 8)
    return e


def _ecc_block(buf, major_count, minor_count, major_mult, minor_inc, dest):
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = buf[index]
            index += minor_inc
            if index >= size:
                index -= size
            a ^= t
            b ^= t
            a = _F[a]
        a = _B[_F[a] ^ b]
        buf[dest + major] = a
        buf[dest + major + major_count] = a ^ b


def fix_form1(sector):
    """Mode 2 Form 1 sector의 EDC와 ECC를 다시 계산한 bytearray를 반환한다."""
    s = bytearray(sector)
    if s[15] != 2 or s[18] & 0x20:
        raise ValueError("Mode 2 Form 1 sector가 아님")
    e = edc(s[16:2072])
    s[2072:2076] = e.to_bytes(4, "little")
    # ECC는 header를 0으로 둔 12..2247 영역으로 계산한다 (Mode 2 규칙)
    buf = bytearray(4) + s[16:2076] + bytearray(276)
    _ecc_block(buf, 86, 24, 2, 86, 2064)   # P -> buf[2064:2236]
    _ecc_block(buf, 52, 43, 86, 88, 2236)  # Q -> buf[2236:2340]
    s[2076:2352] = buf[2064:2340]
    return s
