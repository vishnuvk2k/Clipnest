"""Fetchly's main window."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    QEvent, QObject, QProcess, QProcessEnvironment, QSize, Qt, QThread, QTimer, QUrl, Signal,
)
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from . import __version__, engine, theme
from .downloads import DownloadManager, Job
from .jobs import (
    MP3_QUALITIES, MP4_QUALITIES, JobOptions, MediaInfo, detect_source, format_duration,
    info_args, parse_info, unsupported_reason,
)
from .store import History, Settings

QUALITY_LABELS = {
    "mp3": {"320": ("320 kbps", "Best"), "256": ("256 kbps", ""),
            "192": ("192 kbps", ""), "128": ("128 kbps", "Smaller")},
    "mp4": {"2160": ("4K · 2160p", "Best"), "1440": ("1440p", ""),
            "1080": ("1080p", "Full HD"), "720": ("720p", "")},
}
BROWSERS = [("", "Don't use a browser login"), ("chrome", "Google Chrome"),
            ("edge", "Microsoft Edge"), ("firefox", "Firefox"), ("brave", "Brave"),
            ("opera", "Opera")]


# -- small helpers ------------------------------------------------------------

def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


def icon_label(name: str, color: str = theme.TEXT_2, size: int = 18) -> QLabel:
    lb = QLabel()
    lb.setPixmap(theme.icon(name, color, size).pixmap(size, size))
    lb.setFixedSize(size, size)
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


def card() -> QFrame:
    f = QFrame()
    f.setObjectName("Card")
    return f


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)


def show_in_folder(path: str) -> None:
    p = Path(path)
    if engine.IS_WINDOWS and p.exists():
        subprocess.Popen(["explorer", "/select,", str(p)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent if p.is_file() else p)))


def open_file(path: str) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


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


# -- widgets ------------------------------------------------------------------

class NavButton(QPushButton):
    def __init__(self, icon_name: str, text: str):
        super().__init__()
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIcon(theme.icon(icon_name, theme.TEXT_2))
        self.setIconSize(theme.ICON_SIZE)
        self.setText("  " + text)
        self.badge = label("", "Badge")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.hide()
        lay = hbox(None, self.badge, margins=(0, 0, 12, 0))
        self.setLayout(lay)

    def set_badge(self, n: int) -> None:
        self.badge.setText(str(n))
        self.badge.setVisible(n > 0)


class FormatCard(QPushButton):
    def __init__(self, icon_name: str, name: str, desc: str):
        super().__init__()
        self.setObjectName("FormatCard")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(f"{name}: {desc}")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.icon_box = QLabel()
        self.icon_box.setObjectName("FormatIcon")
        self.icon_box.setFixedSize(44, 44)
        self.icon_box.setAlignment(Qt.AlignCenter)
        self.icon_box.setPixmap(theme.icon(icon_name, "#FFFFFF", 22).pixmap(22, 22))
        text = vbox(label(name, "FormatName"), label(desc, "FormatDesc"), spacing=2)
        self.setLayout(hbox(self.icon_box, 14, text, None, margins=(16, 14, 16, 14)))
        for w in (self.icon_box,):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.toggled.connect(self._sync)
        self.setMinimumHeight(76)

    def _sync(self, on: bool) -> None:
        self.icon_box.setProperty("on", "true" if on else "false")
        repolish(self.icon_box)


class DownloadRow(QFrame):
    def __init__(self, job: Job, manager: DownloadManager):
        super().__init__()
        self.setObjectName("Card")
        self.job, self.manager = job, manager
        self.kind_icon = QLabel()
        self.kind_icon.setFixedSize(40, 40)
        self.kind_icon.setAlignment(Qt.AlignCenter)
        self.title = label("", None)
        self.title.setStyleSheet("font-weight: 600;")
        self.title.setMinimumWidth(80)
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status = label("", "Small")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setAccessibleName("Download progress")

        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("IconButton")
        self.cancel_btn.setIcon(theme.icon("close", theme.TEXT_2, 16))
        self.cancel_btn.setToolTip("Cancel")
        self.cancel_btn.setAccessibleName("Cancel download")
        self.cancel_btn.clicked.connect(lambda: self.manager.cancel(self.job))
        self.play_btn = QPushButton()
        self.play_btn.setObjectName("IconButton")
        self.play_btn.setIcon(theme.icon("play", theme.TEXT_2, 16))
        self.play_btn.setToolTip("Play")
        self.play_btn.setAccessibleName("Play file")
        self.play_btn.clicked.connect(lambda: self.job.files and open_file(self.job.files[-1]))
        self.folder_btn = QPushButton("Open folder")
        self.folder_btn.setObjectName("SmallButton")
        self.folder_btn.clicked.connect(self._open_folder)

        top = hbox(self.title, 12, self.status)
        top.setStretch(0, 1)
        middle = vbox(top, 8, self.bar)
        lay = hbox(self.kind_icon, 14, middle, 10, self.play_btn, self.folder_btn,
                   self.cancel_btn, spacing=6, margins=(16, 12, 12, 12))
        lay.setStretch(2, 1)
        self.setLayout(lay)
        self.refresh()

    def _open_folder(self):
        if self.job.files:
            show_in_folder(self.job.files[-1])
        else:
            show_in_folder(self.job.opts.out_dir)

    def refresh(self) -> None:
        j = self.job
        kind = "MP3 · " + j.opts.quality + " kbps" if j.opts.fmt == "mp3" else \
            "MP4 · " + QUALITY_LABELS["mp4"][j.opts.quality][0]
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(j.title, Qt.ElideRight, max(self.title.width(), 200)))
        self.title.setToolTip(j.title)
        self.status.setText(f"{kind} · {j.status}")
        self.status.setObjectName("Error" if j.state == "error" else "Small")
        self.status.setWordWrap(j.state == "error")
        repolish(self.status)
        self.bar.setValue(int(j.fraction * 1000))
        self.bar.setVisible(j.state in ("queued", "running"))
        done = j.state == "done"
        self.cancel_btn.setVisible(j.state in ("queued", "running"))
        self.folder_btn.setVisible(done)
        self.play_btn.setVisible(done and len(j.files) == 1)
        if done:
            self.kind_icon.setStyleSheet("background: rgba(95,211,154,0.14); border-radius: 8px;")
            self.kind_icon.setPixmap(theme.icon("check", theme.GREEN, 18, 2.5).pixmap(18, 18))
        elif j.state == "error":
            self.kind_icon.setStyleSheet("background: rgba(255,122,133,0.14); border-radius: 8px;")
            self.kind_icon.setPixmap(theme.icon("alert", theme.RED, 18).pixmap(18, 18))
        else:
            self.kind_icon.setStyleSheet("background: #2C2A36; border-radius: 8px;")
            name = "music" if j.opts.fmt == "mp3" else "video"
            if j.state == "cancelled":
                name = "close"
            self.kind_icon.setPixmap(theme.icon(name, theme.TEXT_2, 18).pixmap(18, 18))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.refresh()


# -- pages --------------------------------------------------------------------

def scroll_page(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    inner.setObjectName("Page")
    area.setWidget(inner)
    return area


def page_container(content_layout: QVBoxLayout) -> QWidget:
    """Centres content with a max width, like the design."""
    content = QWidget()
    content.setObjectName("Page")
    content.setMaximumWidth(880)
    content.setLayout(content_layout)
    outer = QWidget()
    lay = hbox(margins=(40, 36, 40, 48))
    lay.addWidget(content, 1)
    lay.addStretch(0)
    outer.setLayout(lay)
    return outer


class DownloadPage(QWidget):
    def __init__(self, settings: Settings, manager: DownloadManager):
        super().__init__()
        self.settings, self.manager = settings, manager
        self.info: MediaInfo | None = None
        self.info_url = ""
        self.info_proc: QProcess | None = None
        self.net = QNetworkAccessManager(self)
        self.rows: dict[int, DownloadRow] = {}
        self.engine_ready = False

        # Header
        h1 = label("What do you want to fetch?", "H1")
        sub = label("Paste a YouTube or Instagram link. Fetchly saves the original file, "
                    "with no watermark.", "Sub", wrap=True)

        # Engine setup banner
        self.setup_box = card()
        self.setup_text = label("Setting up the download engine…", "Small")
        self.setup_bar = QProgressBar()
        self.setup_bar.setRange(0, 1000)
        self.setup_bar.setTextVisible(False)
        self.setup_box.setLayout(vbox(self.setup_text, 8, self.setup_bar, margins=(16, 14, 16, 14)))

        # Link input
        link_label = label("Link", "Label")
        self.link_box = QFrame()
        self.link_box.setObjectName("LinkBox")
        self.link_box.setFixedHeight(52)
        self.link = QLineEdit()
        self.link.setObjectName("LinkInput")
        self.link.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self.link.setClearButtonEnabled(True)
        self.link.setAccessibleName("Link")
        link_label.setBuddy(self.link)
        self.link.installEventFilter(self)
        self.link_box.setLayout(hbox(icon_label("link", theme.MUTED), 10, self.link,
                                     margins=(16, 0, 10, 0)))
        paste = QPushButton("  Paste")
        paste.setIcon(theme.icon("paste", theme.TEXT))
        paste.setFixedHeight(52)
        paste.setCursor(Qt.PointingHandCursor)
        paste.clicked.connect(self.paste)
        self.link_error = label("", "Error")
        self.link_error.hide()

        # Preview
        self.preview = card()
        self.thumb = QLabel()
        self.thumb.setObjectName("Thumb")
        self.thumb.setFixedSize(208, 117)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.duration = label("", "Duration")
        self.duration.setParent(self.thumb)
        self.chip_source = label("", "Chip")
        self.chip_kind = label("", "Chip")
        self.media_title = label("", "MediaTitle", wrap=True)
        self.media_meta = label("", "Muted", wrap=True)
        info_col = vbox(hbox(self.chip_source, self.chip_kind, None, spacing=8), 8,
                        self.media_title, 6, self.media_meta, None)
        self.preview.setLayout(hbox(self.thumb, 20, info_col, margins=(16, 16, 16, 16)))
        self.preview.hide()

        # Format
        self.mp3_card = FormatCard("music", "MP3 audio", "Music, podcasts, Reel audio")
        self.mp4_card = FormatCard("video", "MP4 video", "720p to 4K, sound included")
        fmt_group = QButtonGroup(self)
        fmt_group.addButton(self.mp3_card)
        fmt_group.addButton(self.mp4_card)
        fmt_grid = QGridLayout()
        fmt_grid.setSpacing(12)
        fmt_grid.addWidget(self.mp3_card, 0, 0)
        fmt_grid.addWidget(self.mp4_card, 0, 1)
        self.mp3_card.clicked.connect(lambda: self.set_format("mp3"))
        self.mp4_card.clicked.connect(lambda: self.set_format("mp4"))

        # Quality pills
        self.pill_row = QHBoxLayout()
        self.pill_row.setSpacing(8)
        self.pill_group = QButtonGroup(self)
        self.pills: dict[str, QPushButton] = {}

        # Options
        self.opt_cover = QCheckBox("Add cover art")
        self.opt_tags = QCheckBox("Add title && artist tags")
        self.opt_subs = QCheckBox("Download subtitles")
        self.opt_playlist = QCheckBox("Download whole playlist")
        for box, key in ((self.opt_cover, "cover_art"), (self.opt_tags, "tags"),
                         (self.opt_subs, "subtitles"), (self.opt_playlist, "playlist")):
            box.setChecked(settings[key])
            box.setCursor(Qt.PointingHandCursor)
            box.toggled.connect(lambda on, k=key: self.settings.set(k, on))
        options = vbox(self.opt_cover, self.opt_tags, self.opt_subs, self.opt_playlist, spacing=10)

        save_box = card()
        self.save_dir = label("", None)
        self.save_dir.setStyleSheet("font-size: 13px;")
        change = QPushButton("Change")
        change.setObjectName("SmallButton")
        change.clicked.connect(self.change_dir)
        save_box.setLayout(hbox(icon_label("folder", theme.MUTED), 12,
                                vbox(label("Save to", "Small"), self.save_dir), 16, change,
                                margins=(14, 10, 10, 10)))

        self.go = QPushButton()
        self.go.setObjectName("Primary")
        self.go.setIcon(theme.icon("download", "#FFFFFF", 20, 2.2))
        self.go.setIconSize(QSize(20, 20))
        self.go.setCursor(Qt.PointingHandCursor)
        self.go.clicked.connect(self.start)

        # Downloads list
        self.list_box = vbox(spacing=12)
        self.empty = label("Your downloads will show up here.", "Small")
        clear = QPushButton("Clear finished")
        clear.setObjectName("SmallButton")
        clear.clicked.connect(self.clear_finished)

        lay = vbox(spacing=0)
        lay.addLayout(vbox(h1, 8, sub))
        lay.addSpacing(28)
        lay.addWidget(self.setup_box)
        lay.addLayout(vbox(link_label, 8, hbox(self.link_box, 10, paste), 8, self.link_error))
        lay.addSpacing(20)
        lay.addWidget(self.preview)
        lay.addSpacing(24)
        lay.addLayout(vbox(label("Format", "Label"), 10, fmt_grid))
        lay.addSpacing(24)
        lay.addLayout(vbox(label("Quality", "Label"), 10, hbox(self.pill_row, None)))
        lay.addSpacing(24)
        lay.addLayout(hbox(options, None, save_box, spacing=24))
        lay.addSpacing(28)
        lay.addWidget(self.go)
        lay.addSpacing(32)
        lay.addLayout(hbox(label("Downloads", "H2"), None, clear))
        lay.addSpacing(12)
        lay.addWidget(self.empty)
        lay.addLayout(self.list_box)
        lay.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll_page(page_container(lay)))

        self.fetch_timer = QTimer(self, singleShot=True, interval=500)
        self.fetch_timer.timeout.connect(self.fetch_info)
        self.link.textChanged.connect(self.on_link_changed)
        self.link.returnPressed.connect(self.start)

        manager.job_added.connect(self.add_row)
        manager.job_changed.connect(lambda j: j.id in self.rows and self.rows[j.id].refresh())

        self.set_format(settings["format"])
        self.set_engine_ready(False)

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
                                    "\nCheck your internet connection and restart Fetchly.")
            self.setup_text.setObjectName("Error")
            self.setup_text.setWordWrap(True)
            repolish(self.setup_text)
            self.setup_bar.hide()
        self.update_button()
        if ready and self.link.text().strip():
            self.fetch_info()

    # -- format & quality
    def fmt(self) -> str:
        return "mp3" if self.mp3_card.isChecked() else "mp4"

    def set_format(self, fmt: str) -> None:
        self.settings.set("format", fmt)
        (self.mp3_card if fmt == "mp3" else self.mp4_card).setChecked(True)
        self.mp3_card._sync(fmt == "mp3")
        self.mp4_card._sync(fmt == "mp4")
        for btn in self.pills.values():
            self.pill_group.removeButton(btn)
            btn.deleteLater()
        self.pills = {}
        current = self.settings[f"{fmt}_quality"]
        for q in (MP3_QUALITIES if fmt == "mp3" else MP4_QUALITIES):
            text, tag = QUALITY_LABELS[fmt][q]
            btn = QPushButton(f"{text}   {tag}" if tag else text)
            btn.setObjectName("Pill")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setChecked(q == current)
            btn.clicked.connect(lambda _=False, q=q: self.set_quality(q))
            self.pill_group.addButton(btn)
            self.pill_row.addWidget(btn)
            self.pills[q] = btn
        self.opt_cover.setVisible(fmt == "mp3")
        self.opt_tags.setVisible(fmt == "mp3")
        self.opt_subs.setVisible(fmt == "mp4")
        self.save_dir.setText(self.settings[f"{fmt}_dir"])
        self.update_button()

    def set_quality(self, q: str) -> None:
        self.settings.set(f"{self.fmt()}_quality", q)
        self.update_button()

    def update_button(self) -> None:
        fmt = self.fmt()
        q = self.settings[f"{fmt}_quality"]
        text = QUALITY_LABELS[fmt][q][0]
        self.go.setText(f"  Fetch {fmt.upper()} · {text}")
        self.go.setEnabled(self.engine_ready)

    def change_dir(self) -> None:
        fmt = self.fmt()
        d = QFileDialog.getExistingDirectory(self, "Save downloads to", self.settings[f"{fmt}_dir"])
        if d:
            self.settings.set(f"{fmt}_dir", d)
            self.save_dir.setText(d)

    # -- link & preview
    def eventFilter(self, obj, event):
        if obj is self.link and event.type() in (QEvent.FocusIn, QEvent.FocusOut):
            self.link_box.setProperty("focused", "true" if event.type() == QEvent.FocusIn else "false")
            repolish(self.link_box)
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
            self.preview.hide()
            self.info = None
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
        args = info_args(str(engine.ytdlp_path()), url, self.settings["cookies_browser"],
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
            self.show_link_error(url, "Couldn't start the download engine. Restart Fetchly.")

    def on_info_timeout(self, proc: QProcess, url: str) -> None:
        if proc is self.info_proc and proc.state() != QProcess.NotRunning:
            self.info_proc = None
            proc.kill()
            self.show_link_error(url, "Looking up this link took too long. You can still "
                                      "press Fetch to try downloading it.")

    def show_link_error(self, url: str, text: str) -> None:
        if url != self.link.text().strip():
            return
        self.info_url = ""
        self.preview.hide()
        self.link_error.setText(text)
        self.link_error.setWordWrap(True)
        self.link_error.show()

    def show_preview_loading(self, url: str) -> None:
        self.preview.show()
        self.chip_source.setText(detect_source(url) or "Link")
        self.chip_kind.setText("Looking up…")
        self.media_title.setText("Getting video details…")
        self.media_meta.setText("")
        self.duration.hide()
        self.thumb.setPixmap(theme.icon("play", theme.MUTED, 28).pixmap(28, 28))

    def on_info(self, proc: QProcess, url: str, code: int) -> None:
        out = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        err = bytes(proc.readAllStandardError()).decode("utf-8", "replace")
        proc.deleteLater()
        if proc is self.info_proc:
            self.info_proc = None
        if url != self.link.text().strip():
            return
        if code != 0 or not out.strip():
            from .jobs import friendly_error
            self.info_url = ""
            self.preview.hide()
            self.link_error.setText(friendly_error(err or "Couldn't read this link."))
            self.link_error.setWordWrap(True)
            self.link_error.show()
            return
        try:
            info = parse_info(out)
        except ValueError:
            self.preview.hide()
            return
        self.info = info
        source = detect_source(url) or info.source
        self.chip_source.setText(source)
        self.chip_kind.setText(info.kind)
        self.media_title.setText(info.title)
        meta = [info.uploader] if info.uploader else []
        if info.is_playlist:
            meta.append(f"{info.entries} videos")
            if not self.opt_playlist.isChecked():
                meta.append("tick “Download whole playlist” to get them all")
        elif info.max_height:
            meta.append(f"Available up to {_height_name(info.max_height)}")
        self.media_meta.setText(" · ".join(meta))
        dur = format_duration(info.duration)
        self.duration.setText(dur)
        self.duration.adjustSize()
        self.duration.move(208 - self.duration.width() - 8, 117 - self.duration.height() - 8)
        self.duration.setVisible(bool(dur))
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
            dpr = self.devicePixelRatioF()
            size = QSize(int(208 * dpr), int(117 * dpr))
            px = px.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x, y = (px.width() - size.width()) // 2, (px.height() - size.height()) // 2
            px = _rounded(px.copy(x, y, size.width(), size.height()), 8 * dpr)
            px.setDevicePixelRatio(dpr)
            self.thumb.setPixmap(px)

    # -- downloading
    def start(self) -> None:
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
        fmt = self.fmt()
        out_dir = self.settings[f"{fmt}_dir"]
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            self.link_error.setText(f"Can't save to {out_dir}. Choose another folder.")
            self.link_error.show()
            return
        opts = JobOptions(
            url=url, fmt=fmt, quality=self.settings[f"{fmt}_quality"], out_dir=out_dir,
            cover_art=self.opt_cover.isChecked(), tags=self.opt_tags.isChecked(),
            subtitles=self.opt_subs.isChecked(), playlist=self.opt_playlist.isChecked(),
            cookies_browser=self.settings["cookies_browser"],
        )
        title = self.info.title if self.info and self.info_url == url else url
        self.manager.add(opts, title)
        self.link.clear()
        self.info_url = ""

    def add_row(self, job: Job) -> None:
        row = DownloadRow(job, self.manager)
        self.rows[job.id] = row
        self.list_box.insertWidget(0, row)
        self.empty.hide()

    def clear_finished(self) -> None:
        for jid, row in list(self.rows.items()):
            if row.job.state in ("done", "error", "cancelled"):
                row.deleteLater()
                del self.rows[jid]
        self.empty.setVisible(not self.rows)


def _height_name(h: int) -> str:
    if h >= 2160:
        return "4K"
    if h >= 1440:
        return "1440p"
    return f"{h}p"


def _rounded(px: QPixmap, radius: float) -> QPixmap:
    from PySide6.QtGui import QPainter, QPainterPath
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


class HistoryPage(QWidget):
    def __init__(self, history: History):
        super().__init__()
        self.history = history
        clear = QPushButton("Clear history")
        clear.setObjectName("SmallButton")
        clear.clicked.connect(self.clear)
        self.list_box = vbox(spacing=10)
        lay = vbox(hbox(label("History", "H1"), None, clear), 8,
                   label("Everything you've downloaded with Fetchly.", "Sub"), 28,
                   self.list_box, None)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll_page(page_container(lay)))
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
        row = card()
        files = [f for f in item.get("files", []) if f]
        exists = any(Path(f).exists() for f in files)
        kind = item.get("fmt", "mp3")
        ic = QLabel()
        ic.setFixedSize(40, 40)
        ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet("background: #2C2A36; border-radius: 8px;")
        ic.setPixmap(theme.icon("music" if kind == "mp3" else "video", theme.TEXT_2).pixmap(18, 18))
        title = label(item.get("title", ""), None)
        title.setStyleSheet("font-weight: 600;")
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        when = time.strftime("%d %b %Y, %H:%M", time.localtime(item.get("time", 0)))
        q = item.get("quality", "")
        qtext = f"{q} kbps" if kind == "mp3" else QUALITY_LABELS["mp4"].get(q, (q,))[0]
        extra = f" · {len(files)} files" if len(files) > 1 else ""
        meta = label(f"{kind.upper()} · {qtext}{extra} · {when}" +
                     ("" if exists else " · file moved or deleted"), "Small")
        lay = hbox(ic, 14, vbox(title, 4, meta), 10, spacing=6, margins=(16, 12, 12, 12))
        lay.setStretch(2, 1)
        if exists:
            if len(files) == 1:
                play = QPushButton()
                play.setObjectName("IconButton")
                play.setIcon(theme.icon("play", theme.TEXT_2, 16))
                play.setToolTip("Play")
                play.setAccessibleName("Play file")
                play.clicked.connect(lambda: open_file(files[0]))
                lay.addWidget(play)
            folder = QPushButton("Open folder")
            folder.setObjectName("SmallButton")
            folder.clicked.connect(lambda: show_in_folder(files[-1]))
            lay.addWidget(folder)
        row.setLayout(lay)
        return row


class SettingsPage(QWidget):
    update_requested = Signal()

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.dir_labels: dict[str, QLabel] = {}

        def section(title: str, *rows) -> QFrame:
            box = card()
            box.setLayout(vbox(label(title, "H2"), 14, *rows, spacing=0, margins=(20, 18, 20, 20)))
            return box

        def folder_row(fmt: str, text: str):
            lb = label(settings[f"{fmt}_dir"], "Small")
            lb.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self.dir_labels[fmt] = lb
            btn = QPushButton("Change")
            btn.setObjectName("SmallButton")
            btn.clicked.connect(lambda: self.change_dir(fmt))
            row = hbox(vbox(label(text), 2, lb), 16, btn)
            row.setStretch(0, 1)
            return vbox(row, 12)

        self.browser = QComboBox()
        for key, text in BROWSERS:
            self.browser.addItem(text, key)
        self.browser.setCurrentIndex(max(0, [b[0] for b in BROWSERS].index(settings["cookies_browser"])
                                         if settings["cookies_browser"] in [b[0] for b in BROWSERS] else 0))
        self.browser.currentIndexChanged.connect(
            lambda: self.settings.set("cookies_browser", self.browser.currentData()))
        self.browser.setAccessibleName("Browser to use for logins")

        auto_paste = QCheckBox("Fill in links I copy automatically")
        auto_paste.setChecked(settings["auto_paste"])
        auto_paste.toggled.connect(lambda on: self.settings.set("auto_paste", on))
        auto_update = QCheckBox("Update the download engine when Fetchly starts")
        auto_update.setChecked(settings["auto_update"])
        auto_update.toggled.connect(lambda on: self.settings.set("auto_update", on))

        self.engine_text = label("Checking…", "Small", wrap=True)
        self.update_btn = QPushButton("  Check for updates")
        self.update_btn.setIcon(theme.icon("refresh", theme.TEXT))
        self.update_btn.setObjectName("SmallButton")
        self.update_btn.clicked.connect(self.update_requested.emit)

        engine_row = hbox(self.engine_text, 16, self.update_btn)
        engine_row.setStretch(0, 1)

        lay = vbox(
            label("Settings", "H1"), 28,
            section("Save locations", folder_row("mp3", "MP3 audio"), folder_row("mp4", "MP4 video")),
            20,
            section("Logins",
                    label("Private Instagram posts, and YouTube when it asks you to confirm "
                          "you're not a bot, need you to be logged in. Choose the browser "
                          "where you're logged in and Fetchly will use that login. "
                          "Close that browser first if downloads fail.", "Small", wrap=True),
                    14, hbox(self.browser, None)),
            20,
            section("General", auto_paste, 10, auto_update),
            20,
            section("Download engine",
                    engine_row,
                    10,
                    label("Fetchly uses yt-dlp, FFmpeg and Deno (all free and open source) to "
                          "download and convert files.", "Small", wrap=True)),
            20,
            section(f"About Fetchly {__version__}",
                    label("Made by <b>Vishnu VK</b>, built with <b>Claude Code</b>.", None),
                    8,
                    label("Free and open source. Please download only content you have "
                          "the right to save, and respect creators' copyright.", "Small", wrap=True)),
            None,
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll_page(page_container(lay)))

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
        self.setWindowTitle("Fetchly")
        self.setWindowIcon(theme.app_icon())
        self.resize(1200, 860)
        self.setMinimumSize(760, 560)

        self.settings = Settings()
        self.history = History()
        self.manager = DownloadManager(self)

        # Sidebar
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(240)
        logo = QLabel()
        logo.setPixmap(theme.logo_pixmap(34))
        brand = label("Fetchly", "Brand")
        self.nav_download = NavButton("download", "Download")
        self.nav_history = NavButton("history", "History")
        self.nav_settings = NavButton("settings", "Settings")
        nav = QButtonGroup(self)
        for i, b in enumerate((self.nav_download, self.nav_history, self.nav_settings)):
            nav.addButton(b, i)
        self.nav_download.setChecked(True)
        engine_box = QFrame()
        engine_box.setObjectName("EngineBox")
        self.engine_icon = icon_label("clock", theme.MUTED, 14)
        self.engine_label = label("Setting up…", "EngineText", wrap=True)
        engine_box.setLayout(hbox(self.engine_icon, 8, self.engine_label, margins=(12, 10, 12, 10)))
        side.setLayout(vbox(
            hbox(logo, 12, brand, None, margins=(12, 4, 12, 24)),
            self.nav_download, 4, self.nav_history, 4, self.nav_settings, None, engine_box,
            margins=(12, 20, 12, 16),
        ))

        # Pages
        self.download_page = DownloadPage(self.settings, self.manager)
        self.history_page = HistoryPage(self.history)
        self.settings_page = SettingsPage(self.settings)
        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")
        for p in (self.download_page, self.history_page, self.settings_page):
            self.stack.addWidget(p)
        nav.idClicked.connect(self.stack.setCurrentIndex)
        nav.idClicked.connect(lambda i: i == 1 and self.history_page.reload())

        central = QWidget()
        central.setObjectName("Content")
        central.setLayout(hbox(side, self.stack))
        self.setCentralWidget(central)

        self.manager.active_count_changed.connect(self.nav_download.set_badge)
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
            self.set_engine_status("Download engine up to date", busy=False,
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
        if busy:
            name, color = "clock", theme.MUTED
        elif error:
            name, color = "alert", theme.RED
        else:
            name, color = "check", theme.GREEN
        self.engine_icon.setPixmap(theme.icon(name, color, 14, 2.5).pixmap(14, 14))
        self.engine_label.setText(text)
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
    """Gives the taskbar the icon built into Fetchly.exe.

    Qt's own window icon sometimes doesn't reach the Windows taskbar, which
    then shows a blank default icon instead of the Fetchly logo.
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
        caption = ctypes.c_int(0x001C1516)   # BG colour as COLORREF (0x00BBGGRR)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)
    except Exception:
        pass


def _write_check_icon() -> str:
    path = engine.data_dir() / "ui" / "check.svg"
    path.parent.mkdir(exist_ok=True)
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                    'stroke="#ffffff" stroke-width="3" stroke-linecap="round" '
                    'stroke-linejoin="round"><path d="M5 12l5 5 9-10"/></svg>')
    return path.as_posix()


def main() -> int:
    if engine.IS_WINDOWS:
        import ctypes
        # Own taskbar icon instead of Python's.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fetchly.App")
    app = QApplication(sys.argv)
    app.setApplicationName("Fetchly")
    app.setApplicationDisplayName("Fetchly")
    app.setWindowIcon(theme.app_icon())
    font = QFont("Segoe UI Variable Text" if engine.IS_WINDOWS else app.font().family())
    font.setPixelSize(14)
    app.setFont(font)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET.replace(":/fetchly/check.svg", _write_check_icon()))
    win = MainWindow()
    win.show()
    return app.exec()
