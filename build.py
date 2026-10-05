#!/usr/bin/env python3
"""Generates the static site (one page per entry) from data/entries.csv.

Run locally:   BASE_URL=http://localhost:8000 python build.py   ->  ./dist
On GitHub:     the workflow runs this automatically on every push.
"""
import base64, csv, datetime, html, json, os, re, shutil
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8"))
BASE_URL = (os.environ.get("BASE_URL") or CFG.get("base_url") or "http://localhost:8000").rstrip("/")
BASE_PATH = urlparse(BASE_URL).path.rstrip("/")
SITE = CFG["site_name"]
MAIN = CFG["main_site"].rstrip("/")
POST_URL = CFG["post_url"]
CAT = CFG.get("category_label", "AI & ML Tools")
GH_USER = CFG.get("github_user", "")
GH_URL = f"https://github.com/{GH_USER}" if GH_USER else ""
TODAY = datetime.date.today().isoformat()
DIST = os.path.join(ROOT, "dist")

e = lambda s: html.escape(str(s), quote=True)


# ---------------------------------------------------------------- helpers
def fmt_size(mb):
    mb = float(mb)
    if mb >= 1000:
        g = mb / 1000
        s = f"{g:.1f}".rstrip("0").rstrip(".")
        return f"{s} GB"
    if mb < 10 and mb != int(mb):
        return f"{mb:.1f} MB"
    return f"{int(round(mb))} MB"


TRAIL = {"download", "install", "installation", "setup", "local", "windows", "mac", "macos", "linux", "ubuntu", "android",
         "ios", "docker", "python", "self", "host", "source", "build", "offline", "app", "desktop",
         "binaries", "portable", "voices", "deploy", "hugging", "face", "from", "run", "locally",
         "for", "latest", "updated", "installer", "free", "version", "guide", "10", "11", "64-bit"}


def short_name(title):
    t = re.sub(r"\s*\(\d\)", "", title)
    w = t.split()
    while len(w) > 1 and w[-1].lower() in TRAIL:
        w.pop()
    n = " ".join(w)
    n = re.sub(r"\s+(download|install)\s+", " ", n, flags=re.I)
    return n.strip() or title


def classify(link):
    u = urlparse(link)
    host = u.netloc.lower()
    parts = [p for p in u.path.split("/") if p]
    if host == "github.com" and "/releases/download/" in u.path:
        return {"kind": "asset", "file": parts[-1], "repo": "/".join(parts[:2])}
    if host == "github.com" and len(parts) == 2:
        return {"kind": "repo", "repo": "/".join(parts)}
    if host == "github.com":
        return {"kind": "page", "repo": "/".join(parts[:2])}
    if host == "huggingface.co" and len(parts) >= 5 and parts[2] in ("resolve", "blob"):
        return {"kind": "hffile", "file": parts[-1], "model": "/".join(parts[:2])}
    if host == "huggingface.co" and len(parts) == 2 and parts[0] not in ("docs", "models", "datasets", "spaces"):
        return {"kind": "hf", "model": "/".join(parts)}
    if host == "huggingface.co":
        return {"kind": "hfpage"}
    if host == "ollama.com" and len(parts) == 2 and parts[0] == "library":
        return {"kind": "ollama", "model": parts[1]}
    if host == "hub.docker.com" and len(parts) >= 3 and parts[0] == "r":
        return {"kind": "docker", "image": "/".join(parts[1:3])}
    if host == "marketplace.visualstudio.com":
        return {"kind": "vscode", "item": parse_qs(u.query).get("itemName", [""])[0]}
    if host == "civitai.com":
        return {"kind": "civitai"}
    if re.search(r"\.(exe|msi|dmg|zip)$", u.path):
        return {"kind": "direct", "file": parts[-1]}
    return {"kind": "official", "host": host}


