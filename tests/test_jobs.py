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


def test_mac_browser_detection(tmp_path, monkeypatch):
    from clipnest import browsers, engine
    monkeypatch.setattr(engine, "IS_WINDOWS", False)
    monkeypatch.setattr(engine, "IS_MAC", True)
    monkeypatch.setattr(browsers.Path, "home", lambda: tmp_path)
    (tmp_path / "Library/Application Support/Firefox/Profiles").mkdir(parents=True)
    assert [b.key for b in browsers.installed()] == ["safari", "firefox"]
    assert browsers.cookies_arg("firefox") == "firefox"
    assert browsers.cookies_arg("chrome") == ""


def test_latest_mac_ffmpeg():
    from clipnest.engine import latest_mac_ffmpeg
    html = ('<a href="/download/macos/arm64/1700_8.1/ffmpeg.zip"></a>'
            '<a href="/download/macos/arm64/1800_9.0.2/ffmpeg.zip"></a>'
            '<a href="/download/macos/arm64/1900_N-1234-gabc/ffmpeg.zip"></a>'
            '<a href="/download/macos/amd64/1850_9.0.2/ffmpeg.zip"></a>')
    assert latest_mac_ffmpeg(html, "arm64").endswith("/macos/arm64/1800_9.0.2")
    assert latest_mac_ffmpeg(html, "amd64").endswith("/macos/amd64/1850_9.0.2")
    assert latest_mac_ffmpeg("", "arm64") is None


@pytest.mark.parametrize("url,expected", [
    ("https://www.facebook.com/watch/?v=647537299265662", "Facebook"),
    ("https://fb.watch/abc/", "Facebook"),
    ("https://m.facebook.com/reel/1195289147628387", "Facebook"),
    ("https://x.com/CAF_Online/status/1349365911120195585", "X"),
    ("https://twitter.com/a/status/1", "X"),
    ("https://vimeo.com/76979871", "Vimeo"),
    ("https://player.vimeo.com/video/76979871", "Vimeo"),
    ("https://www.pinterest.com/pin/664281013778109217/", "Pinterest"),
    ("https://in.pinterest.com/pin/1/", "Pinterest"),
    ("https://www.pinterest.co.uk/pin/1/", "Pinterest"),
    ("https://pin.it/abc123", "Pinterest"),
    ("https://notpinterest.example/pin/1", "Link"),
])
def test_detect_new_sources(url, expected):
    assert detect_source(url) == expected


def test_vimeo_login_message():
    msg = friendly_error("ERROR: [vimeo] 7: The web client only works when logged-in. Use --cookies")
    assert "Settings → Logins" in msg


def test_clean_titles():
    from clipnest.jobs import clean_title
    fb = ("9.9K views · 340 reactions | When your trying to help 👊👋 | Beast Camp Training")
    assert clean_title(fb, "Facebook") == "When your trying to help 👊👋"
    assert clean_title("119 reactions · 1.4K shares | Asif on Reels", "Facebook") == "Asif on Reels"
    assert clean_title("Padre enseña a su hijo", "Facebook") == "Padre enseña a su hijo"
    assert clean_title("10 Tips | How to cook", "Facebook") == "10 Tips | How to cook"
    assert clean_title("Pinterest video #659425570427630356", "Pinterest") == \
        "Pinterest 659425570427630356"
    assert clean_title("Pinterest video #1", "YouTube") == "Pinterest video #1"


def test_title_cleanup_args_and_work_dir():
    a = build_args("yt-dlp", opts(url="https://www.facebook.com/reel/1", work_dir="/w"))
    i = a.index("--replace-in-metadata")
    assert a[i + 1] == "title" and a[i + 3] == r"\g<1>"
    assert a[a.index("-P") + 1] == "/w"
    assert "--replace-in-metadata" not in build_args("yt-dlp", opts())
    assert build_args("yt-dlp", opts())[build_args("yt-dlp", opts()).index("-P") + 1] == "/out"


