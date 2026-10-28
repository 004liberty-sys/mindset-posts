"""カルーセル投稿（1080x1350 × 最大10枚）を作る。

使い方: python make_carousel.py              （posts/ の全投稿）
      python make_carousel.py posts/carousel_001.json  （1本だけ）
出力先: output/<id>/01.png, 02.png ...

各スライドの "bg"（a / b / c）に対応する backgrounds/<投稿ID>_<a|b|c>.png があれば、
その画像を暗くして背景に使う。なければ、暗いグラデーションの背景を自動で作る。
"bg" は ["a", "a2"] のような配列でもよい（カルーセルでは最初の1枚を使う。リールでは順に切り替える）。
投稿IDが "005v2" のような派生版で、backgrounds/005v2_a.png がなければ backgrounds/005_a.png を使う。
"type": "law" は写真を使わず、真っ黒な背景に大きな太字だけを中央に出す。
"""
import json
import random
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1350
BRAND = "@mind.set.jp"
BG_DIR = Path("backgrounds")  # Codexが作った背景画像の置き場所（<投稿ID>_<a|b|c>.png）

FONT_CANDIDATES = {
    "serif": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-SemiBold.ttc",
              "C:/Windows/Fonts/yumindb.ttf", "C:/Windows/Fonts/yumin.ttf", "C:/Windows/Fonts/msmincho.ttc"],
    "serif_bold": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
                   "C:/Windows/Fonts/yumindb.ttf", "C:/Windows/Fonts/msmincho.ttc"],
    "serif_light": ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                    "C:/Windows/Fonts/yuminl.ttf", "C:/Windows/Fonts/yumin.ttf", "C:/Windows/Fonts/msmincho.ttc"],
}

# スライド種類ごとの見た目
STYLE = {
    "hook":    dict(main=64, sub=34, glow=(70, 90, 120)),
    "story":   dict(main=54, sub=32, glow=(90, 75, 60)),
    "quote":   dict(main=66, sub=34, glow=(110, 85, 50)),
    "message": dict(main=56, sub=34, glow=None),       # 黒地に文字だけ
    "cta":     dict(main=76, sub=30, glow=(40, 70, 140)),
    "finale":  dict(main=56, sub=40, glow=(40, 70, 140)),  # パンチライン＋合言葉
    "law":     dict(main=64, sub=0, glow=None),        # 真っ黒な背景に太字だけ
}
TEXT = (238, 236, 232)
SUB = (200, 196, 188)
ACCENT = (201, 162, 39)


def font(kind, size):
    for p in FONT_CANDIDATES[kind]:
        if Path(p).exists():
            return ImageFont.truetype(p, size, index=0)
    raise FileNotFoundError(f"フォントが見つかりません: {kind}")


def background(glow, seed):
    """暗いグラデーション＋ぼんやりした光＋フィルムの粒子＋周辺減光。"""
    rnd = random.Random(seed)
    img = Image.new("RGB", (W, H), (10, 10, 12))
    if glow:
        layer = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(layer)
        cx, cy = rnd.randint(250, 830), rnd.randint(300, 900)
        r = rnd.randint(380, 520)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=glow)
        layer = layer.filter(ImageFilter.GaussianBlur(220))
        img = Image.blend(img, layer, 0.55)
    # 粒子
    noise = Image.effect_noise((W, H), 18).convert("RGB")
    img = Image.blend(img, noise, 0.05)
    # 周辺減光
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((-200, -150, W + 200, H + 150), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(180))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(img, dark, mask)


def photo_background(path, bright=False):
    """写真を画面いっぱいに切り抜き、文字が読めるように暗くする。
    bright=True（最後のページ）は全体を暗くしすぎず、文字の周りだけをぼかした影で落とす。"""
    im = Image.open(path).convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)))
    left, top = (im.width - W) // 2, (im.height - H) // 2
    im = im.crop((left, top, left + W, top + H))
    im = Image.blend(im, Image.new("RGB", (W, H), (0, 0, 0)), 0.22 if bright else 0.5)
    # 文字が乗る中央を、ふちをぼかした黒で落とす
    shade = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shade).ellipse((60, 220, W - 60, H - 260), fill=150 if bright else 110)
    shade = shade.filter(ImageFilter.GaussianBlur(140))
    return Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), im, shade)


def draw_center(d, text, fnt, y, fill, line_gap=1.6):
    lines = text.split("\n")
    lh = int(fnt.size * line_gap)
    for i, line in enumerate(lines):
        w = d.textlength(line, font=fnt)
        d.text(((W - w) / 2, y + i * lh), line, font=fnt, fill=fill)
    return lh * len(lines)


def fit(d, text, kind, size, max_w=W - 160):
    while size > 30:
        f = font(kind, size)
        if max(d.textlength(l, font=f) for l in text.split("\n")) <= max_w:
            return f
        size -= 2
    return font(kind, size)


