"""Builds yt-dlp command lines and parses what yt-dlp prints back.

Everything here is plain Python with no Qt, so it can be unit-tested.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

MP3_QUALITIES = ["320", "256", "192", "128"]          # kbps
MP4_QUALITIES = ["2160", "1440", "1080", "720"]       # max height

PROGRESS_TAG = "FETCHLY_DL"
POSTPROCESS_TAG = "FETCHLY_PP"
FILE_TAG = "FETCHLY_FILE"
TITLE_TAG = "FETCHLY_TITLE"

# Fields are separated by a tab, which never appears in yt-dlp's numbers.
PROGRESS_TEMPLATE = (
    f"download:{PROGRESS_TAG}\t%(progress.downloaded_bytes)s\t%(progress.total_bytes)s"
    "\t%(progress.total_bytes_estimate)s\t%(progress.speed)s\t%(progress.eta)s"
    "\t%(info.playlist_index)s\t%(info.n_entries)s"
)
POSTPROCESS_TEMPLATE = f"postprocess:{POSTPROCESS_TAG}\t%(progress.postprocessor)s"

# "<folder of playlist>/<index> - " only when the video is part of a playlist.
OUTPUT_TEMPLATE = (
    "%(playlist_title&{}/|)s%(playlist_index&{} - |)s%(title).180B.%(ext)s"
)

_SOURCES = [
    (re.compile(r"(^|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com)$"), "YouTube"),
    (re.compile(r"(^|\.)music\.youtube\.com$"), "YouTube Music"),
    (re.compile(r"(^|\.)(instagram\.com|instagr\.am)$"), "Instagram"),
]
_URL_RE = re.compile(r"^https?://([^/\s?#]+)", re.IGNORECASE)


def detect_source(url: str) -> str | None:
    """'YouTube', 'Instagram', 'Link' for any other http(s) URL, or None."""
    m = _URL_RE.match(url.strip())
    if not m:
        return None
    host = m.group(1).lower().split(":")[0]
    for pattern, name in reversed(_SOURCES):
        if pattern.search(host):
            return name
    return "Link"


_IG_AUDIO_RE = re.compile(r"^https?://(www\.)?instagram\.com/(reels/)?audio/", re.IGNORECASE)


def unsupported_reason(url: str) -> str | None:
    """A message for links we know can't be downloaded, before trying."""
    if _IG_AUDIO_RE.match(url.strip()):
        return ("Instagram audio pages can't be downloaded directly. Open a Reel that "
                "uses this sound, copy that Reel's link, and fetch it as MP3.")
    return None


@dataclass
class JobOptions:
    url: str
    fmt: str                      # "mp3" | "mp4"
    quality: str                  # kbps for mp3, max height for mp4
    out_dir: str
    cover_art: bool = True
    tags: bool = True
    subtitles: bool = False
    playlist: bool = False
    cookies_browser: str = ""     # "", "chrome", "edge", "firefox", "brave"
    ffmpeg_dir: str = ""
    deno: str = ""                # path to deno, for YouTube


def build_args(ytdlp: str, opts: JobOptions) -> list[str]:
    args = [
        ytdlp,
        "--ignore-config",
        "--newline",
        "--progress",
        "--no-simulate",
        "--color", "never",
        "--encoding", "utf-8",
        "--windows-filenames",
        "--no-mtime",
        "--progress-template", PROGRESS_TEMPLATE,
        "--progress-template", POSTPROCESS_TEMPLATE,
        "--print", f"video:{TITLE_TAG}\t%(title)s",
        "--print", f"after_move:{FILE_TAG}\t%(filepath)s",
        "-P", opts.out_dir,
        "-o", OUTPUT_TEMPLATE,
        "--yes-playlist" if opts.playlist else "--no-playlist",
    ]
    if opts.ffmpeg_dir:
        args += ["--ffmpeg-location", opts.ffmpeg_dir]
    if opts.cookies_browser:
        args += ["--cookies-from-browser", opts.cookies_browser]
    if opts.deno:
        args += ["--js-runtimes", f"deno:{opts.deno}"]

    if opts.fmt == "mp3":
        args += [
            "-f", "ba/b",
            "-x", "--audio-format", "mp3",
            "--audio-quality", f"{opts.quality}K",
        ]
        if opts.tags:
            # Fall back to the channel name when a video has no artist field.
            args += [
                "--embed-metadata",
                "--parse-metadata", "%(artist,creator,uploader,channel|)s:%(meta_artist)s",
            ]
        if opts.cover_art:
            args += ["--embed-thumbnail", "--convert-thumbnails", "jpg"]
    elif opts.fmt == "mp4":
        # Prefer H.264 + AAC so the file plays everywhere; 4K on YouTube only
        # exists as VP9/AV1, which the sort then falls back to.
        args += [
            "-f", "bv*+ba/b",
            "-S", f"res:{opts.quality},vcodec:h264,acodec:aac",
            "--merge-output-format", "mp4",
            "--embed-metadata",
        ]
        if opts.subtitles:
            args += ["--write-subs", "--sub-langs", "en.*,en", "--embed-subs"]
    else:
        raise ValueError(f"unknown format {opts.fmt!r}")

    args += ["--", opts.url]
    return args


