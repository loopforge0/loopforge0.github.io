"""Build /upscaler-shootout/ from content/upscaler-shootout.json.

    python tools/build.py           # the rest of the site first
    python tools/build_shootout.py  # then this page

Order is not optional: build.py deletes and rewrites projects/, and this page lives
inside it. Running build.py alone leaves the projects index linking at nothing, which
tools/check.py reports as a broken link.

This page does not fit build.py's project generator, which is built around videos made of
prompts. This one is a comparison player over 83 clips plus the provenance behind them, so
it gets its own builder, at /projects/video-upscaler/ so it sits with the other project
pages rather than beside them.

It reuses build.py's page shell, so the header, nav, theme toggle, footer and analytics are
the same objects as everywhere else on the site and stay in step automatically.

The content file is generated in the experiment repository by
scripts/build_site_content.py and copied here; nothing in it is written by hand twice.

Standard library only.
"""
import json
import os
import shutil
from pathlib import Path

import build as site

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "video-upscaler.json"
SLUG = "video-upscaler"
DIR = f"projects/{SLUG}"      # under projects/, like every other project page
URL = f"/{DIR}/"
VERSION = "13"   # bump when shootout.css or shootout.js change

e = site.e


def dot(colour):
    return f'<span class="dot" style="background:{colour}"></span>'


def facts(rows):
    rows = [(k, v) for k, v in rows if v]
    return '<dl class="facts">' + "".join(f"<dt>{e(k)}</dt><dd>{e(str(v))}</dd>" for k, v in rows) + "</dl>"


def links_inline(items):
    return " ".join(f'<a href="{e(l["url"])}">{e(l["label"])}</a>' for l in items)


# ---------------------------------------------------------------------------- player

def player(d):
    sources = "".join(
        f'<button type="button" class="sh-chip" data-source="{e(s["id"])}" '
        f'aria-pressed="{"true" if i == 0 else "false"}">{e(s["label"])}</button>'
        for i, s in enumerate(d["sources"]))

    methods = "".join(
        f'<button type="button" class="sh-chip" data-method="{e(m["id"])}" '
        f'style="--tier:{m["tierColour"]}" aria-pressed="false">{dot(m["tierColour"])}'
        f'{e(m["short"])}</button>'
        for m in d["methods"])

    zooms = "".join(
        f'<button type="button" class="sh-chip" data-zoom="{z}" aria-pressed="{"true" if z == 1 else "false"}">'
        f'{label}</button>' for z, label in ((1, "Fit"), (2, "2x"), (4, "4x")))

    modes = "".join(
        f'<button type="button" class="sh-chip" data-mode="{m}" aria-pressed="{"true" if m == "split" else "false"}">'
        f'{label}</button>' for m, label in (("split", "Split"), ("grid", "Grid")))

    return f"""
<div class="sh-player" data-player>
  <div class="sh-row">
    <div class="sh-group" role="group" aria-label="Clip">{sources}</div>
    <div class="sh-spacer"></div>
    <div class="sh-group" role="group" aria-label="View">{modes}</div>
    <div class="sh-group" role="group" aria-label="Zoom">{zooms}</div>
    <button type="button" class="sh-chip" data-pixelate aria-pressed="false" disabled>Show pixels</button>
  </div>
  <div class="sh-row">
    <div class="sh-group" role="group" aria-label="Method">{methods}</div>
  </div>

  <div class="sh-stage-wrap">
    <div class="sh-stage sh-split" data-stage></div>
    <div class="sh-loupe" data-loupe hidden><div class="sh-loupe-box"></div></div>
  </div>

  <div class="sh-transport">
    <button type="button" class="button" data-play aria-pressed="false">Play</button>
    <button type="button" class="sh-chip" data-back aria-label="Previous frame">&#9664; Frame</button>
    <button type="button" class="sh-chip" data-fwd aria-label="Next frame">Frame &#9654;</button>
    <input class="sh-scrub" type="range" min="0" max="123" value="0" step="1" data-scrub
      aria-label="Scrub through the clip">
    <span class="sh-frame" data-frame>frame 1 / 124</span>
  </div>
  <p class="sh-geometry" data-geometry></p>
  <p class="sh-hint">
    Click the picture to zoom in on that spot, then drag to pan. Drag the divider to wipe between two
    methods; pick a third to switch to a grid.
    <kbd>Space</kbd> play &middot; <kbd>&larr;</kbd><kbd>&rarr;</kbd> frame &middot;
    <kbd>1</kbd><kbd>2</kbd><kbd>4</kbd> zoom
  </p>
</div>
<p class="muted" data-source-blurb></p>
"""


