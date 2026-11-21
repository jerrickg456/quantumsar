"""Shared drawing helpers for the video slides and cards."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
ORANGE, BLUE, CYAN, RED = (255, 166, 0), (64, 132, 255), (80, 230, 255), (255, 70, 70)
BG, INK, MUTED = (10, 14, 26), (238, 242, 250), (150, 162, 185)


def font(size: int, bold: bool = False):
    cands = (["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"] if bold else
             ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"])
    cands += ["/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else "")]
    for c in cands:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def mono(size: int):
    for c in ["C:/Windows/Fonts/consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"]:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return font(size)


def background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for i in range(0, W + H, 64):  # subtle diagonal grid, like a radar display
        d.line([(i, 0), (i - H, H)], fill=(20, 28, 46), width=1)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W * 0.55, -H * 0.3, W * 1.25, H * 0.7], fill=(60, 40, 0))
    gd.ellipse([-W * 0.2, H * 0.5, W * 0.4, H * 1.3], fill=(10, 30, 70))
    return Image.blend(img, glow.filter(ImageFilter.GaussianBlur(160)), 0.55)


def centered(d: ImageDraw.ImageDraw, y: float, text: str, f, fill, x0: float = 0, x1: float = W):
    w = d.textlength(text, font=f)
    d.text((x0 + (x1 - x0 - w) / 2, y), text, font=f, fill=fill)


def heading(d: ImageDraw.ImageDraw, kicker: str, title: str, y: int = 70):
    d.text((110, y), kicker.upper(), font=font(30, True), fill=ORANGE)
    d.text((106, y + 42), title, font=font(70, True), fill=INK)


def card(d: ImageDraw.ImageDraw, box, fill=(17, 24, 42), outline=(48, 60, 88), r=26, width=2):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def arrow(d: ImageDraw.ImageDraw, x0, y0, x1, y1, fill=ORANGE, width=8, head=26):
    import math

    d.line([(x0, y0), (x1, y1)], fill=fill, width=width)
    a = math.atan2(y1 - y0, x1 - x0)
    p1 = (x1 - head * math.cos(a - 0.5), y1 - head * math.sin(a - 0.5))
    p2 = (x1 - head * math.cos(a + 0.5), y1 - head * math.sin(a + 0.5))
    d.polygon([(x1, y1), p1, p2], fill=fill)
