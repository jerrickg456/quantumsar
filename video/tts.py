"""Step 1: narration -> per-segment MP3 + exact sentence timings.

Uses edge-tts (Microsoft neural voices). Sentence start offsets come from the
TTS engine's SentenceBoundary events, and each clip's true duration is
measured with ffmpeg. Output: build/audio/<id>.mp3, build/timings.json,
script.md (the narration script with word count).
"""
import asyncio
import json
import re
import subprocess
from pathlib import Path

import edge_tts
import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def duration(path: Path) -> float:
    """Decode the file fully with ffmpeg and read the final timestamp (exact)."""
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path), "-f", "null", "-"],
                       capture_output=True, text=True)
    times = re.findall(r"time=(\d+):(\d+):([\d.]+)", p.stderr)
    h, m, s = times[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


async def _stream(text: str, voice: str, rate: str, out: Path) -> list:
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="SentenceBoundary")
    bounds = []
    with out.open("wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                bounds.append({"start": chunk["offset"] / 1e7, "dur": chunk["duration"] / 1e7, "text": chunk["text"]})
    return bounds


async def synth(seg: dict, voices: list, rate: str) -> dict:
    """The edge-tts service occasionally rejects a voice/rate combination:
    retry, then fall back to the next voice in the list."""
    out = BUILD / "audio" / f"{seg['id']}.mp3"
    text = " ".join(seg["sentences"])
    last = None
    for voice in voices:
        for attempt in range(3):
            try:
                bounds = await _stream(text, voice, rate, out)
                break
            except edge_tts.exceptions.NoAudioReceived as e:
                last = e
                await asyncio.sleep(2 + 2 * attempt)
        else:
            continue
        break
    else:
        raise RuntimeError(f"TTS failed for segment {seg['id']}: {last}")
    # map engine sentences back to our sentence list (engine may merge/split)
    starts = []
    for i, s in enumerate(seg["sentences"]):
        key = s[:25]
        hit = next((b for b in bounds if key[:15] in b["text"]), None)
        starts.append(hit["start"] if hit else (starts[-1] + 0.1 if starts else 0.0))
    return {"id": seg["id"], "file": str(out.relative_to(HERE)), "duration": duration(out),
            "sentence_starts": starts, "sentences": seg["sentences"], "engine_bounds": bounds}


async def main():
    cfg = json.loads((HERE / "segments.json").read_text(encoding="utf-8"))
    (BUILD / "audio").mkdir(parents=True, exist_ok=True)
    timings = []
    for seg in cfg["segments"]:
        t = await synth(seg, [cfg["voice"], *cfg.get("fallback_voices", [])], cfg["rate"])
        timings.append(t)
        print(f"{t['id']:10s} {t['duration']:6.2f}s  starts={[round(x, 2) for x in t['sentence_starts']]}")
    (BUILD / "timings.json").write_text(json.dumps(timings, indent=1), encoding="utf-8")
    words = sum(len(" ".join(s["sentences"]).split()) for s in cfg["segments"])
    total = sum(t["duration"] for t in timings)
    lines = [f"# {cfg['title']} — demo video narration", "",
             f"Voice: `{cfg['voice']}` (edge-tts), rate {cfg['rate']}. "
             f"{words} words, {total:.0f} s of speech.", ""]
    for seg, t in zip(cfg["segments"], timings):
        lines += [f"## {seg['storyboard']}  ({t['duration']:.1f} s)", "", " ".join(seg["sentences"]), ""]
    (HERE / "script.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"total speech {total:.1f}s, {words} words")


if __name__ == "__main__":
    asyncio.run(main())
