"""Clipnest's main window (the "Midnight" design)."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    QEvent, QPointF, QProcess, QProcessEnvironment, QRectF, QSize, Qt, QThread, QTimer, QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame,
    QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
    QVBoxLayout, QWidget,
)

from . import __version__, browsers, engine, theme
from .downloads import DownloadManager, Job
from .jobs import (
    MP3_QUALITIES, MP4_QUALITIES, JobOptions, MediaInfo, check_clip, detect_source,
    format_duration, format_time, friendly_error, info_args, parse_info, parse_time,
    unsupported_reason,
)
from .store import History, Settings

QUALITY_LABELS = {
    "mp3": {"320": ("320 kbps", "Best"), "256": ("256 kbps", ""),
            "192": ("192 kbps", ""), "128": ("128 kbps", "Smaller")},
    "mp4": {"2160": ("4K · 2160p", "Best"), "1440": ("1440p", ""),
            "1080": ("1080p", "Full HD"), "720": ("720p", "")},
}
PILL_LABELS = {"mp3": {"320": "320 kbps", "256": "256", "192": "192", "128": "128"},
               "mp4": {"2160": "4K", "1440": "1440p", "1080": "1080p", "720": "720p"}}
FORMAT_ICONS = {"mp3": "music", "mp4": "video", "image": "image", "thumbnail": "image"}
CHROMIUM = {"chrome", "edge", "brave", "opera", "opera_gx", "vivaldi", "chromium"}
THUMB_W, THUMB_H = 250, 141


def format_label(fmt: str, quality: str) -> str:
    """'MP3 · 320 kbps', 'MP4 · 1080p', 'Thumbnail · JPG' or 'Image · original'."""
    if fmt == "mp3":
        return f"MP3 · {quality} kbps"
    if fmt == "image":
        return "Image · original"
    if fmt == "thumbnail":
        return "Thumbnail · JPG"
    return "MP4 · " + QUALITY_LABELS["mp4"].get(quality, (quality,))[0]


def short_label(fmt: str, quality: str) -> str:
    """Compact version for the Downloads panel: 'MP3', 'MP4 4K', 'Thumbnail'."""
    if fmt == "mp4":
        return "MP4 " + PILL_LABELS["mp4"].get(quality, quality)
    return {"mp3": "MP3", "thumbnail": "Thumbnail", "image": "Image"}.get(fmt, fmt.upper())


def clip_text(start: float | None, end: float | None) -> str:
    if start is None:
        return ""
    return f"{format_time(start)} – {format_time(end)}" if end is not None else \
        f"from {format_time(start)}"


# -- small helpers ------------------------------------------------------------

def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def icon_label(name: str, color: str = theme.TEXT_2, size: int = 18, stroke: float = 2.0) -> QLabel:
    lb = QLabel()
    lb.setPixmap(theme.icon(name, color, size, stroke).pixmap(size, size))
    lb.setFixedSize(size, size)
    lb.setStyleSheet("background: transparent;")
    return lb


def vbox(*widgets, spacing: int = 0, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        elif w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


def hbox(*widgets, spacing: int = 0, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        elif w is None:
            lay.addStretch(1)
        elif isinstance(w, QWidget):
            lay.addWidget(w)
        else:
            lay.addLayout(w)
    return lay


def frame(name: str, layout=None) -> QFrame:
    f = QFrame()
    f.setObjectName(name)
    if layout is not None:
        f.setLayout(layout)
    return f


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


def glow(widget: QWidget, color: str = "#7C5CFF", alpha: int = 110, blur: int = 34, dy: int = 10) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    c = QColor(color)
    c.setAlpha(alpha)
    effect.setColor(c)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    widget.setGraphicsEffect(effect)


def icon_button(name: str, tip: str, size: int = 15) -> QPushButton:
    b = QPushButton()
    b.setObjectName("IconButton")
    b.setIcon(theme.icon(name, theme.TEXT_2, size))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def switch(text: str) -> QCheckBox:
    box = QCheckBox(text)
    box.setObjectName("Switch")
    box.setCursor(Qt.PointingHandCursor)
    return box


def show_in_folder(path: str) -> None:
    p = Path(path)
    if engine.IS_WINDOWS and p.exists():
        subprocess.Popen(["explorer", "/select,", str(p)])
    elif engine.IS_MAC and p.exists():
        subprocess.Popen(["open", "-R", str(p)])    # reveal in Finder
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent if p.is_file() else p)))


def open_file(path: str) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def _rounded(px: QPixmap, radius: float) -> QPixmap:
    out = QPixmap(px.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, px.width(), px.height(), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, px)
    p.end()
    return out


def _height_name(h: int) -> str:
    if h >= 2160:
        return "4K"
    if h >= 1440:
        return "1440p"
    return f"{h}p"


def folder_name(path: str) -> str:
    return Path(path).name or path


# -- engine setup / update in the background ---------------------------------

class EngineWorker(QThread):
    progress = Signal(str, float)
    done = Signal(bool, str)

    def __init__(self, update: bool, parent=None):
        super().__init__(parent)
        self.update = update

    def run(self):
        try:
            if engine.missing_parts():
                engine.install_missing(lambda text, frac: self.progress.emit(text, frac))
            if self.update:
                self.progress.emit("Checking for engine updates", -1)
                engine.update_ytdlp()
            self.done.emit(True, engine.ytdlp_version() or "")
        except Exception as exc:  # network errors, disk full, …
            self.done.emit(False, str(exc))


# -- custom-drawn widgets -----------------------------------------------------

class GlowBackground(QWidget):
    """The deep background with a soft violet glow at the top."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        w, h = self.width(), self.height()
        g = QRadialGradient(QPointF(w * 0.36, -40), max(w * 0.55, 420))
        g.setColorAt(0, QColor(124, 92, 255, 52))
        g.setColorAt(1, QColor(124, 92, 255, 0))
        p.fillRect(self.rect(), g)
        g2 = QRadialGradient(QPointF(w, h), max(w * 0.4, 300))
        g2.setColorAt(0, QColor(180, 107, 255, 16))
        g2.setColorAt(1, QColor(180, 107, 255, 0))
        p.fillRect(self.rect(), g2)