def platform_of(title, c):
    t = title.lower()
    if c["kind"] in ("asset", "direct"):
        f = c["file"].lower()
        if re.search(r"\.(exe|msi)$|win", f): return "Windows"
        if re.search(r"\.dmg$|darwin|mac|osx", f): return "macOS"
        if f.endswith(".apk"): return "Android"
        if re.search(r"appimage|flatpak|linux|\.tgz$|\.tar", f): return "Linux"
        if f.endswith(".vsix"): return "VS Code (Windows, macOS, Linux)"
    for k, v in ((r"\bwindows\b", "Windows"), (r"\bmac(os)?\b", "macOS"), (r"\b(linux|ubuntu)\b", "Linux"), (r"\bandroid\b", "Android"), (r"\bios\b", "iOS")):
        if re.search(k, t): return v
    if c["kind"] == "hffile":
        return "Windows, macOS, Linux (GGUF: llama.cpp, Ollama, LM Studio)"
    if c["kind"] in ("hf", "ollama", "hfpage"):
        return "Windows, macOS, Linux (via Python or Ollama)"
    if c["kind"] == "vscode":
        return "VS Code (Windows, macOS, Linux)"
    return "Windows, macOS, Linux"


SRC_LABEL = {
    "asset": "GitHub Releases (direct file)", "repo": "GitHub repository", "page": "GitHub",
    "hf": "Hugging Face model page", "hffile": "Hugging Face (direct file)", "hfpage": "Hugging Face", "ollama": "Ollama library",
    "docker": "Docker Hub", "vscode": "VS Code Marketplace", "civitai": "Civitai",
    "direct": "Official direct download", "official": "Official website",
}


def steps_for(name, c, link):
    """List of (text, code) tuples."""
    k = c["kind"]
    out = []
    if k in ("asset", "direct"):
        f = c["file"]; fl = f.lower()
        out.append((f"Download <code>{e(f)}</code> using the download button on this page.", None))
        if fl.endswith((".exe", ".msi")):
            out.append(("Double-click the installer and follow the setup wizard. If Windows SmartScreen appears, check that the publisher is the project you expect before continuing.", None))
            out.append((f"Open {e(name)} from the Start menu once setup finishes.", None))
        elif fl.endswith((".zip", ".7z")):
            out.append(("Right-click the archive and extract it (7-Zip handles both .zip and .7z) to a folder with enough free space.", None))
            out.append(("Open the extracted folder and run the launcher or executable. If a README or start script is included, follow it.", None))
        elif fl.endswith(".dmg"):
            out.append(("Open the disk image and drag the app into your Applications folder.", None))
            out.append(("Launch it from Applications. On first run macOS may ask you to confirm that you want to open an app downloaded from the internet.", None))
        elif fl.endswith(".flatpak"):
            out.append(("Install the bundle from a terminal:", f"flatpak install --user ./{f}"))
        elif fl.endswith(".apk"):
            out.append(("Open the APK on your Android phone and allow installation from this source when prompted.", None))
        elif fl.endswith(".vsix"):
            out.append(("Install it into VS Code from a terminal, or use Extensions > ... > Install from VSIX:", f"code --install-extension {f}"))
        elif fl.endswith(".appimage"):
            out.append(("Make the file executable and run it:", f"chmod +x {f}\n./{f}"))
        elif fl.endswith((".tgz", ".tar.gz")):
            out.append(("Extract the archive and follow the install notes from the project page:", f"tar -xzf {f}"))
        elif fl.endswith(".tar.zst"):
            out.append(("Extract the archive and follow the install notes from the project page:", f"tar --zstd -xf {f}"))
        else:
            out.append(("Make the file executable and run it from a terminal:", f"chmod +x {f}\n./{f}"))
        out.append(("Optional but recommended: compare the file's SHA-256 checksum with the one listed on the project's release page, if one is published.", None))
    elif k in ("repo", "page"):
        repo = c["repo"]
        out.append(("Open the project's GitHub page and read the README for the exact install command for your system.", None))
        out.append(("Clone the repository:", f"git clone https://github.com/{repo}.git\ncd {repo.split('/')[1]}"))
        out.append(("Follow the README: most projects install with <code>pip install</code>, <code>npm install</code> or <code>docker compose up</code>. Using a virtual environment keeps your system Python clean.", None))
        out.append(("Run the quick-start example from the README to confirm everything works.", None))
    elif k == "hffile":
        f = c["file"]; m = c["model"]
        out.append((f"Download <code>{e(f)}</code> using the download button on this page. It is a large file, so use a stable connection.", None))
        out.append(("Run it with llama.cpp:", f"llama-cli -m ./{f} -p \"Hello\""))
        out.append(("Or import the file into LM Studio or Jan (Models > Import), or point an Ollama Modelfile at it with <code>FROM ./" + e(f) + "</code>.", None))
        out.append((f"Read the model card and licence on Hugging Face ({e(m)}) before using the model in a project.", None))
    elif k == "hf":
        m = c["model"]
        out.append(("Open the model page and read the model card, especially the licence and the recommended hardware.", None))
        out.append(("If the model is gated, sign in to Hugging Face and accept the licence on the model page first.", None))
        out.append(("Install the CLI and download the files:", f"pip install -U huggingface_hub\nhuggingface-cli download {m}"))
        out.append(("Load it with <code>transformers</code>, <code>diffusers</code> or your preferred runtime, using the example code on the model card.", None))
    elif k == "ollama":
        m = c["model"]
        out.append(("Install Ollama from ollama.com if you do not have it yet.", None))
        out.append(("Pull and run the model:", f"ollama run {m}"))
        out.append(("The first run downloads the weights. After that the model starts from your local disk.", None))
    elif k == "docker":
        out.append(("Install Docker Desktop (Windows, macOS) or Docker Engine (Linux).", None))
        out.append(("Pull the image:", f"docker pull {c['image']}"))
        out.append(("Start a container using the run command shown on the Docker Hub page.", None))
    elif k == "vscode":
        out.append(("Open VS Code and go to the Extensions view (Ctrl+Shift+X).", None))
        if c.get("item"):
            out.append(("Search for the extension, or install it from a terminal:", f"code --install-extension {c['item']}"))
        out.append(("Reload VS Code if prompted and sign in if the extension requires an account.", None))
    else:
        out.append(("Open the official download page using the link on this site.", None))
        out.append(("Choose the build that matches your operating system and download it.", None))
        out.append(("Run the installer or follow the setup instructions on the official page.", None))
    return out


