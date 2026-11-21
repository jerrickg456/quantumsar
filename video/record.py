"""Step 2: drive the running app with Playwright and record it at 1920x1080.

Every action is scheduled at the start time of the sentence it illustrates
(from build/timings.json), and every segment lasts exactly as long as its
narration, so picture and voice stay in sync. The actual time of every
segment start, action and zoom window is logged to build/events.json for the
compositor and the sync checker.

    python record.py --url http://localhost:8501
"""
import argparse
import json
import shutil
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
W, H = 1920, 1080
VW, VH = W, H
DSF = 1.0
UI_ZOOM = 1.2     # enlarge the app (CSS zoom on <body>) so text is readable in the video
GAP = 1.2          # silence between narration segments (s)
LEAD = 0.25        # start an action slightly before its sentence

OVERLAY_JS = r"""
(() => {
  if (window.qsHighlight || !document.body) return;
  document.body.style.zoom = '%ZOOM%';
  const root = document.documentElement;  // overlay lives outside the zoomed body
  const css = document.createElement('style');
  css.textContent = `
    #qs-cursor{position:fixed;z-index:2147483647;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;
      background:rgba(255,166,0,.35);border:2px solid #ffa600;pointer-events:none;transition:transform .12s}
    #qs-cursor.down{transform:scale(.7);background:rgba(255,166,0,.7)}
    .qs-hl{position:fixed;z-index:2147483646;border:4px solid #ffa600;border-radius:12px;pointer-events:none;
      box-shadow:0 0 0 4000px rgba(5,8,15,.38),0 0 28px 6px rgba(255,166,0,.65);opacity:0;transition:opacity .35s}
    .qs-hl.on{opacity:1}
    .qs-tag{position:absolute;left:-4px;top:-46px;background:#ffa600;color:#111;font:700 20px/1 sans-serif;
      padding:9px 14px;border-radius:9px;white-space:nowrap}`;
  document.head.appendChild(css);
  const c = document.createElement('div'); c.id = 'qs-cursor'; root.appendChild(c);
  document.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', () => c.classList.add('down'), true);
  document.addEventListener('mouseup', () => c.classList.remove('down'), true);
  window.qsHighlight = (r, label, ms) => {
    const d = document.createElement('div'); d.className = 'qs-hl';
    const pad = 8;
    Object.assign(d.style, {left: (r.x - pad) + 'px', top: (r.y - pad) + 'px',
                            width: (r.width + 2 * pad) + 'px', height: (r.height + 2 * pad) + 'px'});
    if (label) { const t = document.createElement('div'); t.className = 'qs-tag'; t.textContent = label; d.appendChild(t); }
    root.appendChild(d); requestAnimationFrame(() => d.classList.add('on'));
    setTimeout(() => { d.classList.remove('on'); setTimeout(() => d.remove(), 400); }, ms);
  };
  window.qsClear = () => document.querySelectorAll('.qs-hl').forEach(e => e.remove());
})();
"""


