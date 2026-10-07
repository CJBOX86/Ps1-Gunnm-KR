"""원본 디스크에서 대사 블록을 추출해 번역 자산(색인 + 조각)을 만들거나 갱신한다.

사용법:
  python tools/TEXT/extract_dialog.py [--check]

출력: assets/translation/index.json, assets/translation/segments/<조각>.json
  - 블록: 내용이 같은 블록은 하나로 묶고 files에 모든 사본을 적는다. ID = 첫 파일 경로(확장자 제외)
          (LDP가 아닌 파일은 "@블록 offset"을 붙인다)
  - 줄:  ID = 블록ID#번호. 원문(src)이 앞서 나온 줄과 같으면 ref로 그 줄을 가리키고 ko를 두지 않는다
  - 기존 조각이 있으면 ko/status/note를 보존한다. 원문이 바뀐 줄은 status를 decision으로 바꾸고 note에 남긴다
--check: 파일을 쓰지 않고 현재 자산이 원본 추출 결과와 일치하는지(모집단·원문) 검사만 한다.
"""
import hashlib
import json
import os
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
import dialog_scan  # noqa: E402
import dialog_text  # noqa: E402
import ldp  # noqa: E402
import srctext  # noqa: E402
import psxdisc  # noqa: E402
import verify_source  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TDIR = os.path.join(ROOT, "assets", "translation")
STATUSES = ("untranslated", "draft", "review", "decision", "done")


FONT_TABLE = 0x8008F350   # 실행 파일의 폰트 이름 표: 16byte x 12, 번호 = 상태+0x20 (로더 0x8002A75C)


def loadable_fonts(disc, ents):
    """게임이 실제로 불러올 수 있는 K 폰트 이름 (K04는 표에 없어 불러올 수 없다)."""
    exe = disc.read_file(ents["/SLPS_014.08;1"])
    t_addr = int.from_bytes(exe[0x18:0x1C], "little")
    o = FONT_TABLE - t_addr + 0x800
    names = []
    for i in range(12):
        s = exe[o + 16 * i: o + 16 * i + 16].split(b"\0")[0].decode("ascii")
        if not s.startswith("\\TIM\\K"):
            raise SystemExit(f"폰트 이름 표 형식 불일치: {s!r}")
        names.append(s[5:])
    return names


def knj_sets(disc, ents):
    out = {}
    usable = set(loadable_fonts(disc, ents))
    for p, e in ents.items():
        if p.startswith("/TIM/K") and p.endswith(".KNJ;1") and p[5:-6] in usable:
            k = disc.read_file(e)
            n = next(i for i in range(0, len(k), 2) if k[i:i + 2] == b"\0\0") // 2  # 0000 종료 앞까지
            out[p[5:-6]] = {bytes([k[2 * i + 1], k[2 * i]]).decode("cp932") for i in range(n)}
    return out


def extract(src_bin):
    disc = psxdisc.Disc(src_bin)
    ents = {e["path"]: e for e in disc.walk()}
    fonts = knj_sets(disc, ents)
    found = {}   # 블록 bytes -> [(파일, offset)]
    for p in sorted(ents):
        e = ents[p]
        if e["interleaved"] or not p.startswith(("/M", "/DATA/STS_")):
            continue
        d = disc.read_file(e)
        if p.endswith(".LDP;1"):
            st, sz = ldp.sections(d)[-1]
            blk = d[st * 2048: st * 2048 + sz]
            try:
                ldp.parse_block(blk)
            except (ValueError, IndexError):
                continue
            found.setdefault(blk, []).append((p, st * 2048))
        else:
            for b in dialog_scan.scan(d):
                found.setdefault(d[b["block"]: b["block"] + b["size"]], []).append((p, b["block"]))
    blocks = []
    for blk, locs in found.items():
        p0, off0 = locs[0]
        bid = p0[1:].rsplit(".", 1)[0] + ("" if p0.endswith(".LDP;1") else f"@{off0:x}")
        lines = []
        for i, (flags, plain) in enumerate(ldp.parse_block(blk)):
            lines.append({"id": f"{bid}#{i}", "flags": flags,
                          "src": dialog_text.to_asset(plain.decode("cp932"))})
        chars = set().union(*(dialog_text.display_chars(x["src"]) for x in lines))
        blocks.append({
            "id": bid,
            "files": [{"path": p, "offset": o} for p, o in locs],
            "sha256": hashlib.sha256(blk).hexdigest(),
            "font_candidates": sorted(k for k, s in fonts.items() if chars <= s),
            "lines": lines,
        })
    blocks.sort(key=lambda b: b["id"])
    first = {}
    for b in blocks:
        for x in b["lines"]:
            if x["src"] in first:
                x["ref"] = first[x["src"]]
            else:
                first[x["src"]] = x["id"]
    return blocks


