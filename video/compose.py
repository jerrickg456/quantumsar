"""Step 3: compose out/final.mp4.

Timeline = title card -> one clip per segment (in segments.json order).
* "slides" segments: explainer slides (build/slides/*.png) that change on the
  sentence they belong to, with a slow zoom.
* "screen" segments: cut from the Playwright recording (build/screen.webm) at the
  logged segment times, with smooth zooms on highlighted UI areas. If a segment
  had to wait for a live Classiq job before its narration, that wait is
  fast-forwarded and labelled on screen.
Narration is placed at each segment's start, subtitles (white on a solid black
box) are burned in for the whole video, and a quiet synthesized music bed
(generated here, license-free) runs underneath.

Outputs: out/final.mp4, out/final.srt, out/thumbnail.png
"""
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw

from common import BLUE, H, INK, MUTED, ORANGE, W, background, centered, font

HERE = Path(__file__).resolve().parent
BUILD, OUT = HERE / "build", HERE / "out"
CLIPS = BUILD / "clips"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 30
TITLE_S = 4.0
GAP = 0.8                 # pause after each slide segment
RAMP = 0.45               # zoom ease time
FF_TARGET = 4.0           # a waited-for live job is shown fast-forwarded in ~4 s
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def ff(*args, cwd=None):
    subprocess.run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", *map(str, args)], check=True, cwd=cwd)


def title_card(cfg) -> Path:
    img = background()
    d = ImageDraw.Draw(img)
    centered(d, 300, cfg["title"], font(150, True), (240, 244, 250))
    centered(d, 495, cfg["subtitle"], font(54), ORANGE)
    centered(d, 610, "Thales SAR segmentation challenge  ·  QAOA on Classiq", font(40), MUTED)
    centered(d, 740, "by " + cfg["team"], font(48, True), (240, 244, 250))
    p = BUILD / "title.png"
    img.save(p)
    return p


# ------------------------------------------------------------------ clip builders
def still_clip(png: Path, dur: float, out: Path, fade_in=True, fade_out=True):
    frames = max(int(round(dur * FPS)), 1)
    vf = [f"scale={W * 2}:{H * 2}",   # render at 2x then zoompan, for a smooth slow push-in
          f"zoompan=z='1+0.05*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}"]
    if fade_in:
        vf.append("fade=t=in:st=0:d=0.35")
    if fade_out:
        vf.append(f"fade=t=out:st={max(dur - 0.35, 0):.3f}:d=0.35")
    ff("-loop", "1", "-framerate", FPS, "-t", f"{dur:.3f}", "-i", png, "-vf", ",".join(vf),
       "-frames:v", frames, *ENC, out)


def slides_clip(seg, tm, out: Path) -> None:
    dur = tm["duration"] + GAP
    starts = tm["sentence_starts"]
    cuts = [(starts[s["at"]] if s["at"] else 0.0, s["image"]) for s in seg["slides"]]
    parts = []
    for i, (t0, name) in enumerate(cuts):
        t1 = cuts[i + 1][0] if i + 1 < len(cuts) else dur
        p = CLIPS / f"{seg['id']}_{i}.mp4"
        still_clip(BUILD / "slides" / f"{name}.png", t1 - t0, p, fade_in=(i == 0), fade_out=(i == len(cuts) - 1))
        parts.append(p)
    concat_files(parts, out)


def zoom_exprs(wins):
    T = f"(in/{FPS})"
    R = [f"clip(min(({T}-{a:.3f})/{RAMP},({b:.3f}-{T})/{RAMP}),0,1)" for a, b, *_ in wins]
    z = "1" + "".join(f"+{zz - 1:.3f}*{r}" for (_, _, _, _, zz), r in zip(wins, R))
    cx = f"{W / 2}" + "".join(f"+({c - W / 2:.1f})*{r}" for (_, _, c, _, _), r in zip(wins, R))
    cy = f"{H / 2}" + "".join(f"+({c - H / 2:.1f})*{r}" for (_, _, _, c, _), r in zip(wins, R))
    return z, f"clip(({cx})-iw/zoom/2,0,iw-iw/zoom)", f"clip(({cy})-ih/zoom/2,0,ih-ih/zoom)"


