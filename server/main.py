"""Clipnest Online: the public website version of Clipnest.

Anyone can open the website, paste a link and download the file in their
browser. It runs on a cloud server (see server/Dockerfile and render.yaml),
uses the same yt-dlp commands as the desktop app (clipnest/jobs.py) and the
same web page (clipnest/web/index.html) in "public" mode.

Limits keep one visitor from using up a small free server: a few downloads at
a time, a cap per visitor and per hour, 1080p at most, 500 MB per file, no
whole playlists, and finished files are deleted after 30 minutes.

YouTube and Instagram usually block cloud servers; visitors then get a clear
message pointing to the free desktop app, which works from their own internet.

Run locally:  python -m server.main   (needs yt-dlp and ffmpeg on PATH)
"""

from __future__ import annotations

import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import subprocess
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from clipnest import __version__
from clipnest.jobs import (
    MP3_QUALITIES, MP4_QUALITIES, JobOptions, build_args, detect_source, friendly_error,
    info_args, parse_info, parse_line, unsupported_reason,
)

ENV = os.environ.get
PORT = int(ENV("PORT", "8080"))
YTDLP = ENV("CLIPNEST_YTDLP", "yt-dlp")
EXTRA_ARGS = ENV("CLIPNEST_YTDLP_EXTRA", "").split()      # e.g. a proxy CA option in tests
WORK = Path(ENV("CLIPNEST_WORK", "/tmp/clipnest-online"))
APP_URL = ENV("CLIPNEST_APP_URL", "https://vishnuvk2k.github.io/Clipnest/#download")
MAX_ACTIVE = int(ENV("CLIPNEST_MAX_ACTIVE", "2"))         # downloads running at once
MAX_WAITING = int(ENV("CLIPNEST_MAX_WAITING", "20"))      # downloads waiting in line
PER_VISITOR = int(ENV("CLIPNEST_PER_VISITOR", "3"))       # unfinished per visitor
PER_HOUR = int(ENV("CLIPNEST_PER_HOUR", "20"))            # new downloads per address per hour
KEEP_MINUTES = int(ENV("CLIPNEST_KEEP_MINUTES", "30"))
MAX_FILESIZE = ENV("CLIPNEST_MAX_FILESIZE", "500M")
JOB_TIMEOUT = int(ENV("CLIPNEST_JOB_TIMEOUT", "900"))     # seconds
MP4_ALLOWED = [q for q in MP4_QUALITIES if int(q) <= int(ENV("CLIPNEST_MAX_HEIGHT", "1080"))]

WEB_DIR = Path(__file__).resolve().parent.parent / "clipnest" / "web"
STATIC_FILES = {"/logo.svg": "logo.svg", "/icon.png": "icon.png",
                "/manifest.webmanifest": "manifest.webmanifest",
                "/inter.woff2": "inter.woff2", "/outfit.woff2": "outfit.woff2"}
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("image/svg+xml", ".svg")
VISITOR_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
MAX_BODY = 16 * 1024
CHUNK = 256 * 1024

NOTICE = ("YouTube and Instagram often block online downloaders like this one. "
          "For those, use the free Clipnest app on your computer.")


def blocked_message(log: str) -> str | None:
    """A friendly message when a site refuses to talk to this server."""
    low = log.lower()
    if "sign in to confirm" in low or ("youtube" in low and "429" in low):
        return ("YouTube is blocking downloads from this website right now. The free "
                "Clipnest app on your computer works for YouTube.")
    if "instagram" in low and ("empty media response" in low or "not granting access" in low
                               or "login" in low or "logged-in" in low):
        return ("Instagram only shows this to logged-in people, so this website can't get it. "
                "The free Clipnest app on your computer can use your Instagram login.")
    if "logged-in" in low or "logged in" in low or "login required" in low \
            or "authentication is required" in low or "cookies for the authentication" in low:
        return ("This site only shows this to logged-in people, so this website can't get it. "
                "The free Clipnest app on your computer can use your browser's login.")
    if "file is larger than max-filesize" in low or "larger than max-filesize" in low:
        return f"This file is bigger than this website allows ({MAX_FILESIZE}B). Try a lower quality, or use the Clipnest app."
    return None