# ---------------------------------------------------------------------------- sections

def tier_colour(d, label):
    return next(t["colour"] for t in d["tiers"] if t["label"] == label)


def findings_section(d):
    blocks = []
    for f in d["findings"]:
        paras = "".join(f"<p>{e(p)}</p>" for p in f["paras"])
        table = ""
        if f.get("table"):
            t = f["table"]
            head = "".join(f'<th{" class=num" if i else ""}>{e(h)}</th>' for i, h in enumerate(t["head"]))
            rows = "".join(
                "<tr>" + "".join(f'<td{" class=num" if i else ""}>{e(c)}</td>'
                                 for i, c in enumerate(r)) + "</tr>" for r in t["rows"])
            table = (f'<div class="sh-table-wrap"><table class="sh-table">'
                     f'<caption class="visually-hidden">{e(t["caption"])}</caption>'
                     f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>"
                     f'<p class="sh-caveat">{e(t["caption"])}</p>')
        caveat = f'<p class="sh-caveat">{e(f["caveat"])}</p>' if f.get("caveat") else ""
        blocks.append(f'<article class="topic" id="{e(f["id"])}">'
                      f'<h3 class="question">{e(f["question"])}</h3>'
                      f'<div class="topic-a">{paras}{table}{caveat}</div></article>')
    return f"""
<section class="block">
  <h2 class="section">What we found</h2>
  <div class="topics">{"".join(blocks)}</div>
</section>"""


def methods_section(d):
    rows = []
    for m in d["methods"]:
        spec = []
        if m.get("checkpoint"):
            spec.append(f"<b>checkpoint</b> {e(m['checkpoint'])}")
        if m.get("checkpoint_sha256"):
            spec.append(f"<b>sha256</b> {e(m['checkpoint_sha256'][:16])}&hellip;")
        if m.get("command_template"):
            spec.append(f"<b>command</b> {e(m['command_template'][:120])}&hellip;")
        if m.get("variant_id"):
            spec.append(f"<b>variant</b> {e(m['variant_id'])}")
        measured = []
        if m.get("wall"):
            measured.append(("Wall time", m["wall"]))
        if m.get("peak_vram"):
            measured.append(("Peak VRAM", m["peak_vram"]))
        if m.get("gpu"):
            measured.append(("Ran on", m["gpu"]))
        note = f'<p class="sh-note">{e(m["note"])}</p>' if m.get("note") else ""
        link = f'<p>{links_inline(m["links"])}</p>' if m["links"] else ""
        rows.append(f"""
<article class="sh-method" style="--tier:{m["tier_colour"]}" id="m-{e(m["id"].lower())}">
  <div>
    <h3>{dot(m["tier_colour"])}{e(m["name"])}</h3>
    <p class="kind">{e(m["kind"])} &middot; {e(m["tier"])}</p>
    <p>{e(m["blurb"])}</p>
    <p>{e(m["why"])}</p>
    {note}{link}
  </div>
  <div>
    {facts(measured)}
    {f'<p class="sh-spec">{" &middot; ".join(spec)}</p>' if spec else ""}
  </div>
</article>""")

    nr = d["not_run"]
    rows.append(f"""
<article class="sh-method" style="--tier:{nr["tier_colour"]}" id="m-m03">
  <div>
    <h3>{dot(nr["tier_colour"])}{e(nr["name"])}</h3>
    <p class="kind">Planned &middot; not attempted</p>
    <p>{e(nr["blurb"])}</p>
    <p>{links_inline(nr["links"])}</p>
  </div>
  <div></div>
</article>""")

    return f"""
<section class="block" id="methods">
  <h2 class="section">The eleven methods</h2>
  <p class="lede">In the video's running order: lowest memory requirement to highest, paid services
    last. The colour is the hardware tier and means the same thing here as it does on screen.</p>
  {"".join(rows)}
</section>"""


