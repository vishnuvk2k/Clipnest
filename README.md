<p align="center"><img src="assets/fetchly.png" width="112" alt="Fetchly logo"></p>

<h1 align="center">Fetchly</h1>
<p align="center"><em>Say it: FETCH-lee</em><br>A free, open-source desktop app to save YouTube and Instagram media as MP3 or MP4.</p>

## Features

- **MP3 audio** at 320, 256, 192 or 128 kbps, with cover art and title/artist tags
- **MP4 video** at 4K, 1440p, 1080p or 720p, with sound, optional subtitles
- **YouTube** videos, Shorts, music and whole playlists
- **Instagram** Reels and video posts, and Reel audio as MP3
- Original files, **no watermark**, no ads, no account
- Download queue with progress, history, and auto-paste of copied links
- The download engine (yt-dlp) **updates itself** when Fetchly starts, so it keeps working when sites change

## Download

Get `Fetchly.exe` from the [Releases](../../releases) page and run it. No install needed.

On first launch Fetchly downloads its engine (yt-dlp and FFmpeg, about 100 MB) into
`%LOCALAPPDATA%\Fetchly`. After that it works offline apart from the downloads themselves.

> Windows SmartScreen may warn about an unknown publisher because the app isn't code-signed.
> Click **More info → Run anyway**.

## If a download fails

- **"Confirm you're not a bot" or a private Instagram post:** open **Settings → Logins**, choose
  the browser where you're logged in to YouTube/Instagram, close that browser, and try again.
- **A site changed and downloads stopped working:** **Settings → Check for updates**.

## Run from source

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python Fetchly.py
```

You need FFmpeg and yt-dlp: on Windows Fetchly downloads both itself. On macOS/Linux install
FFmpeg with your package manager (`brew install ffmpeg`, `sudo apt install ffmpeg`); Fetchly
downloads yt-dlp.

Run the tests with `python -m pytest`. Build the single-file app with `pyinstaller fetchly.spec`
(output in `dist/`). GitHub Actions builds `Fetchly.exe` on every push and attaches it to a
release when you push a tag such as `v1.0.0`.

## How it works

| File | What it does |
|---|---|
| `fetchly/app.py` | The window: download page, history, settings |
| `fetchly/downloads.py` | Runs downloads in the background, two at a time, with a queue |
| `fetchly/jobs.py` | Builds yt-dlp commands for each format and reads its progress |
| `fetchly/engine.py` | Installs and updates yt-dlp and FFmpeg |
| `fetchly/store.py` | Saves settings and history |
| `fetchly/theme.py` | Colors, styles, icons and the logo |

## Responsible use

Fetchly is a tool. Download only content you own, that's licensed for reuse (for example
Creative Commons), or that you otherwise have the right to save. Respect creators' copyright and
the terms of the sites you use. Fetchly isn't affiliated with YouTube, Google, Instagram or Meta.

## Credits and license

Fetchly is MIT licensed (see [LICENSE](LICENSE)). It uses
[yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), [FFmpeg](https://ffmpeg.org) (GPL build,
downloaded separately at runtime) and [Qt for Python](https://www.qt.io/qt-for-python) (LGPL).