def bg_keys(slide):
    """スライドの "bg" を配列にそろえる（"a" → ["a"]、なし → []）。"""
    bg = slide.get("bg") or []
    return [bg] if isinstance(bg, str) else list(bg)


def bg_path(post_id, key):
    """backgrounds/<投稿ID>_<key>.png。派生版（005v2）でなければ元の投稿（005）の画像を探す。"""
    for pid in (post_id, re.match(r"\d*", post_id).group()):
        p = BG_DIR / f"{pid}_{key}.png"
        if pid and p.exists():
            return p
    return None


def render(slide, idx, total, seed, bg_key=None):
    """bg_key を渡すと、その背景で描く（リールで1枚のスライドに複数の写真を使うとき）。"""
    st = STYLE[slide["type"]]
    if slide["type"] == "law":
        img = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        fm = fit(d, slide["main"], "serif_bold", st["main"])
        mh = int(fm.size * 1.6) * len(slide["main"].split("\n"))
        draw_center(d, slide["main"], fm, (H - mh) // 2 - 20, TEXT)
        draw_footer(img, idx, total)
        return img

    keys = bg_keys(slide)
    key = bg_key or (keys[0] if keys else None)
    bg_file = bg_path(seed.split("-")[0], key) if key else None
    img = (photo_background(bg_file, bright=slide["type"] == "finale")
           if bg_file else background(st["glow"], seed))
    d = ImageDraw.Draw(img)

    if slide["type"] == "finale":
        render_finale(d, slide, st)
        draw_footer(img, idx, total)
        return img

    kind = "serif_bold" if slide["type"] in ("cta", "quote") else "serif"
    fm = fit(d, slide["main"], kind, st["main"])
    fs = fit(d, slide.get("sub", ""), "serif_light", st["sub"]) if slide.get("sub") else None

    mh = int(fm.size * 1.6) * len(slide["main"].split("\n"))
    gap = 70 if slide["type"] != "quote" else 40
    sh = int(fs.size * 1.7) * len(slide["sub"].split("\n")) if fs else 0
    y = (H - (mh + (gap + sh if fs else 0))) // 2 - 20

    draw_center(d, slide["main"], fm, y, TEXT)
    if slide["type"] == "cta":
        lw = 80
        d.rectangle(((W - lw) / 2, y + mh + gap / 2 - 2, (W + lw) / 2, y + mh + gap / 2 + 1), fill=ACCENT)
    if fs:
        color = ACCENT if slide["type"] == "quote" else SUB
        draw_center(d, slide["sub"], fs, y + mh + gap, color, 1.7)

    draw_footer(img, idx, total)
    return img


def render_finale(d, slide, st):
    """上にパンチライン、下に金の線と合言葉、その下に小さく呼びかけ。"""
    fm = fit(d, slide["main"], "serif", st["main"])
    total = int(fm.size * 1.6) * len(slide["main"].split("\n")) + 90 + 60 + 70 + 30 + 100
    top = (H - total) // 2 - 20
    mh = draw_center(d, slide["main"], fm, top, TEXT)
    y = top + mh + 90
    d.rectangle(((W - 80) / 2, y, (W + 80) / 2, y + 3), fill=ACCENT)
    fs = fit(d, slide["sub"], "serif_bold", st["sub"])
    draw_center(d, slide["sub"], fs, y + 60, TEXT)
    if slide.get("foot"):
        ff = fit(d, slide["foot"], "serif", 32)
        draw_center(d, slide["foot"], ff, y + 60 + int(fs.size * 1.6) + 30, TEXT, 1.7)


def draw_footer(img, idx, total):
    # ページ番号とブランド名（明るい背景でも読めるよう、うっすら黒い影を付ける）
    small = font("serif_light", 26)
    d = ImageDraw.Draw(img)
    pg = f"{idx}/{total}"
    items = [((W - 70 - d.textlength(pg, font=small), 60), pg, (150, 150, 150)),
             (((W - d.textlength(BRAND, font=small)) / 2, H - 90), BRAND, (170, 170, 170))]
    shadow = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shadow)
    for (x, y), text, _ in items:
        sd.text((x + 1, y + 2), text, font=small, fill=210, stroke_width=3, stroke_fill=210)
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    img.paste((0, 0, 0), (0, 0), shadow)
    for xy, text, fill in items:
        d.text(xy, text, font=small, fill=fill)


def main(path):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    out = Path("output") / spec["id"]
    out.mkdir(parents=True, exist_ok=True)
    slides = spec["slides"]
    for i, s in enumerate(slides, 1):
        p = out / f"{i:02d}.png"
        render(s, i, len(slides), seed=f"{spec['id']}-{i}").save(p)
        print("作成:", p)


if __name__ == "__main__":
    for f in (sys.argv[1:] or sorted(str(x) for x in Path("posts").glob("carousel_*.json"))):
        main(f)
