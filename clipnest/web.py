"""Clipnest Web: lets a phone (or any browser on the same network) use Clipnest.

The app serves one small web page. Someone with the secret link pastes a link
there, the download runs here on this computer (so it uses this computer's
internet connection and browser logins, which YouTube and Instagram accept),
and the finished file can be saved to the phone. Files are also kept in the
usual Downloads folder on the computer.

The HTTP server runs in background threads (Python's standard library), and
anything that touches the download queue is handed to the Qt main thread.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import mimetypes
import secrets
import subprocess
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface

from . import __version__, browsers, engine
from .jobs import (
    MP3_QUALITIES, MP4_QUALITIES, JobOptions, detect_source, friendly_error, info_args,
    parse_info, unsupported_reason,
)

DEFAULT_PORT = 8765
RUN_ID = secrets.token_hex(4)      # job numbers restart with the app; this tells runs apart
PORT_TRIES = 10
WEB_DIR = Path(__file__).with_name("web")
STATIC_FILES = {"/logo.svg": "logo.svg", "/icon.png": "icon.png",
                "/manifest.webmanifest": "manifest.webmanifest",
                "/inter.woff2": "inter.woff2", "/outfit.woff2": "outfit.woff2"}
mimetypes.add_type("font/woff2", ".woff2")      # unknown to some Windows setups
mimetypes.add_type("image/svg+xml", ".svg")
MAX_BODY = 16 * 1024
CHUNK = 256 * 1024


def new_key() -> str:
    return secrets.token_urlsafe(18)


def key_ok(given: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


def _rank(addr: str) -> tuple[int, str]:
    ip = ipaddress.ip_address(addr)
    if ip in ipaddress.ip_network("100.64.0.0/10"):
        return (1, addr)        # Tailscale and similar: works away from home
    if ip.is_private:
        return (0, addr)        # home Wi-Fi: what most people want first
    return (2, addr)


def lan_addresses() -> list[str]:
    """This computer's IPv4 addresses that other devices can reach, best first."""
    found = []
    for iface in QNetworkInterface.allInterfaces():
        flags = iface.flags()
        if not (flags & QNetworkInterface.IsUp and flags & QNetworkInterface.IsRunning):
            continue
        if flags & QNetworkInterface.IsLoopBack:
            continue
        for entry in iface.addressEntries():
            ip = entry.ip()
            if ip.protocol() != QAbstractSocket.IPv4Protocol:
                continue
            addr = ip.toString()
            if addr.startswith("169.254.") or addr in found:
                continue      # 169.254: no network (Windows' self-assigned address)
            found.append(addr)
    return sorted(found, key=_rank)


def job_to_dict(job) -> dict:
    files = []
    for n, f in enumerate(job.files):
        p = Path(f)
        try:
            size = p.stat().st_size
        except OSError:
            continue          # moved or deleted on the computer
        files.append({"n": n, "name": p.name, "size": size})
    return {
        "id": job.id, "title": job.title, "fmt": job.opts.fmt, "quality": job.opts.quality,
        "state": job.state, "status": job.status, "fraction": round(job.fraction, 4),
        "files": files,
    }


def content_disposition(name: str) -> str:
    """Attachment header that keeps non-English names and emoji intact."""
    ascii_name = name.encode("ascii", "replace").decode().replace('"', "'").replace("?", "_")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(name)}"


class _Bridge(QObject):
    """Runs queue changes on the Qt main thread for the server threads."""
    start_requested = Signal(object)
    cancel_requested = Signal(int)

    def __init__(self, manager, settings):
        super().__init__()
        self.manager, self.settings = manager, settings
        self.start_requested.connect(self._start)
        self.cancel_requested.connect(self._cancel)

    def _start(self, req: dict) -> None:
        try:
            s = self.settings
            fmt = req["fmt"]
            out_dir = s["mp3_dir" if fmt == "mp3" else "mp4_dir"]
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            opts = JobOptions(
                url=req["url"], fmt=fmt, quality=req["quality"], out_dir=out_dir,
                cover_art=s["cover_art"], tags=s["tags"], subtitles=s["subtitles"],
                playlist=req["playlist"],
                cookies_browser=browsers.cookies_arg(s["cookies_browser"]),
            )
            job = self.manager.add(opts, req["title"] or req["url"], origin="web")
            req["job_id"] = job.id
        except Exception as exc:          # report, never leave the phone waiting
            req["error"] = f"Couldn't start the download: {exc}"
        finally:
            req["done"].set()

    def _cancel(self, job_id: int) -> None:
        for job in self.manager.jobs:
            if job.id == job_id and job.origin == "web":
                self.manager.cancel(job)


