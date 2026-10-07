"""원문(일본어)과 번역문을 나란히 보거나 검색한다 — 재번역·검수용.

저장소 번역 파일에는 원문이 없으므로 원본 디스크에서 추출한 원문(work/src/)을 붙여 보여 준다.

사용법:
  python tools/TRANSLATE/tr_view.py M3/O/MP801_0          블록(장면) 하나의 모든 줄
  python tools/TRANSLATE/tr_view.py --find 이드            번역문에서 검색
  python tools/TRANSLATE/tr_view.py --find-src イド        원문에서 검색
  python tools/TRANSLATE/tr_view.py --menu NOR/SHOP.E      메뉴 파일 하나
  ... > work/review.txt                        파일로 저장해 편집기에서 보기

고칠 때: assets/translation/segments/<조각>.json에서 해당 줄 id의 "ko"를 고치고
"status"를 review(검수 필요) 또는 done(완료)으로 바꾼 뒤 python tools/BUILD/build_patch.py
"""
import glob
import json
import os
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
import srctext  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TDIR = os.path.join(ROOT, "assets", "translation")


def show(x, ref_ko=None):
    ko = x.get("ko") if "ref" not in x else f"(같은 원문 → {x['ref']}) {ref_ko or ''}"
    print(f"[{x['id']}] {x.get('status', '')}")
    print("  원문:", x["src"].replace("\n", "\n        "))
    print("  번역:", (ko or "").replace("\n", "\n        "))
    print()


def main(argv):
    args = argv[1:]
    if not args:
        raise SystemExit(__doc__)
    if args[0] == "--menu":
        src = srctext.menu_src()
        for fn in sorted(glob.glob(os.path.join(TDIR, "menu", "*.json"))):
            j = json.load(open(fn, encoding="utf-8"))
            if args[1].replace("/", "_") not in os.path.basename(fn):
                continue
            for x in j["strings"]:
                x["src"] = src[x["id"]]
                show(x)
        return 0
    lines = {}
    for fn in sorted(glob.glob(os.path.join(TDIR, "segments", "*.json"))):
        for b in json.load(open(fn, encoding="utf-8"))["blocks"]:
            srctext.attach_lines(b["lines"], srctext.dialog_src())
            for x in b["lines"]:
                lines[x["id"]] = (b["id"], os.path.basename(fn), x)
    hits = []
    if args[0] == "--find":
        hits = [v for v in lines.values() if args[1] in (v[2].get("ko") or "")]
    elif args[0] == "--find-src":
        hits = [v for v in lines.values() if args[1] in v[2]["src"]]
    else:
        hits = [v for v in lines.values() if v[0] == args[0]]
    last = None
    for bid, fn, x in hits:
        if bid != last:
            print(f"=== {bid}  ({fn})")
            last = bid
        show(x, lines.get(x.get("ref"), (0, 0, {}))[2].get("ko"))
    print(f"{len(hits)}줄")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