def segment_of(bid):
    return "-".join(bid.split("@")[0].split("/")[:-1]) or "root"


def population_hash(blocks):
    h = hashlib.sha256()
    for b in blocks:
        for x in b["lines"]:
            h.update(f"{x['id']}\t{x['src']}\n".encode("utf-8"))
    return h.hexdigest()


def load_existing():
    old = {}
    seg_dir = os.path.join(TDIR, "segments")
    if not os.path.isdir(seg_dir):
        return old
    for fn in os.listdir(seg_dir):
        with open(os.path.join(seg_dir, fn), encoding="utf-8") as f:
            for b in json.load(f)["blocks"]:
                for x in b["lines"]:
                    old[x["id"]] = x
    return old


def merge(blocks, old):
    changed = 0
    for b in blocks:
        for x in b["lines"]:
            o = old.get(x["id"])
            if "ref" in x:
                if o and o.get("ko") is not None:   # 참조를 끊고 따로 번역한 줄
                    x.pop("ref")
                else:
                    continue
            x["ko"] = None
            x["status"] = "untranslated"
            x["note"] = ""
            if not o:
                continue
            for k in ("ko", "status", "note"):
                if k in o:
                    x[k] = o[k]
            if "src" in o and o["src"] != x["src"]:   # 원문 없는 자산은 모집단 해시로 변경을 잡는다
                changed += 1
                x["status"] = "decision"
                x["note"] = (x["note"] + "\n" if x["note"] else "") + f"[원문 변경] 이전 원문: {o.get('src')}"
    return changed


def main(argv):
    cfg = verify_source.local_config()
    src_bin = os.path.join(ROOT, cfg["source_bin"])
    if verify_source.main(["", src_bin]) != 0:
        raise SystemExit("원본 불일치")
    blocks = extract(src_bin)
    n_lines = sum(len(b["lines"]) for b in blocks)
    n_own = sum(1 for b in blocks for x in b["lines"] if "ref" not in x)
    pop = population_hash(blocks)
    if "--check" in argv:
        with open(os.path.join(TDIR, "index.json"), encoding="utf-8") as f:
            idx = json.load(f)
        ok = idx["population"]["sha256"] == pop
        print(f"모집단 {'일치' if ok else '불일치'}: 블록 {len(blocks)}, 줄 {n_lines}")
        return 0 if ok else 1
    srctext.save_cache("dialog.json", srctext.dialog_map(blocks))
    changed = merge(blocks, load_existing())
    segs = {}
    for b in blocks:
        segs.setdefault(segment_of(b["id"]), []).append(b)
    os.makedirs(os.path.join(TDIR, "segments"), exist_ok=True)
    for name, bs in segs.items():
        with open(os.path.join(TDIR, "segments", name + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(srctext.strip({"segment": name, "blocks": bs}), f, ensure_ascii=False, indent=1)
            f.write("\n")
    old_scope = None
    if os.path.exists(os.path.join(TDIR, "index.json")):
        with open(os.path.join(TDIR, "index.json"), encoding="utf-8") as f:
            old_scope = json.load(f).get("scope")   # 범위 설명은 사람이 관리하므로 보존
    index = {
        "schema": 1,
        "source_profile": "slps-01408-redump",
        "scope": old_scope or {
            "dialogue": "맵 스크립트 대사 블록 (LDP 마지막 섹션, DATA/STS_*.SPB, 기타 M* 파일의 블록)",
            "survey_complete": False,
            "excluded_pending": ["메뉴·시스템 문자열 (NOR/*.E, 실행 파일)", "Y_MBDATA/MBTEXT.*", "그래픽 텍스트"],
        },
        "population": {"extractor": "tools/TEXT/extract_dialog.py", "blocks": len(blocks), "lines": n_lines,
                       "own_lines": n_own, "sha256": pop},
        "statuses": list(STATUSES),
        "segments": sorted(segs),
        "release_approval": None,
    }
    with open(os.path.join(TDIR, "index.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"블록 {len(blocks)}, 줄 {n_lines} (번역 대상 {n_own}), 조각 {len(segs)}, 원문 변경 {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
