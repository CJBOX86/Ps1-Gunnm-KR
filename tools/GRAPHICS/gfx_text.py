"""그래픽 텍스트(그림으로 그려진 일본어) 교체: 4bpp TIM에 한글을 다시 그린다.

config/graphics.json의 항목마다
  - 원본 TIM의 크기·CLUT·VRAM 좌표를 그대로 두고 픽셀만 새로 그린다 (파일 크기 불변)
  - 글자는 안티앨리어싱 회색조로 그린 뒤, 원본 CLUT(회색조 16색)에서 밝기가 가장 가까운 색 번호로 바꾼다.
    밝기 0은 원본에서 투명(색 값 0x0000)인 번호로 둔다
  - lines: [{"text", "x"|"align", "y"}], font(저장소 안 경로), size, tracking(글자 사이 추가 px)
    fit: true면 글자 덩어리를 그림 크기에 맞게 늘이거나 줄인다(큰 제목용)

사용법(미리보기): python tools/GRAPHICS/gfx_text.py [출력 폴더]  -> PNG로 원본과 결과를 나란히 저장
"""
import json
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tim_layout(tim):
    """(flags, clut 시작 offset, clut 목록, 픽셀 블록 offset, w(16bit 단위), h)"""
    flags = struct.unpack_from("<I", tim, 4)[0]
    if flags & 7 != 0 or not flags & 8:
        raise ValueError("4bpp CLUT TIM만 지원")
    ln, _, _, cw, ch = struct.unpack_from("<IHHHH", tim, 8)
    clut = [struct.unpack_from("<H", tim, 20 + 2 * i)[0] for i in range(16)]
    p = 8 + ln
    _, _, _, w, h = struct.unpack_from("<IHHHH", tim, p)
    return clut, p, w, h


def luminance(v):
    return ((v & 31) + (v >> 5 & 31) + (v >> 10 & 31)) * 255 // 93


def render_text(spec, size_px, fonts):
    """회색조(L) 이미지에 글자를 그린다."""
    W, H = size_px
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    for ln in spec["lines"]:
        font = fonts[ln.get("font", spec["font"]), ln.get("size", spec.get("size"))]
        tr = ln.get("tracking", spec.get("tracking", 0))
        widths = [font.getlength(c) for c in ln["text"]]
        total = sum(widths) + tr * (len(ln["text"]) - 1)
        align = ln.get("align", "left")
        x = ln.get("x", 0)
        if align == "right":
            x = W - ln.get("x", 0) - total
        elif align == "center":
            x = (W - total) / 2
        for c, cw in zip(ln["text"], widths):
            d.text((x, ln.get("y", 0)), c, font=font, fill=255)
            x += cw + tr
    if spec.get("fit"):
        bb = im.getbbox()
        m = spec.get("margin", 2)
        crop = im.crop(bb)
        crop = crop.resize((W - 2 * m, H - 2 * m), Image.LANCZOS)
        im = Image.new("L", (W, H), 0)
        im.paste(crop, (m, m))
    return im


def build_tim(tim, spec, root=ROOT):
    clut, p, w, h = tim_layout(tim)
    W = w * 4
    fonts = _FontCache(root)
    gray = render_text(spec, (W, h), fonts)
    lum = [luminance(v) for v in clut]
    transparent = [i for i, v in enumerate(clut) if v == 0]
    if not transparent:
        raise ValueError("투명색(0x0000) CLUT 번호가 없음")
    opaque = [i for i, v in enumerate(clut) if v != 0]
    idx = []
    for v in gray.tobytes():
        if v < 12:
            idx.append(transparent[0])
        else:
            idx.append(min(opaque, key=lambda i: abs(lum[i] - v)))
    pix = bytearray(w * 2 * h)
    for n, v in enumerate(idx):
        pix[n // 2] |= v << (4 * (n & 1))
    out = bytearray(tim)
    out[p + 12:p + 12 + len(pix)] = pix
    return bytes(out)


class _FontCache(dict):
    def __init__(self, root):
        super().__init__()
        self.root = root

    def __missing__(self, key):
        path, size = key
        f = ImageFont.truetype(os.path.join(self.root, path), size)
        self[key] = f
        return f


def decode_preview(tim):
    clut, p, w, h = tim_layout(tim)
    W = w * 4
    im = Image.new("RGB", (W, h))
    px = []
    for n in range(W * h):
        v = clut[(tim[p + 12 + n // 2] >> (4 * (n & 1))) & 15]
        px.append((40, 50, 70) if v == 0 else ((v & 31) << 3, (v >> 5 & 31) << 3, (v >> 10 & 31) << 3))
    im.putdata(px)
    return im


def load_config(root=ROOT):
    with open(os.path.join(root, "config", "graphics.json"), encoding="utf-8") as f:
        return json.load(f)


def main(argv):
    import psxdisc
    import verify_source
    out_dir = argv[1] if len(argv) > 1 else os.path.join(ROOT, "work", "gfx_preview")
    os.makedirs(out_dir, exist_ok=True)
    local = verify_source.local_config()
    disc = psxdisc.Disc(os.path.join(ROOT, local["source_bin"]))
    ents = {e["path"]: e for e in disc.walk()}
    rows = []
    for spec in load_config()["images"]:
        orig = disc.read_file(ents[spec["file"]])
        new = build_tim(orig, spec)
        a, b = decode_preview(orig), decode_preview(new)
        rows.append((a, b))
    W = max(a.width + b.width for a, b in rows) + 12
    H = sum(max(a.height, b.height) + 6 for a, b in rows)
    sheet = Image.new("RGB", (W, H), (255, 0, 255))
    y = 0
    for a, b in rows:
        sheet.paste(a, (0, y))
        sheet.paste(b, (a.width + 12, y))
        y += max(a.height, b.height) + 6
    dst = os.path.join(out_dir, "gfx_compare.png")
    sheet.resize((W * 3, H * 3), Image.NEAREST).save(dst)
    print(dst)


if __name__ == "__main__":
    _TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                    if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
    main(sys.argv)
