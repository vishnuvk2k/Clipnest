"""Puts Clipnest Web on your own domain with Cloudflare Tunnel.

You create a tunnel in the Cloudflare dashboard (free), point its public
hostname (e.g. getclipnest.com) at http://localhost:8765, and paste the
tunnel's token into Clipnest. Clipnest then runs Cloudflare's `cloudflared`
program, which connects out to Cloudflare: no router or firewall changes,
and HTTPS comes from Cloudflare.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QThread, QTimer, Signal

from . import engine

RETRY_SECONDS = 30


def normalize_address(text: str) -> str:
    """'getclipnest.com' -> 'https://getclipnest.com'."""
    text = text.strip().rstrip("/")
    if text and "://" not in text:
        text = "https://" + text
    return text


def parse_token(text: str) -> str:
    """Accepts the bare token or the whole install command Cloudflare shows."""
    words = text.strip().split()
    if not words:
        return ""
    if "--token" in words and words.index("--token") + 1 < len(words):
        return words[words.index("--token") + 1]
    return max(words, key=len)          # the token is by far the longest word


def classify(line: str) -> tuple[str, str] | None:
    """Turns a cloudflared log line into (state, message), or None."""
    low = line.lower()
    if "registered tunnel connection" in low:
        return ("online", "")
    if "token" in low and ("not valid" in low or "invalid" in low or "malformed" in low):
        return ("error", "Cloudflare didn't accept the tunnel token. Copy it again from the "
                         "Cloudflare dashboard.")
    if "unauthorized" in low or "tunnel not found" in low or ("deleted" in low and "tunnel" in low):
        return ("error", "Cloudflare says this tunnel doesn't exist any more. Create a new "
                         "one and paste its token.")
    if "no such host" in low or "failed to dial" in low or (
            "connection refused" in low and "edge" in low):
        return ("connecting", "Can't reach Cloudflare yet. Check the internet connection.")
    return None


class _Installer(QThread):
    done = Signal(bool, str)

    def run(self):
        try:
            engine.install_cloudflared(lambda *_: None)
            self.done.emit(True, "")
        except Exception as exc:
            self.done.emit(False, str(exc))


class Tunnel(QObject):
    """States: off, installing, connecting, online, error."""
    state_changed = Signal()

    def __init__(self, settings, web, parent=None):
        super().__init__(parent)
        self.settings, self.web = settings, web
        self.state = "off"
        self.message = ""
        self.proc: QProcess | None = None
        self.installer: _Installer | None = None
        self._buffer = ""
        self._wanted = False
        self.retry = QTimer(self, singleShot=True, interval=RETRY_SECONDS * 1000)
        self.retry.timeout.connect(self._launch)

    def _set(self, state: str, message: str = "") -> None:
        if (state, message) != (self.state, self.message):
            self.state, self.message = state, message
            self.state_changed.emit()

    def start(self) -> None:
        self._wanted = True
        token = self.settings["tunnel_token"]
        if not token:
            self._set("error", "Paste the tunnel token from Cloudflare first.")
            return
        if not self.web.running and not self.web.start():
            self._set("error", self.web.error or "Couldn't start Clipnest Web.")
            return
        if engine.cloudflared_path() is None:
            self._set("installing", "Downloading Cloudflare Tunnel…")
            if self.installer is None:
                self.installer = _Installer(self)
                self.installer.done.connect(self._installed)
                self.installer.start()
            return
        self._launch()

    def _installed(self, ok: bool, error: str) -> None:
        self.installer.deleteLater()
        self.installer = None
        if not ok:
            self._set("error", f"Couldn't download Cloudflare Tunnel: {error}")
        elif self._wanted:
            self._launch()

    def _launch(self) -> None:
        if not self._wanted or self.proc is not None:
            return
        exe = engine.cloudflared_path()
        if exe is None:
            self.start()
            return
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        # The token goes in the environment, not on the command line, so it
        # doesn't show up in process lists.
        env.insert("TUNNEL_TOKEN", self.settings["tunnel_token"])
        proc.setProcessEnvironment(env)
        proc.readyReadStandardOutput.connect(lambda: self._read(proc))
        proc.finished.connect(lambda code, _s: self._finished(proc, code))
        proc.errorOccurred.connect(lambda err: err == QProcess.FailedToStart and self._finished(proc, -1))
        self.proc = proc
        self._buffer = ""
        self._set("connecting", "Connecting to Cloudflare…")
        proc.start(str(exe), ["tunnel", "--no-autoupdate", "run"])

    def _read(self, proc: QProcess) -> None:
        self._buffer += bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            result = classify(line)
            if result:
                self._set(*result)

    def _finished(self, proc: QProcess, code: int) -> None:
        if proc is not self.proc:
            return
        self.proc = None
        proc.deleteLater()
        if not self._wanted:
            self._set("off")
            return
        if self.state == "error":
            return              # e.g. a wrong token: retrying won't help
        self._set("connecting", f"The tunnel stopped. Trying again in {RETRY_SECONDS} seconds…")
        self.retry.start()

    def stop(self) -> None:
        self._wanted = False
        self.retry.stop()
        if self.proc is not None:
            proc, self.proc = self.proc, None
            proc.kill()
            proc.waitForFinished(3000)
            proc.deleteLater()
        self._set("off")
