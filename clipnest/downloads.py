"""Runs downloads in the background with QProcess and keeps the queue moving."""

from __future__ import annotations

import itertools
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from . import engine
from .jobs import JobOptions, LineEvent, build_args, format_bytes, friendly_error, parse_line

MAX_PARALLEL = 2
STALE_WORK_SECONDS = 12 * 3600


def work_root() -> Path:
    return engine.data_dir() / "work"


def clean_old_work_dirs(root: Path | None = None) -> None:
    """Removes work folders left behind by a crash or a forced shutdown."""
    root = root or work_root()
    if not root.is_dir():
        return
    for d in root.iterdir():
        try:
            if time.time() - d.stat().st_mtime > STALE_WORK_SECONDS:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def unique_path(path: Path) -> Path:
    """'song.mp3' -> 'song (2).mp3' when the name is taken, never overwriting."""
    if not path.exists():
        return path
    for n in itertools.count(2):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate


def move_finished(files: list[str], work_dir: Path, out_dir: Path) -> list[str]:
    """Moves finished files from the work folder into the user's folder.

    yt-dlp never sees the user's folder, so it can't reuse (and then delete) a
    file that's already there, e.g. the MP4 of a video now being saved as MP3.
    Playlist subfolders are kept.
    """
    moved = []
    for f in files:
        src = Path(f)
        if not src.is_file():
            continue
        try:
            rel = src.resolve().relative_to(work_dir.resolve())
        except ValueError:
            rel = Path(src.name)
        dest = unique_path(out_dir / rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        moved.append(str(dest))
    return moved

_ids = itertools.count(1)


@dataclass
class Job:
    opts: JobOptions
    title: str
    id: int = field(default_factory=lambda: next(_ids))
    origin: str = "app"            # "web" when started from Clipnest Web
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
        clean_old_work_dirs()

    def add(self, opts: JobOptions, title: str, origin: str = "app") -> Job:
        job = Job(opts=opts, title=title, origin=origin)
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
                shutil.rmtree(job.opts.work_dir, ignore_errors=True)

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
            self._finish(job, "error", "The download engine is missing. Restart Clipnest.")
            return
        ffmpeg = engine.ffmpeg_path()
        job.opts.ffmpeg_dir = str(ffmpeg.parent) if ffmpeg else ""
        deno = engine.deno_path()
        job.opts.deno = str(deno) if deno else ""
        work = work_root() / f"{os.getpid()}-{job.id}"
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        job.opts.work_dir = str(work)
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
            return
        # Keep whatever finished, even when a later playlist item failed.
        try:
            job.files = move_finished(job.files, Path(job.opts.work_dir), Path(job.opts.out_dir))
        except OSError as exc:
            self._finish(job, "error", f"Couldn't save the file to {job.opts.out_dir}: {exc}")
            return
        if code == 0 and job.files:
            job.fraction = 1.0
            n = len(job.files)
            self._finish(job, "done", "Done" if n == 1 else f"Done · {n} files")
        elif code == 0:
            self._finish(job, "error", "Nothing was downloaded from this link.")
        else:
            self._finish(job, "error", friendly_error("\n".join(job.log)))

    def _failed_to_start(self, job: Job, err) -> None:
        if err == QProcess.FailedToStart:
            self._finish(job, "error", "Couldn't start the download engine. Restart Clipnest.")

    def _finish(self, job: Job, state: str, status: str) -> None:
        job.state = state
        job.status = status
        if state == "error":
            job.error = status
        if job.process is not None:
            job.process.deleteLater()
            job.process = None
        if job.opts.work_dir:
            shutil.rmtree(job.opts.work_dir, ignore_errors=True)
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
