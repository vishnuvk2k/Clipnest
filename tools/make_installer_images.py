"""Renders the setup wizard's side panel and header logo into installer/.

Run from the repo root: python tools/make_installer_images.py
"""

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

from fetchly import theme

app = QGuiApplication([])
out = Path(__file__).resolve().parent.parent / "installer"
out.mkdir(exist_ok=True)


def save_bmp(img: QImage, path: Path) -> None:
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB").save(path, "BMP")


def side_panel(scale: float) -> QImage:
    w, h = round(164 * scale), round(314 * scale)
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor(theme.ACCENT))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    logo = round(84 * scale)
    p.drawPixmap(round((w - logo) / 2), round(78 * scale), theme.svg_pixmap(theme.LOGO_SVG, logo, 1.0))
    p.setPen(QColor("#FFFFFF"))
    f = QFont()
    f.setPixelSize(round(26 * scale))
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 182 * scale, w, 34 * scale), Qt.AlignCenter, "Fetchly")
    f.setPixelSize(round(11.5 * scale))
    f.setBold(False)
    p.setFont(f)
    p.setPen(QColor("#E6E0FF"))
    p.drawText(QRectF(8 * scale, 218 * scale, w - 16 * scale, 60 * scale),
               Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, "MP3 & MP4 downloader\nfor YouTube & Instagram")
    p.end()
    return img


def header_logo(scale: float) -> QImage:
    s = round(55 * scale)
    img = QImage(s, s, QImage.Format_ARGB32)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    inner = round(48 * scale)
    off = (s - inner) // 2
    svg = theme.LOGO_SVG if inner >= 40 else theme.LOGO_SMALL_SVG
    p.drawPixmap(off, off, theme.svg_pixmap(svg, inner, 1.0))
    p.end()
    return img


for scale, tag in ((1.0, "100"), (1.5, "150"), (2.0, "200")):
    save_bmp(side_panel(scale), out / f"wizard-{tag}.bmp")
    save_bmp(header_logo(scale), out / f"wizard-small-{tag}.bmp")
print("wrote", ", ".join(sorted(p.name for p in out.glob("*.bmp"))))
