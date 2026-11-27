"""Colors, the Qt stylesheet and the SVG icons, matching the Clipnest design."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ACCENT = "#7C5CFF"        # Clipnest Violet (Midnight)
ACCENT_2 = "#A66BFF"      # gradient end
ACCENT_HOVER = "#8C70FF"
ACCENT_SOFT = "#A88BFF"
ACCENT_TINT = "rgba(124, 92, 255, 0.14)"
GRADIENT = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #7C5CFF, stop:1 #A66BFF)"
GRADIENT_HOVER = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #8A6CFF, stop:1 #B27DFF)"
BG = "#0D0C13"
PANEL = "#15141D"
SURFACE = "#1B1A25"
SURFACE_2 = "#23212F"
SIDEBAR = PANEL
BORDER = "#24222F"
BORDER_2 = "#302E3D"
TEXT = "#F4F3FA"
TEXT_2 = "#C9C6D6"
MUTED = "#8C89A0"
GREEN = "#3DDC97"
RED = "#FF7A85"
AMBER = "#FFC069"
RECORD = "#140F26"

LOGO_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ACCENT_2}"/></linearGradient></defs>
<rect width="64" height="64" rx="18" fill="url(#g)"/>
<circle cx="32" cy="32" r="21" fill="{RECORD}"/>
<circle cx="32" cy="32" r="17" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="0.8"/>
<circle cx="32" cy="32" r="14" fill="none" stroke="#ffffff" stroke-opacity="0.12" stroke-width="0.8"/>
<path d="M17.5 24.5a16.5 16.5 0 0 1 9-8.4" fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="1.6" stroke-linecap="round"/>
<circle cx="32" cy="32" r="10.5" fill="#ffffff"/>
<path d="M32 26.5v10M27.5 32.5l4.5 4.5 4.5-4.5" fill="none" stroke="{ACCENT}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

# Bolder version for 16-32 px, where the grooves would turn to mush.
LOGO_SMALL_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ACCENT_2}"/></linearGradient></defs>
<rect width="64" height="64" rx="18" fill="url(#g)"/>
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
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.5"/><path d="M21 16l-5-5-9 9"/>',
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
    "scissors": '<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/>'
                '<path d="M20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"/>',
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
QMainWindow, #Content {{ background: {BG}; }}
#Page, #Transparent {{ background: transparent; }}
QScrollArea {{ border: 0; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_2}; border-radius: 3px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: #4A4757; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* top bar */
#TopBar {{ background: rgba(13, 12, 19, 0.85); border-bottom: 1px solid {BORDER}; }}
#Brand {{ font-size: 20px; font-weight: 700; }}
#Tabs {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 12px; }}
#Tab {{
    background: transparent; border: 0; border-radius: 9px; color: {MUTED};
    min-height: 34px; padding: 0 14px; font-size: 13px; font-weight: 600; text-align: left;
}}
#Tab:hover {{ color: {TEXT_2}; }}
#Tab:checked {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER_2}; }}
#Badge {{
    background: {GRADIENT}; color: white; border-radius: 9px; font-size: 11px;
    font-weight: 700; min-width: 18px; max-height: 18px; min-height: 18px; padding: 0 5px;
}}
#StatusPill {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 15px; }}
#StatusText {{ color: {MUTED}; font-size: 12px; }}

/* text */
#H1 {{ font-size: 30px; font-weight: 700; }}
#Hero {{ font-size: 40px; font-weight: 800; }}
#H2 {{ font-size: 16px; font-weight: 600; }}
#Sub {{ color: {MUTED}; font-size: 15px; }}
#Label {{ color: {TEXT_2}; font-size: 13px; font-weight: 600; }}
#Muted {{ color: {MUTED}; }}
#Small {{ color: {MUTED}; font-size: 12.5px; }}
#Error {{ color: {RED}; font-size: 13px; }}
#Warn {{ color: {AMBER}; font-size: 12.5px; }}

/* paste box */
#PasteBox {{ background: {PANEL}; border: 1px solid #4B3D99; border-radius: 16px; }}
#PasteBox[focused="true"] {{ border: 1px solid {ACCENT}; }}
#LinkInput {{ background: transparent; border: 0; padding: 0; min-height: 0; font-size: 15px;
             selection-background-color: {ACCENT}; }}

/* buttons */
QPushButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 11px;
    padding: 0 16px; min-height: 42px; font-weight: 600;
}}
QPushButton:hover {{ background: #2B2938; }}
QPushButton:pressed {{ background: #1F1D29; }}
QPushButton:disabled {{ color: #5F5C70; }}
#Grad, #Go {{ background: {GRADIENT}; border: 0; color: white; }}
#Grad:hover, #Go:hover {{ background: {GRADIENT_HOVER}; }}
#Go {{ font-size: 16px; border-radius: 14px; min-height: 54px; }}
#Go:disabled, #Grad:disabled {{ background: #2E2846; color: #8F88AE; }}
#SmallButton {{ min-height: 34px; padding: 0 12px; font-size: 13px; border-radius: 9px; font-weight: 500; }}
#LinkButton {{ background: transparent; border: 0; color: {MUTED}; min-height: 26px; padding: 0 2px;
              font-size: 12.5px; font-weight: 600; }}
#LinkButton:hover {{ color: {TEXT_2}; }}
#IconButton {{ background: {SURFACE_2}; border: 0; min-height: 30px; max-height: 30px; min-width: 30px;
              max-width: 30px; padding: 0; border-radius: 8px; }}
#IconButton:hover {{ background: #312F3F; }}
#ThumbSave {{ background: rgba(13, 12, 19, 0.78); border: 1px solid rgba(255,255,255,0.18); color: white;
             min-height: 28px; max-height: 28px; padding: 0 9px; border-radius: 8px; font-size: 12px; }}
#ThumbSave:hover {{ background: rgba(124, 92, 255, 0.85); }}

/* panels */
#Panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 20px; }}
#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
#Rail {{ background: rgba(21, 20, 29, 0.6); border-left: 1px solid {BORDER}; }}
#Thumb {{ background: {SURFACE_2}; border-radius: 12px; }}
#Chip {{ background: {SURFACE_2}; color: {TEXT_2}; border: 1px solid {BORDER}; border-radius: 10px;
        padding: 2px 9px; font-size: 11.5px; font-weight: 600; }}
#ChipRed {{ background: rgba(255,78,69,0.10); color: #FF8A80; border: 1px solid rgba(255,78,69,0.25);
           border-radius: 10px; padding: 2px 9px; font-size: 11.5px; font-weight: 600; }}
#SiteChip {{ background: {PANEL}; color: {TEXT_2}; border: 1px solid {BORDER}; border-radius: 14px;
            padding: 5px 12px; font-size: 12.5px; font-weight: 600; }}
#Duration {{ background: rgba(0,0,0,0.72); border-radius: 6px; padding: 2px 7px; font-size: 12px; font-weight: 600; }}
#MediaTitle {{ font-size: 20px; font-weight: 700; }}
#Kbd {{ background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 6px; padding: 1px 6px;
       font-size: 11.5px; font-weight: 600; color: {TEXT_2}; }}

/* format choices */
#Choice {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; text-align: left;
          min-height: 64px; padding: 0; }}
#Choice:hover {{ border-color: #3D3A4E; background: {SURFACE}; }}
#Choice:checked {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(124,92,255,0.18),
                  stop:1 rgba(124,92,255,0.06)); border: 1px solid rgba(155,123,255,0.75); }}
#ChoiceIcon {{ background: {SURFACE_2}; border-radius: 10px; }}
#ChoiceIcon[on="true"] {{ background: {GRADIENT}; }}
#ChoiceName {{ font-size: 14.5px; font-weight: 600; background: transparent; }}
#ChoiceDesc {{ font-size: 12px; color: {MUTED}; background: transparent; }}

#Pill {{ background: transparent; border: 1px solid {BORDER_2}; border-radius: 15px; color: {TEXT_2};
        padding: 0 13px; min-height: 30px; max-height: 30px; font-size: 12.5px; font-weight: 600; }}
#Pill:hover {{ border-color: #4A4757; }}
#Pill:checked {{ background: {GRADIENT}; border: 0; color: white; }}

/* trim */
#TimeBox {{ background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 8px; padding: 0 8px;
           min-height: 32px; max-height: 32px; font-weight: 600; font-size: 14px; }}
#TimeBox:focus {{ border-color: {ACCENT}; }}
#TimeBox[bad="true"] {{ border-color: {RED}; }}

QCheckBox {{ spacing: 10px; background: transparent; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; border: 1px solid #4A4757; background: {SURFACE_2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url(:/clipnest/check.svg); }}
#Switch::indicator {{ width: 36px; height: 20px; border: 0; border-radius: 10px; image: url(:/clipnest/switch-off.svg); background: transparent; }}
#Switch::indicator:checked {{ image: url(:/clipnest/switch-on.svg); background: transparent; }}

QProgressBar {{ background: {SURFACE_2}; border: 0; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ background: {GRADIENT}; border-radius: 3px; }}

QLineEdit {{ background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 8px; padding: 0 10px;
            min-height: 34px; selection-background-color: {ACCENT}; }}
QComboBox {{
    background: {SURFACE_2}; border: 1px solid {BORDER_2}; border-radius: 9px;
    padding: 0 12px; min-height: 40px; min-width: 240px;
}}
QComboBox::drop-down {{ border: 0; width: 28px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER_2}; selection-background-color: {ACCENT};
    outline: 0; padding: 4px;
}}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER_2}; padding: 6px; }}
QMessageBox {{ background: {SURFACE}; }}
"""
