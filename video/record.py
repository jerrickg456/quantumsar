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
UI_ZOOM = 1.35     # enlarge the app (CSS zoom on <body>) so text is readable in the video
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
    def segment(self, seg_id: str, plan: list):
        tm = self.timings[seg_id]
        self.seg = seg_id
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
        self.page.evaluate("""() => { const m = document.querySelector('[data-testid="stMain"]')
            || document.querySelector('section.main'); (m || window).scrollTo({top: 0, behavior: 'smooth'}); }""")
        self.page.wait_for_timeout(900)


def build_plan(d: Director):
    pg = d.page
    run_btn = pg.get_by_test_id("stBaseButton-primary")
    img_cols = pg.get_by_test_id("stHorizontalBlock").first
    images = img_cols.get_by_test_id("stImage")
    sidebar = pg.get_by_test_id("stSidebar")

    def wait_result():
        pg.get_by_text("Result produced by").wait_for(timeout=180_000)
        pg.wait_for_timeout(400)

    def select(label: str, text: str):
        box = sidebar.get_by_test_id("stSelectbox").filter(has_text=label)
        d.click(box)
        pg.keyboard.type(text, delay=45)
        pg.wait_for_timeout(300)
        opt = pg.get_by_role("option", name=text).first
        d.move_to(opt, steps=8)
        opt.click()
        pg.wait_for_timeout(600)

    def toggle(text: str):
        d.click(sidebar.get_by_text(text, exact=True))
        pg.wait_for_timeout(700)

    # ---------------- hook
    def hook_input():
        d.highlight(images.nth(0), "Raw SAR image: speckle noise", 7.5, zoom=1.6)

    def hook_slow():
        d.highlight(sidebar.get_by_test_id("stSelectbox").filter(has_text="Solver"), None, 4.5)

    # ---------------- idea
    def idea_energy():
        cap = pg.get_by_test_id("stMain").get_by_test_id("stCaptionContainer").first
        d.highlight(cap, "MRF energy = Ising Hamiltonian", 9.5, zoom=1.45)

    def explainer_item(text: str):
        """Open the 'How it works' expander if needed, scroll the bullet into
        view and let the layout settle before measuring it."""
        exp = pg.get_by_test_id("stExpander").filter(has_text="How it works")
        if not exp.get_by_text(text).is_visible():
            d.scroll_to(exp)
            d.click(exp.get_by_text("How it works & honest limitations"))
            pg.wait_for_timeout(700)
        li = exp.get_by_text(text).locator("xpath=ancestor::li[1]")
        d.scroll_to(li)
        pg.wait_for_timeout(300)
        return li

    def idea_explainer():
        d.highlight(explainer_item("Quantum encoding"), "1 pixel = 1 qubit", 5.0)

    def idea_qaoa():
        d.scroll_top()
        d.highlight(sidebar.get_by_test_id("stSelectbox").filter(has_text="Solver"), "QAOA on Classiq", 4.5)

    # ---------------- demo
    def demo_start():
        d.scroll_top()

    def demo_pick():
        select("Sample image", "sar_000_normal")
        d.move_to(sidebar.get_by_test_id("stSelectbox").filter(has_text="Solver"))
        d.highlight(sidebar.get_by_test_id("stSelectbox").filter(has_text="Solver"), None, 1.6)

    def demo_tiles():
        d.highlight(sidebar.get_by_test_id("stSlider").filter(has_text="Tile size"), "3×3 tiles = 9 qubits", 6.0)

    def demo_run():
        d.click(run_btn)
        wait_result()
        d.highlight(pg.get_by_text("Quantum circuit (per tile)").locator("xpath=ancestor::div[@data-testid='stVerticalBlock'][1]"),
                    "Circuit per tile", 4.5)

    def demo_badge():
        d.highlight(pg.locator(".mode-badge").first, None, 5.5, zoom=1.5)

    def demo_compare():
        d.highlight(images.nth(1), "Ground truth", 3.8)
        pg.wait_for_timeout(250)
        d.highlight(images.nth(2), "QAOA result", 3.6)

    def demo_three():
        toggle("3 classes (target / shadow / background)")
        d.click(run_btn)
        wait_result()

    def demo_shadow():
        d.highlight(images.nth(2), "Target + shadow", 5.0, zoom=1.6)

    # ---------------- edges
    def edges_on():
        toggle("Edge detection")
        d.click(run_btn)
        wait_result()
        pg.wait_for_timeout(300)
        d.highlight(images.nth(3), "Single-pixel edges", 4.5)

    def edges_zoom():
        d.highlight(images.nth(3), None, 4.6, zoom=1.7)
        pg.wait_for_timeout(4900)
        toggle("3 classes (target / shadow / background)")   # back to 2 classes for the benchmark
        d.scroll_to(pg.get_by_role("button", name="⚡ Benchmark all solvers"), block="start")

    # ---------------- benchmark
    def bench_click():
        d.click(pg.get_by_role("button", name="⚡ Benchmark all solvers"))
        pg.get_by_text("Export CSV").wait_for(timeout=180_000)
        pg.wait_for_timeout(500)
        d.scroll_to(pg.get_by_role("button", name="⚡ Benchmark all solvers"), block="start")

    def bench_table():
        tbl = pg.get_by_test_id("stTable").last
        d.highlight(tbl, "QAOA ≈ exact graph-cut energy", 6.5, zoom=1.3)
        pg.wait_for_timeout(6800)
        d.highlight(pg.get_by_test_id("stVegaLiteChart").first, "Accuracy (IoU)", 3.0)

    def bench_runtime():
        d.highlight(pg.get_by_test_id("stVegaLiteChart").nth(1), "Runtime: classical still faster", 4.2)

    def bench_csv():
        btn = pg.get_by_test_id("stDownloadButton")
        d.move_to(btn)
        d.highlight(btn, None, 2.2)

    # ---------------- limits
    def lim_intro():
        d.scroll_top()
        d.click(run_btn)          # re-run 2-class view so the badge matches what is said next
        wait_result()

    def lim_tiles():
        d.scroll_to(pg.get_by_text("Quantum circuit (per tile)"), block="start")
        d.highlight(pg.get_by_test_id("stTable").nth(2), "qubits / tile", 6.0)

    def lim_cached():
        d.scroll_top()
        d.highlight(pg.locator(".mode-badge").first, "Cached Classiq run", 5.5)

    def lim_future():
        d.highlight(explainer_item("Limits."), "Honest limitations", 5.5)

    return [
        ("hook", [(1, hook_input), (2, hook_slow)]),
        ("idea", [(0, idea_energy), (3, idea_explainer), (4, idea_qaoa)]),
        ("demo", [(0, demo_start), (1, demo_pick), (2, demo_tiles), (3, demo_run), (4, demo_badge),
                  (5, demo_compare), (6, demo_three), (7, demo_shadow)]),
        ("edges", [(0, edges_on), (1, edges_zoom)]),
        ("benchmark", [(0, bench_click), (2, bench_table), (3, bench_runtime), (4, bench_csv)]),
        ("limits", [(0, lim_intro), (1, lim_tiles), (2, lim_cached), (3, lim_future)]),
    ]


def warm_up(browser, url: str):
    """Load the app once so first-run imports don't stall the recording."""
    ctx = browser.new_context(viewport={"width": W, "height": H})
    pg = ctx.new_page()
    pg.goto(url, wait_until="networkidle")
    pg.get_by_test_id("stBaseButton-primary").wait_for(timeout=120_000)
    pg.get_by_test_id("stBaseButton-primary").click()
    pg.get_by_text("Result produced by").wait_for(timeout=180_000)
    ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8501")
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
        page.goto(a.url, wait_until="networkidle")
        page.get_by_test_id("stBaseButton-primary").wait_for(timeout=120_000)
        page.wait_for_timeout(1500)
        d.ensure_overlay()
        page.mouse.move(W * 0.6, H * 0.45)
        d.log("ready")
        for seg_id, plan in build_plan(d):
            d.segment(seg_id, plan)
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
