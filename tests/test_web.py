import json
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from clipnest import web
from clipnest.jobs import JobOptions


class FakeSettings(dict):
    def set(self, key, value):
        self[key] = value


def make_job(job_id, files, state="done", origin="web"):
    return SimpleNamespace(id=job_id, title=f"Song {job_id}", origin=origin, state=state,
                           status="Done", fraction=1.0, files=files,
                           opts=JobOptions(url="u", fmt="mp3", quality="320", out_dir="/o"))


@pytest.fixture
def server(tmp_path):
    song = tmp_path / "Café ☕ song.mp3"
    song.write_bytes(b"ID3" + b"x" * 5000)
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    manager = SimpleNamespace(jobs=[
        make_job(1, [str(song)]),
        make_job(2, [str(secret)], origin="app"),          # started on the computer
        make_job(3, [str(song)], state="running"),
    ])
    settings = FakeSettings(web_key="k" * 24, cookies_browser="")
    srv = web.WebServer(manager, settings, engine_ready=lambda: True)
    assert srv.start()
    yield srv, f"http://127.0.0.1:{srv.port}"
    srv.stop()


def get(url, key=None):
    req = urllib.request.Request(url, headers={"X-Clipnest-Key": key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_page_is_public_but_api_needs_the_key(server):
    srv, base = server
    status, headers, body = get(base + "/")
    assert status == 200 and b"Clipnest" in body
    assert headers["Referrer-Policy"] == "no-referrer"
    assert get(base + "/api/jobs")[0] == 403
    assert get(base + "/api/jobs", key="wrong")[0] == 403
    status, _, body = get(base + "/api/jobs", key="k" * 24)
    jobs = json.loads(body)["jobs"]
    assert status == 200 and [j["id"] for j in jobs] == [3, 1]     # phone jobs only, newest first


def test_files_only_from_finished_phone_downloads(server):
    srv, base = server
    key = "?key=" + "k" * 24
    status, headers, body = get(base + "/api/file/1/0" + key)
    assert status == 200 and body.startswith(b"ID3") and len(body) == 5003
    assert "filename*=UTF-8''Caf%C3%A9%20%E2%98%95%20song.mp3" in headers["Content-Disposition"]
    assert get(base + "/api/file/2/0" + key)[0] == 404       # started on the computer
    assert get(base + "/api/file/3/0" + key)[0] == 404       # not finished
    assert get(base + "/api/file/1/5" + key)[0] == 404
    assert get(base + "/api/file/../../etc/passwd" + key)[0] == 404
    assert get(base + "/api/file/1/0")[0] == 403              # no key


def test_download_requests_are_checked(server):
    srv, _ = server
    assert "https://" in srv.request_download({"url": "not a link", "fmt": "mp3", "quality": "320"})["error"]
    assert "quality" in srv.request_download({"url": "https://youtu.be/x", "fmt": "mp3", "quality": "999"})["error"]
    assert "quality" in srv.request_download({"url": "https://youtu.be/x", "fmt": "exe", "quality": "1"})["error"]
    assert "Reel" in srv.request_download(
        {"url": "https://www.instagram.com/reels/audio/1/", "fmt": "mp3", "quality": "320"})["error"]


def test_new_link_replaces_the_key():
    settings = FakeSettings(web_key="")
    srv = web.WebServer(SimpleNamespace(jobs=[]), settings, engine_ready=lambda: True)
    first = srv.key()
    assert len(first) >= 20 and settings["web_key"] == first
    srv.new_link()
    assert settings["web_key"] != first
    assert web.key_ok(settings["web_key"], settings["web_key"])
    assert not web.key_ok("", "")


def test_address_order():
    addrs = ["100.101.5.9", "8.8.8.8", "192.168.1.20"]
    assert sorted(addrs, key=web._rank) == ["192.168.1.20", "100.101.5.9", "8.8.8.8"]
