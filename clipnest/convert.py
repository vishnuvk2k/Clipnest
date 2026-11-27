"""Makes MP4s from YouTube's 4K and 1440p play on Apple devices.

YouTube offers 4K and 1440p only as VP9 or AV1 video. Clipnest saves those in
an MP4, but QuickTime Player, Photos and iPhones can't play VP9/AV1 there. On
a Mac, Clipnest re-encodes such files to HEVC (H.265) with the Mac's built-in
video hardware (VideoToolbox), which is fast and keeps the quality.

Plain functions here (no Qt) so they can be tested; downloads.py runs them.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import engine

# Video formats QuickTime plays inside an MP4.
APPLE_PLAYABLE = {"h264", "hevc", "prores", "mpeg4", "mjpeg"}
# Bitrates when the source doesn't say (bits per second), by height.
DEFAULT_BITRATE = {2160: 20_000_000, 1440: 12_000_000, 1080: 8_000_000}
MIN_BITRATE = {2160: 12_000_000, 1440: 7_000_000, 1080: 4_000_000}
MAX_BITRATE = 50_000_000


@dataclass
class MediaFacts:
    video_codec: str = ""
    audio_codec: str = ""
    height: int = 0
    video_bitrate: int = 0
    total_bitrate: int = 0
    duration: float = 0.0


def probe_args(ffprobe: str, path: str) -> list[str]:
    return [ffprobe, "-v", "error", "-show_entries",
            "stream=codec_type,codec_name,height,bit_rate:format=duration,bit_rate",
            "-of", "json", path]


def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def parse_probe(text: str) -> MediaFacts:
    data = json.loads(text or "{}")
    facts = MediaFacts()
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not facts.video_codec:
            facts.video_codec = (s.get("codec_name") or "").lower()
            facts.height = _int(s.get("height"))
            facts.video_bitrate = _int(s.get("bit_rate"))
        elif s.get("codec_type") == "audio" and not facts.audio_codec:
            facts.audio_codec = (s.get("codec_name") or "").lower()
    fmt = data.get("format", {})
    facts.duration = float(fmt.get("duration") or 0) if fmt.get("duration") not in (None, "N/A") else 0.0
    facts.total_bitrate = _int(fmt.get("bit_rate"))
    return facts


def needs_apple_convert(facts: MediaFacts) -> bool:
    return bool(facts.video_codec) and facts.video_codec not in APPLE_PLAYABLE


def _bucket(height: int) -> int:
    return 2160 if height >= 2000 else 1440 if height >= 1300 else 1080


def target_bitrate(facts: MediaFacts) -> int:
    """About the same bitrate as the source: HEVC at that rate looks as good."""
    b = _bucket(facts.height)
    source = facts.video_bitrate or max(0, facts.total_bitrate - 192_000)
    if not source:
        return DEFAULT_BITRATE[b]
    return max(MIN_BITRATE[b], min(MAX_BITRATE, int(source * 1.15)))


def convert_args(ffmpeg: str, src: str, dst: str, facts: MediaFacts,
                 encoder: str = "hevc_videotoolbox") -> list[str]:
    audio = ["-c:a", "copy"] if facts.audio_codec in ("aac", "") else ["-c:a", "aac", "-b:a", "192k"]
    return [
        ffmpeg, "-y", "-hide_banner", "-nostats", "-loglevel", "error", "-progress", "pipe:1",
        "-i", src,
        "-map", "0:v:0", "-map", "0:a?", "-map", "0:s?",
        "-c:v", encoder, "-b:v", str(target_bitrate(facts)),
        "-tag:v", "hvc1",                    # how QuickTime recognises HEVC in MP4
        *audio, "-c:s", "copy",
        "-map_metadata", "0", "-movflags", "+faststart",
        dst,
    ]


def progress_fraction(line: str, duration: float) -> float | None:
    """FFmpeg's '-progress' lines: out_time_us=12345678 -> share of the video done."""
    if not duration or not line.startswith(("out_time_us=", "out_time_ms=")):
        return None
    try:
        us = int(line.split("=", 1)[1])          # both are microseconds, despite the name
    except ValueError:
        return None
    return max(0.0, min(1.0, us / 1_000_000 / duration))


def ffprobe_path() -> Path | None:
    ff = engine.ffmpeg_path()
    if ff is None:
        return None
    probe = ff.with_name("ffprobe" + (".exe" if engine.IS_WINDOWS else ""))
    return probe if probe.exists() else None


def probe(path: str) -> MediaFacts | None:
    ffprobe = ffprobe_path()
    if ffprobe is None:
        return None
    try:
        p = subprocess.run(probe_args(str(ffprobe), path), capture_output=True, timeout=60,
                           creationflags=engine.NO_WINDOW)
        return parse_probe(p.stdout.decode("utf-8", "replace")) if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