def requirements(name, c, size_txt, mb):
    k = c["kind"]
    rows = []
    if k == "hffile":
        rows.append(("Disk space", f"At least {fmt_size(mb * 1.1)} free for the model file."))
        rows.append(("Memory", f"Roughly {fmt_size(mb * 1.2)} of free RAM or GPU VRAM to load the model, plus extra for the context window."))
        rows.append(("Software", "A GGUF-compatible runtime such as llama.cpp, Ollama, LM Studio or Jan."))
    elif k in ("hf", "ollama", "hfpage"):
        rows.append(("Disk space", f"At least {fmt_size(mb * 1.15)} free for the model files, plus room for caches."))
        rows.append(("Memory", "Full-precision weights need roughly the file size in GPU VRAM or system RAM. Quantised builds (GGUF, 4-bit) need much less."))
        rows.append(("Software", "Python 3.10 or newer with the matching library, or a runtime such as Ollama or llama.cpp."))
    elif k in ("asset", "direct"):
        rows.append(("Disk space", f"About {fmt_size(mb * 2.2 if mb < 2000 else mb * 1.3)} free to download and unpack."))
        rows.append(("Operating system", "A current 64-bit version of the platform listed above."))
        rows.append(("Network", "An internet connection for the download and for first-run updates or model downloads."))
    elif k == "docker":
        rows.append(("Disk space", f"About {fmt_size(mb * 1.3)} free for the image and its layers."))
        rows.append(("Software", "Docker Desktop or Docker Engine, with GPU passthrough only if the project needs it."))
    else:
        rows.append(("Disk space", f"Around {fmt_size(max(mb * 1.5, 50))} free, depending on the dependencies you install."))
        rows.append(("Software", "Git plus Python 3.10 or newer, Node.js or Docker, depending on the project."))
        rows.append(("Tip", "Use a virtual environment or container so the install does not touch your system packages."))
    return rows