def test_image_pin_args_and_info():
    a = build_args("yt-dlp", opts(url="https://www.pinterest.com/pin/1/", fmt="image",
                                  quality="original"))
    assert "--skip-download" in a and "--write-thumbnail" in a and "-x" not in a
    assert any(x.startswith("after_video:" + FILE_TAG) for x in a)
    from clipnest.jobs import info_args
    assert "--ignore-no-formats-error" in info_args("yt-dlp", "https://pin.it/x")
    assert "--ignore-no-formats-error" not in info_args("yt-dlp", "https://youtu.be/x")
    info = parse_info(json.dumps({
        "title": "Pinterest video #659", "uploader": "NA", "extractor_key": "Pinterest",
        "formats": [], "thumbnails": [{"url": "s", "width": 60, "height": 60},
                                      {"url": "o", "width": 4817, "height": 2480}]}))
    assert (info.kind, info.image_size, info.title, info.uploader) == \
        ("Image", (4817, 2480), "Pinterest 659", "")
    video_pin = parse_info(json.dumps({"title": "Origami", "extractor_key": "Pinterest",
                                       "formats": [{"height": 1920}], "thumbnails": [{"url": "a"}]}))
    assert video_pin.kind == "Video" and video_pin.image_size is None
    assert parse_info(json.dumps({"title": "t", "extractor_key": "Twitter"})).kind == "Post"


def test_new_friendly_errors():
    ig = ("ERROR: [Instagram] C5R: Instagram sent an empty media response. Check if this post is "
          "accessible in your browser without being logged-in.")
    assert "Instagram only shows this" in friendly_error(ig)
    assert "DRM" in friendly_error("ERROR: [DRM] The requested site is known to use DRM protection.")
    assert "has no video" in friendly_error("ERROR: [twitter] 1: No video could be found in this tweet")
    assert "Vimeo" in friendly_error("ERROR: [vimeo] 1: The web client only works when logged-in.")
    assert "logged in" in friendly_error("ERROR: [Reddit] 6: Account authentication is required.")
    assert "limiting" in friendly_error("ERROR: [x] HTTP Error 429: Too Many Requests")
    real_bot = ("ERROR: [youtube] x: Sign in to confirm you’re not a bot. Use --cookies-from-browser "
                "or --cookies for the authentication.")
    assert "not a bot" in friendly_error(real_bot)


def test_finished_files_never_overwrite(tmp_path):
    from clipnest.downloads import move_finished, unique_path
    work, out = tmp_path / "work", tmp_path / "out"
    (work / "Mix").mkdir(parents=True)
    out.mkdir()
    (out / "Origami.mp4").write_text("my video")
    (work / "Origami.mp4").write_text("new")
    (work / "Mix" / "01 - a.mp3").write_text("a")
    moved = move_finished([str(work / "Origami.mp4"), str(work / "Mix" / "01 - a.mp3"),
                           str(work / "gone.mp3")], work, out)
    assert moved == [str(out / "Origami (2).mp4"), str(out / "Mix" / "01 - a.mp3")]
    assert (out / "Origami.mp4").read_text() == "my video"
    assert unique_path(out / "Origami.mp4") == out / "Origami (3).mp4"


def test_settings_of_removed_features_are_dropped(tmp_path, monkeypatch):
    from clipnest import engine, store
    monkeypatch.setattr(engine, "data_dir", lambda: tmp_path)
    (tmp_path / "settings.json").write_text(json.dumps(
        {"format": "mp4", "web_enabled": True, "web_password": "pbkdf2_sha256$1$aa$bb",
         "tunnel_token": "secret"}))
    s = store.Settings()
    assert s["format"] == "mp4"
    saved = json.loads((tmp_path / "settings.json").read_text())
    assert "web_password" not in saved and "tunnel_token" not in saved and saved["format"] == "mp4"


def test_leftover_cloudflared_is_removed(tmp_path, monkeypatch):
    from clipnest import engine
    monkeypatch.setattr(engine, "data_dir", lambda: tmp_path)
    leftover = engine.engine_dir() / engine._exe("cloudflared")
    leftover.write_bytes(b"x")
    engine.remove_leftovers()
    assert not leftover.exists()
    engine.remove_leftovers()            # nothing there: no error