def matrix_section(d):
    head = "".join(f'<th class="num">{e(s["label"])}</th>' for s in d["sources"])
    rows = []
    for m in d["methods"]:
        cells = []
        for s in d["sources"]:
            c = d["cells"][m["id"]][s["id"]]
            if c.get("wall"):
                cells.append(f'<td class="num">{e(c["wall"])}</td>')
            elif c.get("service"):
                cells.append('<td class="num">cloud</td>')
            else:
                cells.append('<td class="num">&mdash;</td>')
        rows.append(f'<tr><td><span class="sh-name">{dot(m["tier_colour"])}'
                    f'<span>{e(m["name"])}<small>{e(m["tier"])}</small></span></span></td>'
                    + "".join(cells) + "</tr>")
    return f"""
<section class="block" id="matrix">
  <h2 class="section">Wall time, every cell</h2>
  <div class="sh-table-wrap"><table class="sh-table">
    <thead><tr><th>Method</th>{head}</tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table></div>
  <p class="sh-caveat">Times are comparable only within a hardware tier. The 12 GB rows ran on an
    RTX 3060 and the 80 GB rows on a rented A100 &mdash; putting them in one table is a convenience,
    not a race. Peak VRAM and the hardware for each method are in the method list below; the exact
    settings and checkpoint hash for every cell are on the workflow that produced it.</p>
</section>"""


def extras_section(d):
    out = []
    for x in d["extras"]:
        def clip(c):
            note = f"<small>{e(c['note'])}</small>" if c.get("note") else ""
            return (f'<figure class="sh-clip"><video muted playsinline loop preload="none" '
                    f'poster="{e(d["media_base"])}/{e(c["poster"])}" '
                    f'src="{e(d["media_base"])}/{e(c["clip"])}" controls></video>'
                    f"<figcaption>{e(c['label'])}{note}</figcaption></figure>")

        def row(clips, head=""):
            # One button starts every clip in the row from frame 0 together, which is the
            # only way a four-way chunk comparison means anything.
            bar = ('<p class="sh-rowbar"><button type="button" class="sh-chip" data-rowplay>'
                   "Play all</button></p>") if len(clips) > 1 else ""
            return (head + f'<div data-syncrow>{bar}'
                    f'<div class="sh-clips">{"".join(clip(c) for c in clips)}</div></div>')

        body = ""
        if x.get("clips"):
            body += row(x["clips"])
        for g in x.get("groups", []):
            body += row(g["clips"], f'<p class="sh-group-head">{e(g["source"])}</p>')
        finding = f'<p class="sh-note">{e(x["finding"])}</p>' if x.get("finding") else ""
        out.append(f"""
<section class="sh-extra" id="x-{e(x["id"])}">
  <h3>{e(x["title"])}</h3>
  <p>{e(x["blurb"])}</p>
  {facts(x.get("facts", []))}
  {finding}
  {body}
</section>""")
    return f"""
<section class="block" id="extras">
  <h2 class="section">Extras</h2>
  <p class="lede">Everything outside the 45-cell matrix: the 4x run, the raw chunking experiment, two
    sources that were withdrawn after being run, and the commercial services at the size they actually
    delivered. None of it is a matrix cell and none of it should be pooled with the rows above.</p>
  {"".join(out)}
</section>"""