def tokens(s):
    stop = {"install", "download", "local", "windows", "mac", "macos", "linux", "ubuntu", "python", "setup", "the", "and", "for", "ai", "self", "host",
            "latest", "updated", "docker", "offline", "installer", "free", "version", "guide", "10", "11"}
    return {t for t in re.findall(r"[a-z0-9\.]+", s.lower()) if t not in stop and len(t) > 1}


def trunc(s, n):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0].rstrip(",.;:-") + "\u2026"


# ---------------------------------------------------------------- layout
def head(title, desc, canonical, og_type="website", extra=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canonical)}">
<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<meta name="theme-color" content="#0969da">
<link rel="icon" type="image/svg+xml" href="{BASE_PATH}/assets/favicon.svg">
<link rel="stylesheet" href="{BASE_PATH}/assets/style.css">
<meta property="og:site_name" content="{e(SITE)}">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(canonical)}">
<meta property="og:image" content="{BASE_URL}/assets/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{BASE_URL}/assets/og.png">
{extra}</head>
<body>
"""


def header_html():
    gh_link = f'<a href="{e(GH_URL)}" rel="noopener">GitHub</a>' if GH_URL else ""
    return f"""<header class="site"><div class="wrap">
<a class="brand" href="{BASE_PATH}/"><img src="{BASE_PATH}/assets/favicon.svg" alt="" width="28" height="28">{e(SITE)} {e(CAT)}</a>
<nav class="top" aria-label="Main"><a href="{BASE_PATH}/">All tools</a><a href="{BASE_PATH}/disclaimer/">Disclaimer</a>{gh_link}<a class="cta" href="{e(MAIN)}/">Visit {e(SITE)}</a></nav>
</div></header>
"""


def footer_html():
    footer_gh = f'<br><a href="{e(GH_URL)}" rel="noopener">github.com/{e(GH_USER)}</a>' if GH_URL else ""
    return f"""<footer class="site"><div class="wrap"><div class="cols">