def info_args(ytdlp: str, url: str, cookies_browser: str = "", deno: str = "") -> list[str]:
    args = [ytdlp, "--ignore-config", "-J", "--flat-playlist", "--no-warnings",
            "--encoding", "utf-8"]
    if cookies_browser:
        args += ["--cookies-from-browser", cookies_browser]
    if deno:
        args += ["--js-runtimes", f"deno:{deno}"]
    return args + ["--", url]


@dataclass
class MediaInfo:
    title: str
    uploader: str = ""
    duration: float | None = None
    thumbnail: str = ""
    source: str = ""
    is_playlist: bool = False
    entries: int = 0
    max_height: int = 0
    kind: str = "Video"


def parse_info(raw: str) -> MediaInfo:
    data = json.loads(raw)
    is_playlist = data.get("_type") == "playlist"
    thumb = data.get("thumbnail") or ""
    if not thumb and data.get("thumbnails"):
        thumb = data["thumbnails"][-1].get("url", "")
    entries = data.get("entries") or []
    if is_playlist and not thumb and entries:
        first = entries[0] or {}
        thumbs = first.get("thumbnails") or []
        thumb = first.get("thumbnail") or (thumbs[-1].get("url", "") if thumbs else "")
    heights = [f.get("height") or 0 for f in data.get("formats") or []]
    extractor = data.get("extractor_key") or data.get("extractor") or ""
    if is_playlist:
        kind = "Playlist"
    elif "instagram" in extractor.lower():
        kind = "Reel / post"
    else:
        kind = "Video"
    return MediaInfo(
        title=data.get("title") or data.get("id") or "Untitled",
        uploader=data.get("uploader") or data.get("channel") or "",
        duration=data.get("duration"),
        thumbnail=thumb,
        source=extractor.replace("Tab", "").replace("Playlist", ""),
        is_playlist=is_playlist,
        entries=data.get("playlist_count") or len(entries),
        max_height=max(heights, default=0),
        kind=kind,
    )


def format_duration(seconds: float | None) -> str:
    if not seconds:
        return ""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _num(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None   # yt-dlp prints "NA" for unknown values


@dataclass
class Progress:
    fraction: float | None = None
    speed: float | None = None
    eta: float | None = None
    item: int | None = None
    items: int | None = None


@dataclass
class LineEvent:
    kind: str                     # "progress" | "postprocess" | "title" | "file" | "log"
    progress: Progress = field(default_factory=Progress)
    text: str = ""


_PP_LABELS = {
    "ExtractAudio": "Converting to MP3…",
    "Merger": "Joining video and audio…",
    "EmbedThumbnail": "Adding cover art…",
    "Metadata": "Adding tags…",
    "EmbedSubtitle": "Adding subtitles…",
    "ThumbnailsConvertor": "Preparing cover art…",
    "VideoConvertor": "Converting video…",
}


def postprocess_label(name: str) -> str:
    """yt-dlp reports names like 'FFmpegExtractAudio' or 'Merger'."""
    return _PP_LABELS.get(name.removeprefix("FFmpeg"), "Finishing…")


def parse_line(line: str) -> LineEvent:
    line = line.rstrip("\r\n")
    parts = line.split("\t")
    tag = parts[0]
    if tag == PROGRESS_TAG and len(parts) >= 8:
        done, total, estimate, speed, eta, idx, n = (_num(p) for p in parts[1:8])
        total = total or estimate
        frac = min(done / total, 1.0) if done is not None and total else None
        return LineEvent("progress", Progress(
            fraction=frac, speed=speed, eta=eta,
            item=int(idx) if idx else None, items=int(n) if n else None,
        ))
    if tag == POSTPROCESS_TAG and len(parts) >= 2:
        return LineEvent("postprocess", text=postprocess_label(parts[1]))
    if tag == TITLE_TAG and len(parts) >= 2:
        return LineEvent("title", text="\t".join(parts[1:]))
    if tag == FILE_TAG and len(parts) >= 2:
        return LineEvent("file", text="\t".join(parts[1:]))
    return LineEvent("log", text=line)


def friendly_error(log: str) -> str:
    """Turns yt-dlp's last ERROR line into something a person can act on."""
    errors = [l for l in log.splitlines() if l.startswith("ERROR:")]
    msg = errors[-1][6:].strip() if errors else (log.strip().splitlines() or ["Unknown error"])[-1]
    low = msg.lower()
    if "private" in low or "login required" in low or "log in" in low or "rate-limit" in low:
        return ("This needs you to be logged in. In Settings, choose the browser "
                "you're logged in with, then try again.")
    if "sign in to confirm" in low:
        return ("YouTube asked to confirm you're not a bot. In Settings, choose the "
                "browser you're logged in with, then try again.")
    if "http error 404" in low:
        return "Couldn't find anything at this link. Check that it's complete."
    if "unable to download" in low and ("getaddrinfo" in low or "timed out" in low or "network" in low):
        return "Couldn't connect. Check your internet connection."
    if "unsupported url" in low:
        return "This link isn't supported."
    if "video unavailable" in low or "not available" in low:
        return "This video isn't available (removed, private or blocked in your country)."
    if "ffmpeg" in low and "not found" in low:
        return "FFmpeg is missing. Restart Fetchly to reinstall it."
    return msg
