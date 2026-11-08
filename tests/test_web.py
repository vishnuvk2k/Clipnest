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
    settings = FakeSettings(web_key="k" * 24, cookies_browser="", web_password="")
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
    settings = FakeSettings(web_key="", web_password="")
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


def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_password_hashing():
    stored = web.hash_password("open sesame")
    assert "open sesame" not in stored and stored.startswith("pbkdf2_sha256$")
    assert web.check_password("open sesame", stored)
    assert not web.check_password("open sesamE", stored)
    assert not web.check_password("x", "garbage")
    assert web.hash_password("same") != web.hash_password("same")      # salted


def test_login_guard_locks_out_guessing():
    now = [1000.0]
    g = web.LoginGuard(clock=lambda: now[0])
    for _ in range(4):
        g.failed("1.2.3.4")
    assert g.wait_seconds("1.2.3.4") == 0
    g.failed("1.2.3.4")
    assert g.wait_seconds("1.2.3.4") > 800          # about 15 minutes
    assert g.wait_seconds("5.6.7.8") == 0           # other visitors unaffected
    now[0] += 15 * 60 + 1
    assert g.wait_seconds("1.2.3.4") == 0
    for i in range(30):                              # many visitors guessing together
        g.failed(f"10.0.0.{i}")
    assert g.wait_seconds("9.9.9.9") > 0
    g.reset()
    assert g.wait_seconds("9.9.9.9") == 0


def test_password_sign_in_over_http(server, monkeypatch):
    srv, base = server
    monkeypatch.setattr(web.time, "sleep", lambda s: None)
    status, _, body = get(base + "/api/hello")
    assert json.loads(body) == {"password": False}
    assert "isn't turned on" in post(base + "/api/login", {"password": "whatever1"})["error"]
    with pytest.raises(ValueError):
        srv.set_password("short")
    old_key = srv.key()
    srv.set_password("correct horse")
    assert srv.key() != old_key                      # everyone signed out
    assert json.loads(get(base + "/api/hello")[2]) == {"password": True}
    assert post(base + "/api/login", {"password": "wrong one"})["error"] == "That password isn't right."
    r = post(base + "/api/login", {"password": "correct horse"})
    assert r["key"] == srv.key()
    assert get(base + "/api/jobs", key=r["key"])[0] == 200
    for _ in range(5):
        post(base + "/api/login", {"password": "nope nope"})
    assert "Too many wrong tries" in post(base + "/api/login", {"password": "correct horse"})["error"]


def test_tunnel_helpers():
    from clipnest.tunnel import classify, parse_token
    tok = "eyJhIjoiMTIzNDU2Nzg5MCIsInQiOiJhYmNkZWYiLCJzIjoiWFlaIn0="
    assert parse_token(tok) == tok
    assert parse_token(f"  sudo cloudflared service install {tok}\n") == tok
    assert parse_token(f"cloudflared.exe tunnel run --token {tok}") == tok
    assert parse_token("") == ""
    assert classify("2026-11-08T10:00:00Z INF Registered tunnel connection connIndex=0")[0] == "online"
    assert classify("ERR Provided Tunnel token is not valid.")[0] == "error"
    assert classify("INF Starting tunnel tunnelID=abc") is None


def test_normalize_address():
    from clipnest.tunnel import normalize_address
    assert normalize_address(" getclipnest.com/ ") == "https://getclipnest.com"
    assert normalize_address("https://web.getclipnest.com") == "https://web.getclipnest.com"
    assert normalize_address("") == ""


def test_quick_tunnel_address():
    from clipnest.tunnel import find_quick_url
    line = ("2026-11-08T12:00:00Z INF |  https://bright-lake-tiger-crane.trycloudflare.com"
            "                                    |")
    assert find_quick_url(line) == "https://bright-lake-tiger-crane.trycloudflare.com"
    assert find_quick_url("INF Requesting new quick Tunnel on https://api.trycloudflare.com...") == ""
    assert find_quick_url("INF Starting tunnel") == ""
