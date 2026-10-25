import json

import pytest

from clipnest.jobs import (
    FILE_TAG, POSTPROCESS_TAG, PROGRESS_TAG, TITLE_TAG, JobOptions, build_args,
    detect_source, format_duration, friendly_error, parse_info, parse_line,
)


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=abc", "YouTube"),
    ("https://youtu.be/abc", "YouTube"),
    ("https://music.youtube.com/watch?v=abc", "YouTube Music"),
    ("https://www.instagram.com/reel/abc/", "Instagram"),
    ("https://example.com/video", "Link"),
    ("not a link", None),
    ("ftp://example.com/x", None),
])
def test_detect_source(url, expected):
    assert detect_source(url) == expected


def opts(**kw):
    base = dict(url="https://youtu.be/x", fmt="mp3", quality="320", out_dir="/out")
    return JobOptions(**{**base, **kw})


def test_mp3_args():
    args = build_args("yt-dlp", opts())
    assert args[-2:] == ["--", "https://youtu.be/x"]
    assert "-x" in args and args[args.index("--audio-format") + 1] == "mp3"
    assert args[args.index("--audio-quality") + 1] == "320K"
    assert "--embed-thumbnail" in args and "--embed-metadata" in args
    assert "--no-playlist" in args


def test_mp3_without_extras():
    args = build_args("yt-dlp", opts(cover_art=False, tags=False, playlist=True))
    assert "--embed-thumbnail" not in args and "--embed-metadata" not in args
    assert "--yes-playlist" in args


@pytest.mark.parametrize("height", ["2160", "1440", "1080", "720"])
def test_mp4_args(height):
    args = build_args("yt-dlp", opts(fmt="mp4", quality=height, subtitles=True))
    assert args[args.index("-S") + 1].startswith(f"res:{height},")
    assert args[args.index("--merge-output-format") + 1] == "mp4"
    assert "--embed-subs" in args and "-x" not in args


def test_cookies_and_ffmpeg():
    args = build_args("yt-dlp", opts(cookies_browser="edge", ffmpeg_dir="C:/ff"))
    assert args[args.index("--cookies-from-browser") + 1] == "edge"
    assert args[args.index("--ffmpeg-location") + 1] == "C:/ff"


def test_unknown_format():
    with pytest.raises(ValueError):
        build_args("yt-dlp", opts(fmt="wav"))


def test_parse_progress():
    ev = parse_line(f"{PROGRESS_TAG}\t500\t1000\tNA\t2048.5\t12\t3\t10")
    assert ev.kind == "progress"
    assert ev.progress.fraction == 0.5 and ev.progress.eta == 12
    assert (ev.progress.item, ev.progress.items) == (3, 10)


def test_parse_progress_estimate_and_unknown():
    assert parse_line(f"{PROGRESS_TAG}\t250\tNA\t1000\tNA\tNA\tNA\tNA").progress.fraction == 0.25
    assert parse_line(f"{PROGRESS_TAG}\t250\tNA\tNA\tNA\tNA\tNA\tNA").progress.fraction is None


def test_parse_other_lines():
    assert parse_line(f"{POSTPROCESS_TAG}\tFFmpegExtractAudio").text == "Converting to MP3…"
    assert parse_line(f"{POSTPROCESS_TAG}\tMerger").text == "Joining video and audio…"
    assert parse_line(f"{FILE_TAG}\tC:\\Music\\a\tb.mp3\r\n").text == "C:\\Music\\a\tb.mp3"
    assert parse_line(f"{TITLE_TAG}\tMy song").text == "My song"
    assert parse_line("[youtube] something").kind == "log"


def test_parse_info_video():
    info = parse_info(json.dumps({
        "title": "Song", "uploader": "Band", "duration": 245, "thumbnail": "http://t",
        "extractor_key": "Youtube", "formats": [{"height": 1080}, {"height": 2160}, {}],
    }))
    assert (info.title, info.uploader, info.max_height, info.kind) == ("Song", "Band", 2160, "Video")


def test_parse_info_playlist_and_instagram():
    pl = parse_info(json.dumps({"_type": "playlist", "title": "Mix", "playlist_count": 12,
                                "entries": [{"thumbnails": [{"url": "a"}, {"url": "b"}]}]}))
    assert pl.is_playlist and pl.entries == 12 and pl.thumbnail == "b" and pl.kind == "Playlist"
    ig = parse_info(json.dumps({"title": "Reel", "extractor_key": "Instagram"}))
    assert ig.kind == "Reel / post"


def test_format_duration():
    assert format_duration(None) == ""
    assert format_duration(65) == "1:05"
    assert format_duration(3725) == "1:02:05"


def test_friendly_errors():
    assert "logged in" in friendly_error("ERROR: [Instagram] x: login required")
    assert "not a bot" in friendly_error("ERROR: [youtube] x: Sign in to confirm you're not a bot")
    assert "isn't supported" in friendly_error("ERROR: Unsupported URL: http://x")
    assert friendly_error("ERROR: something odd") == "something odd"


def test_deno_runtime():
    args = build_args("yt-dlp", opts(deno=r"C:\Clipnest\deno.exe"))
    assert args[args.index("--js-runtimes") + 1] == r"deno:C:\Clipnest\deno.exe"
    assert "--js-runtimes" not in build_args("yt-dlp", opts())


def test_instagram_audio_pages_are_explained():
    from clipnest.jobs import unsupported_reason
    assert "Reel" in unsupported_reason("https://www.instagram.com/reels/audio/1847049089984134?x=1")
    assert unsupported_reason("https://instagram.com/audio/123/")
    assert unsupported_reason("https://www.instagram.com/reel/ABC123/") is None
    assert unsupported_reason("https://youtu.be/x") is None


def test_old_default_folders_move_to_downloads(tmp_path, monkeypatch):
    from pathlib import Path
    from clipnest import engine, store
    monkeypatch.setattr(engine, "data_dir", lambda: tmp_path)
    old = str(Path.home() / "Music" / "Fetchly")
    (tmp_path / "settings.json").write_text(json.dumps({"mp3_dir": old, "mp4_dir": "D:/Mine"}))
    s = store.Settings()
    assert s["mp3_dir"] == store.downloads_dir()
    assert s["mp4_dir"] == "D:/Mine"


def test_browser_login_errors():
    opera = ('ERROR: could not find opera cookies database in '
             '"C:\\Users\\x\\AppData\\Roaming\\Opera Software\\Opera Stable"')
    assert "Settings → Logins" in friendly_error(opera)
    assert "Close it" in friendly_error("ERROR: Could not copy Chrome cookie database. See ...")
    assert "Firefox" in friendly_error("ERROR: Failed to decrypt with DPAPI. See ...")


def test_browser_detection(tmp_path, monkeypatch):
    from clipnest import browsers, engine
    monkeypatch.setattr(engine, "IS_WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    (tmp_path / "Roaming/Opera Software/Opera GX Stable").mkdir(parents=True)
    (tmp_path / "Local/Microsoft/Edge/User Data").mkdir(parents=True)
    assert [b.key for b in browsers.installed()] == ["edge", "opera_gx"]
    assert browsers.cookies_arg("edge") == "edge"
    gx = browsers.cookies_arg("opera_gx")
    assert gx.startswith("opera:") and "Opera GX Stable" in gx
    assert browsers.cookies_arg("opera") == ""      # plain Opera isn't installed
    assert browsers.cookies_arg("") == ""