class Ring(QWidget):
    """Round progress for a download, with the format icon inside."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(38, 38)
        self.fraction = 0.0
        self.state = "running"
        self.icon_name = "video"

    def set(self, fraction: float, state: str, icon_name: str) -> None:
        self.fraction, self.state, self.icon_name = fraction, state, icon_name
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(3, 3, 32, 32)
        if self.state in ("done", "error", "cancelled"):
            color = {"done": QColor(61, 220, 151, 34), "error": QColor(255, 122, 133, 34)}.get(
                self.state, QColor(theme.SURFACE_2))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QRectF(0, 0, 38, 38))
            name, col = {"done": ("check", theme.GREEN), "error": ("alert", theme.RED)}.get(
                self.state, ("close", theme.MUTED))
            p.drawPixmap(10, 10, theme.icon(name, col, 18, 2.5).pixmap(18, 18))
            return
        p.setPen(QPen(QColor("#2A2836"), 3))
        p.drawEllipse(r)
        if self.fraction > 0:
            g = QLinearGradient(0, 0, 38, 38)
            g.setColorAt(0, QColor(theme.ACCENT))
            g.setColorAt(1, QColor(theme.ACCENT_2))
            pen = QPen(g, 3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(r, 90 * 16, -int(360 * 16 * min(1.0, self.fraction)))
        p.drawPixmap(11, 11, theme.icon(self.icon_name, theme.TEXT_2, 16).pixmap(16, 16))


class Timeline(QWidget):
    """The whole video as a bar; drag the two handles to choose the part."""
    range_changed = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(40)
        self.setMaximumHeight(40)
        self.setCursor(Qt.SizeHorCursor)
        self.duration = 0.0
        self.start, self.end = 0.0, 0.0
        self._drag: str | None = None
        self.setAccessibleName("Part of the video to download")

    def set_duration(self, d: float) -> None:
        self.duration = max(0.0, d or 0.0)
        self.update()

    def set_range(self, start: float, end: float) -> None:
        self.start, self.end = start, end
        self.update()

    def _x(self, t: float) -> float:
        return 0 if not self.duration else t / self.duration * self.width()

    def _t(self, x: float) -> float:
        return 0 if not self.width() else max(0.0, min(1.0, x / self.width())) * self.duration

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, w, h, 9, 9)
        p.setClipPath(clip)
        g = QLinearGradient(0, 0, w, 0)
        for at, c in ((0, "#2E2357"), (0.35, "#5A2E5C"), (0.7, "#7A3F52"), (1, "#30245A")):
            g.setColorAt(at, QColor(c))
        p.fillRect(0, 0, w, h, g)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        for x in range(0, w, 32):
            p.drawLine(x, 0, x, h)
        if not self.duration:
            return
        x1, x2 = self._x(self.start), self._x(self.end)
        p.fillRect(QRectF(0, 0, x1, h), QColor(8, 7, 14, 170))
        p.fillRect(QRectF(x2, 0, w - x2, h), QColor(8, 7, 14, 170))
        p.setClipping(False)
        p.setPen(QPen(QColor("#9B7BFF"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(x1, 1, max(2, x2 - x1), h - 2), 8, 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        for x in (x1, x2):
            p.drawRoundedRect(QRectF(x - 4, 7, 8, h - 14), 4, 4)

    def mousePressEvent(self, e):
        if not self.duration:
            return
        x = e.position().x()
        self._drag = "start" if abs(x - self._x(self.start)) <= abs(x - self._x(self.end)) else "end"
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        t = round(self._t(e.position().x()))
        if self._drag == "start":
            self.start = min(t, self.end - 1)
        else:
            self.end = max(t, self.start + 1)
        self.start, self.end = max(0.0, self.start), min(self.duration, self.end)
        self.update()
        self.range_changed.emit(self.start, self.end)

    def mouseReleaseEvent(self, e):
        self._drag = None


class TabButton(QPushButton):
    def __init__(self, icon_name: str, text: str):
        super().__init__("  " + text)
        self.setObjectName("Tab")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIcon(theme.icon(icon_name, theme.TEXT_2, 16))
        self.setIconSize(QSize(16, 16))
        self.badge = label("", "Badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.hide()
        self.setLayout(hbox(None, self.badge, margins=(0, 0, 8, 0)))
        self._text = text

    def set_badge(self, n: int) -> None:
        self.badge.setText(str(n))
        self.badge.setVisible(n > 0)
        # Room for the badge so it never covers the text.
        self.setText("  " + self._text + ("        " if n > 0 else ""))


class ChoiceCard(QPushButton):
    def __init__(self, icon_name: str, name: str, desc: str):
        super().__init__()
        self.setObjectName("Choice")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.icon_box = QLabel()
        self.icon_box.setObjectName("ChoiceIcon")
        self.icon_box.setFixedSize(38, 38)
        self.icon_box.setAlignment(Qt.AlignCenter)
        self.icon_name = icon_name
        self.name = label(name, "ChoiceName")
        self.desc = label(desc, "ChoiceDesc")
        for w in (self.icon_box, self.name, self.desc):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setLayout(hbox(self.icon_box, 12, vbox(self.name, 1, self.desc), None,
                            margins=(13, 12, 13, 12)))
        self.toggled.connect(self._sync)
        self._sync(False)

    def set_text(self, name: str, desc: str) -> None:
        self.name.setText(name)
        self.desc.setText(desc)
        self.setAccessibleName(f"{name}: {desc}")

    def _sync(self, on: bool) -> None:
        self.icon_box.setProperty("on", "true" if on else "false")
        self.icon_box.setPixmap(theme.icon(self.icon_name, "#FFFFFF" if on else theme.TEXT_2, 18)
                                .pixmap(18, 18))
        repolish(self.icon_box)


class DownloadRow(QFrame):
    def __init__(self, job: Job, manager: DownloadManager):
        super().__init__()
        self.setObjectName("Card")
        self.job, self.manager = job, manager
        self.ring = Ring()
        self.title = label("", None)
        self.title.setStyleSheet("font-weight: 600; font-size: 13.5px; background: transparent;")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status = label("", "Small")
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.cancel_btn = icon_button("close", "Cancel download")
        self.cancel_btn.clicked.connect(lambda: self.manager.cancel(self.job))
        self.open_btn = icon_button("play", "Open")
        self.open_btn.clicked.connect(lambda: self.job.files and open_file(self.job.files[-1]))
        self.folder_btn = icon_button("folder", "Show in folder")
        self.folder_btn.clicked.connect(self._open_folder)
        text = vbox(self.title, 2, self.status)
        lay = hbox(self.ring, 11, text, 8, self.open_btn, 6, self.folder_btn, 6, self.cancel_btn,
                   margins=(11, 10, 11, 10))
        lay.setStretch(2, 1)
        self.setLayout(lay)
        self.refresh()

    def _open_folder(self):
        show_in_folder(self.job.files[-1] if self.job.files else self.job.opts.out_dir)

    def refresh(self) -> None:
        j = self.job
        title = j.title
        if j.opts.clip_start is not None and j.opts.fmt in ("mp3", "mp4"):
            title += f" ({clip_text(j.opts.clip_start, j.opts.clip_end)})"
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(title, Qt.ElideRight, max(self.title.width(), 120)))
        self.title.setToolTip(title)
        status = f"{short_label(j.opts.fmt, j.opts.quality)} · {j.status}"
        error = j.state == "error"
        self.status.setText(status if error else self.status.fontMetrics().elidedText(
            status, Qt.ElideRight, max(self.status.width(), 120)))
        self.status.setToolTip(f"{format_label(j.opts.fmt, j.opts.quality)} · {j.status}")
        self.status.setObjectName("Error" if error else "Small")
        self.status.setWordWrap(error)
        repolish(self.status)
        icon_name = FORMAT_ICONS.get(j.opts.fmt, "video")
        self.ring.set(j.fraction, j.state, icon_name)
        done = j.state == "done"
        self.cancel_btn.setVisible(j.state in ("queued", "running"))
        self.folder_btn.setVisible(done)
        self.open_btn.setVisible(done and len(j.files) == 1)
        self.open_btn.setIcon(theme.icon("image" if j.opts.fmt in ("image", "thumbnail") else "play",
                                         theme.TEXT_2, 15))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.refresh()


# -- pages --------------------------------------------------------------------

def scroll(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    inner.setObjectName("Page")
    area.setWidget(inner)
    area.viewport().setAutoFillBackground(False)
    return area


def centered(content_layout, max_width: int = 900, margins=(30, 26, 30, 30)) -> QWidget:
    content = QWidget()
    content.setObjectName("Page")
    content.setMaximumWidth(max_width)
    content.setLayout(content_layout)
    outer = QWidget()
    outer.setObjectName("Page")
    lay = hbox(None, content, None, margins=margins)
    lay.setStretch(1, 100)
    outer.setLayout(lay)
    return outer


class DownloadPage(QWidget):
    def __init__(self, settings: Settings, manager: DownloadManager):
        super().__init__()
        self.settings, self.manager = settings, manager
        self.info: MediaInfo | None = None
        self.info_url = ""
        self.choice = settings["format"] if settings["format"] in ("mp3", "mp4") else "mp3"
        self.image_mode = False        # a Pinterest image pin: save the picture
        self.info_proc: QProcess | None = None
        self.net = QNetworkAccessManager(self)
        self.rows: dict[int, DownloadRow] = {}
        self.engine_ready = False
        self._clip_ok = True

        # Engine setup banner
        self.setup_text = label("Setting up the download engine…", "Small", wrap=True)
        self.setup_bar = QProgressBar()
        self.setup_bar.setRange(0, 1000)
        self.setup_bar.setTextVisible(False)
        self.setup_box = frame("Card", vbox(self.setup_text, 8, self.setup_bar, margins=(16, 14, 16, 14)))

        # Hero (shown until a link is pasted)
        self.hero_title = label(f"Paste a link. <span style='color:{theme.ACCENT_SOFT}'>Get the file.</span>", "Hero")
        self.hero_title.setAlignment(Qt.AlignCenter)
        self.hero_sub = label("MP3 up to 320 kbps · MP4 up to 4K · thumbnails · any part of a video", "Sub")
        self.hero_sub.setAlignment(Qt.AlignCenter)
        sites = hbox(spacing=8)
        sites.addStretch(1)
        for name, color in (("YouTube", "#FF4E45"), ("Instagram", "#E1306C"), ("Facebook", "#1877F2"),
                            ("X", "#E7E7EA"), ("Vimeo", "#1AB7EA"), ("Pinterest", "#E60023")):
            sites.addWidget(label(f"<span style='color:{color}'>●</span>&nbsp; {name}", "SiteChip"))
        sites.addStretch(1)
        self.hero_sites = QWidget()
        self.hero_sites.setLayout(sites)
        paste_key = "Cmd" if engine.IS_MAC else "Ctrl"
        self.hero_tip = label(f"Tip: copy a link anywhere and Clipnest fills it in, or press "
                              f"<span style='color:{theme.TEXT_2}'><b>{paste_key} + V</b></span>", "Small")
        self.hero_tip.setAlignment(Qt.AlignCenter)

        # Paste box
        self.link = QLineEdit()
        self.link.setObjectName("LinkInput")
        self.link.setPlaceholderText("Paste a YouTube, Instagram or other link")
        self.link.setClearButtonEnabled(True)
        self.link.setAccessibleName("Link")
        self.link.installEventFilter(self)
        self.paste_btn = QPushButton("  Paste")
        self.paste_btn.setIcon(theme.icon("paste", "#FFFFFF", 17))
        self.paste_btn.setObjectName("Grad")
        self.paste_btn.setCursor(Qt.PointingHandCursor)
        self.paste_btn.clicked.connect(self.paste)
        self.paste_box = frame("PasteBox", hbox(icon_label("link", theme.MUTED), 12, self.link, 10,
                                                self.paste_btn, margins=(18, 7, 7, 7)))
        self.paste_box.setFixedHeight(58)
        glow(self.paste_box, alpha=60, blur=40, dy=12)
        self.link_error = label("", "Error", wrap=True)
        self.link_error.hide()

        # Preview card
        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.duration = label("", "Duration")
        self.duration.setParent(self.thumb)
        self.thumb_save = QPushButton("  Save thumbnail", self.thumb)
        self.thumb_save.setObjectName("ThumbSave")
        self.thumb_save.setIcon(theme.icon("image", "#FFFFFF", 13))
        self.thumb_save.setIconSize(QSize(13, 13))
        self.thumb_save.setCursor(Qt.PointingHandCursor)
        self.thumb_save.clicked.connect(lambda: self.start(force="thumbnail"))
        self.chip_source = label("", "Chip")
        self.chip_kind = label("", "Chip")
        self.chip_quality = label("", "Chip")
        self.media_title = label("", "MediaTitle", wrap=True)
        self.media_meta = label("", "Muted", wrap=True)
        self.pill_row = QHBoxLayout()
        self.pill_row.setSpacing(8)
        self.pill_group = QButtonGroup(self)
        self.pills: dict[str, QPushButton] = {}
        self.pill_hint = label("", "Small")
        self.pill_box = QWidget()
        self.pill_box.setLayout(hbox(self.pill_row, 10, self.pill_hint, None))
        info_col = vbox(hbox(self.chip_source, 6, self.chip_kind, 6, self.chip_quality, None), 8,
                        self.media_title, 4, self.media_meta, None, self.pill_box)

        # MP3 / MP4 / Thumbnail
        self.card_mp3 = ChoiceCard("music", "MP3 audio", "Cover art & tags")
        self.card_mp4 = ChoiceCard("video", "MP4 video", "Up to 4K, with sound")
        self.card_thumb = ChoiceCard("image", "Thumbnail", "Best size, JPG")
        group = QButtonGroup(self)
        for c, key in ((self.card_mp3, "mp3"), (self.card_mp4, "mp4"), (self.card_thumb, "thumbnail")):
            group.addButton(c)
            c.clicked.connect(lambda _=False, k=key: self.set_choice(k))
        choices = hbox(self.card_mp3, 10, self.card_mp4, 10, self.card_thumb)

        # Only part of it
        self.trim_on = switch("")
        self.trim_on.setAccessibleName("Download only part of it")
        self.trim_on.toggled.connect(self.on_trim_toggled)
        self.time_from = QLineEdit()
        self.time_to = QLineEdit()
        for t, name in ((self.time_from, "Start"), (self.time_to, "End")):
            t.setObjectName("TimeBox")
            t.setFixedWidth(84)
            t.setAlignment(Qt.AlignCenter)
            t.setAccessibleName(f"{name} time")
            t.textEdited.connect(self.on_times_typed)
        self.time_to.setPlaceholderText("end")
        self.clip_len = label("", "Small")
        self.timeline = Timeline()
        self.timeline.range_changed.connect(self.on_timeline)
        self.tl_start = label("0:00", "Small")
        self.tl_end = label("", "Small")
        self.clip_error = label("", "Error")
        self.clip_error.hide()
        self.trim_body = QWidget()
        self.trim_body.setLayout(vbox(10, self.timeline, 5, hbox(self.tl_start, None, self.tl_end),
                                      self.clip_error))
        self.trim_times = QWidget()
        self.trim_times.setLayout(hbox(self.time_from, 8, label("to", "Muted"), 8, self.time_to, 10,
                                       self.clip_len))
        trim_title = label("Only part of it", None)
        trim_title.setStyleSheet("font-weight: 600; background: transparent;")
        self.trim = frame("Card", vbox(
            hbox(icon_label("scissors", theme.ACCENT_SOFT), 10, trim_title, None, self.trim_times, 12,
                 self.trim_on),
            self.trim_body, margins=(14, 12, 14, 12)))

        # Options + Download
        self.opt_tags = switch("Cover art && tags")
        self.opt_tags.setChecked(settings["cover_art"] and settings["tags"])
        self.opt_tags.toggled.connect(lambda on: (self.settings.set("cover_art", on),
                                                  self.settings.set("tags", on)))
        self.opt_subs = switch("Subtitles")
        self.opt_subs.setChecked(settings["subtitles"])
        self.opt_subs.toggled.connect(lambda on: self.settings.set("subtitles", on))
        self.opt_playlist = switch("Whole playlist")
        self.opt_playlist.setChecked(settings["playlist"])
        self.opt_playlist.toggled.connect(lambda on: (self.settings.set("playlist", on),
                                                      self.refresh_mode()))
        self.go = QPushButton()
        self.go.setObjectName("Go")
        self.go.setIcon(theme.icon("download", "#FFFFFF", 20, 2.2))
        self.go.setIconSize(QSize(20, 20))
        self.go.setCursor(Qt.PointingHandCursor)
        self.go.clicked.connect(lambda: self.start())
        glow(self.go, alpha=120, blur=40, dy=12)
        opts = vbox(self.opt_tags, self.opt_subs, self.opt_playlist, spacing=8)
        bottom = hbox(opts, 18, self.go)
        bottom.setStretch(2, 1)

        self.result = frame("Panel", vbox(
            hbox(self.thumb, 18, info_col), 16, choices, 12, self.trim, 14, bottom,
            margins=(16, 16, 16, 16)))
        self.result.hide()

        # Work area: hero or result, vertically centred when empty
        self.space_top = QWidget()
        self.space_bottom = QWidget()
        for s in (self.space_top, self.space_bottom):
            s.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.paste_row = hbox(None, self.paste_box, None)
        work = vbox(self.space_top, self.setup_box, 4, self.hero_title, 8, self.hero_sub, 22,
                    self.paste_row, 8, self.link_error, 10, self.hero_sites, 14, self.hero_tip,
                    12, self.result, self.space_bottom)
        self.paste_row.setStretch(1, 100)

        # Downloads rail
        clear = QPushButton("Clear finished")
        clear.setObjectName("LinkButton")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self.clear_finished)
        rail_title = label("Downloads", None)
        rail_title.setStyleSheet("font-size: 15px; font-weight: 700; background: transparent;")
        self.list_box = vbox(spacing=10)
        list_inner = QWidget()
        list_inner.setLayout(vbox(self.list_box, None))
        self.empty = QWidget()
        nothing = label("Nothing yet", None)
        nothing.setStyleSheet(f"font-weight: 600; color: {theme.TEXT_2}; background: transparent;")
        nothing.setAlignment(Qt.AlignCenter)
        hint = label("Your downloads appear here.", "Small")
        hint.setAlignment(Qt.AlignCenter)
        arrow = icon_label("download", theme.ACCENT_SOFT, 28, 2.2)
        self.empty.setLayout(vbox(None, hbox(None, arrow, None), 8, nothing, 2, hint, None))
        self.save_btn = QPushButton()
        self.save_btn.setObjectName("LinkButton")
        self.save_btn.setIcon(theme.icon("folder", theme.MUTED, 14))
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setToolTip("Change where files are saved")
        self.save_btn.clicked.connect(self.change_dir)
        foot = frame("Transparent", hbox(self.save_btn, None, margins=(0, 10, 0, 0)))
        foot.setStyleSheet(f"#Transparent {{ border-top: 1px solid {theme.BORDER}; }}")
        self.rail_scroll = scroll(list_inner)
        rail = frame("Rail", vbox(hbox(rail_title, None, clear), 12, self.rail_scroll, self.empty,
                                  foot, margins=(18, 20, 18, 14)))
        rail.setFixedWidth(330)

        page = GlowBackground()
        page.setLayout(hbox(scroll(centered(work)), rail))
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(page)

        self.fetch_timer = QTimer(self, singleShot=True, interval=500)
        self.fetch_timer.timeout.connect(self.fetch_info)
        self.link.textChanged.connect(self.on_link_changed)
        self.link.returnPressed.connect(lambda: self.start())
        manager.job_added.connect(self.add_row)
        manager.job_changed.connect(lambda j: j.id in self.rows and self.rows[j.id].refresh())

        self.set_choice(self.choice)
        self.set_engine_ready(False)
        self.show_result(False)
        self.rail_scroll.hide()

    # -- engine
    def set_engine_progress(self, text: str, frac: float) -> None:
        self.setup_box.show()
        self.setup_text.setText(text + ("…" if frac < 0 else f"… {frac * 100:.0f}%"))
        if frac < 0:
            self.setup_bar.setRange(0, 0)
        else:
            self.setup_bar.setRange(0, 1000)
            self.setup_bar.setValue(int(frac * 1000))

    def set_engine_ready(self, ready: bool, error: str = "") -> None:
        self.engine_ready = ready
        if ready:
            self.setup_box.hide()
        elif error:
            self.setup_box.show()
            self.setup_text.setText("Couldn't set up the download engine: " + error +
                                    "\nCheck your internet connection and restart Clipnest.")
            self.setup_text.setObjectName("Error")
            repolish(self.setup_text)
            self.setup_bar.hide()
        else:
            self.setup_box.hide()
        self.update_button()
        if ready and self.link.text().strip():
            self.fetch_info()

    # -- layout states
    def show_result(self, on: bool) -> None:
        for w in (self.hero_title, self.hero_sub, self.hero_sites, self.hero_tip, self.space_top):
            w.setVisible(not on)
        self.result.setVisible(on)
        self.paste_box.setMaximumWidth(16777215 if on else 680)

    # -- choice, quality, options
    def fmt(self) -> str:
        if self.image_mode:
            return "image"
        return self.choice

    def set_choice(self, key: str) -> None:
        self.choice = key
        if key in ("mp3", "mp4"):
            self.settings.set("format", key)
        {"mp3": self.card_mp3, "mp4": self.card_mp4, "thumbnail": self.card_thumb}[key].setChecked(True)
        self.build_pills()
        self.refresh_mode()

    def build_pills(self) -> None:
        for btn in self.pills.values():
            self.pill_group.removeButton(btn)
            btn.deleteLater()
        self.pills = {}
        fmt = self.choice
        if fmt not in ("mp3", "mp4"):
            return
        current = self.settings[f"{fmt}_quality"]
        for q in (MP3_QUALITIES if fmt == "mp3" else MP4_QUALITIES):
            btn = QPushButton(PILL_LABELS[fmt][q])
            btn.setObjectName("Pill")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setChecked(q == current)
            btn.clicked.connect(lambda _=False, q=q: self.set_quality(q))
            self.pill_group.addButton(btn)
            self.pill_row.addWidget(btn)
            self.pills[q] = btn
        self.pill_hint.setText("MP3 quality" if fmt == "mp3" else "MP4 quality")

    def set_quality(self, q: str) -> None:
        self.settings.set(f"{self.choice}_quality", q)
        self.update_button()

    def refresh_mode(self) -> None:
        """Shows the controls that fit the link and the chosen format."""
        fmt, img = self.fmt(), self.image_mode
        info = self.info if self.info_url == self.link.text().strip() else None
        playlist = bool(info and info.is_playlist)
        self.card_mp3.setVisible(not img)
        self.card_mp4.setVisible(not img)
        if img:
            size = info.image_size if info else None
            self.card_thumb.set_text("Image", f"Original, {size[0]} × {size[1]}" if size else "Original size")
            self.card_thumb.setChecked(True)
        else:
            self.card_thumb.set_text("Thumbnail", "Best size, JPG")
        self.pill_box.setVisible(fmt in ("mp3", "mp4"))
        self.thumb_save.setVisible(not img and bool(info) and not playlist)
        can_trim = fmt in ("mp3", "mp4") and not playlist and bool(info and info.duration) \
            and not self.opt_playlist.isChecked()
        self.trim.setVisible(can_trim)
        self.opt_tags.setVisible(fmt == "mp3")
        self.opt_subs.setVisible(fmt == "mp4")
        self.opt_playlist.setVisible(playlist)
        self.save_btn.setText(f"  Saving to {folder_name(self.settings[self.dir_key() + '_dir'])}")
        self.update_clip()

    def dir_key(self) -> str:
        return "mp3" if self.fmt() == "mp3" else "mp4"     # videos and pictures together

    # -- only part of it
    def on_trim_toggled(self, on: bool) -> None:
        if on and self.info and self.info.duration and not self.time_from.text():
            d = self.info.duration
            start, end = (0.0, d) if d <= 60 else (min(60.0, d / 4), min(d, min(60.0, d / 4) + 60))
            self.time_from.setText(format_time(start))
            self.time_to.setText(format_time(end))
        self.update_clip()

    def on_times_typed(self, _text: str) -> None:
        self.update_clip()

    def on_timeline(self, start: float, end: float) -> None:
        self.time_from.setText(format_time(start))
        self.time_to.setText(format_time(end))
        self.update_clip(from_timeline=True)

    def clip(self) -> tuple[float | None, float | None]:
        if not (self.trim.isVisible() or self.trim.isVisibleTo(self.result)) or not self.trim_on.isChecked():
            return None, None
        return parse_time(self.time_from.text()), (parse_time(self.time_to.text())
                                                   if self.time_to.text().strip() else None)

    def update_clip(self, from_timeline: bool = False) -> None:
        on = self.trim_on.isChecked() and self.trim.isVisibleTo(self.result)
        self.trim_body.setVisible(on)
        self.trim_times.setVisible(on)
        self._clip_ok = True
        if on:
            duration = self.info.duration if self.info else None
            start, end = self.clip()
            problem = check_clip(start, end, duration)
            bad_to = bool(problem) and "end" in problem.lower()
            for t, bad in ((self.time_from, bool(problem) and not bad_to), (self.time_to, bad_to)):
                t.setProperty("bad", "true" if bad else "false")
                repolish(t)
            self.clip_error.setText(problem)
            self.clip_error.setVisible(bool(problem))
            self._clip_ok = not problem
            if not problem and start is not None:
                stop = end if end is not None else (duration or start)
                self.clip_len.setText(f"Clip {format_time(stop - start)}")
                if duration and not from_timeline:
                    self.timeline.set_range(start, stop)
            else:
                self.clip_len.setText("")
            if duration:
                self.timeline.set_duration(duration)
                self.tl_end.setText(format_time(duration))
        self.update_button()

    def update_button(self) -> None:
        fmt = self.fmt()
        if fmt == "image":
            size = self.info.image_size if self.info else None
            text = "Download image · original" + (f" ({size[0]} × {size[1]})" if size else "")
        elif fmt == "thumbnail":
            text = "Download thumbnail · JPG"
        else:
            q = self.settings[f"{fmt}_quality"]
            text = f"Download {fmt.upper()} · {QUALITY_LABELS[fmt][q][0]}"
            start, end = self.clip()
            if start is not None and self._clip_ok:
                text += f" · {clip_text(start, end)}"
        self.go.setText("  " + text)
        self.go.setEnabled(self.engine_ready and self._clip_ok)

    def change_dir(self) -> None:
        key = self.dir_key()
        d = QFileDialog.getExistingDirectory(self, "Save downloads to", self.settings[f"{key}_dir"])
        if d:
            self.settings.set(f"{key}_dir", d)
            self.refresh_mode()

    # -- link & preview
    def eventFilter(self, obj, event):
        if obj is self.link and event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            self.paste_box.setProperty("focused", "true" if event.type() == QEvent.FocusIn else "false")
            repolish(self.paste_box)
        return super().eventFilter(obj, event)

    def paste(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if text:
            self.link.setText(text)

    def offer_clipboard(self) -> None:
        """Called when the window gets focus: picks up a freshly copied link."""
        if not self.settings["auto_paste"] or self.link.text().strip():
            return
        text = QGuiApplication.clipboard().text().strip()
        if text and " " not in text and detect_source(text) and text != getattr(self, "_last_clip", ""):
            self._last_clip = text
            self.link.setText(text)

    def on_link_changed(self, text: str) -> None:
        self.link_error.hide()
        if not text.strip():
            self.info = None
            self.info_url = ""
            self.show_result(False)
        self.image_mode = False
        self.trim_on.setChecked(False)
        self.time_from.clear()
        self.time_to.clear()
        self.fetch_timer.start()

    def fetch_info(self) -> None:
        url = self.link.text().strip()
        if not url or not detect_source(url) or not self.engine_ready or url == self.info_url:
            return
        if reason := unsupported_reason(url):
            self.show_link_error(url, reason)
            return
        if self.info_proc is not None:
            self.info_proc.kill()
        self.info_url = url
        self.info = None
        self.show_preview_loading(url)
        proc = QProcess(self)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        proc.setProcessEnvironment(env)
        deno = engine.deno_path()
        args = info_args(str(engine.ytdlp_path()), url,
                         browsers.cookies_arg(self.settings["cookies_browser"]),
                         str(deno) if deno else "")
        proc.finished.connect(lambda code, _s, p=proc, u=url: self.on_info(p, u, code))
        proc.errorOccurred.connect(lambda err, p=proc, u=url: self.on_info_error(p, u, err))
        self.info_proc = proc
        proc.start(args[0], args[1:])
        # A lookup that hangs (network trouble) must not spin forever.
        QTimer.singleShot(90_000, lambda p=proc, u=url: self.on_info_timeout(p, u))

    def on_info_error(self, proc: QProcess, url: str, err) -> None:
        if err == QProcess.FailedToStart and proc is self.info_proc:
            self.info_proc = None
            self.show_link_error(url, "Couldn't start the download engine. Restart Clipnest.")

    def on_info_timeout(self, proc: QProcess, url: str) -> None:
        if proc is self.info_proc and proc.state() != QProcess.NotRunning:
            self.info_proc = None
            proc.kill()
            self.show_link_error(url, "Looking up this link took too long. You can still "
                                      "press Download to try anyway.")

    def show_link_error(self, url: str, text: str) -> None:
        if url != self.link.text().strip():
            return
        self.info_url = ""
        self.show_result(False)
        self.link_error.setText(text)
        self.link_error.show()

    def show_preview_loading(self, url: str) -> None:
        self.show_result(True)
        self.chip_source.setText(detect_source(url) or "Link")
        self.chip_source.setObjectName("ChipRed" if detect_source(url) in ("YouTube", "YouTube Music") else "Chip")
        repolish(self.chip_source)
        self.chip_kind.setText("Looking up…")
        self.chip_quality.hide()
        self.media_title.setText("Getting details…")
        self.media_meta.setText("")
        self.duration.hide()
        self.thumb_save.hide()
        self.thumb.setPixmap(theme.icon("play", theme.MUTED, 28).pixmap(28, 28))
        self.refresh_mode()

    def on_info(self, proc: QProcess, url: str, code: int) -> None:
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        err = bytes(proc.readAllStandardError()).decode("utf-8", "replace")
        proc.deleteLater()
        if proc is self.info_proc:
            self.info_proc = None
        if url != self.link.text().strip():
            return
        if code != 0 or not out.strip():
            self.show_link_error(url, friendly_error(err or "Couldn't read this link."))
            return
        try:
            info = parse_info(out)
        except ValueError:
            self.show_link_error(url, "Couldn't read this link.")
            return
        self.info = info
        self.chip_kind.setText(info.kind)
        best = ("Up to " + _height_name(info.max_height)) if info.max_height and not info.is_playlist else ""
        self.chip_quality.setText(best)
        self.chip_quality.setVisible(bool(best))
        self.media_title.setText(info.title)
        meta = [info.uploader] if info.uploader else []
        if info.is_playlist:
            meta.append(f"{info.entries} videos")
            if not self.opt_playlist.isChecked():
                meta.append("switch on “Whole playlist” to get them all")
        elif info.image_size:
            meta.append(f"Original image, {info.image_size[0]} × {info.image_size[1]}")
        self.media_meta.setText(" · ".join(meta))
        self.image_mode = info.kind == "Image"
        dur = format_duration(info.duration)
        self.duration.setText(dur)
        self.duration.adjustSize()
        self.duration.move(THUMB_W - self.duration.width() - 8, THUMB_H - self.duration.height() - 8)
        self.duration.setVisible(bool(dur))
        self.thumb_save.adjustSize()
        self.thumb_save.move(8, THUMB_H - self.thumb_save.height() - 8)
        self.refresh_mode()
        if info.thumbnail:
            req = QNetworkRequest(QUrl(info.thumbnail))
            req.setHeader(QNetworkRequest.UserAgentHeader, "Mozilla/5.0")
            reply = self.net.get(req)
            reply.finished.connect(lambda r=reply, u=url: self.on_thumb(r, u))

    def on_thumb(self, reply: QNetworkReply, url: str) -> None:
        reply.deleteLater()
        if reply.error() != QNetworkReply.NoError or url != self.link.text().strip():
            return
        px = QPixmap()
        if px.loadFromData(bytes(reply.readAll())):
            self.set_thumbnail(px)

    def set_thumbnail(self, px: QPixmap) -> None:
        dpr = self.devicePixelRatioF()
        size = QSize(int(THUMB_W * dpr), int(THUMB_H * dpr))
        px = px.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x, y = (px.width() - size.width()) // 2, (px.height() - size.height()) // 2
        px = _rounded(px.copy(x, y, size.width(), size.height()), 12 * dpr)
        px.setDevicePixelRatio(dpr)
        self.thumb.setPixmap(px)

    # -- downloading
    def start(self, force: str = "") -> None:
        url = self.link.text().strip()
        if not self.engine_ready:
            return
        if not detect_source(url):
            self.link_error.setText("Paste a full link that starts with https://")
            self.link_error.show()
            self.link.setFocus()
            return
        if reason := unsupported_reason(url):
            self.show_link_error(url, reason)
            return
        fmt = force or self.fmt()
        if fmt in ("mp3", "mp4") and not self._clip_ok:
            return
        key = "mp3" if fmt == "mp3" else "mp4"
        out_dir = self.settings[f"{key}_dir"]
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            self.link_error.setText(f"Can't save to {out_dir}. Choose another folder.")
            self.link_error.show()
            return
        start, end = self.clip() if fmt in ("mp3", "mp4") else (None, None)
        opts = JobOptions(
            url=url, fmt=fmt, out_dir=out_dir,
            quality=self.settings[f"{fmt}_quality"] if fmt in ("mp3", "mp4") else "original",
            cover_art=self.opt_tags.isChecked(), tags=self.opt_tags.isChecked(),
            subtitles=self.opt_subs.isChecked() and fmt == "mp4",
            playlist=self.opt_playlist.isChecked() and bool(self.info and self.info.is_playlist),
            cookies_browser=browsers.cookies_arg(self.settings["cookies_browser"]),
            clip_start=start, clip_end=end,
            apple_convert=engine.IS_MAC and self.settings["apple_convert"],
        )
        title = self.info.title if self.info and self.info_url == url else url
        self.manager.add(opts, title)
        if not force:                      # "Save thumbnail" keeps the link for more
            self.link.clear()

    def add_row(self, job: Job) -> None:
        row = DownloadRow(job, self.manager)
        self.rows[job.id] = row
        self.list_box.insertWidget(0, row)
        self.empty.hide()
        self.rail_scroll.show()

    def clear_finished(self) -> None:
        for jid, row in list(self.rows.items()):
            if row.job.state in ("done", "error", "cancelled"):
                row.deleteLater()
                del self.rows[jid]
        self.empty.setVisible(not self.rows)
        self.rail_scroll.setVisible(bool(self.rows))


class HistoryPage(GlowBackground):
    def __init__(self, history: History):
        super().__init__()
        self.history = history
        clear = QPushButton("Clear history")
        clear.setObjectName("SmallButton")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self.clear)
        self.list_box = vbox(spacing=10)
        lay = vbox(hbox(label("History", "H1"), None, clear), 6,
                   label("Everything you've downloaded with Clipnest.", "Sub"), 24,
                   self.list_box, None)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll(centered(lay, 900, (30, 30, 30, 30))))
        self.reload()

    def clear(self) -> None:
        if QMessageBox.question(self, "Clear history",
                                "Remove all items from the history? Your files stay where they are.") \
                == QMessageBox.Yes:
            self.history.clear()
            self.reload()

    def reload(self) -> None:
        while self.list_box.count():
            w = self.list_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        if not self.history.items:
            self.list_box.addWidget(label("Nothing yet. Finished downloads appear here.", "Small"))
            return
        for item in self.history.items[:150]:
            self.list_box.addWidget(self._row(item))

    def _row(self, item: dict) -> QFrame:
        files = [f for f in item.get("files", []) if f]
        exists = any(Path(f).exists() for f in files)
        kind = item.get("fmt", "mp3")
        ic = QLabel()
        ic.setFixedSize(38, 38)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(f"background: {theme.SURFACE_2}; border-radius: 10px;")
        ic.setPixmap(theme.icon(FORMAT_ICONS.get(kind, "video"), theme.TEXT_2, 17).pixmap(17, 17))
        title = label(item.get("title", ""), None)
        title.setStyleSheet("font-weight: 600; background: transparent;")
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        when = time.strftime("%d %b %Y, %H:%M", time.localtime(item.get("time", 0)))
        extra = f" · {len(files)} files" if len(files) > 1 else ""
        meta = label(f"{format_label(kind, item.get('quality', ''))}{extra} · {when}" +
                     ("" if exists else " · file moved or deleted"), "Small")
        lay = hbox(ic, 14, vbox(title, 3, meta), 10, spacing=6, margins=(14, 11, 12, 11))
        lay.setStretch(2, 1)
        if exists:
            if len(files) == 1:
                play = icon_button("image" if kind in ("image", "thumbnail") else "play", "Open")
                play.clicked.connect(lambda: open_file(files[0]))
                lay.addWidget(play)
            folder = icon_button("folder", "Show in folder")
            folder.clicked.connect(lambda: show_in_folder(files[-1]))
            lay.addWidget(folder)
        return frame("Card", lay)


class SettingsPage(GlowBackground):
    update_requested = Signal()

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.dir_labels: dict[str, QLabel] = {}

        def section(title: str, *rows) -> QFrame:
            return frame("Panel", vbox(label(title, "H2"), 14, *rows, spacing=0, margins=(20, 18, 20, 20)))

        def folder_row(fmt: str, text: str):
            lb = label(settings[f"{fmt}_dir"], "Small")
            lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self.dir_labels[fmt] = lb
            btn = QPushButton("Change")
            btn.setObjectName("SmallButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: self.change_dir(fmt))
            row = hbox(vbox(label(text), 2, lb), 16, btn)
            row.setStretch(0, 1)
            return vbox(row, 12)

        # Only browsers that are actually on this computer. A saved choice whose
        # browser has gone (or never existed) falls back to no login.
        if settings["cookies_browser"] and not browsers.is_installed(settings["cookies_browser"]):
            settings.set("cookies_browser", "")
        self.browser = QComboBox()
        self.browser.addItem("Don't use a browser login", "")
        for b in browsers.installed():
            self.browser.addItem(b.name, b.key)
        self.browser.setCurrentIndex(max(0, self.browser.findData(settings["cookies_browser"])))
        self.browser.currentIndexChanged.connect(self.on_browser)
        self.browser.setAccessibleName("Browser to use for logins")
        self.browser_warning = label(
            "Chrome, Edge, Brave and Opera on Windows lock their logins, so Clipnest often can't "
            "use them. Firefox works best. If the login can't be read, Clipnest tries without it.",
            "Warn", wrap=True)

        auto_paste = switch("Fill in links I copy automatically")
        auto_paste.setChecked(settings["auto_paste"])
        auto_paste.toggled.connect(lambda on: self.settings.set("auto_paste", on))
        auto_update = switch("Update the download engine when Clipnest starts")
        auto_update.setChecked(settings["auto_update"])
        auto_update.toggled.connect(lambda on: self.settings.set("auto_update", on))
        apple = switch("Make 4K and 1440p videos play in QuickTime and on iPhone")
        apple.setChecked(settings["apple_convert"])
        apple.toggled.connect(lambda on: self.settings.set("apple_convert", on))
        apple_note = label("YouTube's 4K comes as VP9 or AV1, which QuickTime can't play. Clipnest "
                           "converts it to HEVC with your Mac's video chip after downloading.",
                           "Small", wrap=True)
        general = [auto_paste, 10, auto_update]
        if engine.IS_MAC:
            general += [10, apple, 4, apple_note]

        self.engine_text = label("Checking…", "Small", wrap=True)
        self.update_btn = QPushButton("  Check for updates")
        self.update_btn.setIcon(theme.icon("refresh", theme.TEXT))
        self.update_btn.setObjectName("SmallButton")
        self.update_btn.setCursor(Qt.PointingHandCursor)
        self.update_btn.clicked.connect(self.update_requested.emit)
        engine_row = hbox(self.engine_text, 16, self.update_btn)
        engine_row.setStretch(0, 1)

        lay = vbox(
            label("Settings", "H1"), 24,
            section("Save locations", folder_row("mp3", "MP3 audio"),
                    folder_row("mp4", "MP4 video, thumbnails and images")),
            18,
            section("Logins",
                    label("Most downloads don't need this. Instagram, private Facebook and X posts, "
                          "Vimeo, and YouTube when it asks you to confirm you're not a bot need you "
                          "to be logged in: choose the browser where you're logged in.",
                          "Small", wrap=True),
                    12, hbox(self.browser, None), 10, self.browser_warning),
            18,
            section("General", *general),
            18,
            section("Download engine", engine_row, 10,
                    label("Clipnest uses yt-dlp, FFmpeg and Deno (all free and open source) to "
                          "download and convert files.", "Small", wrap=True)),
            18,
            section(f"About Clipnest {__version__}",
                    label("Made by <b>Vishnu VK</b>, built with <b>Claude Code</b>.", None), 8,
                    label("Free and open source. Please download only content you have "
                          "the right to save, and respect creators' copyright.", "Small", wrap=True)),
            None,
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll(centered(lay, 820, (30, 30, 30, 30))))
        self.on_browser()

    def on_browser(self) -> None:
        key = self.browser.currentData() or ""
        self.settings.set("cookies_browser", key)
        self.browser_warning.setVisible(engine.IS_WINDOWS and key in CHROMIUM)

    def change_dir(self, fmt: str) -> None:
        d = QFileDialog.getExistingDirectory(self, "Save downloads to", self.settings[f"{fmt}_dir"])
        if d:
            self.settings.set(f"{fmt}_dir", d)
            self.dir_labels[fmt].setText(d)

    def set_engine_status(self, text: str, busy: bool) -> None:
        self.engine_text.setText(text)
        self.update_btn.setEnabled(not busy)


# -- main window --------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Clipnest")
        self.setWindowIcon(theme.app_icon())
        self.resize(1280, 820)
        self.setMinimumSize(1000, 660)

        self.settings = Settings()
        engine.remove_leftovers()
        self.history = History()
        self.manager = DownloadManager(self)

        # Top bar
        logo = QLabel()
        logo.setPixmap(theme.logo_pixmap(30))
        logo.setStyleSheet("background: transparent;")
        brand = label("Clipnest", "Brand")
        self.tab_download = TabButton("download", "Download")
        self.tab_history = TabButton("history", "History")
        self.tab_settings = TabButton("settings", "Settings")
        tabs = QButtonGroup(self)
        for i, b in enumerate((self.tab_download, self.tab_history, self.tab_settings)):
            tabs.addButton(b, i)
        self.tab_download.setChecked(True)
        tab_box = frame("Tabs", hbox(self.tab_download, 2, self.tab_history, 2, self.tab_settings,
                                     margins=(4, 4, 4, 4)))
        tab_box.setFixedHeight(44)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        self.status_text = label("Setting up…", "StatusText")
        status = frame("StatusPill", hbox(self.status_dot, 8, self.status_text, margins=(12, 0, 14, 0)))
        status.setFixedHeight(30)
        top = frame("TopBar", hbox(logo, 10, brand, 22, tab_box, None, status, margins=(20, 0, 20, 0)))
        top.setFixedHeight(62)

        # Pages
        self.download_page = DownloadPage(self.settings, self.manager)
        self.history_page = HistoryPage(self.history)
        self.settings_page = SettingsPage(self.settings)
        self.stack = QStackedWidget()
        for p in (self.download_page, self.history_page, self.settings_page):
            self.stack.addWidget(p)
        tabs.idClicked.connect(self.stack.setCurrentIndex)
        tabs.idClicked.connect(lambda i: i == 1 and self.history_page.reload())

        central = QWidget()
        central.setObjectName("Content")
        central.setLayout(vbox(top, self.stack))
        self.setCentralWidget(central)

        self.manager.active_count_changed.connect(self.tab_download.set_badge)
        self.manager.job_finished.connect(self.on_job_finished)
        self.settings_page.update_requested.connect(lambda: self.run_engine(update=True))

        self.engine_worker: EngineWorker | None = None
        QTimer.singleShot(0, lambda: self.run_engine(update=self.settings["auto_update"]))

    def run_engine(self, update: bool) -> None:
        if self.engine_worker is not None:
            return
        first_time = bool(engine.missing_parts())
        self.engine_worker = EngineWorker(update, self)
        if first_time:
            self.download_page.set_engine_progress("Setting up the download engine", -1)
            self.engine_worker.progress.connect(self.download_page.set_engine_progress)
        else:
            self.download_page.set_engine_ready(True)
        self.engine_worker.progress.connect(
            lambda text, _f: self.set_engine_status(text + "…", busy=True))
        self.engine_worker.done.connect(self.on_engine_done)
        self.set_engine_status("Checking for updates…" if update else "Setting up…", busy=True)
        self.engine_worker.start()

    def on_engine_done(self, ok: bool, msg: str) -> None:
        self.engine_worker.deleteLater()
        self.engine_worker = None
        if ok and not engine.missing_parts():
            self.download_page.set_engine_ready(True)
            self.set_engine_status("Engine up to date", busy=False,
                                   detail=f"yt-dlp {msg}" if msg else "")
        elif engine.missing_parts():
            self.download_page.set_engine_ready(False, msg or "unknown error")
            self.set_engine_status("Engine not installed", busy=False, error=True)
        else:
            # The update check failed (e.g. offline) but the engine works.
            self.download_page.set_engine_ready(True)
            self.set_engine_status("Couldn't check for updates", busy=False,
                                   detail=f"yt-dlp {engine.ytdlp_version() or ''}")

    def set_engine_status(self, text: str, busy: bool, detail: str = "", error: bool = False) -> None:
        color = theme.RED if error else theme.AMBER if busy else theme.GREEN
        self.status_dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self.status_text.setText(text)
        self.settings_page.set_engine_status(text + (f" · {detail}" if detail else ""), busy)

    def on_job_finished(self, job: Job) -> None:
        if job.state == "done":
            self.history.add(job.title, job.files, job.opts.fmt, job.opts.quality, job.opts.url)

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.download_page.offer_clipboard()

    def closeEvent(self, e):
        if self.manager.active_count():
            answer = QMessageBox.question(
                self, "Downloads in progress",
                "Some downloads haven't finished. Quit and cancel them?")
            if answer != QMessageBox.Yes:
                e.ignore()
                return
        self.manager.shutdown()
        super().closeEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        _dark_title_bar(self)
        _native_window_icon(self)


def _native_window_icon(window: QWidget) -> None:
    """Gives the taskbar the icon built into Clipnest.exe.

    Qt's own window icon sometimes doesn't reach the Windows taskbar, which
    then shows a blank default icon instead of the Clipnest logo.
    """
    if not (engine.IS_WINDOWS and getattr(sys, "frozen", False)):
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p, wintypes.UINT,
                                      ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                        wintypes.LPARAM]
        hinst = kernel32.GetModuleHandleW(None)
        hwnd = int(window.winId())
        # (ICON_BIG, SM_CXICON, SM_CYICON), (ICON_SMALL, SM_CXSMICON, SM_CYSMICON)
        for which, mx, my in ((1, 11, 12), (0, 49, 50)):
            handle = user32.LoadImageW(hinst, ctypes.c_void_p(1), 1,   # IMAGE_ICON, id 1
                                       user32.GetSystemMetrics(mx), user32.GetSystemMetrics(my), 0)
            if handle:
                user32.SendMessageW(hwnd, 0x0080, which, handle)   # WM_SETICON
    except Exception:
        pass


def _dark_title_bar(window: QWidget) -> None:
    """Makes the native Windows 10/11 title bar dark to match the app."""
    if not engine.IS_WINDOWS:
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        value = ctypes.c_int(1)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (new, then old builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        caption = ctypes.c_int(0x00130C0D)   # BG colour as COLORREF (0x00BBGGRR)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
    except Exception:
        pass


def _write_ui_icons() -> dict[str, str]:
    """Small images the stylesheet needs (check mark, switches), as files."""
    folder = engine.data_dir() / "ui"
    folder.mkdir(exist_ok=True)
    files = {
        "check.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                     'stroke="#ffffff" stroke-width="3" stroke-linecap="round" '
                     'stroke-linejoin="round"><path d="M5 12l5 5 9-10"/></svg>',
        "switch-on.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 20">'
                         '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
                         f'<stop offset="0" stop-color="{theme.ACCENT}"/><stop offset="1" '
                         f'stop-color="{theme.ACCENT_2}"/></linearGradient></defs>'
                         '<rect width="36" height="20" rx="10" fill="url(#g)"/>'
                         '<circle cx="26" cy="10" r="7" fill="#fff"/></svg>',
        "switch-off.svg": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 36 20">'
                          '<rect width="36" height="20" rx="10" fill="#3A3848"/>'
                          '<circle cx="10" cy="10" r="7" fill="#fff"/></svg>',
    }
    out = {}
    for name, svg in files.items():
        path = folder / name
        path.write_text(svg, encoding="utf-8")
        out[name] = path.as_posix()
    return out


def app_stylesheet() -> str:
    sheet = theme.STYLESHEET
    for name, path in _write_ui_icons().items():
        sheet = sheet.replace(f":/clipnest/{name}", path)
    return sheet


def _write_check_icon() -> str:          # kept for older helper scripts
    return _write_ui_icons()["check.svg"]


def main() -> int:
    if engine.IS_WINDOWS:
        import ctypes
        # Own taskbar icon instead of Python's.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Clipnest.App")
    app = QApplication(sys.argv)
    app.setApplicationName("Clipnest")
    app.setApplicationDisplayName("Clipnest")
    app.setWindowIcon(theme.app_icon())
    font = QFont("Segoe UI Variable Text" if engine.IS_WINDOWS else app.font().family())
    font.setPixelSize(14)
    app.setFont(font)
    app.setStyle("Fusion")
    app.setStyleSheet(app_stylesheet())
    win = MainWindow()
    win.show()
    return app.exec()
