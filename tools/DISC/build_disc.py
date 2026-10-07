"""파일 교체 목록으로 패치 이미지와 xdelta 패치를 만든다.

사용법:
  python tools/DISC/build_disc.py <manifest.json> <out_dir>

manifest.json:
  {"name": "출력 이름", "replace": {"/TIM/K00.TIM;1": "교체 파일 경로", ...}}
  교체 파일 경로는 manifest 위치 기준.

배치:
  - 새 파일이 원래 할당 sector 수 안에 들어가면 제자리에 쓰고 디렉터리 레코드의 크기만 고친다.
  - 넘치면 원본 데이터 끝(postgap 앞)으로 옮기고 디렉터리 레코드의 LBA·크기를 고친다.
    게임은 ISO 디렉터리에서 이름으로 파일을 찾는다 (실행 파일의 "%s.LDP;1", "dir was not found").
  - postgap(빈 Form 2 sector 150개)은 옮긴 파일 뒤에 다시 붙이고 PVD 볼륨 크기를 갱신한다.

검증 (실패하면 산출물을 남기지 않는다):
  - 원본 bin이 config/source.json의 지원 원본과 일치
  - 교체 대상은 cooked(Form 1) 파일
  - 대상 sector의 원본 EDC/ECC 재계산이 원본과 일치 (sector 계산기 자가 검증)
  - 원본 데이터 영역에서 변경 sector가 쓰기 계획 안에만 있음
  - 출력 이미지를 다시 읽어 교체 파일은 새 내용, 나머지 파일은 원본과 같은 LBA·내용
  - xdelta3로 원본에 패치를 적용한 결과가 출력과 같은 SHA-256
"""
import hashlib
import json
import os
import struct
import subprocess
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
import cdsector  # noqa: E402
import psxdisc  # noqa: E402
import verify_source  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECTOR = cdsector.SECTOR
POSTGAP = 150


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def bcd(v):
    return (v // 10) << 4 | v % 10


def set_address(s, lba):
    a = lba + 150
    s[12:15] = bytes([bcd(a // 4500), bcd(a // 75 % 60), bcd(a % 75)])


def dir_records(disc):
    """{경로: (디렉터리 sector LBA, sector 안 offset)}"""
    out = {}

    def walk(lba, size, path):
        for i in range((size + 2047) // 2048):
            d, _ = disc.user(lba + i)
            o = 0
            while o < 2048 and d[o]:
                rec = d[o: o + d[o]]
                nl = rec[32]
                name = rec[33: 33 + nl]
                if name not in (b"\0", b"\1"):
                    full = path + "/" + name.decode("ascii")
                    elba, esz = struct.unpack_from("<I", rec, 2)[0], struct.unpack_from("<I", rec, 10)[0]
                    if rec[25] & 2:
                        walk(elba, esz, full)
                    else:
                        out[full] = (lba + i, o)
                o += d[o]

    pvd, _ = disc.user(16)
    root = pvd[156:190]
    walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")
    return out


def file_sector(template, lba, data):
    s = bytearray(template)
    set_address(s, lba)
    s[24:24 + 2048] = data.ljust(2048, b"\0")
    return bytes(cdsector.fix_form1(s))


def plan(src_bin, replace):
    disc = psxdisc.Disc(src_bin)
    ents = {e["path"]: e for e in disc.walk()}
    recs = dir_records(disc)
    data_end = disc.sectors - POSTGAP
    for k in range(data_end, disc.sectors):
        if disc.raw(k)[18] & 0x20 == 0:
            raise SystemExit(f"LBA {k}: postgap이 아님")
    writes, owner = {}, {}
    dir_edit = {}            # 디렉터리 sector LBA -> bytearray(raw)
    appended = []            # 원본 데이터 끝 뒤에 붙일 sector
    layout = {}

    def own(lba, who):
        if lba in owner:
            raise SystemExit(f"LBA {lba} 중복 소유: {owner[lba]}, {who}")
        owner[lba] = who

    for iso_path, new in replace.items():
        e = ents.get(iso_path)
        if e is None:
            raise SystemExit(f"디스크에 없는 경로: {iso_path}")
        if e["interleaved"]:
            raise SystemExit(f"인터리브 파일은 교체 대상이 아님: {iso_path}")
        old_n = (e["size"] + 2047) // 2048
        new_n = (len(new) + 2047) // 2048
        first, last = disc.raw(e["lba"]), disc.raw(e["lba"] + old_n - 1)
        for i in range(old_n):
            raw = disc.raw(e["lba"] + i)
            if bytes(cdsector.fix_form1(raw)) != raw:
                raise SystemExit(f"LBA {e['lba'] + i}: 원본 EDC/ECC 재계산 불일치")
        if new_n <= old_n:
            lba = e["lba"]
            for i in range(old_n):
                chunk = new[i * 2048:(i + 1) * 2048]
                raw = disc.raw(lba + i)
                if i < new_n:
                    t = bytearray(raw)
                    t[24:24 + len(chunk)] = chunk  # 파일 끝 뒤 byte는 원본 유지
                    if i == new_n - 1:
                        t[16:24] = last[16:24]     # EOF 표시 subheader
                    s = bytes(cdsector.fix_form1(t))
                else:
                    s = raw  # 남는 sector는 그대로 둔다
                if s != raw:
                    own(lba + i, iso_path)
                    writes[lba + i] = s
        else:
            lba = data_end + len(appended)
            for i in range(new_n):
                tmpl = last if i == new_n - 1 else first
                appended.append(file_sector(tmpl, lba + i, new[i * 2048:(i + 1) * 2048]))
        layout[iso_path] = (lba, len(new))
        if (lba, len(new)) != (e["lba"], e["size"]):
            dlba, off = recs[iso_path]
            s = dir_edit.setdefault(dlba, bytearray(disc.raw(dlba)))
            r = 24 + off
            s[r + 2:r + 10] = struct.pack("<I", lba) + struct.pack(">I", lba)
            s[r + 10:r + 18] = struct.pack("<I", len(new)) + struct.pack(">I", len(new))
    total = data_end + len(appended) + POSTGAP
    if total != disc.sectors:
        s = dir_edit.setdefault(16, bytearray(disc.raw(16)))
        s[24 + 80:24 + 88] = struct.pack("<I", total) + struct.pack(">I", total)
    for dlba, s in dir_edit.items():
        own(dlba, "ISO 디렉터리/PVD")
        writes[dlba] = bytes(cdsector.fix_form1(s))
    postgap = []
    for k in range(POSTGAP):
        s = bytearray(disc.raw(data_end + k))
        set_address(s, data_end + len(appended) + k)
        if s[2348:2352] != b"\0\0\0\0":
            s[2348:2352] = cdsector.edc(s[16:2348]).to_bytes(4, "little")
        postgap.append(bytes(s))
    return writes, owner, appended, postgap, layout, data_end


def verify_output(src_bin, out_bin, replace, layout):
    a, b = psxdisc.Disc(src_bin), psxdisc.Disc(out_bin)
    ea = {e["path"]: e for e in a.walk()}
    eb = {e["path"]: e for e in b.walk()}
    if ea.keys() != eb.keys():
        raise SystemExit("출력 디렉터리의 파일 목록이 원본과 다름")
    for p, e in eb.items():
        if p in replace:
            if (e["lba"], e["size"]) != layout[p] or b.read_file(e) != replace[p]:
                raise SystemExit(f"교체 파일 확인 실패: {p}")
        elif e["interleaved"]:
            if (e["lba"], e["size"]) != (ea[p]["lba"], ea[p]["size"]):
                raise SystemExit(f"인터리브 파일 위치 변경: {p}")
        elif (e["lba"], e["size"]) != (ea[p]["lba"], ea[p]["size"]) or b.read_file(e) != a.read_file(ea[p]):
            raise SystemExit(f"교체하지 않은 파일이 바뀜: {p}")


def main(argv):
    manifest_path, out_dir = argv[1], argv[2]
    with open(manifest_path, encoding="utf-8") as f:
        man = json.load(f)
    base = os.path.dirname(os.path.abspath(manifest_path))
    cfg = verify_source.local_config()
    src_bin = os.path.join(ROOT, cfg["source_bin"])
    if verify_source.main(["", src_bin]) != 0:
        raise SystemExit("원본 불일치")
    replace = {}
    for iso_path, p in man["replace"].items():
        with open(os.path.join(base, p), "rb") as f:
            replace[iso_path] = f.read()
    writes, owner, appended, postgap, layout, data_end = plan(src_bin, replace)
    print(f"쓰기 계획: 제자리 sector {len(writes)}개, 추가 sector {len(appended)}개")
    for lba in sorted(writes):
        print(f"  LBA {lba:6d}  {owner[lba]}")
    for p, (lba, size) in layout.items():
        print(f"  배치 {p}: LBA {lba}, {size} byte")

    os.makedirs(out_dir, exist_ok=True)
    name = man["name"]
    tmp = os.path.join(out_dir, name + ".bin.tmp")
    out_bin = os.path.join(out_dir, name + ".bin")
    try:
        with open(src_bin, "rb") as a, open(tmp, "wb") as b:
            for lba in range(0, data_end, 512):
                chunk = bytearray(a.read(SECTOR * min(512, data_end - lba)))
                for k in range(len(chunk) // SECTOR):
                    s = writes.get(lba + k)
                    if s is not None:
                        chunk[k * SECTOR:(k + 1) * SECTOR] = s
                b.write(chunk)
            for s in appended + postgap:
                b.write(s)
        # 원본 데이터 영역: 계획 밖 변경 금지
        with open(src_bin, "rb") as a, open(tmp, "rb") as b:
            for lba in range(data_end):
                if a.read(SECTOR) != b.read(SECTOR) and lba not in writes:
                    raise SystemExit(f"계획 밖 변경: LBA {lba}")
        verify_output(src_bin, tmp, replace, layout)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    os.replace(tmp, out_bin)
    with open(os.path.join(out_dir, name + ".cue"), "w", encoding="ascii") as f:
        f.write(f'FILE "{name}.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')

    xd = man.get("xdelta3") or cfg.get("xdelta3")
    if xd:
        xd = os.path.join(ROOT, xd)   # config/local.json의 상대경로는 저장소 최상위 기준
        patch = os.path.join(out_dir, name + ".xdelta")
        if os.path.exists(patch):
            os.remove(patch)
        subprocess.run([xd, "-e", "-9", "-s", src_bin, out_bin, patch], check=True)
        check = out_bin + ".check"
        subprocess.run([xd, "-d", "-f", "-s", src_bin, patch, check], check=True)
        ok = sha256(check) == sha256(out_bin)
        os.remove(check)
        if not ok:
            raise SystemExit("xdelta 적용 결과가 출력과 다름")
        print(f"xdelta: {patch} ({os.path.getsize(patch)} bytes), 적용 검증 일치")
    print(json.dumps({"bin": out_bin, "sha256": sha256(out_bin)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
