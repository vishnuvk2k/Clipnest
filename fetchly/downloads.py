"""Runs downloads in the background with QProcess and keeps the queue moving."""

from __future__ import annotations

import itertools
import subprocess
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from . import engine
from .jobs import JobOptions, LineEvent, build_args, format_bytes, friendly_error, parse_line

MAX_PARALLEL = 2

_ids = itertools.count(1)


@dataclass
class Job:
    opts: JobOptions
    title: str
    id: int = field(default_factory=lambda: next(_ids))
    state: str = "queued"          # queued | running | done | error | cancelled
    fraction: float = 0.0
    status: str = "Waiting…"
    files: list[str] = field(default_factory=list)
    error: str = ""
    process: QProcess | None = None
    log: list[str] = field(default_factory=list)
    _buffer: str = ""
    _part: int = 1
    _last_fraction: float = 0.0


class DownloadManager(QObject):
    job_added = Signal(object)
    job_changed = Signal(object)
    job_finished = Signal(object)
    active_count_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs: list[Job] = []

    def add(self, opts: JobOptions, title: str) -> Job:
        job = Job(opts=opts, title=title)
        self.jobs.append(job)
        self.job_added.emit(job)
        self._pump()
        return job

    def cancel(self, job: Job) -> None:
        if job.state == "queued":
            self._finish(job, "cancelled", "Cancelled")
        elif job.state == "running" and job.process is not None:
            job.state = "cancelled"
            self._kill_tree(job.process)

    def active_count(self) -> int:
        return sum(j.state in ("queued", "running") for j in self.jobs)

    def shutdown(self) -> None:
        for job in self.jobs:
            if job.state == "running" and job.process is not None:
                job.state = "cancelled"
                self._kill_tree(job.process)
                job.process.waitForFinished(3000)

    # -- internals ---------------------------------------------------------

    def _pump(self) -> None:
        running = sum(j.state == "running" for j in self.jobs)
        for job in self.jobs:
            if running >= MAX_PARALLEL:
                break
            if job.state == "queued":
                self._start(job)
                running += 1
        self.active_count_changed.emit(self.active_count())

    def _start(self, job: Job) -> None:
        try:
            self._launch(job)
        except Exception as exc:   # never leave a job stuck on "Waiting…"
            self._finish(job, "error", f"Couldn't start the download: {exc}")

    def _launch(self, job: Job) -> None:
        ytdlp = engine.ytdlp_path()
        if ytdlp is None:
            self._finish(job, "error", "The download engine is missing. Restart Fetchly.")
            return
        ffmpeg = engine.ffmpeg_path()
        job.opts.ffmpeg_dir = str(ffmpeg.parent) if ffmpeg else ""
        deno = engine.deno_path()
        job.opts.deno = str(deno) if deno else ""
        args = build_args(str(ytdlp), job.opts)

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        proc.setProcessEnvironment(env)
        # No console window flashes up on Windows: Qt starts child processes of
        # a GUI app with CREATE_NO_WINDOW by itself.
        proc.readyReadStandardOutput.connect(lambda: self._read(job))
        proc.finished.connect(lambda code, _status: self._done(job, code))
        proc.errorOccurred.connect(lambda err: self._failed_to_start(job, err))
        job.process = proc
        job.state = "running"
        job.status = "Starting…"
        self.job_changed.emit(job)
        proc.start(args[0], args[1:])

    def _read(self, job: Job) -> None:
        data = bytes(job.process.readAllStandardOutput()).decode("utf-8", "replace")
        job._buffer += data.replace("\r\n", "\n").replace("\r", "\n")
        *lines, job._buffer = job._buffer.split("\n")
        changed = False
        for line in lines:
            if line:
                changed |= self._handle(job, parse_line(line), line)
        if changed:
            self.job_changed.emit(job)

    def _handle(self, job: Job, ev: LineEvent, raw: str) -> bool:
        if job.state != "running":
            return False
        if ev.kind == "progress":
            p = ev.progress
            if p.fraction is None:
                return False
            # MP4s arrive as two streams (video, then audio): count the parts.
            if p.fraction < job._last_fraction - 0.5:
                job._part += 1
            job._last_fraction = p.fraction
            job.fraction = p.fraction
            bits = [f"{p.fraction * 100:.0f}%"]
            if p.speed:
                bits.append(f"{format_bytes(p.speed)}/s")
            if p.eta:
                bits.append(f"{int(p.eta) // 60}:{int(p.eta) % 60:02d} left")
            if p.items and p.items > 1 and p.item:
                bits.insert(0, f"{p.item} of {p.items}")
            elif job.opts.fmt == "mp4":
                bits.insert(0, "Video" if job._part == 1 else "Audio")
            job.status = " · ".join(bits)
            return True
        if ev.kind == "postprocess":
            if ev.text != "Finishing…" and job.status != ev.text:
                job.status = ev.text
                return True
            return False
        if ev.kind == "title":
            job.title = ev.text
            job._part = 1
            job._last_fraction = 0.0
            return True
        if ev.kind == "file":
            job.files.append(ev.text)
            return False
        job.log.append(raw)
        del job.log[:-200]
        return False

    def _done(self, job: Job, code: int) -> None:
        if job._buffer:
            self._handle(job, parse_line(job._buffer), job._buffer)
            job._buffer = ""
        if job.state == "cancelled":
            self._finish(job, "cancelled", "Cancelled")
        elif code == 0:
            job.fraction = 1.0
            n = len(job.files)
            self._finish(job, "done", "Done" if n <= 1 else f"Done · {n} files")
        else:
            self._finish(job, "error", friendly_error("\n".join(job.log)))

    def _failed_to_start(self, job: Job, err) -> None:
        if err == QProcess.FailedToStart:
            self._finish(job, "error", "Couldn't start the download engine. Restart Fetchly.")

    def _finish(self, job: Job, state: str, status: str) -> None:
        job.state = state
        job.status = status
        if state == "error":
            job.error = status
        if job.process is not None:
            job.process.deleteLater()
            job.process = None
        self.job_changed.emit(job)
        self.job_finished.emit(job)
        self._pump()

    @staticmethod
    def _kill_tree(proc: QProcess) -> None:
        if engine.IS_WINDOWS and proc.processId():
            # Also stops the ffmpeg child that yt-dlp may be running.
            subprocess.run(
                ["taskkill", "/PID", str(proc.processId()), "/T", "/F"],
                capture_output=True, creationflags=engine.NO_WINDOW,
            )
        else:
            proc.kill()
