"""Step 0: generate the explainer slides (1920x1080 PNG) used by the video.

Slides are drawn from the project's real data (synthetic SAR chips and their
ground truth) plus a live screenshot of the public GitHub repository.
Output: build/slides/<name>.png
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from common import BG, BLUE, CYAN, H, INK, MUTED, ORANGE, RED, W, arrow, background, card, centered, font, heading, mono

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "build" / "slides"
sys.path.insert(0, str(ROOT / "src"))
from quantumsar.data import load_sample, to_uint8  # noqa: E402

CLS = np.array([[34, 42, 62], [255, 166, 0], [64, 132, 255]], dtype=np.uint8)


def sar(name: str, size: int) -> Image.Image:
    img, _ = load_sample(ROOT / "data", name)
    return Image.fromarray(to_uint8(img)).convert("RGB").resize((size, size), Image.NEAREST)


def mask(name: str, size: int, three=True) -> Image.Image:
    _, lab = load_sample(ROOT / "data", name)
    if not three:
        lab = (lab == 1).astype(np.uint8)
    return Image.fromarray(CLS[lab]).resize((size, size), Image.NEAREST)


def framed(base: Image.Image, im: Image.Image, x: int, y: int, label: str | None = None, color=INK):
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([x - 8, y - 8, x + im.width + 8, y + im.height + 8], radius=18, outline=(70, 84, 116), width=3)
    base.paste(im, (x, y))
    if label:
        centered(d, y + im.height + 22, label, font(38, True), color, x, x + im.width)


# ----------------------------------------------------------------- slides
def s_radar():
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "The problem", "Radar can see what cameras cannot")
    # satellite
    sx, sy = 520, 300
    d.rectangle([sx - 60, sy - 40, sx + 60, sy + 40], fill=(200, 208, 225))
    for dx in (-1, 1):
        x0 = sx + dx * 75
        d.rectangle([min(x0, x0 + dx * 170), sy - 28, max(x0, x0 + dx * 170), sy + 28], fill=(60, 110, 200), outline=(140, 180, 255), width=3)
    d.ellipse([sx - 18, sy + 30, sx + 18, sy + 66], fill=ORANGE)
    # radar beam to the ground through clouds
    beam = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(beam).polygon([(sx, sy + 60), (300, 790), (900, 790)], fill=(255, 166, 0, 55))
    img.paste(Image.alpha_composite(img.convert("RGBA"), beam).convert("RGB"))
    d = ImageDraw.Draw(img)
    d.line([(sx, sy + 60), (300, 790)], fill=ORANGE, width=3)
    d.line([(sx, sy + 60), (900, 790)], fill=ORANGE, width=3)
    for cx, cy in [(380, 540), (560, 580), (740, 530)]:
        for r, ox in [(55, -50), (70, 0), (55, 55)]:
            d.ellipse([cx + ox - r, cy - r, cx + ox + r, cy + r], fill=(120, 132, 158))
    d.rectangle([200, 790, 1000, 815], fill=(60, 80, 60))
    centered(d, 830, "night  ·  clouds  ·  smoke", font(34, True), MUTED, 200, 1000)
    # right side: what SAR produces
    framed(img, sar("sar_000_normal", 480), 1200, 240, "a SAR image of a vehicle", INK)
    d.text((1120, 800), "SAR = Synthetic Aperture Radar", font=font(44, True), fill=ORANGE)
    return img


def s_speckle():
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "The problem", "SAR images are full of speckle noise")
    framed(img, sar("sar_004_speckled", 540), 250, 240, "heavy speckle", INK)
    framed(img, sar("sar_002_low_snr", 540), 1130, 240, "faint target, low contrast", INK)
    return img


def s_task():
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "The task (Thales challenge)", "Label every pixel: image segmentation")
    framed(img, sar("sar_000_normal", 500), 220, 240, "noisy radar image", INK)
    arrow(d, 800, 490, 1080, 490, width=12, head=40)
    framed(img, mask("sar_000_normal", 500), 1170, 240, None)
    y = 775
    for lab, col, x in [("vehicle", ORANGE, 1150), ("shadow", BLUE, 1370), ("background", (110, 120, 150), 1560)]:
        d.rounded_rectangle([x, y + 6, x + 34, y + 40], radius=6, fill=col)
        d.text((x + 46, y), lab, font=font(36, True), fill=INK)
    return img


def s_puzzle():
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "Why it is hard", "Every pixel depends on its neighbours")
    n, s, x0, y0 = 10, 57, 190, 250
    rng = np.random.default_rng(3)
    for i in range(n):
        for j in range(n):
            x, y = x0 + j * s, y0 + i * s
            if j < n - 1:
                d.line([(x + 22, y + 22), (x + s + 22, y + 22)], fill=(80, 96, 130), width=3)
            if i < n - 1:
                d.line([(x + 22, y + 22), (x + 22, y + s + 22)], fill=(80, 96, 130), width=3)
    for i in range(n):
        for j in range(n):
            x, y = x0 + j * s, y0 + i * s
            c = ORANGE if (3 <= i <= 6 and 3 <= j <= 7) else (rng.choice([60, 90, 120]),) * 3
            d.ellipse([x + 6, y + 6, x + 38, y + 38], fill=tuple(int(v) for v in c))
    card(d, [1000, 260, 1760, 800])
    d.text((1050, 300), "One 64 × 64 image", font=font(46, True), fill=INK)
    d.text((1050, 370), "= 4,096 pixels", font=font(46, True), fill=ORANGE)
    d.text((1050, 480), "possible labellings:", font=font(40), fill=MUTED)
    d.text((1050, 535), "2⁴⁰⁹⁶ ≈ 10¹²³³", font=mono(72), fill=ORANGE)
    d.text((1050, 660), "atoms in the universe ≈ 10⁸⁰", font=font(40), fill=MUTED)
    return img


def s_spins():
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "Our idea", "Each pixel is a tiny magnet (a spin)")
    n, s, x0, y0 = 9, 66, 200, 230
    for i in range(n):
        for j in range(n):
            up = 2 <= i <= 6 and 2 <= j <= 6 and not (i in (2, 6) and j in (2, 6))
            cx, cy = x0 + j * s + 33, y0 + i * s + 33
            col = ORANGE if up else (110, 122, 150)
            if up:
                arrow(d, cx, cy + 22, cx, cy - 22, fill=col, width=6, head=18)
            else:
                arrow(d, cx, cy - 22, cx, cy + 22, fill=col, width=6, head=18)
    card(d, [1000, 240, 1780, 830])
    rows = [("↑  up", "vehicle", ORANGE), ("↓  down", "background", (150, 160, 185)),
            ("bright pixel", "prefers  ↑", INK), ("neighbours", "like to agree", INK),
            ("lowest energy", "= cleanest picture", ORANGE)]
    for k, (a, b, col) in enumerate(rows):
        d.text((1050, 270 + k * 108), a, font=font(44, True), fill=col)
        d.text((1400, 270 + k * 108), b, font=font(44), fill=INK)
    return img


def s_qaoa():
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "Our idea", "QAOA searches for the lowest energy")
    # energy landscape
    xs = np.linspace(0, 1, 400)
    ys = 0.55 + 0.18 * np.sin(14 * xs) + 0.12 * np.cos(31 * xs) - 0.35 * np.exp(-((xs - 0.68) / 0.06) ** 2)
    pts = [(150 + x * 900, 280 + y * 470) for x, y in zip(xs, ys)]
    d.line(pts, fill=BLUE, width=7)
    k = int(np.argmax([p[1] for p in pts]))
    bx, by = pts[k]
    d.ellipse([bx - 20, by - 20, bx + 20, by + 20], fill=ORANGE)
    d.text((bx - 170, by + 40), "best answer", font=font(40, True), fill=ORANGE)
    d.text((150, 260), "energy", font=font(34), fill=MUTED)
    card(d, [1150, 240, 1790, 830])
    d.text((1195, 270), "QAOA", font=font(64, True), fill=ORANGE)
    d.text((1195, 350), "Quantum Approximate", font=font(40), fill=INK)
    d.text((1195, 400), "Optimisation Algorithm", font=font(40), fill=INK)
    for k2, t in enumerate(["1. put all qubits in superposition", "2. apply the energy (cost) layer",
                            "3. apply the mixing layer", "4. repeat, then measure", "→ low-energy answers"]):
        d.text((1195, 490 + k2 * 58), t, font=font(34), fill=INK if k2 < 4 else ORANGE)
    d.text((1195, 775), "runs on Classiq", font=font(34, True), fill=CYAN)
    return img


def s_tiles():
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "Our idea", "Too many pixels? Solve small tiles")
    size = 560
    im = sar("sar_000_normal", size)
    framed(img, im, 190, 230, "4,096 pixels: too many qubits", INK)
    step = size / 64 * 3
    k = 0.0
    while k <= size:
        d.line([(190 + k, 230), (190 + k, 230 + size)], fill=(255, 166, 0), width=1)
        d.line([(190, 230 + k), (190 + size, 230 + k)], fill=(255, 166, 0), width=1)
        k += step
    t0 = (190 + step * 9, 230 + step * 9)
    d.rectangle([t0[0], t0[1], t0[0] + step, t0[1] + step], outline=CYAN, width=5)
    arrow(d, t0[0] + step, t0[1] + step / 2, 1000, 420, fill=CYAN, width=5, head=22)
    card(d, [1010, 240, 1780, 820])
    g, gx, gy = 70, 1110, 300
    for i in range(3):
        for j in range(3):
            d.rounded_rectangle([gx + j * g, gy + i * g, gx + j * g + 58, gy + i * g + 58], radius=10, fill=(40, 52, 80), outline=CYAN, width=3)
            d.text((gx + j * g + 14, gy + i * g + 8), f"q{i * 3 + j}", font=mono(28), fill=CYAN)
    d.text((1360, 310), "1 tile = 3 × 3 pixels", font=font(40, True), fill=INK)
    d.text((1360, 370), "= 9 qubits", font=font(40, True), fill=CYAN)
    for k2, t in enumerate(["• solve each tile with QAOA", "• tile borders = fixed neighbours",
                            "• many tiles in one Classiq job", "• stitch tiles back together"]):
        d.text((1060, 560 + k2 * 60), t, font=font(38), fill=INK)
    return img


def s_stack():
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "How we built it", "Technology")
    items = [
        ("Quantum", "Classiq Python SDK · QAOA circuits · Classiq cloud simulator", ORANGE),
        ("Quantum model", "Ising / QUBO energy · tiling · brute-force verified", ORANGE),
        ("Classical", "Graph cut · simulated annealing · ICM · Otsu · k-means", BLUE),
        ("Backend", "Python · FastAPI · background jobs", CYAN),
        ("Website", "React · TypeScript · Tailwind · React Bits", CYAN),
        ("Quality", "40+ automated tests · GitHub Actions CI", (120, 220, 140)),
        ("Hosting", "Docker container on Render", (120, 220, 140)),
    ]
    for k, (a, b, col) in enumerate(items):
        y = 220 + k * 88
        card(d, [110, y, 1810, y + 76], r=18)
        d.text((150, y + 13), a, font=font(38, True), fill=col)
        d.text((560, y + 15), b, font=font(36), fill=INK)
    return img


def s_github(shot: Path):
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "Open source", "github.com/jerrickg456/quantumsar")
    if shot.exists():
        sc = Image.open(shot).convert("RGB")
        sc.thumbnail((1640, 600))
        x = (W - sc.width) // 2
        d.rounded_rectangle([x - 10, 230, x + sc.width + 10, 240 + sc.height + 10], radius=16, outline=(70, 84, 116), width=3)
        img.paste(sc, (x, 240))
    return img


def s_deploy():
    img = background()
    d = ImageDraw.Draw(img)
    heading(d, "How we deployed it", "From code to a live quantum web app")

    def box(x, y, w, h, title, sub, col):
        card(d, [x, y, x + w, y + h], outline=col, width=4)
        centered(d, y + 26, title, font(42, True), col, x, x + w)
        for k, s in enumerate(sub):
            centered(d, y + 90 + k * 46, s, font(32), INK, x, x + w)

    box(110, 230, 440, 220, "GitHub", ["public code", "every change pushed"], INK)
    box(110, 560, 440, 220, "GitHub Actions", ["runs all tests", "builds Docker image"], (120, 220, 140))
    box(740, 230, 520, 330, "Render", ["Docker container", "React website", "FastAPI backend", "background jobs"], CYAN)
    box(1450, 230, 380, 330, "Classiq", ["quantum cloud", "synthesis +", "simulator"], ORANGE)
    arrow(d, 330, 450, 330, 550, fill=INK)
    arrow(d, 550, 670, 735, 520, fill=(120, 220, 140))
    arrow(d, 1260, 370, 1440, 370, fill=ORANGE)
    arrow(d, 1440, 440, 1265, 440, fill=ORANGE)
    d.text((1270, 300), "QAOA jobs", font=font(30, True), fill=ORANGE)
    d.text((1290, 455), "results", font=font(30, True), fill=ORANGE)
    card(d, [740, 600, 1830, 720], outline=(255, 210, 120), width=3)
    d.text((780, 620), "Secure: Classiq login stored as a Render secret", font=font(36, True), fill=(255, 210, 120))
    d.text((780, 668), "the live site runs quantum jobs on its own, safely", font=font(32), fill=INK)
    centered(d, 770, "quantumsar.onrender.com", font(52, True), CYAN, 740, 1830)
    return img


def s_team(cfg):
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    logo = Image.open(ROOT / "Team From Nowhere.png").convert("RGB")
    logo.thumbnail((900, 520))
    img.paste(logo, ((W // 2 - logo.width) // 2 + 30, (H - logo.height) // 2 - 110))
    red, gold, ink = (165, 20, 25), (214, 150, 20), (40, 40, 48)
    x0 = W // 2 + 40
    d.text((x0, 110), "TEAM", font=font(40, True), fill=gold)
    d.text((x0, 155), cfg["team"].replace("Team ", ""), font=font(92, True), fill=red)
    for k, m in enumerate(cfg["members"]):
        y = 305 + k * 68
        d.ellipse([x0, y + 16, x0 + 18, y + 34], fill=gold)
        d.text((x0 + 40, y), m, font=font(50, True), fill=ink)
    d.line([(x0, 665), (W - 120, 665)], fill=(225, 225, 230), width=3)
    d.text((x0, 685), "Code:  " + cfg["repo_url"], font=font(38, True), fill=red)
    d.text((x0, 740), "Live app:  " + cfg["demo_url"], font=font(38, True), fill=(30, 90, 200))
    centered(d, 820, "QuantumSAR  ·  Thales SAR segmentation challenge  ·  built with Classiq", font(30), (120, 120, 130))
    return img


def github_screenshot(path: Path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 640}, device_scale_factor=1.5, color_scheme="dark")
        pg.goto("https://github.com/jerrickg456/quantumsar", wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(path))
        b.close()


def main():
    cfg = json.loads((HERE / "segments.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    shot = OUT / "_github_raw.png"
    try:
        github_screenshot(shot)
    except Exception as e:  # noqa: BLE001
        print("github screenshot skipped:", e)
    slides = {"s_radar": s_radar, "s_speckle": s_speckle, "s_task": s_task, "s_puzzle": s_puzzle,
              "s_spins": s_spins, "s_qaoa": s_qaoa, "s_tiles": s_tiles, "s_stack": s_stack,
              "s_github": lambda: s_github(shot), "s_deploy": s_deploy, "s_team": lambda: s_team(cfg)}
    for name, fn in slides.items():
        fn().save(OUT / f"{name}.png")
        print("slide", name)


if __name__ == "__main__":
    main()