def workflows_section(d):
    items = []
    for w in d["workflows"]:
        files = "".join(
            f'<a href="/{DIR}/workflows/{e(f["path"].split("/", 1)[1])}" download>{e(f["source"])}</a>'
            for f in w["files"])
        spec = []
        if w.get("checkpoint"):
            spec.append(f"<b>checkpoint</b> {e(w['checkpoint'])}")
        if w.get("vae"):
            spec.append(f"<b>vae</b> {e(w['vae'])}")
        if w.get("settings"):
            spec.append("<b>settings</b> " + e(", ".join(f"{k}={v}" for k, v in w["settings"].items())))
        patch = ""
        if w.get("required_patch"):
            patch = (f'<p class="sh-note">Needs a one-line patch to ComfyUI: '
                     f'<a href="/{DIR}/workflows/{e(w["required_patch"].split("/", 1)[1])}" download>'
                     f'{e(w["required_patch"].rsplit("/", 1)[1])}</a>. {e(w.get("patch_note", ""))}</p>')
        items.append(f"""
<li style="--tier:{w["tier_colour"]}">
  <span class="sh-name">{dot(w["tier_colour"])}<span>{e(w["name"])}
    <small>API-format graphs, one per source. {links_inline(w["links"])}</small></span></span>
  <div class="files">{files}</div>
  {f'<p class="sh-spec">{" &middot; ".join(spec)}</p>' if spec else ""}
  {patch}
</li>""")
    return f"""
<section class="block" id="workflows">
  <h2 class="section">Workflows and models</h2>
  <p class="lede">Every graph here is the exact API-format JSON that ran, one per source, built for
    this experiment and downloadable. Drop one into ComfyUI and it reproduces the cell. The
    checkpoint, VAE and full settings for each are listed beside it.</p>
  <ul class="sh-dl">{"".join(items)}</ul>

  <h3 class="sh-group-head">The control has no graph, it has one command</h3>
  <p>M00 is the floor everything else has to beat, and it is a single ffmpeg call with no
    model and no GPU. Run it on any of the frozen sources above and you have reproduced the
    control exactly.</p>
  <pre class="script" tabindex="0">{e(next(m["command_template"] for m in d["methods"] if m.get("command_template")))}</pre>
  <p class="sh-caveat">The two commercial services have no workflow to publish: they take a target
    resolution through a web interface and expose nothing about what they do internally. That is the
    provenance gap described above, and it is why they are not matrix cells.</p>

  <h3 class="sh-group-head">The five frozen sources</h3>
  <p>Every method in this comparison was given these exact bytes and nothing else. Each one is the
    unmodified file, not a re-encode, so the hash below is the hash in the experiment's manifest.</p>
  <div class="sh-table-wrap"><table class="sh-table">
    <thead><tr><th>Clip</th><th>Axis</th><th class="num">Size</th><th>sha256</th><th></th></tr></thead>
    <tbody>{"".join(
        f'<tr><td><b>{e(s["id"])}</b> {e(s["label"])}</td>'
        f'<td>{e(next(x["axis"] for x in d["sources"] if x["id"] == s["id"]))}</td>'
        f'<td class="num">{e(s["size"])}, {s["frames"]}f</td>'
        f'<td><code class="sh-spec">{e(s["sha256"][:20])}&hellip;</code></td>'
        f'<td><a href="{e(d["media_base"])}/{e(s["clip"])}" download>Download</a></td></tr>'
        for s in d["frozen_sources"])}</tbody>
  </table></div>

  <h3 class="sh-group-head">How the sources were made</h3>
  <p>S04, S05 and S07 were generated for this experiment with MiniMax H3 rather than found, so the
    graphs that produced them are part of reproducing it. S06 is the withdrawn billboard clip in
    Extras.</p>
  <div class="files">{"".join(
      f'<a href="/{DIR}/workflows/source-generation/{e(g["name"])}" download>{e(g["name"])}</a>'
      for g in d["generation_workflows"])}</div>
</section>"""


def credit_item(i):
    name = f"<b>{e(i['label'])}</b>"
    if i.get("url"):
        name = f'<a href="{e(i["url"])}">{name}</a>'
    return f'<li>{name}<small>{e(i["note"])}</small></li>'


def credits_section(d):
    cols = []
    for group in d["credits"]:
        items = "".join(credit_item(i) for i in group["items"])
        cols.append(f'<div><h3>{e(group["heading"])}</h3><ul>{items}</ul></div>')
    env = d["environment"]
    return f"""
<section class="block" id="credits">
  <h2 class="section">Credits</h2>
  <p class="lede">This experiment is almost entirely other people's work, run carefully and written
    down. The methods, the node packs and the services below are theirs; the controls, the mistakes
    and the measurements are mine.</p>
  <div class="sh-credits">{"".join(cols)}</div>
  <h3 class="sh-group-head">Exactly what it ran on</h3>
  {facts([
      ("Local", env["local"]),
      ("Rented", env["pod"]),
      ("ComfyUI", env["comfyui"]),
      ("VideoHelperSuite", env["video_helper_suite"]),
      ("KJNodes", env["kjnodes"]),
      ("ComfyUI-LTXVideo", env["ltxvideo"]),
      ("SeedVR2 nodes", env["seedvr2"]),
      ("Total spend", f"${env['total_cost_usd']} of a $10 budget"),
  ])}
</section>"""


# ---------------------------------------------------------------------------- page

