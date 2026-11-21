"""Step 3: compose final.mp4 = title card + recorded screen (with zooms) + end card,
narration placed at the logged segment start times, a subtle synthesized music
bed (generated here, so license-free), and burned-in subtitles.

Outputs (video/out/): final.mp4 (H.264/AAC), final.srt, thumbnail.png
"""
import json
import platform
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
BUILD, OUT = HERE / "build", HERE / "out"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1920, 1080, 30
TITLE_S = 4.0
END_PAD = 2.5
RAMP = 0.45
SCREEN_SEGMENTS = ["hook", "idea", "demo", "edges", "benchmark", "limits"]
ORANGE, BLUE, BG = (255, 166, 0), (64, 132, 255), (14, 19, 32)


# ------------------------------------------------------------------ fonts & cards
def font(size: int, bold: bool = False):
    cands = (["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"] if bold else
             ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"])
    cands += ["/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else "")]
    for c in cands:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for i in range(0, W + H, 64):  # subtle grid like a radar display
        d.line([(i, 0), (i - H, H)], fill=(22, 30, 48), width=1)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([W * 0.55, -H * 0.3, W * 1.25, H * 0.7], fill=(60, 40, 0))
    gd.ellipse([-W * 0.2, H * 0.5, W * 0.4, H * 1.3], fill=(10, 30, 70))
    return Image.blend(img, glow.filter(ImageFilter.GaussianBlur(160)), 0.55)


def centered(d, y, text, f, fill):
    w = d.textlength(text, font=f)
    d.text(((W - w) / 2, y), text, font=f, fill=fill)


def title_card(cfg) -> Path:
    img = background()
    d = ImageDraw.Draw(img)
    centered(d, 330, cfg["title"], font(150, True), (240, 244, 250))
    centered(d, 520, cfg["subtitle"], font(54), ORANGE)
    centered(d, 640, "MRF energy  →  Ising Hamiltonian  →  QAOA on Classiq", font(40), (170, 182, 205))
    p = BUILD / "title.png"
    img.save(p)
    return p


def end_card(cfg) -> Path:
    img = background()
    d = ImageDraw.Draw(img)
    centered(d, 250, cfg["title"], font(130, True), (240, 244, 250))
    centered(d, 450, "Code:  " + cfg["repo_url"], font(52, True), ORANGE)
    centered(d, 540, "Live demo:  " + cfg["demo_url"], font(52, True), BLUE)
    centered(d, 680, "Open source · tested · one-command Docker run", font(40), (170, 182, 205))
    centered(d, 750, "Built with Classiq · FastAPI · Streamlit", font(36), (130, 142, 165))
    p = BUILD / "end.png"
    img.save(p)
    return p


# ------------------------------------------------------------------ timeline
def load():
    cfg = json.loads((HERE / "segments.json").read_text(encoding="utf-8"))
    timings = {t["id"]: t for t in json.loads((BUILD / "timings.json").read_text(encoding="utf-8"))}
    events = json.loads((BUILD / "events.json").read_text(encoding="utf-8"))
    starts = {e["segment"]: e["t"] for e in events if e["kind"] == "segment_start"}
    ends = {e["segment"]: e["t"] for e in events if e["kind"] == "segment_end"}
    rec0 = starts["hook"] - 0.6
    rec1 = ends["limits"]
    return cfg, timings, events, starts, rec0, rec1


def segment_offsets(starts, rec0, rec_len, timings):
    """Global start time (s) of each narration segment in the final video."""
    off = {s: TITLE_S + (starts[s] - rec0) for s in SCREEN_SEGMENTS}
    off["cta"] = TITLE_S + rec_len + 0.6
    return off


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def chunks(sentence: str, maxlen: int = 78):
    words, cur, out = sentence.split(), "", []
    for w in words:
        if len(cur) + len(w) + 1 > maxlen and cur:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    out.append(cur)
    return out


def write_srt(offsets, timings) -> list:
    cues = []
    for seg_id, g in offsets.items():
        tm = timings[seg_id]
        st = tm["sentence_starts"] + [tm["duration"]]
        for j, sent in enumerate(tm["sentences"]):
            a, b = g + st[j], g + st[j + 1] - 0.05
            parts = chunks(sent)
            total = sum(len(p) for p in parts)
            t = a
            for ptxt in parts:
                dt = (b - a) * len(ptxt) / total
                cues.append((t, t + dt, ptxt))
                t += dt
    lines = []
    for i, (a, b, txt) in enumerate(cues, 1):
        lines += [str(i), f"{srt_time(a)} --> {srt_time(b)}", txt, ""]
    (BUILD / "subs.srt").write_text("\n".join(lines), encoding="utf-8")
    return cues


def zoom_exprs(events, rec0):
    wins = [(e["t0"] - rec0, e["t1"] - rec0, e["cx"], e["cy"], e["z"]) for e in events if e["kind"] == "zoom"]
    T = f"(in/{FPS})"
    R = [f"clip(min(({T}-{a:.3f})/{RAMP},({b:.3f}-{T})/{RAMP}),0,1)" for a, b, *_ in wins]
    z = "1" + "".join(f"+{z - 1:.3f}*{r}" for (_, _, _, _, z), r in zip(wins, R))
    cx = f"{W / 2}" + "".join(f"+({cx - W / 2:.1f})*{r}" for (_, _, cx, _, _), r in zip(wins, R))
    cy = f"{H / 2}" + "".join(f"+({cy - H / 2:.1f})*{r}" for (_, _, _, cy, _), r in zip(wins, R))
    x = f"clip(({cx})-iw/zoom/2,0,iw-iw/zoom)"
    y = f"clip(({cy})-ih/zoom/2,0,ih-ih/zoom)"
    return z, x, y


def music_expr(total: float) -> str:
    """Soft evolving pad: two alternating chords (Am9 / Fmaj7) with slow swells."""
    chord_a = [110.0, 220.0, 261.63, 329.63, 493.88]
    chord_b = [87.31, 174.61, 261.63, 349.23, 440.0]
    sel = "(0.5+0.5*cos(PI*t/8))"  # crossfade every 8 s

    def chord(fs):
        return "+".join(f"{0.9 / (k + 1):.2f}*sin(2*PI*{f}*t)" for k, f in enumerate(fs))
    return f"0.12*(({sel})*({chord(chord_a)})+(1-{sel})*({chord(chord_b)}))*(0.75+0.25*sin(2*PI*0.11*t))"


def main():
    OUT.mkdir(exist_ok=True)
    cfg, timings, events, starts, rec0, rec1 = load()
    rec_len = rec1 - rec0
    end_len = timings["cta"]["duration"] + 0.6 + END_PAD
    total = TITLE_S + rec_len + end_len
    offsets = segment_offsets(starts, rec0, rec_len, timings)
    write_srt(offsets, timings)
    tpng, epng = title_card(cfg), end_card(cfg)
    z, x, y = zoom_exprs(events, rec0)

    seg_ids = SCREEN_SEGMENTS + ["cta"]
    inputs = ["-loop", "1", "-t", f"{TITLE_S}", "-i", str(tpng),
              "-i", str(BUILD / "screen.webm"),
              "-loop", "1", "-t", f"{end_len:.3f}", "-i", str(epng)]
    for s in seg_ids:
        inputs += ["-i", str(HERE / timings[s]["file"])]

    style = ("FontName=%s,FontSize=15,PrimaryColour=&H00FFFFFF,OutlineColour=&H90101010,BackColour=&H90101010,"
             "BorderStyle=3,Outline=2,Shadow=0,MarginV=26,Alignment=2") % (
        "Segoe UI" if platform.system() == "Windows" else "DejaVu Sans")
    g = [
        f"[0:v]fps={FPS},scale={W}:{H},format=yuv420p,fade=t=in:st=0:d=0.6,fade=t=out:st={TITLE_S - 0.6}:d=0.6[v0]",
        f"[1:v]trim=start={rec0:.3f}:end={rec1:.3f},setpts=PTS-STARTPTS,fps={FPS},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={FPS},format=yuv420p,"
        f"fade=t=in:st=0:d=0.5,fade=t=out:st={rec_len - 0.6:.3f}:d=0.6[v1]",
        f"[2:v]fps={FPS},scale={W}:{H},format=yuv420p,fade=t=in:st=0:d=0.6,fade=t=out:st={end_len - 0.8:.3f}:d=0.8[v2]",
        "[v0][v1][v2]concat=n=3:v=1:a=0[vc]",
        f"[vc]subtitles=subs.srt:force_style='{style}'[vout]",
    ]
    for i, s in enumerate(seg_ids):
        ms = int(offsets[s] * 1000)
        g.append(f"[{3 + i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{i}]")
    g.append("".join(f"[a{i}]" for i in range(len(seg_ids))) +
             f"amix=inputs={len(seg_ids)}:normalize=0:duration=longest[voice]")
    g.append(f"aevalsrc='{music_expr(total)}':s=48000:d={total:.3f},lowpass=f=1400,"
             f"aformat=channel_layouts=stereo,volume=0.10,afade=t=in:d=2,afade=t=out:st={total - 3:.3f}:d=3[music]")
    g.append("[voice][music]amix=inputs=2:normalize=0:duration=first,apad,atrim=0:" + f"{total:.3f}" +
             ",alimiter=limit=0.95[aout]")
    (BUILD / "graph.txt").write_text(";\n".join(g), encoding="utf-8")

    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-stats", *inputs,
           "-/filter_complex", "graph.txt", "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", f"{total:.3f}",
           str(OUT / "final.mp4")]
    subprocess.run(cmd, cwd=BUILD, check=True)
    shutil.copy(BUILD / "subs.srt", OUT / "final.srt")
    thumbnail(cfg, events, rec0)
    size = (OUT / "final.mp4").stat().st_size / 1e6
    print(f"final.mp4: {total:.1f}s, {size:.1f} MB")
    json.dump({"total_s": total, "offsets": offsets, "rec0": rec0, "rec1": rec1},
              open(BUILD / "layout.json", "w"), indent=1)


def thumbnail(cfg, events, rec0):
    t = next(e["t"] for e in events if e.get("name") == "demo_shadow") - rec0 + TITLE_S + 2.5
    frame = BUILD / "thumb_src.png"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(OUT / "final.mp4"),
                    "-frames:v", "1", str(frame)], check=True)
    img = Image.open(frame).convert("RGB")
    shade = Image.new("RGB", img.size, BG)
    mask = Image.linear_gradient("L").rotate(90).resize(img.size)  # dark on the left
    img = Image.composite(shade, img, mask.point(lambda v: int(v * 0.92)))
    d = ImageDraw.Draw(img)
    d.text((90, 330), cfg["title"], font=font(150, True), fill=(245, 245, 250))
    d.text((96, 520), "Radar segmentation", font=font(70, True), fill=ORANGE)
    d.text((96, 610), "with QAOA on Classiq", font=font(70, True), fill=(235, 238, 245))
    img.resize((1280, 720), Image.LANCZOS).save(OUT / "thumbnail.png")


if __name__ == "__main__":
    main()