def _fontfile() -> str:
    for c in ["C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if Path(c).exists():
            return c.replace(":", "\\:")
    return ""


def screen_clip(seg_id, events, out: Path) -> float:
    """Cut one walkthrough scene; returns the offset of its narration inside the clip."""
    ev = [e for e in events if e["segment"] == seg_id]
    t_start = next(e["t"] for e in ev if e["kind"] == "segment_start")
    t_end = next(e["t"] for e in ev if e["kind"] == "segment_end")
    before = next((e["t"] for e in ev if e["kind"] == "before"), None)
    parts, lead = [], 0.0
    if before is not None and t_start - before > FF_TARGET + 1:
        speed = (t_start - before) / FF_TARGET
        p = CLIPS / f"{seg_id}_ff.mp4"
        label = f"fast-forward x{speed:.0f}   waiting for the live Classiq job"
        vf = (f"setpts=PTS/{speed:.4f},fps={FPS},scale={W}:{H},"
              f"drawbox=x=40:y=36:w=1010:h=76:color=black@0.8:t=fill,"
              f"drawtext=fontfile='{_fontfile()}':text='{label}':x=66:y=56:fontsize=36:fontcolor=white")
        script = CLIPS / f"{seg_id}_ff.txt"
        script.write_text(vf, encoding="utf-8")
        ff("-ss", f"{before:.3f}", "-to", f"{t_start:.3f}", "-i", BUILD / "screen.webm",
           "-/filter:v", script, "-frames:v", int(FF_TARGET * FPS), "-an", *ENC, p)
        parts.append(p)
        lead = FF_TARGET
    elif before is not None:
        t_start = before
    wins = [(e["t0"] - t_start, e["t1"] - t_start, e["cx"], e["cy"], e["z"]) for e in ev
            if e["kind"] == "zoom" and e.get("z", 1) > 1.01]
    dur = t_end - t_start
    vf = [f"fps={FPS}"]
    if wins:
        z, x, y = zoom_exprs(wins)
        vf.append(f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={FPS}")
    vf += [f"scale={W}:{H}", "fade=t=in:st=0:d=0.3", f"fade=t=out:st={dur - 0.3:.3f}:d=0.3"]
    p = CLIPS / f"{seg_id}_main.mp4"
    script = CLIPS / f"{seg_id}_vf.txt"
    script.write_text(",".join(vf), encoding="utf-8")
    ff("-ss", f"{t_start:.3f}", "-to", f"{t_end:.3f}", "-i", BUILD / "screen.webm",
       "-/filter:v", script, "-an", *ENC, p)
    parts.append(p)
    concat_files(parts, out)
    return lead


def concat_files(parts, out: Path):
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    ff("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out)


def duration_of(p: Path) -> float:
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(p)], capture_output=True, text=True)
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


# ------------------------------------------------------------------ subtitles & music
def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def chunks(sentence: str, maxlen: int = 72):
    words, cur, out = sentence.split(), "", []
    for w_ in words:
        if len(cur) + len(w_) + 1 > maxlen and cur:
            out.append(cur)
            cur = w_
        else:
            cur = f"{cur} {w_}".strip()
    out.append(cur)
    return out


def write_srt(offsets, timings):
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


def music_expr() -> str:
    """Soft evolving pad (two alternating chords), synthesized: license-free."""
    chord_a = [110.0, 220.0, 261.63, 329.63, 493.88]
    chord_b = [87.31, 174.61, 261.63, 349.23, 440.0]
    sel = "(0.5+0.5*cos(PI*t/8))"

    def chord(fs):
        return "+".join(f"{0.9 / (k + 1):.2f}*sin(2*PI*{f}*t)" for k, f in enumerate(fs))
    return f"0.12*(({sel})*({chord(chord_a)})+(1-{sel})*({chord(chord_b)}))*(0.75+0.25*sin(2*PI*0.11*t))"


# ------------------------------------------------------------------ main
def main():
    cfg = json.loads((HERE / "segments.json").read_text(encoding="utf-8"))
    timings = {t["id"]: t for t in json.loads((BUILD / "timings.json").read_text(encoding="utf-8"))}
    events = json.loads((BUILD / "events.json").read_text(encoding="utf-8"))
    shutil.rmtree(CLIPS, ignore_errors=True)
    CLIPS.mkdir(parents=True)
    OUT.mkdir(exist_ok=True)

    clips, offsets, t = [], {}, 0.0
    tc = CLIPS / "00_title.mp4"
    still_clip(title_card(cfg), TITLE_S, tc)
    clips.append(tc)
    t += duration_of(tc)
    for i, seg in enumerate(cfg["segments"], 1):
        out = CLIPS / f"{i:02d}_{seg['id']}.mp4"
        if seg["kind"] == "slides":
            slides_clip(seg, timings[seg["id"]], out)
            lead = 0.0
        else:
            lead = screen_clip(seg["id"], events, out)
        dur = duration_of(out)
        offsets[seg["id"]] = t + lead
        clips.append(out)
        print(f"{seg['id']:10s} {dur:6.1f}s  narration at {offsets[seg['id']]:6.1f}s", flush=True)
        t += dur
    total = t
    silent = BUILD / "video_silent.mp4"
    concat_files(clips, silent)
    write_srt(offsets, timings)

    seg_ids = [s["id"] for s in cfg["segments"]]
    inputs = ["-i", silent] + sum([["-i", HERE / timings[s]["file"]] for s in seg_ids], [])
    # white text on a solid black box (BorderStyle=3 draws an opaque box in OutlineColour)
    style = ("FontName=%s,FontSize=17,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
             "BackColour=&H00000000,BorderStyle=3,Outline=6,Shadow=0,MarginV=34,Alignment=2") % (
        "Segoe UI" if platform.system() == "Windows" else "DejaVu Sans")
    g = [f"[0:v]subtitles=subs.srt:force_style='{style}'[vout]"]
    for i, s in enumerate(seg_ids):
        ms = int(offsets[s] * 1000)
        g.append(f"[{1 + i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{i}]")
    g.append("".join(f"[a{i}]" for i in range(len(seg_ids))) +
             f"amix=inputs={len(seg_ids)}:normalize=0:duration=longest[voice]")
    g.append(f"aevalsrc='{music_expr()}':s=48000:d={total:.3f},lowpass=f=1400,"
             f"aformat=channel_layouts=stereo,volume=0.09,afade=t=in:d=2,afade=t=out:st={total - 3:.3f}:d=3[music]")
    g.append(f"[voice][music]amix=inputs=2:normalize=0:duration=first,apad,atrim=0:{total:.3f},"
             f"alimiter=limit=0.95[aout]")
    (BUILD / "graph.txt").write_text(";\n".join(g), encoding="utf-8")
    ff(*inputs, "-/filter_complex", "graph.txt", "-map", "[vout]", "-map", "[aout]",
       "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", f"{total:.3f}", OUT / "final.mp4", cwd=BUILD)
    shutil.copy(BUILD / "subs.srt", OUT / "final.srt")
    json.dump({"total_s": total, "offsets": offsets}, open(BUILD / "layout.json", "w"), indent=1)
    thumbnail(cfg, offsets)
    print(f"final.mp4: {total:.1f}s, {(OUT / 'final.mp4').stat().st_size / 1e6:.1f} MB")


def thumbnail(cfg, offsets):
    frame = BUILD / "thumb_src.png"
    ff("-ss", f"{offsets['w_classes'] + 4.0:.2f}", "-i", OUT / "final.mp4", "-frames:v", 1, frame)
    img = Image.open(frame).convert("RGB")
    shade = Image.new("RGB", img.size, (10, 14, 26))
    mask = Image.linear_gradient("L").rotate(90).resize(img.size)
    img = Image.composite(shade, img, mask.point(lambda v: int(v * 0.92)))
    d = ImageDraw.Draw(img)
    d.text((90, 300), cfg["title"], font=font(150, True), fill=(245, 245, 250))
    d.text((96, 490), "Radar segmentation", font=font(70, True), fill=ORANGE)
    d.text((96, 580), "with QAOA on Classiq", font=font(70, True), fill=INK)
    d.text((96, 700), cfg["team"], font=font(52, True), fill=BLUE)
    img.resize((1280, 720), Image.LANCZOS).save(OUT / "thumbnail.png")


if __name__ == "__main__":
    main()
