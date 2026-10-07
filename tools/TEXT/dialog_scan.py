"""맵 스크립트(LDP/MP/EDP 등)에 들어 있는 XOR 0x8C 암호화 대사 블록 스캐너 (조사용).

블록 형식 (2026-10-06 MP801_0.LDP와 실행 중 RAM으로 확인):
  u32 block_size        # 이 필드를 포함한 블록 전체 byte 수
  u32 unknown           # 의미 미확인 (MP801: 0x28, MP106_2: 0xd4)
  u16 n, u16 n
  n x (u32 offset, u32 length)   # 첫 offset = 12 + 8*n   # offset은 블록 시작(block_size 필드) 기준
  record = u32 type(디스크에서는 7) + (SJIS ^ 0x8C) + 0a 0a, 4byte 정렬
실행 중에는 표시 직전에 제자리 복호화되고 type이 5로 바뀐다.

사용법:
  python tools/TEXT/dialog_scan.py <extract_dir> <out.jsonl>
"""
import json
import os
import struct
import sys

KEY = 0x8C


def decode(raw):
    body = raw[4:]
    end = body.find(b"\x0a\x0a")
    if end < 0:
        return None
    plain = bytes(b ^ KEY for b in body[:end])
    try:
        return plain.decode("cp932")
    except UnicodeDecodeError:
        return None


def scan(d):
    out = []
    o = 0
    lim = len(d) - 16
    while o < lim:
        size, _, n1, n2 = struct.unpack_from("<IIHH", d, o)
        hdr = 12 + 8 * n1
        if (0 < n1 == n2 < 4096 and hdr < size and o + size <= len(d)
                and struct.unpack_from("<I", d, o + 12)[0] == hdr):
            base = o
            pairs = [struct.unpack_from("<II", d, base + 12 + 8 * i) for i in range(n1)]
            ok = all(hdr <= off and off + ln <= size
                     and struct.unpack_from("<I", d, base + off)[0] in (5, 7)
                     for off, ln in pairs)
            if ok:
                lines = []
                for i, (off, ln) in enumerate(pairs):
                    t = decode(d[base + off: base + off + ln])
                    lines.append({"i": i, "off": base + off, "len": ln, "text": t})
                if all(x["text"] is not None for x in lines):
                    out.append({"block": o, "size": size, "lines": lines})
                    o += size
                    continue
        o += 4
    return out


def main():
    root, dst = sys.argv[1], sys.argv[2]
    n_blocks = n_lines = 0
    with open(dst, "w", encoding="utf-8") as f:
        for dp, _, fs in os.walk(root):
            for fn in sorted(fs):
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, root).replace("\\", "/")
                for b in scan(open(p, "rb").read()):
                    n_blocks += 1
                    for ln in b["lines"]:
                        n_lines += 1
                        f.write(json.dumps({"file": rel, "block": b["block"], **ln},
                                           ensure_ascii=False) + "\n")
    print(f"blocks={n_blocks} lines={n_lines}")


if __name__ == "__main__":
    main()
