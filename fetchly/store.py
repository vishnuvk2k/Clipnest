"""Settings and download history, saved as JSON in Fetchly's data folder."""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import engine

MAX_HISTORY = 300


def downloads_dir() -> str:
    """The user's Downloads folder, wherever Windows has it (it can be moved)."""
    if engine.IS_WINDOWS:
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("data", ctypes.c_byte * 16)]

            folder_id = GUID()
            folder_id.data[:] = uuid.UUID("374DE290-123F-4565-9164-39C4925E467B").bytes_le
            path = ctypes.c_wchar_p()
            shell32 = ctypes.windll.shell32
            shell32.SHGetKnownFolderPath.argtypes = [
                ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
            if shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path)) == 0:
                result = path.value
                ctypes.windll.ole32.CoTaskMemFree(path)
                if result:
                    return result
        except Exception:
            pass
    return str(Path.home() / "Downloads")


# Folders earlier versions picked automatically; moved to Downloads on upgrade.
_OLD_DEFAULTS = {str(Path.home() / sub / "Fetchly")
                 for sub in ("Music", "Videos", "Downloads")}


DEFAULTS = {
    "format": "mp3",
    "mp3_quality": "320",
    "mp4_quality": "1080",
    "mp3_dir": downloads_dir(),
    "mp4_dir": downloads_dir(),
    "cover_art": True,
    "tags": True,
    "subtitles": False,
    "playlist": False,
    "cookies_browser": "",
    "auto_paste": True,
    "auto_update": True,
}


class JsonFile:
    def __init__(self, name: str, default):
        self.path = engine.data_dir() / name
        self.default = default

    def load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self.default

    def save(self, value) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)


class Settings:
    def __init__(self):
        self._file = JsonFile("settings.json", {})
        loaded = self._file.load()
        self.values = {**DEFAULTS, **(loaded if isinstance(loaded, dict) else {})}
        for key in ("mp3_dir", "mp4_dir"):
            if self.values[key] in _OLD_DEFAULTS:
                self.values[key] = DEFAULTS[key]

    def __getitem__(self, key):
        return self.values[key]

    def set(self, key, value) -> None:
        if self.values.get(key) != value:
            self.values[key] = value
            self._file.save(self.values)


class History:
    def __init__(self):
        self._file = JsonFile("history.json", [])
        loaded = self._file.load()
        self.items: list[dict] = loaded if isinstance(loaded, list) else []

    def add(self, title: str, files: list[str], fmt: str, quality: str, url: str) -> None:
        self.items.insert(0, {
            "title": title, "files": files, "fmt": fmt, "quality": quality,
            "url": url, "time": int(time.time()),
        })
        del self.items[MAX_HISTORY:]
        self._file.save(self.items)

    def clear(self) -> None:
        self.items = []
        self._file.save(self.items)
