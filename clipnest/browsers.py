"""Which browsers are installed, for borrowing their YouTube/Instagram login.

yt-dlp reads the browser's cookies itself; we only tell it which browser,
and for browsers it doesn't know by name (Opera GX), where the profile is.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import engine


@dataclass(frozen=True)
class Browser:
    key: str          # what Settings stores
    name: str         # what the person sees
    ytdlp: str        # yt-dlp browser name
    folder: str       # profile folder; "{local}" / "{roaming}" are expanded
    use_path: bool = False   # pass the folder to yt-dlp (it can't find it alone)


_WINDOWS = [
    Browser("firefox", "Firefox", "firefox", "{roaming}/Mozilla/Firefox/Profiles"),
    Browser("chrome", "Google Chrome", "chrome", "{local}/Google/Chrome/User Data"),
    Browser("edge", "Microsoft Edge", "edge", "{local}/Microsoft/Edge/User Data"),
    Browser("brave", "Brave", "brave", "{local}/BraveSoftware/Brave-Browser/User Data"),
    Browser("opera", "Opera", "opera", "{roaming}/Opera Software/Opera Stable"),
    Browser("opera_gx", "Opera GX", "opera", "{roaming}/Opera Software/Opera GX Stable", True),
    Browser("vivaldi", "Vivaldi", "vivaldi", "{local}/Vivaldi/User Data"),
    Browser("chromium", "Chromium", "chromium", "{local}/Chromium/User Data"),
]

# Elsewhere we can't cheaply check what's installed, so offer the common ones.
_OTHER = [
    Browser("firefox", "Firefox", "firefox", ""),
    Browser("chrome", "Google Chrome", "chrome", ""),
    Browser("edge", "Microsoft Edge", "edge", ""),
    Browser("brave", "Brave", "brave", ""),
    Browser("opera", "Opera", "opera", ""),
    Browser("vivaldi", "Vivaldi", "vivaldi", ""),
    Browser("chromium", "Chromium", "chromium", ""),
    Browser("safari", "Safari", "safari", ""),
]


def _expand(folder: str) -> Path:
    local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    roaming = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    return Path(folder.format(local=local, roaming=roaming))


def all_browsers() -> list[Browser]:
    return _WINDOWS if engine.IS_WINDOWS else _OTHER


def installed() -> list[Browser]:
    if not engine.IS_WINDOWS:
        return list(_OTHER)
    return [b for b in _WINDOWS if _expand(b.folder).is_dir()]


def find(key: str) -> Browser | None:
    return next((b for b in all_browsers() if b.key == key), None)


def is_installed(key: str) -> bool:
    return any(b.key == key for b in installed())


def cookies_arg(key: str) -> str:
    """The value for yt-dlp's --cookies-from-browser, or "" for no login."""
    browser = find(key)
    if browser is None or not is_installed(key):
        return ""
    if browser.use_path:
        return f"{browser.ytdlp}:{_expand(browser.folder)}"
    return browser.ytdlp
