"""Puts the public website together in _site/ for GitHub Pages.

- site/            the home page (download the app)
- site/demo/       a demo of Clipnest Web: the real page from clipnest/web/
                   plus site/demo-src/demo.js, which simulates the computer

Run: python tools/build_site.py
"""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"


def main() -> None:
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(ROOT / "site", OUT, ignore=shutil.ignore_patterns("demo-src"))
    demo = OUT / "demo"
    shutil.copytree(ROOT / "clipnest" / "web", demo)
    for name in ("demo.js", "thumb.svg"):
        shutil.copy(ROOT / "site" / "demo-src" / name, demo / name)
    page = demo / "index.html"
    html = page.read_text(encoding="utf-8")
    marker = "<script>"
    assert html.count(marker) == 1, "expected one inline script in clipnest/web/index.html"
    html = html.replace(marker, '<script src="demo.js"></script>\n' + marker)
    html = html.replace("<title>Clipnest</title>", "<title>Clipnest Web demo</title>")
    page.write_text(html, encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    print(f"Website ready in {OUT}")


if __name__ == "__main__":
    main()
