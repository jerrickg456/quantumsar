# QuantumSAR demo video (reproducible)

`./make_video.sh` rebuilds the 2–3 minute product demo from the running app:

| step | script | what it does |
|---|---|---|
| 1 | `tts.py` | Narration from `segments.json` → one MP3 per storyboard segment with **edge-tts**; sentence start times come from the TTS engine's sentence-boundary events, clip lengths are measured with ffmpeg. Writes `script.md`. |
| 2 | `record.py` | Playwright drives the React web UI (via its `data-testid` hooks) at 1920×1080 with video recording on. Every click / highlight / zoom is scheduled at the start of the sentence it illustrates, and every segment lasts exactly as long as its audio. Logs all real timestamps to `build/events.json`. |
| 3 | `compose.py` | ffmpeg: title card → recording (smooth zooms on highlighted UI areas) → end card; narration placed at the logged segment starts; generated ambient music bed (synthesized with `aevalsrc`, so license-free) at low volume; subtitles (`final.srt`) burned in; H.264/AAC. Also renders `thumbnail.png`. |
| 4 | `check.py` | Sync check: grabs one frame per narrated sentence and builds contact sheets (`build/check/sheet_*.png`) with the sentence under each frame; flags actions that started late. |

Edit `segments.json` to change the narration, voice, or the repo / demo links shown on the end card,
and `record.py` (`build_plan`) to change what happens on screen for each sentence.

Requirements: `pip install -r video/requirements.txt` (plus the app's own requirements). ffmpeg comes
from `imageio-ffmpeg`, so no system install is needed. edge-tts needs internet access.
