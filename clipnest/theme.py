"""Colors, the Qt stylesheet and the SVG icons, matching the Clipnest design."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ACCENT = "#6E4EF7"        # Clipnest Violet
ACCENT_HOVER = "#7F63FF"
ACCENT_SOFT = "#A897FF"
ACCENT_TINT = "rgba(110, 78, 247, 0.14)"
BG = "#16151C"
SIDEBAR = "#1B1A22"
SURFACE = "#1E1D25"
SURFACE_2 = "#24232C"
BORDER = "#2B2935"
BORDER_2 = "#34323F"
TEXT = "#F2F1F7"
TEXT_2 = "#C8C5D3"
MUTED = "#A09DAE"
GREEN = "#5FD39A"
RED = "#FF7A85"
RECORD = "#17122B"

LOGO_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="18" fill="{ACCENT}"/>
<circle cx="32" cy="32" r="21" fill="{RECORD}"/>
<circle cx="32" cy="32" r="17" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="0.8"/>
<circle cx="32" cy="32" r="14" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="0.8"/>
<path d="M17.5 24.5a16.5 16.5 0 0 1 9-8.4" fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="1.6" stroke-linecap="round"/>
<circle cx="32" cy="32" r="10.5" fill="#ffffff"/>
<path d="M32 26.5v10M27.5 32.5l4.5 4.5 4.5-4.5" fill="none" stroke="{ACCENT}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

# Bolder version for 16-32 px, where the grooves would turn to mush.
LOGO_SMALL_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="18" fill="{ACCENT}"/>
<circle cx="32" cy="32" r="22" fill="{RECORD}"/>
<circle cx="32" cy="32" r="12" fill="#ffffff"/>
<path d="M32 26v11M27 32l5 5 5-5" fill="none" stroke="{ACCENT}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

_ICON_PATHS = {
    "download": '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    "history": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "settings": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/>'
                '<circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "music": '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    "video": '<rect x="2" y="5" width="15" height="14" rx="2"/><path d="M17 10l5-3v10l-5-3z"/>',
    "link": '<path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/>'
            '<path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>',
    "paste": '<rect x="8" y="3" width="8" height="4" rx="1"/>'
             '<path d="M8 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "check": '<path d="M5 12l5 5 9-10"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "play": '<path d="M7 5l12 7-12 7z"/>',
    "alert": '<circle cx="12" cy="12" r="9"/><path d="M12 7v6M12 16.5v.5"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
}


def svg_pixmap(svg: str, size: int, dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    px.setDevicePixelRatio(dpr)
    return px


def icon(name: str, color: str = TEXT_2, size: int = 18, stroke: float = 2.0) -> QIcon:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{_ICON_PATHS[name]}</svg>'
    )
    return QIcon(svg_pixmap(svg, size))


def asset_path(name: str) -> Path:
    """Files under assets/, both from source and inside the PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / "assets" / name


def app_icon() -> QIcon:
    ico = asset_path("clipnest.ico")
    if ico.exists():
        return QIcon(str(ico))
    ic = QIcon()
    for s in (16, 20, 24, 32):
        ic.addPixmap(svg_pixmap(LOGO_SMALL_SVG, s, 1.0))
    for s in (48, 64, 128, 256):
        ic.addPixmap(svg_pixmap(LOGO_SVG, s, 1.0))
    return ic


def logo_pixmap(size: int) -> QPixmap:
    return svg_pixmap(LOGO_SVG if size >= 40 else LOGO_SMALL_SVG, size)


ICON_SIZE = QSize(18, 18)