<div><p><strong>{e(SITE)} {e(CAT)}</strong> is an independent directory of download links, file sizes and install guides.</p>
<p>All product names, logos and brands are property of their respective owners. We are not affiliated with, endorsed by or sponsored by any project listed. Always download software from the official source and check licences before use.</p></div>
<div><p><a href="{BASE_PATH}/">All tools</a><br><a href="{BASE_PATH}/disclaimer/">Disclaimer</a><br><a href="{e(MAIN)}/">{e(MAIN.replace('https://', ''))}</a>{footer_gh}</p><p>Updated {TODAY}</p></div>
</div></div></footer>
</body>
</html>
"""


def jsonld(*objs):
    return "".join('<script type="application/ld+json">' + json.dumps(o, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + "</script>\n" for o in objs)


# ---------------------------------------------------------------- pages
INDEX = {}


def build_entry(r, i, rows, meta):
    eid, title, mb, link, desc = r["entry_id"], r["headline_text"], float(r["file_size"]), r["download_link"], r["description"].strip()
    c = meta[eid]["c"]; name = meta[eid]["name"]; plat = meta[eid]["plat"]
    size_txt = fmt_size(mb)
    exact = c["kind"] in ("asset", "direct", "hffile")
    post = POST_URL.format(entry_id=eid)
    post_b64 = base64.b64encode(post.encode()).decode()
    canonical = f"{BASE_URL}/{eid}/"
    page_title = f"{title} \u2013 Download Guide | {SITE}" if "updat" in title.lower() else f"{title} \u2013 {r['headline_suffix']} & Download Guide | {SITE}"
    meta_desc = trunc(f"{desc} Get the {name} download link, file size ({'' if exact else '~'}{size_txt}) and a step-by-step install guide.", 158)
    src = SRC_LABEL[c["kind"]]
    steps = steps_for(name, c, link)
    reqs = requirements(name, c, size_txt, mb)

    # related
    me = meta[eid]["tok"]
    scored = []
    cand = {j for tk in me for j in INDEX.get(tk, ())} | set(range(max(0, i - 3), min(len(rows), i + 4)))
    cand.discard(i)
    for j in cand:
        o = rows[j]
        t = meta[o["entry_id"]]["tok"]
        jac = len(me & t) / (len(me | t) or 1)
        scored.append((jac + 0.06 / (1 + abs(i - j)), j))
    rel = [rows[j] for _, j in sorted(scored, reverse=True)[:6]]

    faqs = [
        (f"What is the file size of {name}?",
         f"The listed size for {name} is {'' if exact else 'about '}{size_txt}. " + ("This is the exact size of the release file at the time of the last update." if exact else "This is an approximate figure for the main package, image or model file. The final size depends on the version and on any extra dependencies or models you choose to download.")),
        (f"Where does the {name} download come from?",
         f"The link on this page points to {src.lower()}, which is the project's own distribution channel or the closest official source we could find. We do not host or modify any files."),
        (f"How do I install {name}?",
         "Follow the numbered steps on this page. In short: " + re.sub(r"<[^>]+>", "", steps[0][0]).rstrip(".") + ", then work through the remaining steps in order."),
        (f"Is it safe to download {name}?",
         "Only download from official sources, keep your operating system updated, and compare checksums when the project publishes them. If a file asks for unusual permissions, stop and review the project's documentation first."),
    ]

    # body
    steps_html = "".join(
        "<li>" + t + (f"<pre><code>{e(code)}</code></pre>" if code else "") + "</li>" for t, code in steps)
    spec = [("Name", e(title)), ("Category", e(r["category"])), ("File size", ("" if exact else "~") + e(size_txt)),
            ("Platform", e(plat)), ("Source", e(src)), ("Last updated", TODAY)]
    spec_html = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in spec)
    req_html = "".join(f"<tr><th>{e(k)}</th><td>{e(v)}</td></tr>" for k, v in reqs)
    faq_html = "".join(f"<details><summary>{e(q)}</summary><p>{e(a)}</p></details>" for q, a in faqs)
    rel_html = "".join(
        f'<a class="tile" href="{BASE_PATH}/{o["entry_id"]}/"><b>{e(o["headline_text"])}</b><small>{e(trunc(o["description"], 90))}</small><div class="sz">{e(fmt_size(o["file_size"]))}</div></a>'
        for o in rel)

    p1 = e(desc)
    if c["kind"] == "asset":
        p2 = (f"This page points to the {e(name)} installer or package <code>{e(c['file'])}</code>, published on the project's GitHub Releases page. "
              f"The file is {e(size_txt)}, so make sure you have a stable connection and enough free space before you start.")
    elif c["kind"] == "hffile":
        p2 = (f"This page points to the {e(name)} model file <code>{e(c['file'])}</code> on Hugging Face. "
              f"The file is {e(size_txt)}, so make sure you have enough disk space and RAM or VRAM before you start.")
    elif c["kind"] in ("hf", "ollama"):
        p2 = (f"{e(name)} is distributed as model weights. The download is {('about ' + e(size_txt))}, so check the hardware notes below, "
              "and read the licence on the model page before using it in a project.")
    elif c["kind"] in ("repo", "page"):
        p2 = (f"The official source for {e(name)} is its GitHub repository. Installation is normally done by cloning the repository or installing the package it provides, "
              f"and the full set of files and dependencies comes to roughly {e(size_txt)}.")
    else:
        p2 = (f"The download for {e(name)} is provided through {e(src.lower())}. The main file is about {e(size_txt)}, and the notes below cover what you need before installing.")
    p3 = (f"Use the green download button to open the {e(name)} entry on {e(SITE)}, where the current link and details are kept up to date. "
          "The steps below explain how to install it and what to check first.")

    body = head(page_title, meta_desc, canonical, "article", jsonld(
        {"@context": "https://schema.org", "@type": "SoftwareApplication", "name": title, "applicationCategory": "DeveloperApplication",
         "operatingSystem": plat, "description": desc, "url": canonical, "fileSize": ("" if exact else "~") + size_txt,
         "dateModified": TODAY},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL + "/"},
            {"@type": "ListItem", "position": 2, "name": CAT, "item": BASE_URL + "/"},
            {"@type": "ListItem", "position": 3, "name": title, "item": canonical}]},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faqs]}))
    body += header_html()
    body += f"""<div class="wrap">