def build():
    d = json.loads(CONTENT.read_text(encoding="utf-8"))
    d["media_base"] = os.environ.get("SHOOTOUT_MEDIA_BASE") or d["media_base"]

    # what the player needs at runtime, kept to just that.
    # SHOOTOUT_MEDIA_BASE points the player at a local copy of outputs/web so the whole
    # page can be exercised before anything is uploaded. Never set it for a real build.
    media_base = os.environ.get("SHOOTOUT_MEDIA_BASE") or d["media_base"]
    if media_base != d["media_base"]:
        print(f"  ! media base overridden to {media_base} - this build is for preview only")
    runtime = {
        "mediaBase": media_base,
        "frames": 124,
        "duration": 124 / 24,
        "defaultPick": ["M00", "M02c"],
        "sources": [{"id": s["id"], "label": s["label"], "axis": s["axis"], "blurb": s["blurb"],
                     "width": s["width"], "height": s["height"], "target": s["target"]}
                    for s in d["sources"]],
        "methods": [{"id": m["id"], "name": m["name"], "short": m["short"], "tier": m["tier"],
                     "tierColour": m["tier_colour"], "kind": m["kind"]} for m in d["methods"]],
        "cells": d["cells"],
    }

    facts_rows = [
        ("Clips", f"{len(d['sources'])} clips, 124 frames at 24 fps, upscaled by {len(d['methods'])} methods"),
        ("Output", "exactly 2x width and height, same fps, same frame count, no interpolation"),
        ("Settings", "denoise, sharpening and face enhancement off wherever they can be turned off"),
        ("Hardware", f"{d['environment']['local']}, and {d['environment']['pod']}"),
    ]

    body = f"""
<div class="wrap">
  <div class="crumbs"><a href="/">Loop Forge</a> / <a href="/projects/">Projects</a></div>
  <header class="sh-hero">
    <h1 class="display page-title">{e(d["title"])}</h1>
    <p class="lede">{e(d["lede"])}</p>
  </header>

  <section id="compare">
    {player(runtime)}
    <p class="sh-status">{e(d["scope"])} {e(d["encode_note"])}</p>
    {facts(facts_rows)}
  </section>

  {findings_section(d)}
  {matrix_section(d)}
  {methods_section(d)}
  {extras_section(d)}
  {workflows_section(d)}
  {credits_section(d)}
  <div style="height:88px"></div>
</div>
<script>window.SHOOTOUT = {json.dumps(runtime, separators=(",", ":")).replace("</", "<\\/")};</script>
<script src="/assets/shootout.js?v={VERSION}" defer></script>"""

    extra_head = f'<link rel="stylesheet" href="/assets/shootout.css?v={VERSION}">\n'
    ld = {"@context": "https://schema.org", "@type": "Dataset",
          "name": d["title"], "description": d["lede"],
          "url": site.SITE + URL,
          "creator": {"@type": "Organization", "name": "Loop Forge", "url": site.SITE + "/"},
          "license": "https://creativecommons.org/licenses/by/4.0/",
          "measurementTechnique": "Controlled 2x upscaling comparison with frozen sources, "
                                  "hash-verified outputs and per-run provenance"}
    extra_head += site.json_ld(ld)

    site.out(f"{DIR}/index.html", site.page(
        path=URL, title=f"{d['title']}: every clip, workflow and measurement | Loop Forge",
        description=d["lede"][:300], body=body, current="Projects", extra_head=extra_head))

    copy_workflows(d)
    add_to_sitemap()
    print(f"built {URL} with {len(d['methods'])} methods and {len(d['extras'])} extra sections")


def copy_workflows(d):
    """Publish the API graphs next to the page so every download link is a real file."""
    src_root = Path(d.get("workflow_source", ROOT.parent / "h3-upscaling" / "workflows"))
    dest_root = ROOT / DIR / "workflows"
    if not src_root.exists():
        print(f"  ! workflow source {src_root} not found; download links will 404")
        return
    shutil.rmtree(dest_root, ignore_errors=True)
    wanted = set()
    for w in d["workflows"]:
        for f in w["files"]:
            wanted.add(f["path"].split("/", 1)[1])
        if w.get("required_patch"):
            wanted.add(w["required_patch"].split("/", 1)[1])
    for g in d.get("generation_workflows", []):
        wanted.add(g["path"].split("/", 1)[1])
    for rel in sorted(wanted):
        src = src_root / rel
        if not src.exists():
            print(f"  ! missing {src}")
            continue
        dest = dest_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    print(f"  {len(wanted)} workflow files -> {dest_root.relative_to(ROOT)}")


def add_to_sitemap():
    """build.py writes sitemap.xml without this page; put it back, idempotently."""
    p = ROOT / "sitemap.xml"
    if not p.exists():
        return
    text = p.read_text(encoding="utf-8")
    entry = f"  <url><loc>{site.SITE}{URL}</loc></url>\n"
    if entry in text:
        return
    p.write_text(text.replace("</urlset>", entry + "</urlset>"), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    build()