class Director:
    def __init__(self, page: Page, timings: dict):
        self.page = page
        self.t0 = time.monotonic()
        self.timings = timings
        self.events: list[dict] = []
        self.seg_start = 0.0
        self.seg = None

    # ------------------------------------------------------------ clock
    def now(self) -> float:
        return time.monotonic() - self.t0

    def wait_until(self, t: float):
        dt = t - self.now()
        if dt > 0:
            self.page.wait_for_timeout(dt * 1000)

    def log(self, kind: str, **kw):
        self.events.append({"t": round(self.now(), 3), "kind": kind, "segment": self.seg, **kw})

    # ------------------------------------------------------------ segments
    def segment(self, seg_id: str, plan: list, before=None):
        """``before`` runs BEFORE the narration clock starts (e.g. wait for a live job)."""
        tm = self.timings[seg_id]
        self.seg = seg_id
        if before:
            self.log("before", name=before.__name__)
            before()
        self.seg_start = self.now()
        self.log("segment_start", duration=tm["duration"])
        for idx, action in plan:
            planned = self.seg_start + max(tm["sentence_starts"][idx] - LEAD, 0)
            self.wait_until(planned)
            self.log("action", sentence=idx, planned=round(planned, 3), name=action.__name__)
            action()
        self.wait_until(self.seg_start + tm["duration"] + GAP)
        self.log("segment_end")

    # ------------------------------------------------------------ primitives
    def ensure_overlay(self):
        self.page.evaluate(OVERLAY_JS.replace("%ZOOM%", str(UI_ZOOM)))
        if getattr(self, "site_label", None):  # small chip showing which site is being recorded
            self.page.evaluate("""(label) => { if (document.getElementById('qs-site')) return;
              const c = document.createElement('div'); c.id = 'qs-site';
              Object.assign(c.style, {position: 'fixed', right: '18px', top: '14px', zIndex: 2147483645,
                background: 'rgba(6,10,20,.82)', color: '#e2e8f0', font: '600 17px sans-serif',
                padding: '8px 14px', borderRadius: '999px', border: '1px solid rgba(110,231,183,.6)'});
              c.innerHTML = '<span style="color:#6ee7b7">●</span>&nbsp; live site: ' + label;
              document.documentElement.appendChild(c); }""", self.site_label)

    def move_to(self, loc, steps: int = 22):
        loc.scroll_into_view_if_needed()
        b = loc.bounding_box()
        self.page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=steps)
        return b

    def click(self, loc):
        self.move_to(loc)
        self.page.wait_for_timeout(150)
        loc.click()

    def highlight(self, loc, label: str | None = None, seconds: float = 3.0, zoom: float | None = None):
        self.ensure_overlay()
        b = loc.bounding_box()
        if not b:
            return
        self.page.evaluate("([r, l, ms]) => window.qsHighlight(r, l, ms)", [b, label, int(seconds * 1000)])
        if zoom:
            self.log("zoom", t0=round(self.now(), 3), t1=round(self.now() + seconds, 3),
                     cx=(b["x"] + b["width"] / 2) * DSF, cy=(b["y"] + b["height"] / 2) * DSF, z=zoom)

    def scroll_to(self, loc, block: str = "center"):
        self.page.evaluate("() => window.qsClear && window.qsClear()")  # fixed overlays must not outlive a scroll
        loc.evaluate(f"e => e.scrollIntoView({{behavior: 'smooth', block: '{block}'}})")
        self.page.wait_for_timeout(900)

    def scroll_top(self):
        self.page.evaluate("() => window.qsClear && window.qsClear()")
        self.page.evaluate("() => window.scrollTo({top: 0, behavior: 'smooth'})")
        self.page.wait_for_timeout(900)


def make_upload_image(path: Path) -> Path:
    """A fresh, never-seen SAR-like image (new random seed every recording), so
    the upload scene always runs genuinely LIVE on Classiq."""
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(int(time.time()))
    n = 64
    img = rng.gamma(3.0, 1 / 3.0, (n, n))
    yy, xx = np.mgrid[0:n, 0:n]
    cx, cy = rng.uniform(24, 40), rng.uniform(22, 36)
    ang = rng.uniform(0, np.pi)
    u = np.cos(ang) * (xx - cx) + np.sin(ang) * (yy - cy)
    v = -np.sin(ang) * (xx - cx) + np.cos(ang) * (yy - cy)
    target = (np.abs(u / 9) ** 4 + np.abs(v / 5) ** 4) <= 1
    img[target] *= 7.0
    shadow = np.zeros_like(target)
    ys, xs = np.nonzero(target)
    for k in range(1, 11):
        shadow[np.clip(ys + k, 0, n - 1), xs] = True
    img[shadow & ~target] *= 0.25
    x = np.log1p(img)
    x = (np.clip((x - x.min()) / (x.max() - x.min()), 0, 1) * 255).astype(np.uint8)
    Image.fromarray(x).save(path)
    return path


