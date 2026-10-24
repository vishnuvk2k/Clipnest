"""Settings and download history, saved as JSON in Fetchly's data folder."""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import engine

MAX_HISTORY = 300


def _default_dir(kind: str) -> str:
    home = Path.home()
    base = home / kind if (home / kind).is_dir() else home / "Downloads"
    return str(base / "Fetchly")


DEFAULTS = {
    "format": "mp3",
    "mp3_quality": "320",
    "mp4_quality": "1080",
    "mp3_dir": _default_dir("Music"),
    "mp4_dir": _default_dir("Videos"),
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
