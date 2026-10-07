"""디스크 안의 이미지(TIM)를 PNG로 뽑는다 — HD 리텍스처 작업용 참고 자료.

사용법:
  python tools/GRAPHICS/extract_textures.py [출력 폴더] [--patched]
    기본 출력: ../texture-extract (저장소 밖)
    --patched: 원본 대신 work/out/gunnm-kr-dev.bin(한글 패치 빌드)에서 뽑는다

출력 구조 (디스크 폴더 구조를 따름):
  <폴더>/<파일>.png                단독 TIM (4/8/16bpp, 팔레트 적용, 투명색 = 알파 0)
  <폴더>/<파일>_<offset>.png       BIN 등 묶음 파일 안의 TIM
  <폴더>/<이름>.TM1/pal00.png ...  TM1 텍스처 페이지(4bpp)를 같은 이름 CL1의 팔레트 16개로 각각 칠한 것
                                   + index.png (팔레트 번호 없이 색 번호만 회색조)
  manifest.csv                     파일, 위치, 크기, 형식, VRAM 좌표

주의: 맵 배경·3D 모델 텍스처 상당수는 LDP/MP/MDL 안에 별도 형식으로 있어 여기서 뽑히지 않는다.
      실제 HD 교체 모드는 DuckStation 텍스처 덤프(해시 이름)로 만들어야 한다 — 이 PNG는 참고용.
"""
import csv
import os
import struct
import sys

from PIL import Image

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
import psxdisc  # noqa: E402
import verify_source  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKIP_EXT = {"LDP", "MP", "BGM", "VB", "VH", "STR", "XA"}


def rgba(v):
    """PS1 15bit 색 -> RGBA. 0x0000은 투명"""
    if v == 0:
        return (0, 0, 0, 0)
    return ((v & 31) << 3 | (v & 31) >> 2, (v >> 5 & 31) << 3 | (v >> 5 & 31) >> 2,
            (v >> 10 & 31) << 3 | (v >> 10 & 31) >> 2, 255)


def parse_tim(d, o):
    """오프셋 o의 TIM -> dict 또는 None"""
    if d[o:o + 4] != b"\x10\0\0\0" or o + 20 > len(d):
        return None
    flags = struct.unpack_from("<I", d, o + 4)[0]
    mode = flags & 7
    if flags & ~0xF or mode > 3:
        return None
    p, cluts, cpos = o + 8, [], None
    if flags & 8:
        ln, cx, cy, cw, ch = struct.unpack_from("<IHHHH", d, p)
        if cw == 0 or ch == 0 or cw * ch * 2 + 12 != ln or p + ln > len(d):
            return None
        raw = struct.unpack_from(f"<{cw * ch}H", d, p + 12)
        cluts = [raw[i * cw:(i + 1) * cw] for i in range(ch)]
        cpos = (cx, cy)
        p += ln
    if p + 12 > len(d):
        return None
    ln, x, y, w, h = struct.unpack_from("<IHHHH", d, p)
    if w == 0 or h == 0 or w * h * 2 + 12 != ln or p + ln > len(d) or w > 1024 or h > 512:
        return None
    if mode in (0, 1) and not cluts:
        return None
    return {"mode": mode, "cluts": cluts, "clut_pos": cpos, "pos": (x, y), "w": w, "h": h,
            "pix": d[p + 12:p + ln], "size": p + ln - o}


def indices(t):
    w, h, pix = t["w"], t["h"], t["pix"]
    if t["mode"] == 0:
        return w * 4, h, [(pix[(n // 2)] >> (4 * (n & 1))) & 15 for n in range(w * 4 * h)]
    if t["mode"] == 1:
        return w * 2, h, list(pix)
    return None


def to_image(t, clut=None):
    if t["mode"] == 2:
        px = struct.unpack_from(f"<{t['w'] * t['h']}H", t["pix"])
        im = Image.new("RGBA", (t["w"], t["h"]))
        im.putdata([rgba(v) for v in px])
        return im
    W, H, idx = indices(t)
    clut = clut if clut is not None else t["cluts"][0]
    im = Image.new("RGBA", (W, H))
    im.putdata([rgba(clut[i]) if i < len(clut) else (0, 0, 0, 0) for i in idx])
    return im


def index_image(t, bpp4=True):
    """16bpp로 저장된 4bpp 페이지의 색 번호를 회색조로"""
    pix, w, h = t["pix"], t["w"], t["h"]
    im = Image.new("L", (w * 4, h))
    im.putdata([((pix[n // 2] >> (4 * (n & 1))) & 15) * 17 for n in range(w * 4 * h)])
    return im


def main(argv):
    patched = "--patched" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    out = os.path.abspath(args[0] if args else os.path.join(ROOT, "..", "texture-extract"))
    local = verify_source.local_config()
    src = os.path.join(ROOT, "work", "out", "gunnm-kr-dev.bin") if patched else os.path.join(ROOT, local["source_bin"])
    disc = psxdisc.Disc(src)
    ents = {e["path"]: e for e in disc.walk()}
    files = {p.split(";")[0]: e for p, e in ents.items() if not e["interleaved"]}
    rows, n_png = [], 0

    def save(im, rel):
        nonlocal n_png
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im.save(dst)
        n_png += 1

    for path in sorted(files):
        ext = path.rsplit(".", 1)[-1].upper()
        if ext in SKIP_EXT or ext == "CL1":
            continue
        d = disc.read_file(files[path])
        base = path.strip("/")
        if ext == "TM1":
            t = parse_tim(d, 0)
            cl = files.get(path[:-4] + ".CL1")
            if t and t["mode"] == 2 and cl:
                c = parse_tim(disc.read_file(cl), 0)
                raw = struct.unpack_from(f"<{c['w'] * c['h']}H", c["pix"])
                pals = [raw[i * 16:(i + 1) * 16] for i in range(len(raw) // 16)]
                page = dict(t, mode=0, cluts=pals)
                save(index_image(t), f"{base}/index.png")
                for i, pal in enumerate(pals):
                    if any(pal):
                        save(to_image(page, pal), f"{base}/pal{i:02d}.png")
                rows.append([path, 0, t["w"] * 4, t["h"], "4bpp page + CL1", t["pos"], c["pos"]])
                continue
        o = 0
        while True:
            o = d.find(b"\x10\0\0\0", o)
            if o < 0:
                break
            t = parse_tim(d, o)
            if not t:
                o += 4
                continue
            name = f"{base}.png" if o == 0 and t["size"] >= len(d) - 3 else f"{base}_{o:X}.png"
            im = to_image(t)
            save(im, name)
            # 팔레트가 여러 줄이면 나머지 팔레트 버전도
            for i, pal in enumerate(t["cluts"][1:], 1):
                save(to_image(t, pal), name[:-4] + f"_pal{i:02d}.png")
            rows.append([path, hex(o), im.width, im.height, ["4bpp", "8bpp", "16bpp", "24bpp"][t["mode"]],
                         t["pos"], t["clut_pos"]])
            o += t["size"]
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "manifest.csv"), "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(["file", "offset", "width", "height", "format", "vram_xy", "clut_xy"])
        wr.writerows(rows)
    print(f"이미지 {len(rows)}개 -> PNG {n_png}장: {out}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