def build_plan(d: Director):
    """Shot list for the walkthrough on the deployed React UI (data-testid hooks)."""
    pg = d.page
    T = pg.get_by_test_id
    upload_png = make_upload_image(BUILD / "my_radar_image.png")

    def wait_result():
        T("mode-badge").wait_for(timeout=180_000)
        pg.wait_for_timeout(500)

    def run():
        d.click(T("run-btn"))
        wait_result()

    def run_in_place(*toggles: str):
        for t in toggles:
            T(t).dispatch_event("click")
        pg.wait_for_timeout(150)
        T("run-btn").dispatch_event("click")
        pg.wait_for_timeout(400)
        wait_result()

    def show(testid: str, block: str = "center"):
        d.scroll_to(T(testid), block=block)

    # ---------------- w_intro: the live app
    def intro_site():
        d.highlight(pg.locator("#qs-site"), None, 6.0, zoom=1.0)

    def intro_formula():
        d.highlight(T("hero-formula"), "image energy  ->  quantum Hamiltonian", 7.5, zoom=1.45)

    # ---------------- w_demo
    def demo_pick():
        show("controls", block="start")
        d.click(T("thumb-sar_000_normal"))
        pg.wait_for_timeout(400)
        d.highlight(T("panel-input"), "noisy input", 3.0)

    def demo_run():
        d.move_to(T("solver-classiq"))
        d.highlight(T("solver-classiq"), "Quantum solver", 2.2)
        pg.wait_for_timeout(1200)
        run()
        show("panels")          # back to the result after clicking Run

    def demo_fast():
        d.highlight(T("panel-seg"), "solved on Classiq earlier", 4.5)

    def demo_badge():
        d.highlight(T("mode-badge"), None, 5.0, zoom=1.5)

    def demo_compare():
        d.highlight(T("panel-gt"), "true answer", 3.6)
        pg.wait_for_timeout(250)
        d.highlight(T("panel-seg"), "our result", 3.4)

    def demo_metrics():
        show("metrics")
        d.highlight(T("metrics"), "scores", 3.2)
        pg.wait_for_timeout(3300)
        d.highlight(T("circuit-card"), "9-qubit circuit per tile", 4.0)

    # ---------------- w_classes
    def classes_three():
        # start the (2-class) benchmark now, off-screen: on the free server it takes
        # ~15 s, so its table is ready when the benchmark narration begins
        T("bench-btn").dispatch_event("click")
        pg.wait_for_timeout(300)
        show("panels")
        run_in_place("toggle-3class")
        d.highlight(T("panel-seg"), "vehicle + shadow", 5.0, zoom=1.6)

    def classes_edges():
        run_in_place("toggle-edges")
        pg.wait_for_timeout(300)
        d.highlight(T("panel-edges"), "one-pixel outline", 4.5, zoom=1.6)
        pg.wait_for_timeout(4700)
        T("toggle-3class").dispatch_event("click")   # back to 2 classes for the benchmark
        T("toggle-edges").dispatch_event("click")
        show("bench-btn", block="start")

    # ---------------- w_bench
    def bench_wait():
        T("bench-table").wait_for(timeout=180_000)
        pg.wait_for_timeout(400)
        show("bench-table", block="start")

    def bench_table():
        d.highlight(T("row-classiq"), "QAOA on Classiq", 4.0)
        pg.wait_for_timeout(300)
        d.highlight(T("row-graphcut"), "exact optimum: same energy", 4.0)
        pg.wait_for_timeout(4300)
        show("chart-energy")
        d.highlight(T("chart-iou"), "accuracy", 2.6)

    def bench_runtime():
        d.highlight(T("chart-runtime"), "classical is still faster", 4.2, zoom=1.3)

    def bench_csv():
        show("export-csv")
        d.move_to(T("export-csv"))
        d.highlight(T("export-csv"), None, 2.2)

    # ---------------- w_upload: live Classiq run
    def up_choose():
        show("controls", block="start")
        d.move_to(T("upload-btn"))
        d.highlight(T("upload-btn"), "upload your own image", 3.0)
        pg.locator("input[type=file]").set_input_files(str(upload_png))
        pg.wait_for_timeout(800)

    def up_run():
        d.highlight(T("cache-hint"), "runs LIVE on Classiq", 3.0)
        pg.wait_for_timeout(1200)
        d.click(T("run-btn"))
        T("job-progress").wait_for(timeout=60_000)

    def up_progress():
        show("job-progress")
        d.highlight(T("job-progress"), "live progress", 6.0, zoom=1.5)

    def up_how():
        show("how-encoding")
        d.highlight(T("how-model"), None, 1.8)
        for t in ("how-encoding", "how-qaoa", "how-tiling"):
            pg.wait_for_timeout(1700)
            d.highlight(T(t), None, 1.8)

    def up_limits():
        show("how-limits")
        d.highlight(T("how-limits"), "honest limitations", 7.0, zoom=1.25)

    # ---------------- w_live
    def live_wait():
        show("panels")
        T("mode-badge").wait_for(timeout=1_200_000)   # the live job finishes (~1-2 min)
        pg.wait_for_timeout(600)

    def live_badge():
        d.highlight(T("mode-badge"), None, 5.0, zoom=1.5)

    def live_seg():
        d.highlight(T("panel-seg"), "computed live on Classiq", 3.5)

    return [
        ("w_intro", [(1, intro_site), (2, intro_formula)], None),
        ("w_demo", [(0, demo_pick), (1, demo_run), (2, demo_fast), (3, demo_badge), (4, demo_compare),
                    (5, demo_metrics)], None),
        ("w_classes", [(0, classes_three), (1, classes_edges)], None),
        ("w_bench", [(0, bench_wait), (1, bench_table), (2, bench_runtime), (3, bench_csv)], None),
        ("w_upload", [(0, up_choose), (1, up_run), (2, up_progress), (3, up_how), (4, up_limits)], None),
        ("w_live", [(0, live_badge), (1, live_seg)], live_wait),
    ]