class WebServer(QObject):
    state_changed = Signal()

    def __init__(self, manager, settings, engine_ready, parent=None):
        super().__init__(parent)
        self.manager, self.settings = manager, settings
        self.engine_ready = engine_ready          # callable -> bool
        self.bridge = _Bridge(manager, settings)
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.error = ""

    # -- control (main thread) ------------------------------------------

    @property
    def running(self) -> bool:
        return self.httpd is not None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1] if self.httpd else 0

    def key(self) -> str:
        if not self.settings["web_key"]:
            self.settings.set("web_key", new_key())
        return self.settings["web_key"]

    def new_link(self) -> None:
        """A new secret key: phones with the old link lose access."""
        self.settings.set("web_key", new_key())
        self.state_changed.emit()

    def urls(self) -> list[str]:
        if not self.running:
            return []
        return [f"http://{a}:{self.port}/?key={self.key()}" for a in lan_addresses()]

    def start(self) -> bool:
        if self.running:
            return True
        self.key()
        self.error = ""
        handler = type("Handler", (_Handler,), {"app": self})
        for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_TRIES):
            try:
                self.httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
                break
            except OSError:
                continue
        else:
            self.error = (f"Couldn't start Clipnest Web: ports {DEFAULT_PORT}–"
                          f"{DEFAULT_PORT + PORT_TRIES - 1} are all in use.")
            self.state_changed.emit()
            return False
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="clipnest-web",
                                       daemon=True)
        self.thread.start()
        self.state_changed.emit()
        return True

    def stop(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
            self.state_changed.emit()

    # -- used by the server threads -------------------------------------

    def web_jobs(self) -> list[dict]:
        jobs = [j for j in list(self.manager.jobs) if j.origin == "web"]
        return [job_to_dict(j) for j in reversed(jobs)]

    def find_file(self, job_id: int, n: int) -> Path | None:
        for job in list(self.manager.jobs):
            if job.id == job_id and job.origin == "web" and job.state == "done":
                if 0 <= n < len(job.files):
                    p = Path(job.files[n])
                    return p if p.is_file() else None
        return None

    def lookup(self, url: str) -> dict:
        if reason := unsupported_reason(url):
            return {"error": reason}
        ytdlp = engine.ytdlp_path()
        if ytdlp is None:
            return {"error": "The download engine is missing. Restart Clipnest on your computer."}
        deno = engine.deno_path()
        args = info_args(str(ytdlp), url, browsers.cookies_arg(self.settings["cookies_browser"]),
                         str(deno) if deno else "")
        try:
            p = subprocess.run(args, capture_output=True, timeout=90,
                               creationflags=engine.NO_WINDOW)
        except subprocess.TimeoutExpired:
            return {"error": "Looking up this link took too long. You can still try to download it."}
        except OSError as exc:
            return {"error": f"Couldn't start the download engine: {exc}"}
        out = p.stdout.decode("utf-8", "replace")
        if p.returncode != 0 or not out.strip():
            return {"error": friendly_error(p.stderr.decode("utf-8", "replace")
                                            or "Couldn't read this link.")}
        try:
            info = parse_info(out)
        except ValueError:
            return {"error": "Couldn't read this link."}
        return {
            "title": info.title, "uploader": info.uploader, "duration": info.duration,
            "thumbnail": info.thumbnail, "source": detect_source(url) or info.source,
            "kind": info.kind, "is_playlist": info.is_playlist, "entries": info.entries,
            "max_height": info.max_height,
            "image_size": list(info.image_size) if info.image_size else None,
        }

    def request_download(self, body: dict) -> dict:
        url = str(body.get("url", "")).strip()
        fmt = str(body.get("fmt", ""))
        quality = str(body.get("quality", ""))
        if not detect_source(url):
            return {"error": "Paste a full link that starts with https://"}
        if reason := unsupported_reason(url):
            return {"error": reason}
        if fmt == "mp3" and quality not in MP3_QUALITIES or \
                fmt == "mp4" and quality not in MP4_QUALITIES or \
                fmt not in ("mp3", "mp4", "image"):
            return {"error": "Choose MP3 or MP4 and a quality."}
        if fmt == "image":
            quality = "original"
        if not self.engine_ready():
            return {"error": "Clipnest is still setting up on your computer. Try again in a minute."}
        req = {"url": url, "fmt": fmt, "quality": quality,
               "playlist": bool(body.get("playlist")),
               "title": str(body.get("title", ""))[:300], "done": threading.Event()}
        self.bridge.start_requested.emit(req)
        if not req["done"].wait(10):
            return {"error": "Clipnest on your computer didn't respond. Is it still open?"}
        if "error" in req:
            return {"error": req["error"]}
        return {"id": req["job_id"]}


class _Handler(BaseHTTPRequestHandler):
    app: WebServer
    server_version = "Clipnest"
    sys_version = ""

    def log_message(self, *args) -> None:    # keep the app's output quiet
        pass

    # -- helpers ----------------------------------------------------------

    def _headers(self, status: int, ctype: str, length: int | None = None,
                 extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")   # the link holds the key
        self.send_header("X-Frame-Options", "DENY")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _authorized(self, query: dict) -> bool:
        given = self.headers.get("X-Clipnest-Key") or (query.get("key") or [""])[0]
        return key_ok(given, self.app.key())

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

    # -- routes -------------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if path in ("/", "/index.html"):
            self._static("index.html", "text/html; charset=utf-8")
            return
        if path in STATIC_FILES:
            name = STATIC_FILES[path]
            ctype = "application/manifest+json" if name.endswith("webmanifest") else \
                mimetypes.guess_type(name)[0] or "application/octet-stream"
            self._static(name, ctype)
            return
        if not path.startswith("/api/"):
            self._json({"error": "Not found"}, 404)
            return
        if not self._authorized(query):
            self._json({"error": "unauthorized"}, 403)
            return
        if path == "/api/status":
            self._json({"ready": self.app.engine_ready(), "version": __version__})
        elif path == "/api/jobs":
            self._json({"jobs": self.app.web_jobs(), "run": RUN_ID})
        elif path.startswith("/api/file/"):
            self._file(path)
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        if not self._authorized(query):
            self._json({"error": "unauthorized"}, 403)
            return
        body = self._body()
        if body is None:
            self._json({"error": "Bad request"}, 400)
            return
        if path == "/api/info":
            url = str(body.get("url", "")).strip()
            if not detect_source(url):
                self._json({"error": "Paste a full link that starts with https://"})
            else:
                self._json(self.app.lookup(url))
        elif path == "/api/download":
            self._json(self.app.request_download(body))
        elif path == "/api/cancel":
            try:
                self.app.bridge.cancel_requested.emit(int(body.get("id")))
            except (TypeError, ValueError):
                pass
            self._json({"ok": True})
        else:
            self._json({"error": "Not found"}, 404)

    def _static(self, name: str, ctype: str) -> None:
        try:
            data = (WEB_DIR / name).read_bytes()
        except OSError:
            self._json({"error": "Not found"}, 404)
            return
        self._headers(200, ctype, len(data))
        self.wfile.write(data)

    def _file(self, path: str) -> None:
        parts = path.split("/")          # ['', 'api', 'file', '<id>', '<n>']
        try:
            job_id, n = int(parts[3]), int(parts[4])
        except (IndexError, ValueError):
            self._json({"error": "Not found"}, 404)
            return
        f = self.app.find_file(job_id, n)
        if f is None:
            self._json({"error": "This file isn't on the computer any more."}, 404)
            return
        size = f.stat().st_size
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        self._headers(200, ctype, size, {"Content-Disposition": content_disposition(f.name)})
        try:
            with f.open("rb") as fh:
                while chunk := fh.read(CHUNK):
                    self.wfile.write(chunk)
        except (ConnectionError, OSError):
            pass          # the phone cancelled the download
