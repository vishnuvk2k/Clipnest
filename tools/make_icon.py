"""Renders the Clipnest logo to assets/: .ico (Windows), .icns (macOS) and .png.

Run from the repo root: python tools/make_icon.py
"""

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication

from clipnest import theme

app = QGuiApplication([])
assets = Path(__file__).resolve().parent.parent / "assets"
assets.mkdir(exist_ok=True)


def render(size: int) -> Image.Image:
    svg = theme.LOGO_SMALL_SVG if size <= 32 else theme.LOGO_SVG
    px = theme.svg_pixmap(svg, size, 1.0)
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    px.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")


sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
images = [render(s) for s in sizes]
images[-1].save(assets / "clipnest.ico", sizes=[(s, s) for s in sizes], append_images=images[:-1])
render(512).save(assets / "clipnest.png")
# macOS app icon; Pillow builds every size it needs from the 1024 px image.
render(1024).save(assets / "clipnest.icns")
(assets / "clipnest.svg").write_text(theme.LOGO_SVG)
print("wrote", ", ".join(p.name for p in sorted(assets.iterdir())))
