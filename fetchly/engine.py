"""Locates, installs and updates the download engine (yt-dlp + FFmpeg).

Fetchly drives the standalone yt-dlp program instead of importing it as a
library. That way yt-dlp can update itself (`yt-dlp -U`) whenever YouTube or
Instagram change, without a new Fetchly release.
"""

from __future__ import annotations

import io
import os
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

# Keeps a console window from flashing up for every child process on Windows.
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

ProgressFn = Callable[[str, float], None]


def data_dir() -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        path = base / "Fetchly"
    elif IS_MAC:
        path = Path.home() / "Library" / "Application Support" / "Fetchly"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        path = base / "fetchly"
    path.mkdir(parents=True, exist_ok=True)
    return path


def engine_dir() -> Path:
    path = data_dir() / "engine"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _exe(name: str) -> str:
    return f"{name}.exe" if IS_WINDOWS else name


def ytdlp_path() -> Path | None:
    """yt-dlp installed by Fetchly first (it can self-update), then PATH."""
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


def is_own_ytdlp(path: Path | None) -> bool:
    return path is not None and path.parent == engine_dir()


def missing_parts() -> list[str]:
    parts = []
    if ytdlp_path() is None:
        parts.append("yt-dlp")
    if ffmpeg_path() is None:
        parts.append("ffmpeg")
    return parts


def _download(url: str, label: str, progress: ProgressFn) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Fetchly"})
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


def install_ffmpeg(progress: ProgressFn) -> None:
    if not IS_WINDOWS:
        raise RuntimeError(
            "FFmpeg was not found. Install it with your package manager "
            "(for example `brew install ffmpeg` or `sudo apt install ffmpeg`)."
        )
    data = _download(FFMPEG_WIN_URL, "Downloading FFmpeg", progress)
    progress("Unpacking FFmpeg", 1.0)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.namelist():
            name = member.rsplit("/", 1)[-1]
            if name in ("ffmpeg.exe", "ffprobe.exe"):
                (engine_dir() / name).write_bytes(zf.read(member))


def install_missing(progress: ProgressFn) -> None:
    if ytdlp_path() is None:
        install_ytdlp(progress)
    if ffmpeg_path() is None:
        install_ffmpeg(progress)


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