<nav class="crumbs" aria-label="Breadcrumb"><a href="{BASE_PATH}/">Home</a><span>/</span><a href="{BASE_PATH}/">{e(CAT)}</a><span>/</span>{e(title)}</nav>
<section class="hero">
<div class="badges"><span class="badge blue">{e(r['headline_suffix'])}</span><span class="badge">{e(r['category'])}</span><span class="badge">{e(size_txt)}</span></div>
<h1>{e(title)}</h1>
<p class="lead">{e(desc)}</p>
<button class="btn primary" type="button" id="dl" data-u="{e(post_b64)}">&#8595; Download {e(name)}</button>
<p class="note">Opens the {e(name)} page on {e(SITE)}. Files come from the official source and are not hosted here.</p>
</section>
<div class="layout">
<main><article>
<h2>Overview</h2>
<p>{p1}</p><p>{p2}</p><p>{p3}</p>
<h2>Download details</h2>
<table class="spec">{spec_html}</table>
<h2>How to install {e(name)}</h2>
<ol class="steps">{steps_html}</ol>
<h2>System requirements</h2>
<table class="spec">{req_html}</table>
<h2>Frequently asked questions</h2>
{faq_html}
<h2>Related tools</h2>
<div class="related">{rel_html}</div>
</article></main>
</div></div>
<script>
(function(){{var b=document.getElementById('dl');if(!b)return;
b.addEventListener('click',function(){{var u=atob(b.getAttribute('data-u'));var w=window.open(u,'_blank','noopener');if(!w)location.href=u}});}})();
</script>
"""
    body += footer_html()
    return body


def build_index(rows, meta):
    title = f"{CAT} \u2013 Download Links, File Sizes & Install Guides | {SITE}"
    desc = f"Browse {len(rows)} {CAT.lower()} with direct download links, file sizes and step-by-step install guides for local LLMs, image and speech models, agents and developer tools."
    items = "".join(
        f'<a class="tile" data-s="{e((o["headline_text"] + " " + o["description"]).lower())}" href="{BASE_PATH}/{o["entry_id"]}/"><b>{e(o["headline_text"])}</b><small>{e(trunc(o["description"], 110))}</small><div class="sz">{e(fmt_size(o["file_size"]))}</div></a>'
        for o in rows)
    h = head(title, desc, BASE_URL + "/", "website", jsonld(
        {"@context": "https://schema.org", "@type": "CollectionPage", "name": title, "description": desc, "url": BASE_URL + "/",
         "mainEntity": {"@type": "ItemList", "numberOfItems": len(rows), "itemListElement": [
             {"@type": "ListItem", "position": n + 1, "url": f"{BASE_URL}/{o['entry_id']}/", "name": o["headline_text"]} for n, o in enumerate(rows[:100])]}}))
    h += header_html()
    h += f"""<div class="wrap">
<section class="home-hero">
<h1>{e(CAT)}</h1>
<p>{len(rows)} tools with download links, file sizes and install guides. Local LLM apps, image and video generators, speech models, agents, RAG tools and more.</p>
<input id="q" class="search" type="search" placeholder="Search tools, e.g. Ollama, Whisper, ComfyUI&hellip;" aria-label="Search tools" autocomplete="off">
<div class="count" id="count">{len(rows)} tools</div>
</section>
<div class="related" id="grid" style="padding-bottom:40px">{items}</div>
</div>
<script>
(function(){{var q=document.getElementById('q'),g=document.getElementById('grid'),c=document.getElementById('count'),t=[].slice.call(g.children);
q.addEventListener('input',function(){{var v=q.value.trim().toLowerCase(),n=0;t.forEach(function(x){{var m=!v||x.getAttribute('data-s').indexOf(v)>-1;x.style.display=m?'':'none';if(m)n++}});c.textContent=n+(n===1?' tool':' tools')}})}})();
</script>
"""
    return h + footer_html()


def build_disclaimer():
    t = f"Disclaimer | {SITE} {CAT}"
    d = f"Important information about the download links, trademarks and software listed on {SITE} {CAT}."
    h = head(t, d, BASE_URL + "/disclaimer/") + header_html()
    h += f"""<div class="wrap"><main class="doc"><h1>Disclaimer</h1>