def wait_healthy(url: str, timeout_s: int = 300):
    """Free-tier hosts sleep when idle: poll /health until the real app answers."""
    import json as _json
    import urllib.request

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=30) as r:
                if _json.loads(r.read()).get("status") == "ok":
                    return
        except Exception:  # noqa: BLE001 - still waking up
            pass
        time.sleep(5)
    raise RuntimeError(f"{url} did not become healthy within {timeout_s}s")


def warm_up(browser, url: str):
    """Wake the (free-tier) server and load the app once before recording."""
    wait_healthy(url)
    ctx = browser.new_context(viewport={"width": W, "height": H})
    pg = ctx.new_page()
    pg.goto(url, wait_until="networkidle", timeout=180_000)
    pg.get_by_test_id("run-btn").click()
    pg.get_by_test_id("mode-badge").wait_for(timeout=180_000)
    ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=json.loads((HERE / "segments.json").read_text(encoding="utf-8"))["app_url"])
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()
    timings = {t["id"]: t for t in json.loads((BUILD / "timings.json").read_text(encoding="utf-8"))}
    rec_dir = BUILD / "rec"
    shutil.rmtree(rec_dir, ignore_errors=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not a.headed)
        warm_up(browser, a.url)
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=DSF,
                                  record_video_dir=str(rec_dir), record_video_size={"width": VW, "height": VH})
        page = ctx.new_page()
        d = Director(page, timings)           # video clock starts with the page
        d.site_label = a.url.split("//")[-1].rstrip("/")
        page.goto(a.url, wait_until="networkidle")
        page.get_by_test_id("run-btn").wait_for(timeout=120_000)
        page.wait_for_timeout(2500)          # let the hero intro animations play
        d.ensure_overlay()
        page.mouse.move(W * 0.6, H * 0.45)
        d.log("ready")
        for seg_id, plan, before in build_plan(d):
            d.segment(seg_id, plan, before)
        d.log("end")
        video_path = page.video.path()
        ctx.close()
        browser.close()
    shutil.copy(video_path, BUILD / "screen.webm")
    (BUILD / "events.json").write_text(json.dumps(d.events, indent=1), encoding="utf-8")
    late = [e for e in d.events if e["kind"] == "action" and e["t"] - e["planned"] > 0.7]
    print(f"recorded {d.now():.1f}s -> build/screen.webm; {len(late)} late actions")
    for e in late:
        print(f"  LATE {e['segment']}/{e['name']}: {e['t'] - e['planned']:.2f}s")


if __name__ == "__main__":
    main()
