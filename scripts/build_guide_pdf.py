"""Render docs/PROJECT_GUIDE.md to a printable PDF (docs/QuantumSAR_Project_Guide.pdf).

    python scripts/build_guide_pdf.py
"""
import base64
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "PROJECT_GUIDE.md"
OUT = ROOT / "docs" / "QuantumSAR_Project_Guide.pdf"
LOGO = ROOT / "Team From Nowhere.png"

CSS = """
@page { size: A4; margin: 16mm 15mm 18mm 15mm; }
body { font-family: 'Segoe UI', 'DejaVu Sans', Arial, sans-serif; color: #1c2230; font-size: 10.5pt; line-height: 1.5; }
h1 { color: #a51419; font-size: 24pt; margin: 0 0 4pt; }
h2 { color: #a51419; border-bottom: 2px solid #f0c36d; padding-bottom: 3pt; margin-top: 18pt; page-break-after: avoid; }
h3 { color: #b07a00; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #d9dce3; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #fbf3e2; }
code { background: #f3f4f7; padding: 0 3pt; border-radius: 3pt; font-size: 9pt; }
pre { background: #f3f4f7; padding: 8pt; border-radius: 6pt; font-size: 8.8pt; white-space: pre-wrap; page-break-inside: avoid; }
blockquote { border-left: 4px solid #f0c36d; margin: 8pt 0; padding: 2pt 10pt; color: #555; background: #fffaf0; }
a { color: #1e5ac8; text-decoration: none; }
img { max-width: 100%; }
.cover { text-align: center; page-break-after: always; padding-top: 30mm; }
.cover img { width: 115mm; }
.cover .t { font-size: 34pt; font-weight: 800; color: #1c2230; margin-top: 10mm; }
.cover .s { font-size: 15pt; color: #a51419; margin-top: 2mm; }
.cover .m { font-size: 12pt; margin-top: 12mm; line-height: 1.8; }
.cover .l { font-size: 11pt; margin-top: 10mm; }
"""


def main():
    md = SRC.read_text(encoding="utf-8")
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    # images referenced relative to docs/ -> absolute file URLs
    body = body.replace('src="../', f'src="{(ROOT).as_uri()}/')
    logo = base64.b64encode(LOGO.read_bytes()).decode()
    cover = f"""<div class="cover"><img src="data:image/png;base64,{logo}">
      <div class="t">QuantumSAR</div>
      <div class="s">Finding vehicles in noisy radar images with quantum optimisation</div>
      <div class="m"><b>Team From Nowhere</b><br>Jerrick Austin Manuel G · Nidhin Suresh · Suresh Ramanujam<br>
        Yokeshwaran Anandan · Hari Babu</div>
      <div class="l">Live app: <a href="https://quantumsar.onrender.com">quantumsar.onrender.com</a><br>
        Code: <a href="https://github.com/jerrickg456/quantumsar">github.com/jerrickg456/quantumsar</a><br>
        Thales SAR image segmentation challenge · built with Classiq</div></div>"""
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{cover}{body}</body></html>"
    tmp = ROOT / "docs" / "_guide.html"
    tmp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(tmp.as_uri(), wait_until="networkidle")
        pg.pdf(path=str(OUT), format="A4", print_background=True, display_header_footer=True,
               header_template="<span></span>",
               footer_template="<div style='font-size:8pt;color:#888;width:100%;text-align:center'>"
                               "QuantumSAR · Team From Nowhere · page <span class='pageNumber'></span> / "
                               "<span class='totalPages'></span></div>",
               margin={"top": "16mm", "bottom": "18mm", "left": "15mm", "right": "15mm"})
        b.close()
    tmp.unlink()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
