"""Locates, installs and updates the download engine (yt-dlp + FFmpeg).

Clipnest drives the standalone yt-dlp program instead of importing it as a
library. That way yt-dlp can update itself (`yt-dlp -U`) whenever YouTube or
Instagram change, without a new Clipnest release.
"""

from __future__ import annotations

import io
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

YTDLP_URLS = {
    "win32": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe",
    "darwin": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos",
    "linux": "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux",
}
FFMPEG_WIN_URL = (
    "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)
# Static macOS builds for Apple Silicon (arm64) and Intel (amd64). The page
# lists every build; we take the newest numbered release.
FFMPEG_MAC_INDEX = "https://ffmpeg.martin-riedl.de/"
FFMPEG_MAC_BASE = "https://ffmpeg.martin-riedl.de"
# yt-dlp needs a JavaScript runtime to read YouTube pages fully.
DENO_URL = "https://github.com/denoland/deno/releases/latest/download/deno-{target}.zip"

# Keeps a console window from flashing up for every child process on Windows.
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

ProgressFn = Callable[[str, float], None]


def data_dir() -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path, old = base / "Clipnest", base / "Fetchly"
    elif IS_MAC:
        base = Path.home() / "Library" / "Application Support"
        path, old = base / "Clipnest", base / "Fetchly"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        path, old = base / "clipnest", base / "fetchly"
    if not path.exists() and old.is_dir():
        # The app was called Fetchly before 1.1: keep its settings, history
        # and downloaded engine.
        try:
            old.rename(path)
        except OSError:
            pass
    path.mkdir(parents=True, exist_ok=True)
    return path


def engine_dir() -> Path:
    path = data_dir() / "engine"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _exe(name: str) -> str:
    return f"{name}.exe" if IS_WINDOWS else name


def ytdlp_path() -> Path | None:
    """yt-dlp installed by Clipnest first (it can self-update), then PATH."""
    own = engine_dir() / _exe("yt-dlp")
    if own.exists():
        return own
    found = shutil.which("yt-dlp")
    return Path(found) if found else None


def ffmpeg_path() -> Path | None:
    own = engine_dir() / _exe("ffmpeg")
    if own.exists():
        return own
    found = shutil.which("ffmpeg")
    return Path(found) if found else None


def deno_path() -> Path | None:
    own = engine_dir() / _exe("deno")
    if own.exists():
        return own
    found = shutil.which("deno")
    return Path(found) if found else None


def is_own_ytdlp(path: Path | None) -> bool:
    return path is not None and path.parent == engine_dir()


def missing_parts() -> list[str]:
    parts = []
    if ytdlp_path() is None:
        parts.append("yt-dlp")
    if ffmpeg_path() is None:
        parts.append("ffmpeg")
    if deno_path() is None:
        parts.append("deno")
    return parts


def _is_arm() -> bool:
    return platform.machine().lower() in ("arm64", "aarch64")


def _download(url: str, label: str, progress: ProgressFn) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Clipnest"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        while chunk := resp.read(256 * 1024):
            buf.write(chunk)
            if total:
                progress(label, buf.tell() / total)
    return buf.getvalue()


def install_ytdlp(progress: ProgressFn) -> None:
    key = "win32" if IS_WINDOWS else ("darwin" if IS_MAC else "linux")
    data = _download(YTDLP_URLS[key], "Downloading yt-dlp", progress)
    target = engine_dir() / _exe("yt-dlp")
    tmp = target.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    if not IS_WINDOWS:
        target.chmod(target.stat().st_mode | stat.S_IEXEC)


def _unzip(data: bytes, names: tuple[str, ...]) -> None:
    """Writes the named files (found anywhere in the zip) to the engine folder."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.namelist():
            name = member.rsplit("/", 1)[-1]
            if name in names:
                target = engine_dir() / name
                target.write_bytes(zf.read(member))
                if not IS_WINDOWS:
                    target.chmod(target.stat().st_mode | stat.S_IEXEC)


def latest_mac_ffmpeg(index_html: str, arch: str) -> str | None:
    """Folder URL of the newest numbered release build for "arm64"/"amd64"."""
    builds = re.findall(rf"/download/macos/{arch}/(\d+)_(\d+(?:\.\d+)+)/ffmpeg\.zip", index_html)
    if not builds:
        return None
    stamp, version = max(builds, key=lambda b: int(b[0]))
    return f"{FFMPEG_MAC_BASE}/download/macos/{arch}/{stamp}_{version}"


def install_ffmpeg(progress: ProgressFn) -> None:
    if IS_WINDOWS:
        data = _download(FFMPEG_WIN_URL, "Downloading FFmpeg", progress)
        progress("Unpacking FFmpeg", 1.0)
        _unzip(data, ("ffmpeg.exe", "ffprobe.exe"))
        return
    if IS_MAC:
        index = _download(FFMPEG_MAC_INDEX, "Finding FFmpeg", lambda *_: None).decode("utf-8", "replace")
        folder = latest_mac_ffmpeg(index, "arm64" if _is_arm() else "amd64")
        if folder is None:
            raise RuntimeError("Couldn't find an FFmpeg download for this Mac.")
        for tool in ("ffmpeg", "ffprobe"):
            data = _download(f"{folder}/{tool}.zip", f"Downloading {tool}", progress)
            _unzip(data, (tool,))
        return
    raise RuntimeError(
        "FFmpeg was not found. Install it with your package manager "
        "(for example `sudo apt install ffmpeg`)."
    )


def _deno_target() -> str:
    if IS_WINDOWS:
        return "x86_64-pc-windows-msvc"
    arch = "aarch64" if _is_arm() else "x86_64"
    return f"{arch}-apple-darwin" if IS_MAC else f"{arch}-unknown-linux-gnu"


def install_deno(progress: ProgressFn) -> None:
    data = _download(DENO_URL.format(target=_deno_target()), "Downloading the YouTube helper", progress)
    _unzip(data, (_exe("deno"),))


def install_missing(progress: ProgressFn) -> None:
    if ytdlp_path() is None:
        install_ytdlp(progress)
    if ffmpeg_path() is None:
        install_ffmpeg(progress)
    if deno_path() is None:
        install_deno(progress)


def ytdlp_version() -> str | None:
    path = ytdlp_path()
    if path is None:
        return None
    try:
        out = subprocess.run(
            [str(path), "--version"], capture_output=True, text=True,
            timeout=30, creationflags=NO_WINDOW,
        )
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def update_ytdlp() -> tuple[bool, str]:
    """Runs `yt-dlp -U`. Returns (ok, message)."""
    path = ytdlp_path()
    if path is None:
        return False, "yt-dlp is not installed"
    if not is_own_ytdlp(path):
        return True, "Using the system yt-dlp; update it with your package manager"
    try:
        out = subprocess.run(
            [str(path), "-U"], capture_output=True, text=True,
            timeout=180, creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    text = (out.stdout + out.stderr).strip().splitlines()
    return out.returncode == 0, (text[-1] if text else "Done")
