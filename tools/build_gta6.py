"""Build /projects/gta6-style/ from content/gta6-style.json.

    python tools/build.py           # the rest of the site first
    python tools/build_shootout.py
    python tools/build_gta6.py      # then this page

Like the upscaler page, this lives inside projects/, which build.py clears, so it must run after build.py.

The page is a prompt builder plus the showcase it was tested on. The builder runs
assets/gta6-style/gta6_prompt.js, a port of the ComfyUI node pack's nodes.py; the experiment repository
checks the two write identical prompts (gta6-tests/comfyui-gta6-style/web/parity_test.py) and copies the
script, presets.json and every image here with gta6-tests/build_site_content.py.

Standard library only.
"""
import json
from pathlib import Path

import build as site

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "gta6-style.json"
SLUG = "gta6-style"
DIR = f"projects/{SLUG}"
URL = f"/{DIR}/"
VERSION = "3"   # bump when gta6.css or gta6.js change

e = site.e
IMG = f"/assets/img/{SLUG}"
DL = f"/assets/dl/{SLUG}"

WF_LABEL = {"photo": "One photo", "two": "Two photos", "group": "Group from photos", "text": "Text only"}


def caption(c):
    th = c["theme"]
    bits = [th["theme"]]
    for k in ("background", "style_variant", "hue", "vehicle"):
        if th.get(k):
            bits.append(th[k])
    return " · ".join(bits)


def showcase_card(c, i):
    ph = "".join(f'<img src="{IMG}/src-{e(p)}.jpg" alt="" width="40" height="40" loading="lazy">' for p in c["photos"])
    src = (f'<span class="g6-src" title="Made from these photos">{ph}</span>' if ph
           else '<span class="g6-src g6-src-text">no photo</span>')
    return f"""<figure class="g6-card">
  <div class="g6-img"><img src="{IMG}/{e(c['name'])}-t.jpg" alt="" width="{c['w']}" height="{c['h']}" loading="{'eager' if i < 3 else 'lazy'}" decoding="async"
    data-full="{IMG}/{e(c['name'])}.jpg" data-dl="{DL}/{e(c['name'])}.png" data-cap="{e(caption(c))}"></div>
  <figcaption>
    <div class="g6-meta"><span class="g6-kind">{e(WF_LABEL[c['wf']])}</span>{src}</div>
    <p>{e(caption(c))}</p>
    <div class="g6-actions">
      <button type="button" class="button g6-load" data-case="{i}">Load these settings</button>
      <a class="g6-dl" href="{DL}/{e(c['name'])}.png" download>PNG with workflow</a>
    </div>
  </figcaption>
</figure>"""


def builder():
    return """<section class="block g6-builder" id="builder" aria-labelledby="builder-h">
  <div class="block-head"><h2 class="section" id="builder-h">Build a prompt</h2></div>
  <p class="g6-intro">Pick a theme and describe each person, then copy the prompt into a Qwen-Image 2.1 workflow.
  This page writes the same prompt the ComfyUI nodes write, word for word.</p>
  <noscript><p class="notice">The prompt builder needs JavaScript.</p></noscript>
  <div class="g6-layout">
    <form class="g6-form" id="g6-form" autocomplete="off">
      <fieldset class="g6-box">
        <legend>Input</legend>
        <div class="g6-seg" role="radiogroup" aria-label="Input" id="g6-mode"></div>
        <p class="g6-hint" id="g6-mode-hint"></p>
      </fieldset>
      <fieldset class="g6-box">
        <legend>Theme</legend>
        <div class="g6-grid" id="g6-theme"></div>
      </fieldset>
      <fieldset class="g6-box">
        <legend>People</legend>
        <p class="g6-hint" id="g6-people-hint"></p>
        <ol class="g6-people" id="g6-people"></ol>
        <div class="g6-add" id="g6-add">
          <button type="button" class="button quiet" data-add="female">Add a woman</button>
          <button type="button" class="button quiet" data-add="male">Add a man</button>
        </div>
      </fieldset>
      <fieldset class="g6-box">
        <legend>Scene</legend>
        <div class="g6-grid" id="g6-scene"></div>
        <label class="g6-field g6-wide"><span>Your own specifics</span>
          <textarea id="g6-your" rows="3" placeholder="Actions, props, extra scene details. Added after the people and before the background."></textarea></label>
      </fieldset>
    </form>
    <aside class="g6-out" aria-live="polite">
      <div class="g6-out-head"><h3>Prompt</h3><span class="g6-size" id="g6-size"></span></div>
      <p class="g6-error" id="g6-error" hidden></p>
      <textarea id="g6-prompt" readonly rows="14" aria-label="Generated prompt"></textarea>
      <div class="g6-out-actions">
        <button type="button" class="button" data-g6copy="g6-prompt">Copy prompt</button>
        <span class="g6-count" id="g6-count"></span>
      </div>
      <p class="g6-hint" id="g6-images"></p>
      <details class="g6-style-only">
        <summary>Style sentences only</summary>
        <p class="g6-hint">Just the style part, to add to a prompt you write yourself.</p>
        <textarea id="g6-style" readonly rows="6" aria-label="Style sentences only"></textarea>
        <button type="button" class="button quiet" data-g6copy="g6-style">Copy style sentences</button>
      </details>
    </aside>
  </div>
</section>"""