def explain(log: str) -> dict:
    blocked = blocked_message(log)
    if blocked:
        return {"error": blocked, "app_url": APP_URL}
    return {"error": friendly_error(log)}


@dataclass
class Job:
    visitor: str
    url: str
    fmt: str
    quality: str
    title: str
    id: str = field(default_factory=lambda: secrets.token_urlsafe(9))
    state: str = "queued"          # queued | running | done | error | cancelled
    status: str = "Waiting…"
    fraction: float = 0.0
    files: list[Path] = field(default_factory=list)
    app_url: str = ""
    created: float = field(default_factory=time.time)
    ended: float = 0.0
    proc: subprocess.Popen | None = None
    _part: int = 1
    _last: float = 0.0

    @property
    def folder(self) -> Path:
        return WORK / self.id

    def to_dict(self) -> dict:
        files = []
        for n, f in enumerate(self.files):
            try:
                files.append({"n": n, "name": f.name, "size": f.stat().st_size})
            except OSError:
                pass
        d = {"id": self.id, "title": self.title, "fmt": self.fmt, "quality": self.quality,
             "state": self.state, "status": self.status, "fraction": round(self.fraction, 4),
             "files": files}
        if self.app_url:
            d["app_url"] = self.app_url
        return d


class Service:
    """Download queue, limits and clean-up. Shared by all request threads."""

    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: dict[str, Job] = {}
        self.waiting: queue.Queue[Job] = queue.Queue()
        self.recent: dict[str, list[float]] = {}        # address -> start times
        self.lookups = threading.Semaphore(4)
        WORK.mkdir(parents=True, exist_ok=True)
        for old in WORK.iterdir():                       # left from a previous run
            shutil.rmtree(old, ignore_errors=True)
        for _ in range(MAX_ACTIVE):
            threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._janitor, daemon=True).start()

    # -- requests -----------------------------------------------------------

    def lookup(self, url: str) -> dict:
        if not detect_source(url):
            return {"error": "Paste a full link that starts with https://"}
        if reason := unsupported_reason(url):
            return {"error": reason}
        if not self.lookups.acquire(timeout=30):
            return {"error": "This website is busy right now. Try again in a minute."}
        args = info_args(YTDLP, url)
        args[1:1] = EXTRA_ARGS
        try:
            p = subprocess.run(args, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            return {"error": "Looking up this link took too long. You can still try to download it."}
        finally:
            self.lookups.release()
        out = p.stdout.decode("utf-8", "replace")
        if p.returncode != 0 or not out.strip():
            return explain(p.stderr.decode("utf-8", "replace") or "Couldn't read this link.")
        try:
            info = parse_info(out)
        except ValueError:
            return {"error": "Couldn't read this link."}
        return {
            "title": info.title, "uploader": info.uploader, "duration": info.duration,
            "thumbnail": info.thumbnail, "source": detect_source(url) or info.source,
            "kind": info.kind, "is_playlist": False, "entries": 0,
            "max_height": min(info.max_height, int(MP4_ALLOWED[0])) if info.max_height else 0,
            "image_size": list(info.image_size) if info.image_size else None,
        }

    def start(self, visitor: str, address: str, body: dict) -> dict:
        url = str(body.get("url", "")).strip()
        fmt, quality = str(body.get("fmt", "")), str(body.get("quality", ""))
        if not detect_source(url):
            return {"error": "Paste a full link that starts with https://"}
        if reason := unsupported_reason(url):
            return {"error": reason}
        if fmt == "image":
            quality = "original"
        elif fmt == "mp4" and quality in MP4_QUALITIES and quality not in MP4_ALLOWED:
            quality = MP4_ALLOWED[0]                     # 4K/1440p -> the best this site allows
        elif not (fmt == "mp3" and quality in MP3_QUALITIES or fmt == "mp4" and quality in MP4_ALLOWED):
            return {"error": "Choose MP3 or MP4 and a quality."}
        now = time.time()
        with self.lock:
            mine = [j for j in self.jobs.values()
                    if j.visitor == visitor and j.state in ("queued", "running")]
            if len(mine) >= PER_VISITOR:
                return {"error": f"You can have {PER_VISITOR} downloads going at once. "
                                 "Wait for one to finish."}
            times = [t for t in self.recent.get(address, []) if now - t < 3600]
            if len(times) >= PER_HOUR:
                return {"error": f"You've reached {PER_HOUR} downloads this hour. "
                                 "Try again later, or use the free Clipnest app."}
            if self.waiting.qsize() >= MAX_WAITING:
                return {"error": "This website is very busy right now. Try again in a few minutes."}
            times.append(now)
            self.recent[address] = times
            job = Job(visitor=visitor, url=url, fmt=fmt, quality=quality,
                      title=str(body.get("title", ""))[:300] or url)
            self.jobs[job.id] = job
        self.waiting.put(job)
        return {"id": job.id}

    def list(self, visitor: str) -> list[dict]:
        with self.lock:
            mine = [j for j in self.jobs.values() if j.visitor == visitor]
        return [j.to_dict() for j in sorted(mine, key=lambda j: j.created, reverse=True)]

    def cancel(self, visitor: str, job_id: str) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.visitor != visitor or job.state not in ("queued", "running"):
                return
            job.state, job.status, job.ended = "cancelled", "Cancelled", time.time()
            proc = job.proc
        if proc:
            proc.kill()

    def file(self, visitor: str, job_id: str, n: int) -> Path | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.visitor != visitor or job.state != "done":
                return None
            if 0 <= n < len(job.files) and job.files[n].is_file():
                return job.files[n]
        return None

    # -- background -----------------------------------------------------------

    def _worker(self) -> None:
        while True:
            job = self.waiting.get()
            if job.state == "queued":
                try:
                    self._run(job)
                except Exception as exc:                  # never leave a job hanging
                    self._end(job, "error", f"Something went wrong: {exc}")

    def _run(self, job: Job) -> None:
        job.folder.mkdir(parents=True, exist_ok=True)
        opts = JobOptions(url=job.url, fmt=job.fmt, quality=job.quality, out_dir=str(job.folder),
                          cover_art=True, tags=True, subtitles=False, playlist=False)
        args = build_args(YTDLP, opts)
        args[1:1] = [*EXTRA_ARGS, "--max-filesize", MAX_FILESIZE]
        log: list[str] = []
        with self.lock:
            if job.state != "queued":
                return
            job.state, job.status = "running", "Starting…"
            proc = job.proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        timed_out = threading.Event()
        timer = threading.Timer(JOB_TIMEOUT, lambda: (timed_out.set(), proc.kill()))
        timer.start()
        files: list[Path] = []
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            ev = parse_line(line)
            if ev.kind == "progress" and ev.progress.fraction is not None:
                if ev.progress.fraction < job._last - 0.5:
                    job._part += 1
                job._last = job.fraction = ev.progress.fraction
                bits = [f"{ev.progress.fraction * 100:.0f}%"]
                if job.fmt == "mp4":
                    bits.insert(0, "Video" if job._part == 1 else "Audio")
                job.status = " · ".join(bits)
            elif ev.kind == "postprocess" and ev.text != "Finishing…":
                job.status = ev.text
            elif ev.kind == "title":
                job.title = ev.text
            elif ev.kind == "file":
                files.append(Path(ev.text))
            elif ev.kind == "log":
                log.append(line)
                del log[:-200]
        code = proc.wait()
        timer.cancel()
        if job.state == "cancelled":
            shutil.rmtree(job.folder, ignore_errors=True)
            return
        files = [f for f in files if f.is_file() and job.folder in f.resolve().parents]
        if code == 0 and files:
            job.files = files
            job.fraction = 1.0
            self._end(job, "done", "Done")
        elif code == 0:
            self._end(job, "error", "Nothing was downloaded from this link.")
        else:
            result = explain("\n".join(log)) if log else {"error": "The download stopped."}
            if timed_out.is_set():
                result = {"error": "This download took too long and was stopped."}
            job.app_url = result.get("app_url", "")
            self._end(job, "error", result["error"])

    def _end(self, job: Job, state: str, status: str) -> None:
        with self.lock:
            job.state, job.status, job.ended, job.proc = state, status, time.time(), None
        if state != "done":
            shutil.rmtree(job.folder, ignore_errors=True)

    def _janitor(self) -> None:
        while True:
            time.sleep(60)
            self.clean()

    def clean(self, now: float | None = None) -> None:
        """Deletes finished downloads (and their files) after KEEP_MINUTES."""
        now = now or time.time()
        with self.lock:
            old = [j for j in self.jobs.values()
                   if j.ended and now - j.ended > KEEP_MINUTES * 60]
            for j in old:
                del self.jobs[j.id]
            for addr in list(self.recent):
                self.recent[addr] = [t for t in self.recent[addr] if now - t < 3600]
                if not self.recent[addr]:
                    del self.recent[addr]
        for j in old:
            shutil.rmtree(j.folder, ignore_errors=True)


def content_disposition(name: str) -> str:
    ascii_name = name.encode("ascii", "replace").decode().replace('"', "'").replace("?", "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(name)}"


class Handler(BaseHTTPRequestHandler):
    service: Service
    server_version = "Clipnest"
    sys_version = ""

    def log_message(self, *args) -> None:
        pass

    def _headers(self, status: int, ctype: str, length: int | None = None, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _address(self) -> str:
        # Render and most hosts put the visitor's address first in X-Forwarded-For.
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() or self.client_address[0]

    def _visitor(self, query: dict) -> str | None:
        v = self.headers.get("X-Clipnest-Key") or (query.get("key") or [""])[0]
        return v if VISITOR_RE.match(v) else None

    def _body(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n > MAX_BODY:
            return None
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            return self._static("index.html", "text/html; charset=utf-8")
        if path in STATIC_FILES:
            name = STATIC_FILES[path]
            ctype = "application/manifest+json" if name.endswith("webmanifest") else \
                mimetypes.guess_type(name)[0] or "application/octet-stream"
            return self._static(name, ctype)
        if path == "/api/health":
            return self._json({"ok": True, "version": __version__})
        if path == "/api/hello":
            return self._json({"public": True, "notice": NOTICE, "app_url": APP_URL,
                               "max_quality": MP4_ALLOWED[0], "keep_minutes": KEEP_MINUTES})
        visitor = self._visitor(query)
        if path.startswith("/api/") and visitor is None:
            return self._json({"error": "unauthorized"}, 403)
        if path == "/api/status":
            return self._json({"ready": True, "version": __version__})
        if path == "/api/jobs":
            return self._json({"jobs": self.service.list(visitor), "run": "online"})
        if path.startswith("/api/file/"):
            return self._file(visitor, path)
        self._json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        visitor = self._visitor(query)
        if visitor is None:
            return self._json({"error": "unauthorized"}, 403)
        body = self._body()
        if body is None:
            return self._json({"error": "Bad request"}, 400)
        if path == "/api/info":
            return self._json(self.service.lookup(str(body.get("url", "")).strip()))
        if path == "/api/download":
            return self._json(self.service.start(visitor, self._address(), body))
        if path == "/api/cancel":
            self.service.cancel(visitor, str(body.get("id", "")))
            return self._json({"ok": True})
        self._json({"error": "Not found"}, 404)

    def _static(self, name: str, ctype: str) -> None:
        try:
            data = (WEB_DIR / name).read_bytes()
        except OSError:
            return self._json({"error": "Not found"}, 404)
        self._headers(200, ctype, len(data))
        self.wfile.write(data)

    def _file(self, visitor: str, path: str) -> None:
        parts = path.split("/")             # ['', 'api', 'file', '<id>', '<n>']
        try:
            job_id, n = parts[3], int(parts[4])
        except (IndexError, ValueError):
            return self._json({"error": "Not found"}, 404)
        f = self.service.file(visitor, job_id, n)
        if f is None:
            return self._json({"error": "This file has expired. Download it again."}, 404)
        size = f.stat().st_size
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        self._headers(200, ctype, size, {"Content-Disposition": content_disposition(f.name)})
        try:
            with f.open("rb") as fh:
                while chunk := fh.read(CHUNK):
                    self.wfile.write(chunk)
        except (ConnectionError, OSError):
            pass


def make_server(port: int = PORT) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"service": Service()})
    httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
    httpd.daemon_threads = True
    return httpd


def main() -> None:
    httpd = make_server()
    print(f"Clipnest Online {__version__} on port {httpd.server_address[1]}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
