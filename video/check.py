"""Step 4: sync check. Samples one frame per narrated sentence (1.2 s after it
starts) from out/final.mp4 and lays them out in contact sheets with the
sentence underneath, so a human (or an agent) can verify that what is said
matches what is on screen. Also reports actions that started late.

Outputs build/check/sheet_*.png and exits non-zero if an action was > 2.5 s late.
"""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw

from compose import font

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def main():
    layout = json.loads((BUILD / "layout.json").read_text())
    timings = {t["id"]: t for t in json.loads((BUILD / "timings.json").read_text(encoding="utf-8"))}
    events = json.loads((BUILD / "events.json").read_text(encoding="utf-8"))
    out = BUILD / "check"
    out.mkdir(exist_ok=True)
    samples = []
    for seg, g in layout["offsets"].items():
        for j, (st, txt) in enumerate(zip(timings[seg]["sentence_starts"], timings[seg]["sentences"])):
            t = g + st + 1.2
            f = out / f"{seg}_{j}.jpg"
            subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i",
                            str(HERE / "out" / "final.mp4"), "-frames:v", "1", "-vf", "scale=640:-1", str(f)],
                           check=True)
            samples.append((f, f"[{seg} {j}] {t:5.1f}s  {txt}"))
    per = 6
    for k in range(0, len(samples), per):
        sheet = Image.new("RGB", (3 * 650, 2 * 470), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        for i, (f, cap) in enumerate(samples[k:k + per]):
            x, y = (i % 3) * 650 + 5, (i // 3) * 470 + 5
            sheet.paste(Image.open(f), (x, y))
            d.multiline_text((x, y + 365), "\n".join(textwrap.wrap(cap, 70)[:4]), font=font(17), fill=(255, 230, 160))
        sheet.save(out / f"sheet_{k // per:02d}.png")
    late = [(e["segment"], e["name"], e["t"] - e["planned"]) for e in events
            if e["kind"] == "action" and e["t"] - e["planned"] > 0.7]
    for s, n, dt in late:
        print(f"late action {s}/{n}: {dt:.2f}s")
    print(f"{len(samples)} frames -> {out}")
    sys.exit(1 if any(dt > 2.5 for *_, dt in late) else 0)


if __name__ == "__main__":
    main()
