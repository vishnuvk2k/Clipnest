import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from server import main as online


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(online, "WORK", tmp_path / "work")
    monkeypatch.setattr(online.Service, "_worker", lambda self: None)     # no real downloads
    monkeypatch.setattr(online.Service, "_janitor", lambda self: None)
    return online.Service()


V1, V2 = "a" * 24, "b" * 24


def ask(svc, visitor=V1, address="1.1.1.1", **body):
    body = {"url": "https://www.pinterest.com/pin/1/", "fmt": "mp3", "quality": "320", **body}
    return svc.start(visitor, address, body)


def test_quality_is_capped_and_checked(service):
    r = ask(service, fmt="mp4", quality="2160")
    assert "id" in r and service.jobs[r["id"]].quality == "1080"
    assert "quality" in ask(service, V2, fmt="mp4", quality="999")["error"]
    assert "quality" in ask(service, V2, fmt="exe")["error"]
    assert "https://" in ask(service, V2, url="not a link")["error"]
    assert "Reel" in ask(service, V2, url="https://www.instagram.com/reels/audio/1/")["error"]


def test_limits_per_visitor_and_per_hour(service, monkeypatch):
    for _ in range(online.PER_VISITOR):
        assert "id" in ask(service)
    assert "at once" in ask(service)["error"]
    monkeypatch.setattr(online, "PER_HOUR", 4)
    assert "id" in ask(service, V2)                # 4th start from the same address
    assert "this hour" in ask(service, "c" * 24)["error"]
    assert "id" in ask(service, "c" * 24, address="2.2.2.2")


def test_visitors_only_see_their_own(service):
    job = service.jobs[ask(service)["id"]]
    job.folder.mkdir(parents=True)
    f = job.folder / "song.mp3"
    f.write_bytes(b"ID3")
    job.files, job.state = [f], "done"
    assert [j["id"] for j in service.list(V1)] == [job.id]
    assert service.list(V2) == []
    assert service.file(V1, job.id, 0) == f
    assert service.file(V2, job.id, 0) is None
    service.cancel(V2, job.id)
    assert job.state == "done"


def test_old_files_are_deleted(service):
    job = service.jobs[ask(service)["id"]]
    job.folder.mkdir(parents=True)
    (job.folder / "x.mp3").write_bytes(b"x")
    job.state, job.ended = "done", 1000.0
    service.clean(now=1000.0 + online.KEEP_MINUTES * 60 - 5)
    assert job.id in service.jobs
    service.clean(now=1000.0 + online.KEEP_MINUTES * 60 + 5)
    assert job.id not in service.jobs and not job.folder.exists()


def test_blocked_sites_point_to_the_app():
    yt = online.explain("ERROR: [youtube] x: Sign in to confirm you’re not a bot. Use --cookies")
    assert "YouTube is blocking" in yt["error"] and yt["app_url"]
    ig = online.explain("ERROR: [Instagram] x: Instagram sent an empty media response.")
    assert "Instagram" in ig["error"] and ig["app_url"]
    assert "bigger" in online.explain("ERROR: File is larger than max-filesize (600 > 500)")["error"]
    assert "app_url" not in online.explain("ERROR: Unsupported URL: https://x")


def test_http_api(service, monkeypatch):
    handler = type("H", (online.Handler,), {"service": service})
    httpd = online.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def get(path, key=None):
        req = urllib.request.Request(base + path, headers={"X-Clipnest-Key": key} if key else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    try:
        hello = json.loads(get("/api/hello")[1])
        assert hello["public"] is True and hello["max_quality"] == "1080"
        assert get("/api/health")[0] == 200
        assert b"Clipnest" in get("/")[1]
        assert get("/api/jobs")[0] == 403                  # no visitor ID
        assert get("/api/jobs", key="short")[0] == 403     # malformed
        assert get("/api/jobs", key=V1)[0] == 200
        assert get("/api/file/nope/0", key=V1)[0] == 404
    finally:
        httpd.shutdown()
