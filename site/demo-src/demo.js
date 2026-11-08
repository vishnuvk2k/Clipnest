// Demo mode for the Clipnest Web page on the public website.
// It stands in for the Clipnest app on a computer: link lookups, downloads and
// progress are simulated, and nothing is downloaded. The real page talks to
// Clipnest running on your own computer.
(() => {
  "use strict";
  try { localStorage.setItem("clipnest-key", "demo"); } catch { /* fine */ }

  const SOURCES = [
    [/(^|\.)music\.youtube\.com$/, "YouTube Music"], [/(^|\.)(youtube\.com|youtu\.be)$/, "YouTube"],
    [/(^|\.)instagram\.com$/, "Instagram"], [/(^|\.)(facebook\.com|fb\.watch)$/, "Facebook"],
    [/(^|\.)(x\.com|twitter\.com)$/, "X"], [/(^|\.)vimeo\.com$/, "Vimeo"],
    [/(^|\.)(pinterest\.[a-z.]+|pin\.it)$/, "Pinterest"],
  ];
  const EXAMPLES = {
    "YouTube": ["Sunset Drive · Lo-fi Beats to Relax", "Example Channel", 3734, 2160, "Video"],
    "YouTube Music": ["Morning Run Mix", "Example Artist", 214, 1080, "Video"],
    "Instagram": ["Beach day 🌊", "example.creator", 28, 1920, "Reel / post"],
    "Facebook": ["Our trip to the mountains", "Example Page", 95, 1080, "Video"],
    "X": ["Launch day highlights", "Example", 41, 720, "Post"],
    "Vimeo": ["A short film about light", "Example Studio", 312, 2160, "Video"],
    "Pinterest": ["Cozy reading corner ideas", "", 0, 0, "Image"],
  };
  const jobs = [];
  let nextId = 1;

  function source(url) {
    try {
      const host = new URL(url).hostname.toLowerCase();
      for (const [re, name] of SOURCES) if (re.test(host)) return name;
      return "Link";
    } catch { return null; }
  }

  function reply(data, status = 200) {
    return Promise.resolve(new Response(JSON.stringify(data),
      { status, headers: { "Content-Type": "application/json" } }));
  }

  function tick() {
    for (const j of jobs) {
      if (j.state === "queued") { j.state = "running"; j.status = "Starting…"; }
      else if (j.state === "running") {
        j.fraction = Math.min(1, j.fraction + 0.09 + Math.random() * 0.06);
        const mb = (2 + Math.random() * 6).toFixed(1);
        j.status = j.fraction < 1 ? `${Math.round(j.fraction * 100)}% · ${mb} MB/s`
                                  : j.fmt === "mp3" ? "Converting to MP3…" : "Finishing…";
        if (j.fraction >= 1 && (j.finishing = (j.finishing || 0) + 1) > 2) {
          j.state = "done"; j.status = "Done";
          const ext = j.fmt === "image" ? "jpg" : j.fmt;
          j.files = [{ n: 0, name: `${j.title}.${ext}`, size: j.fmt === "mp3" ? 8.6e6 : j.fmt === "image" ? 2.1e6 : 148e6 }];
        }
      }
    }
  }
  setInterval(tick, 700);

  const realFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const path = typeof input === "string" ? input : input.url;
    if (!path.startsWith("/api/")) return realFetch(input, init);
    const body = init.body ? JSON.parse(init.body) : {};
    if (path === "/api/status") return reply({ ready: true, version: "demo" });
    if (path === "/api/jobs") return reply({ jobs: jobs.slice().reverse(), run: "demo" });
    if (path === "/api/cancel") {
      const j = jobs.find((x) => x.id === body.id);
      if (j && ["queued", "running"].includes(j.state)) { j.state = "cancelled"; j.status = "Cancelled"; }
      return reply({ ok: true });
    }
    if (path === "/api/info") {
      const s = source(body.url);
      if (!s) return reply({ error: "Paste a full link that starts with https://" });
      if (/instagram\.com\/(reels\/)?audio\//i.test(body.url))
        return reply({ error: "Instagram audio pages can't be downloaded directly. Open a Reel that uses this sound, copy that Reel's link, and download it as MP3." });
      if (/spotify\.com/i.test(body.url))
        return reply({ error: "This site protects its media with DRM, so it can't be downloaded." });
      const [title, uploader, duration, height, kind] = EXAMPLES[s] || ["Example video", "", 120, 1080, "Video"];
      return new Promise((done) => setTimeout(() => done(reply({
        title, uploader, duration, thumbnail: "thumb.svg", source: s, kind,
        is_playlist: /[?&]list=/.test(body.url), entries: 12, max_height: height,
        image_size: kind === "Image" ? [2400, 3600] : null,
      })), 900));
    }
    if (path === "/api/download") {
      const s = source(body.url);
      if (!s) return reply({ error: "Paste a full link that starts with https://" });
      const title = body.title || (EXAMPLES[s] || ["Example video"])[0];
      const job = { id: nextId++, title, fmt: body.fmt, quality: body.quality, state: "queued",
                    status: "Waiting…", fraction: 0, files: [] };
      jobs.push(job);
      return reply({ id: job.id });
    }
    return reply({ error: "Not found" }, 404);
  };

  function toast(text) {
    let t = document.getElementById("demo-toast");
    if (!t) {
      t = document.createElement("div");
      t.id = "demo-toast";
      t.setAttribute("role", "status");
      t.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);max-width:min(440px,calc(100% - 32px));" +
        "background:#2C2A37;border:1px solid #4A4760;color:#F2F1F7;padding:12px 16px;border-radius:12px;" +
        "font:500 14.5px/1.45 Inter,system-ui,sans-serif;box-shadow:0 12px 40px rgba(0,0,0,.5);z-index:50;text-align:center";
      document.body.append(t);
    }
    t.textContent = text;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => t.remove(), 4200);
  }

  document.addEventListener("click", (e) => {
    const a = e.target.closest("a.save");
    if (!a) return;
    e.preventDefault();
    toast("This is a demo, so there's no file. With Clipnest on your computer, this saves the real file to your device.");
  }, true);

  document.addEventListener("DOMContentLoaded", () => {
    const bar = document.createElement("div");
    bar.style.cssText = "background:linear-gradient(90deg,#6E4EF7,#8A6BFF);color:#fff;text-align:center;" +
      "font:500 14px/1.4 Inter,system-ui,sans-serif;padding:10px 16px";
    bar.innerHTML = "<b>Demo</b> · Try how Clipnest Web works. Nothing is really downloaded. " +
      "<a href=\"../#download\" style=\"color:#fff;font-weight:600;text-decoration:underline\">Get the app</a> to use it for real.";
    document.body.prepend(bar);
    const so = document.getElementById("signout");
    if (so) so.remove();      // nothing to sign out of in the demo
  });
  // Show "Demo" instead of "Your computer is online" once the page has set it.
  const relabel = () => {
    const t = document.getElementById("conn-text");
    if (t && t.textContent === "Your computer is online") t.textContent = "Demo mode";
  };
  setInterval(relabel, 300);
})();
