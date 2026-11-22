"""Render the README banner GIF from the canvas design.

tools/scene/readme.dc.html is the design exported from the canvas. This script
turns its GIF area into a plain HTML page, opens it in a headless Chromium
browser (Brave/Edge/Chrome), freezes every CSS animation at each frame time and
screenshots it, then writes assets/readme.gif.

Run:  python tools/render_readme_gif.py
"""
import io
import re
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "scene" / "readme.dc.html"
PAGE = ROOT / "tools" / "scene" / "scene.html"
OUT = ROOT / "assets" / "readme.gif"

LOOP_S = 18.0          # every animation period divides this, so the GIF loops seamlessly
FPS = 10
WIDTH, HEIGHT = 998, 600   # CSS px of the design
SCALE = 2                  # render at 2x so it stays sharp when GitHub scales it up
ARCANE = "#58a6ff"

BROWSERS = [
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\Microsoft\EdgeCore\157.0.4341.60\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

LOGOS = {
    "0b623881f81cc4b770d0098b736cd6a1": "packet-tracer.png",
    "34355a701104bb1e7ad00948b0db400f": "winbox.png",
    "88d716b4b6f8a8a2b96c71e8760e8537": "gns3.png",
    "5ad21c6baa227ca8551b833845618c89": "virtualbox.svg",
    "e8c00c3b1915b9e8e37f75d565a682fa": "putty.svg",
}

# Retime the few animations whose period does not divide LOOP_S.
RETIME = [
    ("animation: carry 13s", "animation: carry 18s"),
    ("animation: pull 1.4s", "animation: pull 1.5s"),
    ("animation:win 2.6s", "animation:win 3s"),
    ("ember 1.6s", "ember 1.8s"),
    ("ember 2.2s", "ember 2.25s"),
    ("ember 1.9s", "ember 2s"),
    ("animation-duration: .8s", "animation-duration: .75s"),
    (".fast.fa{animation-duration:.3s}", ".fast.fa{animation-duration:.4s}"),
    (".fast.fb{animation-duration:.3s}", ".fast.fb{animation-duration:.4s}"),
]


def grab_div(html, start):
    """Return the full <div ...>...</div> that begins at index `start`."""
    depth, i = 0, start
    for m in re.finditer(r"<(/?)div\b", html[start:]):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            end = html.index(">", start + m.start()) + 1
            return html[start:end]
    raise ValueError("unbalanced div")


def build_page():
    src = SRC.read_text(encoding="utf-8")
    fonts = re.search(r'<link rel="stylesheet" href="(https://fonts[^"]+)"', src).group(1)
    style = re.search(r"<helmet>.*?<style>(.*?)</style>", src, re.S).group(1)
    area = grab_div(src, src.index('<div style="width: 998px; height: 600px;'))
    area = area.replace("outline: 1px dashed #30363d; ", "background: #0d1117; ")
    area = area.replace("{{arcane}}", ARCANE)
    area = re.sub(
        r'<sc-for list="\{\{(\w+)\}\}" as="p"[^>]*><div style="background: \{\{p\.c\}\}"></div></sc-for>',
        r'<i data-sprite="\1"></i>', area)
    for blob, name in LOGOS.items():
        area = area.replace(f"/_blob/{blob}", f"../../assets/logos/{name}")
    logic = re.search(r"<script type=\"text/x-dc\"[^>]*>(.*?)</script>", src, re.S).group(1)
    page = f"""<!doctype html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="{fonts}">
<style>{style}
html,body{{margin:0;background:#0d1117;font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif}}
i[data-sprite]{{display:contents}}
</style></head>
<body>{area}
<script>
class DCLogic {{ constructor() {{ this.props = {{}}; }} }}
{logic}
const vals = new Component().renderVals();
document.querySelectorAll('i[data-sprite]').forEach((el) => {{
  const parent = el.parentNode;
  for (const p of vals[el.dataset.sprite]) {{
    const d = document.createElement('div');
    d.style.background = p.c;
    parent.insertBefore(d, el);
  }}
  el.remove();
}});
</script>
</body></html>"""
    for a, b in RETIME:
        if a not in page:
            sys.exit(f"retime pattern not found: {a}")
        page = page.replace(a, b)
    PAGE.write_text(page, encoding="utf-8")


def render():
    exe = next((b for b in BROWSERS if Path(b).exists()), None)
    if not exe:
        sys.exit("No Chromium browser found; add its path to BROWSERS.")
    frames = []
    n = int(LOOP_S * FPS)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe, headless=True)
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=SCALE)
        page.goto(PAGE.as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(500)
        page.evaluate("document.getAnimations().forEach(a => a.pause())")
        for f in range(n):
            # Two loops ahead so every delayed animation is already in its steady cycle.
            t = (2 * LOOP_S + f / FPS) * 1000
            page.evaluate(f"document.getAnimations().forEach(a => a.currentTime = {t})")
            png = page.screenshot(clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT})
            frames.append(Image.open(io.BytesIO(png)).convert("RGB"))
        browser.close()

    # One shared palette for every frame keeps colours steady (no flicker).
    fw, fh = frames[0].size
    sample = Image.new("RGB", (fw, fh * 6))
    for i in range(6):
        sample.paste(frames[i * n // 6], (0, fh * i))
    pal = sample.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    out = [fr.quantize(palette=pal, dither=Image.Dither.NONE) for fr in frames]
    out[0].save(OUT, save_all=True, append_images=out[1:], duration=int(1000 / FPS),
                loop=0, optimize=True, disposal=1)
    frames[0].save(PAGE.with_name("preview.png"))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB, {n} frames, {fw}x{fh})")


if __name__ == "__main__":
    build_page()
    render()