def howto(d):
    wfs = "".join(f'<li><a href="{DL}/{e(w["file"])}" download>{e(w["label"])}</a> <span>{e(w["text"])}</span></li>' for w in d["workflows"])
    gh = e(d["github"])
    timings = "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in d["timings"])
    return f"""<section class="block g6-how" id="use">
  <div class="block-head"><h2 class="section">Use it in ComfyUI</h2></div>
  <div class="g6-cols">
    <div>
      <h3>With the prompt from this page</h3>
      <ol class="g6-steps">
        <li>Open any Qwen-Image 2.1 image workflow that uses <code>TextEncodeQwenImage21</code>.</li>
        <li>Paste the prompt into its prompt box, and set the canvas to the width and height shown above the prompt.</li>
        <li>For photos, connect them in the order of the people list: person 1 is image 1, person 2 is image 2. Text only needs no image.</li>
        <li>Use the base model at 40 steps (euler, simple, cfg 1). Turbo gave softer, anime-leaning faces in testing.</li>
      </ol>
      <p class="g6-hint">Photos with busy backgrounds or dappled sunlight leak into the illustration. The workflows below
      first redo each photo on a plain studio background with an 8-step Turbo pass. You can do the same with any
      background-replacement edit before pasting the prompt.</p>
    </div>
    <div>
      <h3>With the node pack</h3>
      <p>The same choices as dropdowns, with the studio clean-up built in. In ComfyUI Manager choose
      <em>Install via Git URL</em> and paste <code>{gh}</code>, or <code>git clone</code> it into <code>ComfyUI/custom_nodes/</code>.
      Restart ComfyUI, then open a workflow. No extra Python packages.</p>
      <p><a class="button" href="{gh}">Get the node pack on GitHub</a></p>
      <ul class="g6-wfs">{wfs}</ul>
      <p class="g6-hint">Every PNG in the showcase also carries its workflow: drop it onto ComfyUI to get the exact settings.</p>
    </div>
    <div>
      <h3>Time on an RTX 3060 12 GB</h3>
      <dl class="facts">{timings}</dl>
      <p class="g6-hint">Base 2.1 int8, 40 steps, 1248x832, measured end to end on my desktop. A faster card should do better.</p>
    </div>
  </div>
</section>"""


def build():
    d = json.loads(CONTENT.read_text(encoding="utf-8"))
    hero = next(c for c in d["cases"] if c["name"] == d["hero"])
    watch = (f'<a class="button watch" href="{e(d["video"])}" target="_blank" rel="noopener">Watch on YouTube</a> ' if d.get("video") else "")
    github = (f'<a class="button quiet" href="{e(d["github"])}">GitHub</a> ' if d.get("github") else "")
    cards = "".join(showcase_card(c, i) for i, c in enumerate(d["cases"]))
    body = f"""
<section class="col-hero">
  <img class="col-hero-media" src="{IMG}/{e(hero['name'])}.jpg" alt="" width="{hero['w']}" height="{hero['h']}" loading="eager" decoding="async">
  <div class="wrap col-hero-body">
    <div class="crumbs"><a href="/">Loop Forge</a> / <a href="/projects/">Projects</a></div>
    <p class="when">{e(site.long_date(d['published']))}</p>
    <h1 class="display page-title">{e(d['title'])}</h1>
    <div class="summary"><p>{e(d['lede'])}</p></div>
    <p class="col-hero-actions">{watch}<a class="button" href="#builder">Build a prompt</a> {github}<a class="button quiet" href="#use">Get the workflows</a></p>
  </div>
</section>
<div class="wrap">
  {builder()}
  {howto(d)}
  <section class="block" id="showcase">
    <div class="block-head"><h2 class="section">{len(d['cases'])} tests</h2></div>
    <p class="g6-intro">Every theme, background, style, hue and aspect ratio, with one person, two, three and four, and
    from text alone. The people in the photos are AI-generated. Load any test's settings into the builder above.</p>
    <div class="g6-gallery">{cards}</div>
  </section>
  <p class="g6-hint g6-legal">GTA VI is a trademark of Take-Two Interactive. This project is not affiliated with Rockstar Games.
  The presets describe the style of the official artwork in words; no artwork is shipped or used as an input.</p>
  <div style="height:88px"></div>
</div>
<script>window.GTA6_CASES = {json.dumps([{k: c[k] for k in ("mode", "theme", "people", "builder")} for c in d["cases"]], separators=(",", ":")).replace("</", "<\\/")};</script>
<script src="/assets/{SLUG}/gta6_prompt.js?v={VERSION}" defer></script>
<script src="/assets/{SLUG}/gta6.js?v={VERSION}" defer></script>"""

    extra_head = f'<link rel="stylesheet" href="/assets/{SLUG}/gta6.css?v={VERSION}">\n'
    extra_head += site.json_ld({"@context": "https://schema.org", "@type": "WebApplication", "name": f"{d['title']}: prompt builder",
                                "description": d["lede"], "url": site.SITE + URL, "applicationCategory": "DesignApplication",
                                "operatingSystem": "Any", "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"}})
    site.out(f"{DIR}/index.html", site.page(
        path=URL, title=f"{d['title']}: free prompt builder and ComfyUI workflows | Loop Forge",
        description=d["lede"][:300], body=body, current="Projects", extra_head=extra_head,
        image=f"img/{SLUG}/{hero['name']}.jpg"))
    add_to_sitemap()
    print(f"built {URL} with {len(d['cases'])} showcase images")


def add_to_sitemap():
    p = ROOT / "sitemap.xml"
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    entry = f"  <url><loc>{site.SITE}{URL}</loc></url>\n"
    if entry not in text:
        p.write_text(text.replace("</urlset>", entry + "</urlset>"), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    build()
