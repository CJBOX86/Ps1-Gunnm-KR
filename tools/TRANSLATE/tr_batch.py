"""초벌 번역 작업 묶음 내보내기·가져오기.

사용법:
  python tools/TRANSLATE/tr_batch.py export <장 폰트> <묶음당 줄 수> <출력 폴더>
      예: export K00 300 work/tr  -> work/tr/K00_01.in.json ...
      대상: 블록의 첫 후보 폰트(폰트 표 순서)가 <장 폰트>인 블록의, ref가 없고 아직 미번역인 줄
  python tools/TRANSLATE/tr_batch.py check <*.out.json ...>   (검사만)
  python tools/TRANSLATE/tr_batch.py apply <*.out.json ...>
      out 형식: {"줄 ID": "번역문", ...}
      검사(구조 제어 코드, 25칸 줄 길이, 인코딩 가능 문자)를 통과한 줄만 ko에 넣고 status를 draft로 한다.
      사람이 손댄 줄(status가 review/decision/done)은 덮어쓰지 않는다.
"""
import glob
import json
import os
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
import dialog_text as dt  # noqa: E402
import srctext  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEG = os.path.join(ROOT, "assets", "translation", "segments")
ORDER = ["K00", "K01", "K02", "K03", "K04_0", "K04_1", "K04_2", "K05", "K06", "K07", "K08", "K99"]


def load_segments():
    segs = {}
    for p in sorted(glob.glob(os.path.join(SEG, "*.json"))):
        with open(p, encoding="utf-8") as f:
            segs[p] = json.load(f)
        srctext.attach_blocks(segs[p]["blocks"])   # 원문은 원본 디스크에서 (tools/TEXT/srctext.py)
    return segs


def save_segment(p, d):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(srctext.strip(d), f, ensure_ascii=False, indent=1)
        f.write("\n")


def chapter_of(block):
    c = block["font_candidates"]
    return min(c, key=ORDER.index) if c else None


def export(chapter, size, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    items = []
    for p, d in load_segments().items():
        for b in d["blocks"]:
            if chapter_of(b) != chapter:
                continue
            todo = [x for x in b["lines"] if "ref" not in x and x.get("ko") is None]
            if todo:
                items.append({"block": b["id"],
                              "context_all_src": [x["src"] for x in b["lines"]],
                              "lines": [{"id": x["id"], "src": x["src"]} for x in todo]})
    chunks, cur, n = [], [], 0
    for it in items:
        if cur and n + len(it["lines"]) > size:
            chunks.append(cur)
            cur, n = [], 0
        cur.append(it)
        n += len(it["lines"])
    if cur:
        chunks.append(cur)
    for i, c in enumerate(chunks, 1):
        path = os.path.join(out_dir, f"{chapter}_{i:02d}.in.json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump({"chapter": chapter, "blocks": c}, f, ensure_ascii=False, indent=1)
        print(path, sum(len(it["lines"]) for it in c), "줄")


def check_one(src, ko, lid=""):
    errs = dt.check_translation(src, ko)
    if errs:
        return errs
    norm = dt.normalize_ko(ko)
    try:
        enc = dt.encode(norm, {c: b"\x88\x9f" for c in norm if dt.is_hangul(c)}, b"\x81\xad")
    except ValueError as e:
        return [str(e)]
    # LDP가 아닌 파일(id에 @)은 블록 크기를 늘릴 수 없다
    if "@" in lid and len(enc) > len(dt.encode(src, {})):
        return [f"크기 고정 파일: 번역 {len(enc)}byte > 원문 {len(dt.encode(src, {}))}byte"]
    w = dt.window_width(norm)
    over = [n for n in dt.visual_lines(norm) if n > w]
    if over:
        return [f"줄 길이 {max(over)}칸 > {w}칸"]
    h = dt.window_height(norm)
    if max(dt.page_heights(norm)) > h:
        return [f"한 페이지 {max(dt.page_heights(norm))}줄 > 창 높이 {h}줄 ({{page}}로 나눌 것)"]
    return []


def check_files(paths):
    """반영하지 않고 검사만 한다. in 파일과 짝을 맞춰 빠진 ID도 알려 준다."""
    src = {}
    for p, d in load_segments().items():
        for b in d["blocks"]:
            for x in b["lines"]:
                src[x["id"]] = x["src"]
    bad = 0
    for op in paths:
        with open(op, encoding="utf-8") as f:
            tr = json.load(f)
        inp = op.replace(".out.json", ".in.json")
        if os.path.exists(inp):
            with open(inp, encoding="utf-8") as f:
                want = {ln["id"] for b in json.load(f)["blocks"] for ln in b["lines"]}
            for lid in sorted(want - tr.keys()):
                print(f"빠짐 {lid}")
                bad += 1
        for lid, ko in tr.items():
            errs = ["없는 ID"] if lid not in src else check_one(src[lid], ko, lid)
            if errs:
                print(f"문제 {lid}: {'; '.join(errs)}")
                bad += 1
    print(f"문제 {bad}건")
    return 0 if bad == 0 else 1


def apply(paths):
    segs = load_segments()
    index = {}
    for p, d in segs.items():
        for b in d["blocks"]:
            for x in b["lines"]:
                index[x["id"]] = (p, x)
    ok = bad = skipped = 0
    touched = set()
    for op in paths:
        with open(op, encoding="utf-8") as f:
            tr = json.load(f)
        for lid, ko in tr.items():
            if lid not in index:
                print(f"없는 ID: {lid}")
                bad += 1
                continue
            p, x = index[lid]
            if "ref" in x or x.get("status") in ("review", "decision", "done"):
                skipped += 1
                continue
            errs = check_one(x["src"], ko, lid)
            if errs:
                print(f"거부 {lid}: {'; '.join(errs)}")
                bad += 1
                continue
            x["ko"], x["status"] = ko, "draft"
            touched.add(p)
            ok += 1
    for p in touched:
        save_segment(p, segs[p])
    print(f"반영 {ok}, 거부 {bad}, 건너뜀 {skipped}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    if sys.argv[1] == "export":
        export(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    elif sys.argv[1] == "apply":
        sys.exit(apply(sys.argv[2:]))
    elif sys.argv[1] == "check":
        sys.exit(check_files(sys.argv[2:]))
    else:
        raise SystemExit(__doc__)
