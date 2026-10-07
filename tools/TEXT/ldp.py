"""맵 스크립트(LDP) 섹션과 대사 블록 읽기·재구성.

LDP 헤더 (sector 0):
  u32 1, u32 nsec, nsec x (u32 start_sector, u32 byte_size)
  각 섹션은 2048 byte 경계에서 시작하고, 파일 크기는 마지막 섹션 끝을 2048로 올림한 값.
  대사 블록은 항상 마지막 섹션이다 (원본 767개 전부).

대사 블록:
  u32 block_size, u32 max_record_len, u16 n, u16 n, n x (u32 offset, u32 len), records
  record = u32 flags(7) + (SJIS ^ 0x8C) + 0A 0A + 00 00, 0 채움으로 4byte 정렬.
게임은 레코드가 든 2048byte sector 하나만 읽어 오므로 (0x80034FEC: offset>>11)
레코드는 섹션 시작 기준 sector 경계에 닿거나 넘으면 안 된다. max_record_len은 스트리밍 슬롯 크기다.
"""
import struct

KEY = 0x8C
SECTOR = 2048


def sections(ldp):
    one, n = struct.unpack_from("<II", ldp, 0)
    if one != 1:
        raise ValueError("LDP 헤더가 아님")
    return [struct.unpack_from("<II", ldp, 8 + 8 * i) for i in range(n)]


def parse_block(blk):
    """블록 bytes -> [(flags, 평문 bytes)]"""
    size, maxlen, n, n2 = struct.unpack_from("<IIHH", blk, 0)
    if n != n2 or size > len(blk):
        raise ValueError("대사 블록 헤더 불일치")
    recs = []
    for i in range(n):
        off, ln = struct.unpack_from("<II", blk, 12 + 8 * i)
        flags = struct.unpack_from("<I", blk, off)[0]
        body = blk[off + 4: off + ln]
        end = 0
        while body[end:end + 2] != b"\x0a\x0a":
            end += 2
        recs.append((flags, bytes(b ^ KEY for b in body[:end])))
    return recs


def build_block(recs):
    """[(flags, 평문 bytes)] -> 블록 bytes. sector 경계를 넘을 레코드는 다음 sector로 민다."""
    n = len(recs)
    head = 12 + 8 * n
    if head > SECTOR:
        raise ValueError(f"레코드 {n}개: 헤더가 첫 sector를 넘음")
    out = bytearray(head)
    pairs = []
    for flags, plain in recs:
        if len(plain) % 2:
            raise ValueError(f"본문 길이가 홀수: {plain!r}")
        rec = struct.pack("<I", flags) + bytes(b ^ KEY for b in plain) + b"\x0a\x0a\0\0"
        rec += b"\0" * (-len(rec) % 4)
        if len(rec) >= SECTOR:
            raise ValueError("레코드가 한 sector에 들어가지 않음")
        off = len(out)
        # 원본 도구는 sector 끝에 딱 맞는 레코드도 다음 sector로 민다
        if off // SECTOR != (off + len(rec)) // SECTOR:
            out += b"\0" * (-off % SECTOR)
            off = len(out)
        pairs.append((off, len(rec)))
        out += rec
    struct.pack_into("<IIHH", out, 0, len(out), max(ln for _, ln in pairs), n, n)
    for i, (off, ln) in enumerate(pairs):
        struct.pack_into("<II", out, 12 + 8 * i, off, ln)
    return bytes(out)


def replace_last_section(ldp, new_sec):
    """마지막 섹션(대사 블록)을 바꾼 LDP를 반환한다. 앞 섹션은 그대로 둔다."""
    secs = sections(ldp)
    start, _ = secs[-1]
    out = bytearray(ldp[: start * SECTOR])
    struct.pack_into("<I", out, 8 + 8 * (len(secs) - 1) + 4, len(new_sec))
    out += new_sec
    out += b"\0" * (-len(out) % SECTOR)
    return bytes(out)