STYLESHEET = f"""
* {{ outline: none; }}
QWidget {{ color: {TEXT}; font-size: 14px; }}
QMainWindow, #Content, #Page {{ background: {BG}; }}
QScrollArea {{ border: 0; background: {BG}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_2}; border-radius: 3px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: #4A4757; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid #26242F; }}
#Brand {{ font-size: 22px; font-weight: 700; }}
#NavButton {{
    text-align: left; padding: 0 12px; height: 44px; border: 0; border-radius: 8px;
    background: transparent; color: {TEXT_2};
}}
#NavButton:hover {{ background: #24232C; }}
#NavButton:checked {{ background: #2A2834; color: {TEXT}; font-weight: 600; }}
#Badge {{
    background: {ACCENT}; color: white; border-radius: 11px; font-size: 12px;
    font-weight: 600; min-width: 22px; max-height: 22px; min-height: 22px; padding: 0 6px;
}}
#EngineBox {{ background: #22212A; border-radius: 8px; }}
#EngineText {{ color: {MUTED}; font-size: 12px; }}

#H1 {{ font-size: 30px; font-weight: 700; }}
#H2 {{ font-size: 16px; font-weight: 600; }}
#Sub {{ color: {MUTED}; font-size: 15px; }}
#Label {{ color: {TEXT_2}; font-size: 13px; font-weight: 600; }}
#Muted {{ color: {MUTED}; }}
#Small {{ color: {MUTED}; font-size: 13px; }}
#Error {{ color: {RED}; font-size: 13px; }}

#LinkBox {{ background: #201F28; border: 1px solid {BORDER_2}; border-radius: 10px; }}
#LinkBox[focused="true"] {{ border: 1px solid {ACCENT}; }}
#LinkInput {{ background: transparent; border: 0; font-size: 15px; selection-background-color: {ACCENT}; }}

QPushButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 10px;
    padding: 0 18px; min-height: 44px; font-weight: 600;
}}
QPushButton:hover {{ background: #2C2B35; }}
QPushButton:pressed {{ background: #22212A; }}
QPushButton:disabled {{ color: #6B6878; }}
#Primary {{ background: {ACCENT}; border: 0; color: white; font-size: 16px; border-radius: 12px; min-height: 56px; }}
#Primary:hover {{ background: {ACCENT_HOVER}; }}
#Primary:disabled {{ background: #3B3460; color: #A9A3C9; }}
#SmallButton {{ min-height: 36px; padding: 0 12px; font-size: 13px; border-radius: 8px; font-weight: 500; }}
#IconButton {{ background: transparent; border: 0; min-height: 40px; min-width: 40px; max-width: 40px; padding: 0; border-radius: 8px; }}
#IconButton:hover {{ background: #2A2834; }}

#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
#Thumb {{ background: #2C2A36; border-radius: 8px; }}
#Chip {{ background: #2E2C39; color: {TEXT_2}; border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600; }}
#Duration {{ background: rgba(0,0,0,0.72); border-radius: 4px; padding: 2px 6px; font-size: 12px; }}
#MediaTitle {{ font-size: 17px; font-weight: 600; }}

#FormatCard {{
    background: {SURFACE}; border: 2px solid {BORDER}; border-radius: 12px;
    min-height: 76px; text-align: left; padding: 0 16px;
}}
#FormatCard:hover {{ border-color: #3D3A4A; }}
#FormatCard:checked {{ background: {ACCENT_TINT}; border-color: {ACCENT}; }}
#FormatIcon {{ background: #2E2C39; border-radius: 10px; }}
#FormatIcon[on="true"] {{ background: {ACCENT}; }}
#FormatName {{ font-size: 16px; font-weight: 600; background: transparent; }}
#FormatDesc {{ font-size: 13px; color: {MUTED}; background: transparent; }}

#Pill {{
    background: #22212A; border: 1px solid {BORDER_2}; border-radius: 22px;
    color: {TEXT_2}; padding: 0 18px; min-height: 44px; font-weight: 600;
}}
#Pill:hover {{ border-color: #4A4757; }}
#Pill:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}

QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 1px solid #4A4757; background: #201F28; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT_SOFT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url(:/clipnest/check.svg); }}

QProgressBar {{ background: #2E2C39; border: 0; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QProgressBar[state="done"]::chunk {{ background: {GREEN}; }}
QProgressBar[state="error"]::chunk {{ background: {RED}; }}

QComboBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 8px;
    padding: 0 12px; min-height: 40px; min-width: 220px;
}}
QComboBox::drop-down {{ border: 0; width: 28px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER_2}; selection-background-color: {ACCENT};
    outline: 0; padding: 4px;
}}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER_2}; padding: 6px; }}
QMessageBox {{ background: {SURFACE}; }}
"""
