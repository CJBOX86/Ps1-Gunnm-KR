"""번역문 전체에서 용어(인물 이름 등)를 일괄 교체한다. 받침이 바뀌면 바로 뒤 조사도 고친다.

사용법:
  python tools/TRANSLATE/rename_term.py <바꿀 말> <새 말>            (미리보기만)
  python tools/TRANSLATE/rename_term.py <바꿀 말> <새 말> --apply    (segments와 glossary.json에 반영)

- 대상: segments/*.json의 모든 ko (상태와 무관), glossary.json의 ko·note
- 조사: 이/가, 을/를, 은/는, 과/와, 으로/로, 이랑/랑, 이나/나, 아/야, 이야/야, 이여/여,
        이라고/라고, 이란/란, 이라/라, 이에요/예요, 이었/였, 이지/지 (ㄹ 받침 + 으로 → 로)
- 대상: glossary.json의 style(말투) 항목 이름·설명도 포함
- 이름이 길어져 줄 너비를 넘으면 그 페이지만 단어 단위로 다시 줄바꿈한다.
  그래도 tr_batch 검사(줄 너비·창 높이)에 걸리는 줄은 목록으로 알려 주고 바꾸지 않는다
"""
import glob
import json
import os
import re
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
import tr_batch as tb  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GLOSSARY = os.path.join(ROOT, "assets", "translation", "glossary.json")

# (받침 있을 때, 받침 없을 때) — 긴 것부터 맞춘다
PARTICLES = [("이라고", "라고"), ("이에요", "예요"), ("이랑", "랑"), ("이나", "나"), ("이야", "야"),
             ("이여", "여"), ("이란", "란"), ("이라", "라"), ("이었", "였"), ("이지", "지"),
             ("으로", "로"), ("이", "가"), ("을", "를"), ("은", "는"), ("과", "와"), ("아", "야")]


def jong(word):
    """마지막 글자의 받침 번호 (0=없음, 8=ㄹ). 한글이 아니면 None."""
    c = word[-1]
    if not ("가" <= c <= "힣"):
        return None
    return (ord(c) - 0xAC00) % 28


def particle_for(word, pair):
    j = jong(word)
    if j is None:
        return None
    has, no = pair
    if has == "으로":
        return "로" if j in (0, 8) else "으로"
    return has if j else no


def replace(text, old, new):
    if old not in text:
        return text
    alts = sorted({p for pair in PARTICLES for p in pair}, key=len, reverse=True)
    pat = re.compile(re.escape(old) + "(" + "|".join(alts) + ")?")

    def sub(m):
        p = m.group(1)
        if not p:
            return new
        end = m.end()
        # 조사 뒤에 한글이 바로 이어지면 단어의 일부일 수 있다 (예: 가자). 「이었」「이지」 등은 뒤에 어미가 붙는다
        if end < len(text) and "가" <= text[end] <= "힣" and p not in ("이었", "였", "이지", "지", "이라", "라"):
            return new + p
        for pair in PARTICLES:
            if p in pair:
                q = particle_for(new, pair)
                return new + (q if q else p)
        return new + p
    return pat.sub(sub, text)


def vis_len(s):
    return len(re.sub(r"\{[^}]*\}", "", s))


def rewrap(ko, width):
    """너비를 넘는 줄이 있는 페이지만 단어 단위로 다시 줄바꿈한다 (줄바꿈 자리의 공백은 원래 띄어쓰기로 본다)."""
    pages = ko.split("{page}")
    out = []
    for pg in pages:
        lines = pg.split("\n")
        if all(vis_len(re.sub(r"\{w[+-]\d\d\}", "", ln)) <= width for ln in lines) or re.search(r"\{w[+-]\d\d\}", pg):
            out.append(pg)
            continue
        words = " ".join(lines).split(" ")
        new, cur = [], ""
        for w in words:
            cand = w if not cur else cur + " " + w
            if vis_len(cand) <= width or not cur:
                cur = cand
            else:
                new.append(cur)
                cur = w
        new.append(cur)
        out.append("\n".join(new))
    return "{page}".join(out)


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    old, new, do = argv[1], argv[2], "--apply" in argv
    segs = tb.load_segments()
    changed, rejected = [], []
    for p, d in segs.items():
        for b in d["blocks"]:
            for x in b["lines"]:
                ko = x.get("ko")
                if not ko or old not in ko:
                    continue
                nk = replace(ko, old, new)
                errs = tb.check_one(x["src"], nk, x["id"])
                if errs:
                    nk2 = rewrap(nk, tb.dt.window_width(tb.dt.normalize_ko(nk)))
                    if not tb.check_one(x["src"], nk2, x["id"]):
                        nk, errs = nk2, []
                if errs:
                    rejected.append((x["id"], nk, errs))
                    continue
                changed.append((x["id"], ko, nk))
                if do:
                    x["ko"] = nk
                    x["_touched"] = True
    for i, (lid, a, b) in enumerate(changed[:15]):
        print(f"{lid}\n  - {a!r}\n  + {b!r}")
    print(f"바꿀 줄 {len(changed)}개 (위에 최대 15개 표시)")
    for lid, nk, errs in rejected:
        print(f"검사 실패로 건너뜀 {lid}: {'; '.join(errs)}\n  {nk!r}")
    if rejected:
        print(f"건너뛴 줄 {len(rejected)}개 — 직접 줄바꿈을 고쳐야 함")
    g = json.load(open(GLOSSARY, encoding="utf-8"))
    gn = 0
    for t in g["terms"]:
        for k in ("ko", "note"):
            if t.get(k) and old in t[k]:
                gn += 1
                if do:
                    t[k] = t[k].replace(old, new)
    style = {}
    for k, v in g.get("style", {}).items():
        nk_, nv = k.replace(old, new), v.replace(old, new)
        if (nk_, nv) != (k, v):
            gn += 1
        style[nk_] = nv
    if do:
        g["style"] = style
    print(f"용어집 항목 {gn}곳")
    if not do:
        print("미리보기입니다. 반영하려면 --apply")
        return 0
    for p, d in segs.items():
        hit = False
        for b in d["blocks"]:
            for x in b["lines"]:
                if x.pop("_touched", False):
                    hit = True
        if hit:
            tb.save_segment(p, d)
    with open(GLOSSARY, "w", encoding="utf-8", newline="\n") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("반영 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
