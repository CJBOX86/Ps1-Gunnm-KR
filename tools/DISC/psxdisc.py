"""PS1 Mode 2/2352 단일 트랙 이미지의 ISO 9660 읽기 도구 (조사용).

사용법:
  python tools/DISC/psxdisc.py list    <image.bin> [--json out.json]
  python tools/DISC/psxdisc.py extract <image.bin> <out_dir> [경로 필터...]
"""
import json
import os
import struct
import sys

SECTOR = 2352


class Disc:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.sectors = os.path.getsize(path) // SECTOR

    def raw(self, lba):
        self.f.seek(lba * SECTOR)
        return self.f.read(SECTOR)

    def user(self, lba):
        """sector의 사용자 데이터. subheader의 form 비트에 따라 2048/2324 byte."""
        r = self.raw(lba)
        if r[15] != 2:
            raise ValueError(f"LBA {lba}: mode {r[15]} (Mode 2 아님)")
        form2 = r[18] & 0x20
        return r[24 : 24 + (2324 if form2 else 2048)], r[16:24]

    def walk(self):
        pvd, _ = self.user(16)
        if pvd[1:6] != b"CD001":
            raise ValueError("PVD 없음")
        root = pvd[156:190]
        out = []
        self._dir(struct.unpack("<I", root[2:6])[0], struct.unpack("<I", root[10:14])[0], "", out)
        return out

    def _dir(self, lba, size, path, out):
        for i in range((size + 2047) // 2048):
            d, _ = self.user(lba + i)
            o = 0
            while o < 2048 and d[o]:
                rec = d[o : o + d[o]]
                o += d[o]
                nl = rec[32]
                name = rec[33 : 33 + nl]
                if name in (b"\0", b"\1"):
                    continue
                elba = struct.unpack("<I", rec[2:6])[0]
                esz = struct.unpack("<I", rec[10:14])[0]
                su = rec[33 + nl + (0 if nl % 2 else 1) :]
                xa = struct.unpack(">H", su[4:6])[0] if len(su) >= 14 and su[6:8] == b"XA" else None
                full = path + "/" + name.decode("ascii")
                if rec[25] & 2:
                    self._dir(elba, esz, full, out)
                else:
                    out.append({"path": full, "lba": elba, "size": esz, "xa_attr": xa,
                                "interleaved": bool(xa is not None and xa & 0x2000)})

    def read_file(self, ent):
        if ent["interleaved"]:
            raise ValueError("XA/STR 인터리브 파일은 cooked 추출 대상이 아님")
        buf = bytearray()
        lba = ent["lba"]
        while len(buf) < ent["size"]:
            d, _ = self.user(lba)
            buf += d[:2048]
            lba += 1
        return bytes(buf[: ent["size"]])


def main(argv):
    cmd, img = argv[1], argv[2]
    disc = Disc(img)
    ents = disc.walk()
    if cmd == "list":
        if "--json" in argv:
            with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as f:
                json.dump(ents, f, indent=1)
        for e in sorted(ents, key=lambda e: e["lba"]):
            print(f'{e["lba"]:7d} {e["size"]:10d} {"I" if e["interleaved"] else " "} {e["path"]}')
    elif cmd == "extract":
        out, filt = argv[3], argv[4:]
        for e in ents:
            if e["interleaved"] or (filt and not any(x in e["path"] for x in filt)):
                continue
            p = os.path.join(out, e["path"].lstrip("/").split(";")[0])
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(disc.read_file(e))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
