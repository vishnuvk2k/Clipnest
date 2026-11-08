// Fills in the newest release from GitHub and picks the right download button.
// Without JavaScript (or if GitHub can't be reached) every button still links
// to the latest release page, so nothing breaks.

const REPO = "vishnuvk2k/clipnest";
const RELEASES = `https://github.com/${REPO}/releases/latest`;

const ASSETS = {
  setup: /Setup.*\.exe$/i,
  portable: /Portable.*\.exe$/i,
  "mac-arm": /apple-silicon\.dmg$/i,
  "mac-intel": /intel\.dmg$/i,
};

function detectOS() {
  const ua = navigator.userAgent;
  const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  if (/android|iphone|ipad|ipod/i.test(ua) || (/Mac/.test(platform) && navigator.maxTouchPoints > 1)) return "mobile";
  if (/win/i.test(platform) || /Windows/.test(ua)) return "windows";
  if (/mac/i.test(platform) || /Mac OS X/.test(ua)) return "mac";
  return "other";
}

// Chrome and Edge on a Mac can tell Apple Silicon from Intel; Safari can't.
async function macArch() {
  try {
    const v = await navigator.userAgentData.getHighEntropyValues(["architecture"]);
    return v.architecture === "x86" ? "intel" : v.architecture === "arm" ? "arm" : "";
  } catch {
    return "";
  }
}

function mb(bytes) {
  return `${Math.round(bytes / 1048576)} MB`;
}

// GitHub allows 60 lookups an hour per visitor, so remember the answer for an hour.
const CACHE_KEY = "clipnest-release";

async function loadRelease() {
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
    if (cached && Date.now() - cached.time < 3600_000) return cached.release;
  } catch { /* storage blocked: just ask GitHub */ }
  try {
    const res = await fetch(`https://api.github.com/repos/${REPO}/releases/latest`,
                            { headers: { Accept: "application/vnd.github+json" } });
    if (!res.ok) return null;
    const r = await res.json();
    const release = {
      tag_name: r.tag_name, published_at: r.published_at, html_url: r.html_url,
      assets: (r.assets || []).map((a) => ({ name: a.name, size: a.size,
                                             browser_download_url: a.browser_download_url })),
    };
    try { localStorage.setItem(CACHE_KEY, JSON.stringify({ time: Date.now(), release })); } catch { /* fine */ }
    return release;
  } catch {
    return null;
  }
}

function setPrimary(icon, label, href, note) {
  document.getElementById("primary-icon").innerHTML = `<use href="#${icon}"/>`;
  document.getElementById("primary-label").textContent = label;
  document.getElementById("primary-download").href = href;
  if (note) document.getElementById("primary-note").innerHTML = note;
}

async function init() {
  const release = await loadRelease();
  const links = {};
  if (release) {
    const version = (release.tag_name || "").replace(/^v/, "");
    for (const [key, re] of Object.entries(ASSETS)) {
      const asset = (release.assets || []).find((a) => re.test(a.name));
      if (!asset) continue;
      links[key] = asset.browser_download_url;
      document.querySelectorAll(`[data-asset="${key}"]`).forEach((a) => (a.href = asset.browser_download_url));
      document.querySelectorAll(`[data-size="${key}"]`).forEach((s) => (s.textContent = `· ${mb(asset.size)}`));
    }
    if (version) {
      const date = new Date(release.published_at).toLocaleDateString(undefined,
        { day: "numeric", month: "short", year: "numeric" });
      document.getElementById("version-line").innerHTML =
        `Version ${version}, released ${date}. <a href="${release.html_url}">What's new</a>`;
    }
  }

  const os = detectOS();
  const v = release && release.tag_name ? ` ${release.tag_name.replace(/^v/, "")}` : "";
  if (os === "windows") {
    setPrimary("i-windows", "Download for Windows", links.setup || RELEASES,
      `Version${v} · Windows 10 and 11 · <a href="#download">Mac and portable versions</a>`);
  } else if (os === "mac") {
    const arch = await macArch();
    const intel = arch === "intel";
    setPrimary("i-apple", intel ? "Download for Mac (Intel)" : "Download for Mac",
      (intel ? links["mac-intel"] : links["mac-arm"]) || RELEASES,
      intel ? `Version${v} · for Intel Macs · <a href="#download">Apple Silicon version</a>`
            : `Version${v} · for M1–M4 Macs · <a href="#download">Intel Mac? Get the Intel version</a>`);
  } else if (os === "mobile") {
    document.getElementById("other-downloads").hidden = true;
    setPrimary("i-download", "See downloads", "#download",
      "Clipnest is a desktop app for Windows and Mac. Open this page on your computer to install it.");
  } else {
    setPrimary("i-download", "Download Clipnest", "#download",
      `For Windows and Mac. On Linux, <a href="https://github.com/${REPO}#run-from-source">run it from source</a>.`);
  }
}

document.querySelectorAll("[data-copy]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const text = document.getElementById(btn.dataset.copy).textContent;
    try {
      await navigator.clipboard.writeText(text);
      btn.querySelector("span").textContent = "Copied";
      setTimeout(() => (btn.querySelector("span").textContent = "Copy"), 1800);
    } catch {
      /* clipboard blocked: the command is still visible to select */
    }
  });
});

init();