<p>{e(SITE)} {e(CAT)} is an independent directory. We list download links, approximate file sizes and install guides for third-party software, models and developer tools.</p>
<p><strong>No affiliation.</strong> All names, logos and trademarks belong to their respective owners. Listing a tool here does not imply endorsement by, or any relationship with, its authors.</p>
<p><strong>No hosting.</strong> We do not host or modify the software. Links point to the official project, its GitHub releases, or another primary source. File sizes marked with a tilde (~) are approximate and may change with each release.</p>
<p><strong>Licences.</strong> Every project has its own licence and terms of use. Some models require you to accept a licence before downloading. Please read them before using anything commercially.</p>
<p><strong>Your responsibility.</strong> Check checksums where available, keep your system updated, and download only from sources you trust. Use all software at your own risk.</p>
<p>Questions or removal requests: please contact us through <a href="{e(MAIN)}/">{e(MAIN.replace('https://', ''))}</a>.</p>
</main></div>
"""
    return h + footer_html()


def build_404():
    h = head(f"Page not found | {SITE}", "This page could not be found.", BASE_URL + "/404.html").replace(
        '<meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">', '<meta name="robots" content="noindex">')
    h += header_html()
    h += f'<div class="wrap"><main class="doc"><h1>Page not found</h1><p>That page does not exist. Try the <a href="{BASE_PATH}/">full tool list</a>.</p></main></div>'
    return h + footer_html()


def write(path, text):
    full = os.path.join(DIST, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    csv_path = os.path.join(ROOT, "entries.csv")
    if not os.path.exists(csv_path):
        csv_path = os.path.join(ROOT, "data", "entries.csv")
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["is_active"].strip().lower() in ("1", "true", "yes")]
    rows = rows[: int(CFG.get("publish_limit", len(rows)))]
    ids = [r["entry_id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate entry_id"
    for r in rows:
        assert re.fullmatch(r"[a-z0-9][a-z0-9\-]*", r["entry_id"]), "bad entry_id: " + r["entry_id"]
        assert r["download_link"].startswith("http"), "missing link: " + r["entry_id"]

    meta = {}
    for r in rows:
        c = classify(r["download_link"]); name = short_name(r["headline_text"])
        meta[r["entry_id"]] = {"c": c, "name": name, "plat": platform_of(r["headline_text"], c), "tok": tokens(r["headline_text"])}

    for n, r in enumerate(rows):
        for tk in meta[r["entry_id"]]["tok"]:
            INDEX.setdefault(tk, []).append(n)
    for tk in [k for k, v in INDEX.items() if len(v) > 400]:
        del INDEX[tk]

    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(os.path.join(DIST, "assets"), exist_ok=True)
    for fn in ("style.css", "favicon.svg", "og.png"):
        for folder in (ROOT, os.path.join(ROOT, "assets")):
            src = os.path.join(folder, fn)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(DIST, "assets", fn))
                break
        else:
            raise SystemExit("missing file: " + fn)
    write(".nojekyll", "")
    write("index.html", build_index(rows, meta))
    write("disclaimer/index.html", build_disclaimer())
    write("404.html", build_404())
    for i, r in enumerate(rows):
        write(f"{r['entry_id']}/index.html", build_entry(r, i, rows, meta))

    urls = [BASE_URL + "/", BASE_URL + "/disclaimer/"] + [f"{BASE_URL}/{r['entry_id']}/" for r in rows]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "".join(f"<url><loc>{e(u)}</loc><lastmod>{TODAY}</lastmod></url>\n" for u in urls) + "</urlset>\n")
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n")
    print(f"Built {len(rows)} entry pages + home + disclaimer + 404 -> {DIST}  (base: {BASE_URL})")


if __name__ == "__main__":
    main()
