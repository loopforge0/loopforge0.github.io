"""Pull every published prompt out of the project folders it was made in.

Writes one normalised file per video to content/<collection>.json and the images each page
needs to assets/img/<collection>/. This is a one-off import that runs on the machine the
videos were made on; the build (tools/build.py) only reads content/ and assets/, so the site
can be rebuilt anywhere once this has run.

Prompt text is always taken from the most authoritative copy that exists: the prompt ComfyUI
embedded in the rendered mp4 where one is available, otherwise the published prompt files.

    python tools/import_sources.py            # everything
    python tools/import_sources.py shots      # one collection
"""
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
REPOS = ROOT.parent
CONTENT = ROOT / "content"
IMG = ROOT / "assets" / "img"

SHOTS_REPO = REPOS / "minimaxh3-shots-skills"
WALK = REPOS / "h3-walking"
CHAIN_PROMPTS = WALK / "prompts-publish"   # identical to ComfyUI-H3-Continuous/prompts apart from CRLF
FIRSTDATE = REPOS / "local-director" / "firstdate-video" / "share"
LTXCMP = REPOS / "ltxminimaxcomparison"
TURBO = REPOS / "minimaxh3"

STILL_EDGE = 1280   # long edge of the large still on a prompt page
THUMB_EDGE = 560    # long edge of grid thumbnails


# ---------------------------------------------------------------------------- media helpers

def save_image(src, dest_stem, collection):
    """Write <stem>.jpg (large) and <stem>-t.jpg (thumb) from an image file or PIL image."""
    im = src if isinstance(src, Image.Image) else Image.open(src)
    im = im.convert("RGB")
    out = IMG / collection
    out.mkdir(parents=True, exist_ok=True)
    for suffix, edge, q in (("", STILL_EDGE, 84), ("-t", THUMB_EDGE, 80)):
        copy = im.copy()
        copy.thumbnail((edge, edge), Image.LANCZOS)
        copy.save(out / f"{dest_stem}{suffix}.jpg", quality=q, optimize=True, progressive=True)
    return {"src": f"img/{collection}/{dest_stem}.jpg", "thumb": f"img/{collection}/{dest_stem}-t.jpg",
            "w": im.width, "h": im.height}


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                          "stream=codec_type,width,height,nb_frames,r_frame_rate:format=duration:format_tags",
                          "-of", "json", str(path)], capture_output=True, text=True, encoding="utf-8").stdout
    return json.loads(out)


def frame_at(path, index):
    """Decode one frame by index and return it as a PIL image."""
    tmp = CONTENT / "_frame.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vf", f"select=eq(n\\,{index})",
                    "-frames:v", "1", str(tmp)], check=True)
    im = Image.open(tmp)
    im.load()
    tmp.unlink()
    return im


def mid_frame(path, fraction=0.5):
    info = probe(path)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    n = int(v.get("nb_frames") or round(float(info["format"]["duration"]) * 24))
    return frame_at(path, int(n * fraction)), info


def embedded_graph(path):
    tags = probe(path)["format"].get("tags", {})
    return json.loads(tags["prompt"]) if "prompt" in tags else {}


def nodes_of(graph, class_type):
    return [n for n in graph.values() if n["class_type"] == class_type]


def read_text(path):
    return Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")


def write(collection):
    CONTENT.mkdir(exist_ok=True)
    path = CONTENT / f"{collection['slug']}.json"
    path.write_text(json.dumps(collection, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}: {len(collection['prompts'])} prompts")


def slugify(text, words=7):
    """A readable URL slug from a title, so addresses never expose internal shot codes."""
    parts = re.sub(r"[^a-z0-9]+", " ", text.lower().replace("'", "")).split()
    return "-".join(parts[:words])


def span(text, needle):
    i = text.find(needle)
    return [i, i + len(needle)] if needle and i >= 0 else None


# ---------------------------------------------------------------------------- 14 camera shots

SHOT_CHAPTERS = {
    "crash-zoom-in": 42, "yoyo-zoom": 80, "dolly-zoom": 125, "snorricam": 171, "rack-focus": 210,
    "split-screen": 245, "whip-pan": 287, "dutch-angle": 324, "super-dolly-in": 361, "eyes-in": 390,
    "aerial-pullback": 418, "handheld": 447, "orbit-360": 482, "crane-rise": 510,
}

SHOT_CAVEATS = {
    "split-screen": "This prompt states absolute reveal times (2s, 4s). H3 ignored them: it opened the last "
                    "panel at 2.46s in two different runs. It is kept exactly as it ran.",
    "crash-zoom-in": "This prompt states a 2 second hold and a 200ms snap. H3 picks its own window. It is kept "
                     "exactly as it ran.",
    "dolly-zoom": "This prompt names a Cooke S4, which is a prime, on a shot that has to zoom. It was thought to "
                  "matter and turned out not to.",
    "crane-rise": "This prompt says \"flown on a drone\" in the style line. Naming equipment there is something "
                  "the shot recipes now advise against.",
}

SHOT_GROUP_TITLES = {"zoom": "Zooms", "specialty": "Specialty shots", "pan and roll": "Pans and rolls",
                     "tracking": "Tracking shots"}


def import_shots():
    slug = "h3-camera-shots"
    shots = json.loads(read_text(SHOTS_REPO / "docs" / "data" / "shots.json"))
    refs = {}
    for name in ("amber-main", "kate", "sofia", "allie"):
        img = save_image(SHOTS_REPO / "docs" / "assets" / "refs" / f"{name}.png", f"ref-{name}", slug)
        refs[name] = {"id": name, "label": name.split("-")[0].capitalize(), "image": img,
                      "note": "Character reference plate"}

    prompts = []
    for s in shots:
        text = read_text(SHOTS_REPO / "prompts" / s["promptFile"])
        assembled = s["a"] + s["gear"] + s["b"] + s["clause"] + s["c"]
        if assembled.strip() != text.strip():
            print(f"  note: {s['id']} gallery text differs from prompt file; using the file")
        highlights = []
        for kind, needle, label in (("gear", s["gear"], "Camera and lens"), ("clause", s["clause"], "Camera clause")):
            sp = span(text, needle)
            if sp:
                highlights.append({"kind": kind, "label": label, "start": sp[0], "end": sp[1]})
        local = s["width"] == 864
        prompts.append({
            "slug": s["slug"],
            "title": s["name"],
            "group": s["group"],
            "still": save_image(SHOTS_REPO / "docs" / "assets" / "stills" / f"{s['id']}.jpg", s["slug"], slug),
            "time": SHOT_CHAPTERS.get(s["slug"]),
            "models": ["MiniMax H3"],
            "techniques": ["Camera movement", "Reference to video"],
            "facts": [
                ["Resolution", f"{s['width']}×{s['height']}"],
                ["Length", f"{s['frames']} frames, {s['duration']:.2f}s"],
                ["Steps", "20, res_multistep / simple, turbo LoRA off"],
                ["Seed", "552013742"],
                ["Ran on", "RTX 3060, 12GB (local)" if local else "RTX 5090 on RunPod"],
            ],
            "refs": [{"tag": f"<Picture {i + 1}>", "ref": r} for i, r in enumerate(s["refs"])],
            "variants": [{"label": "Prompt", "text": text, "highlights": highlights}],
            "notes": [SHOT_CAVEATS[s["slug"]]] if s["slug"] in SHOT_CAVEATS else [],
            "links": [{"label": "Shot recipe, with what the earlier attempts got wrong",
                       "url": f"https://github.com/loopforge0/minimaxh3-shots-skills/blob/main/.claude/skills/h3-camera-shots/shots/{s['slug']}.md"}],
        })

    write({
        "slug": slug,
        "title": "MiniMax H3 camera shots",
        "short": "Fourteen named camera shots",
        "published": "2026-09-13",
        "video": {"id": "GCdKh_KaQVs", "title": "MiniMax H3: 14 Camera Techniques"},
        "models": ["MiniMax H3"],
        "summary": [
            "MiniMax H3 documents twelve camera motions and no named shots. There is no dolly zoom button and no "
            "crash zoom button, so every named film shot has to be written as a sentence built out of those twelve. "
            "Most ways of doing that do not work. These fourteen do.",
            "Each prompt is the exact file that produced the shot, with the camera and lens phrase and the camera "
            "clause marked. More than a hundred generations went into getting here.",
        ],
        "facts": [
            ["Workflow", "MiniMaxH3ReferenceToVideo, ref_image_size max, no background plate"],
            ["Resolution", "1344×768 on a rented RTX 5090, except the snorricam at 864×480 on an RTX 3060"],
            ["Sampling", "20 steps, res_multistep / simple, turbo LoRA off, seed 552013742"],
            ["Prompt format", "The six-section reference format from MiniMax's official guide"],
        ],
        "groups": [{"id": g, "title": t} for g, t in SHOT_GROUP_TITLES.items()],
        "refs": list(refs.values()),
        "links": [
            {"label": "Repository with agent skills that write these for your own scene",
             "url": "https://github.com/loopforge0/minimaxh3-shots-skills"},
            {"label": "ComfyUI workflow (json)",
             "url": "/assets/workflows/h3-camera-shots.json"},
            {"label": "MiniMax's official prompt writing guide",
             "url": "https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md"},
        ],
        "prompts": prompts,
    })


# ---------------------------------------------------------------------------- chained renders

CHAIN_TAKES = [
    {"id": "market-street-3060", "folder": "market-street/3060", "title": "Market Street walk, RTX 3060",
     "time": 125, "res": "864×480", "ran": "RTX 3060, 12GB (local)",
     "frames": [192] * 7, "seeds": [1078725334536121 + 9973 * i for i in range(7)],
     "clips": [WALK / "out" / f"shot-0{i}.mp4" for i in range(1, 8)],
     "note": "One continuous front-tracking walk down Market Street in San Francisco, seven renders long."},
    {"id": "market-street-5090", "folder": "market-street/5090", "title": "Market Street walk, RTX 5090",
     "time": 173, "res": "1376×768", "ran": "RTX 5090 on RunPod",
     "frames": [243] * 7,
     "seeds": [1078725334536121 + 9973 * i for i in range(5)] + [8613402297755119, 1078725334595959],
     "clips": [WALK / "runpod" / "out" / f"shot-0{i}.mp4" for i in range(1, 8)],
     "note": "The same seven shots on a rented RTX 5090, reworked for the longer shot that card could hold. "
             "It adds two instructions the local set does not carry: one holding the camera steady, one keeping "
             "her expression neutral between the scripted beats."},
    {"id": "mia", "folder": "mia-influencer", "title": "Mia talking to camera", "time": 272, "res": "480×864",
     "ran": "RTX 3060, 12GB (local)", "frames": [192, 192, 192, 192], "seeds": [4422180, 4432153, 4442126, 4452099],
     "take": WALK / "showcase-video" / "assets" / "clips" / "mia.mp4",
     "note": "Talking to camera, unbroken, across four renders."},
    {"id": "kate", "folder": "kate-rant", "title": "Kate, six renders of speech", "time": 408, "res": "480×864",
     "ran": "RTX 3060, 12GB (local)", "frames": [158, 192, 209, 158, 175, 209],
     "seeds": [8824375, 8834348, 8844321, 8854294, 8864267, 8874240],
     "take": WALK / "showcase-video" / "assets" / "clips" / "kate.mp4",
     "note": "Six renders of continuous speech. This is the take where the face drifts. Each segment is sized to "
             "the words it has to carry, because runtime with nothing scripted in it is where the model invents "
             "speech-shaped filler."},
    {"id": "stage", "folder": "stage-song", "title": "Kate singing on a stage", "time": 493, "res": "480×864",
     "ran": "RTX 3060, 12GB (local)", "frames": [192, 192, 192], "seeds": [22318, 32291, 42264],
     "take": WALK / "showcase-video" / "assets" / "clips" / "stage.mp4",
     "note": "Singing on a stage, three renders."},
]

MARKET_BEATS = [
    ("Establishing the walk", None, "She comes off a crosswalk and settles into stride"),
    ("High-five on the move", "sofia", "High-five on the move, then her friend peels away"),
    ("Streetcar and pigeons", None, "An F-line streetcar crosses behind; pigeons scatter"),
    ("Selfie without stopping", "allie", "A selfie taken without either of them stopping"),
    ("Under the street trees", None, "Dappled light under street trees; she squints into the sun"),
    ("Dancing alongside", "dany", "A friend falls into step, dances alongside, then drops back"),
    ("Everyone meets her", "sofia allie dany", "All three meet her; the camera arcs to reveal the clock tower"),
]

HANDOFF = 39


def import_chained():
    slug = "h3-chained-renders"
    base = CHAIN_PROMPTS
    refs = {}

    def ref(folder, name, label, note):
        key = f"{folder.split('/')[0]}-{name}"
        if key not in refs:
            refs[key] = {"id": key, "label": label, "note": note,
                         "image": save_image(base / folder.split("/")[0] / "refs" / f"{name}.jpg", f"ref-{key}", slug)}
        return key

    guide = {"tag": "No tag", "text": "MiniMaxH3AddGuide: the last 39 frames of the previous render, plus its audio"}
    prompts = []
    for take in CHAIN_TAKES:
        n = len(take["frames"])
        for i in range(n):
            if take["id"].startswith("market"):
                fname = f"shot-0{i + 1}.txt"
                beat, guests, beat_note = MARKET_BEATS[i]
                wiring = [{"tag": "<Picture 1>", "ref": ref(take["folder"], f"block-{i + 1}", f"Block {i + 1}",
                                                           "Aerial photograph of that block")},
                          {"tag": "<Picture 2>", "ref": ref(take["folder"], "amber", "Amber", "Character plate")}]
                for g_i, g in enumerate((guests or "").split()):
                    wiring.append({"tag": f"<Picture {3 + g_i}>", "ref": ref(take["folder"], g, g.capitalize(),
                                                                          "Character plate")})
                title = f"{beat}, shot {i + 1}"
                clip = take["clips"][i]
                still, _ = mid_frame(clip, 0.6)
            else:
                fname = f"seg-0{i + 1}.txt"
                title = f"{take['title']}, render {i + 1} of {n}"
                beat_note = None
                if take["id"] == "mia":
                    wiring = [{"tag": "<Picture 1>", "ref": ref(take["folder"], "mia", "Mia", "Three-panel character sheet")}]
                elif take["id"] == "kate":
                    wiring = [{"tag": "<Picture 1>", "ref": ref(take["folder"], "kate", "Kate", "Character plate")}]
                else:
                    wiring = [{"tag": "<Picture 1>", "ref": ref(take["folder"], "kate", "Kate", "The singer")},
                              {"tag": "<Picture 2>", "ref": ref(take["folder"], "stage", "Stage", "The stage")}]
                # The take drops each later render's 39 replayed frames, so render i's new frames start
                # after render 0 plus every render in between minus its replay.
                f = take["frames"]
                new_start = 0 if i == 0 else f[0] + sum(x - HANDOFF for x in f[1:i])
                new_len = f[i] if i == 0 else f[i] - HANDOFF
                still = frame_at(take["take"], new_start + new_len // 2)
            if i > 0:
                wiring = wiring + [guide]
            text = read_text(base / take["folder"] / fname)
            frames = take["frames"][i]
            techniques = ["Long takes", "Reference to video"]
            if take["id"] in ("mia", "kate"):
                techniques.append("Speech")
            if take["id"] == "stage":
                techniques.append("Singing")
            if take["id"].startswith("market"):
                techniques.append("Camera movement")
            prompts.append({
                "slug": f"{take['id']}-{i + 1}",
                "title": title,
                "group": take["id"],
                "still": save_image(still, f"{take['id']}-{i + 1}", slug),
                "time": take["time"],
                "models": ["MiniMax H3"],
                "techniques": techniques,
                "facts": [
                    ["Resolution", take["res"]],
                    ["Length", f"{frames} frames, {frames / 24:.2f}s"],
                    ["Handoff", "Opens on the last 39 frames of the render before it" if i else "First render, nothing handed in"],
                    ["Steps", "20"],
                    ["Seed", str(take["seeds"][i])],
                    ["Ran on", take["ran"]],
                ],
                "refs": wiring,
                "variants": [{"label": "Prompt", "text": text}],
                "notes": [beat_note] if beat_note else [],
                "links": [],
            })

    write({
        "slug": slug,
        "title": "MiniMax H3 long takes from chained renders",
        "short": "Twenty seven chained renders",
        "published": "2026-09-05",
        "video": {"id": "kj6tNy6NXH4", "title": "MiniMax H3 in ComfyUI: long videos from chained renders"},
        "models": ["MiniMax H3"],
        "summary": [
            "MiniMax H3 renders top out at about fifteen seconds. To get past that, every render opens on an exact "
            "replay of the last 39 frames of the render before it, so the join is the same frames rather than "
            "similar frames. Character, street and voice all stay put across it.",
            "References are handed in per render, so a new character or a new block of street can arrive halfway "
            "through a take. Twenty seven prompts across five takes, one per render, copied from what was sent.",
        ],
        "facts": [
            ["Workflow", "ComfyUI-H3-Continuous, chaining MiniMaxH3AddGuide"],
            ["Handoff", "39 frames plus audio from the end of each render"],
            ["Tags", "<Picture N> is positional: it comes from the order images are wired in, not from the prompt"],
            ["Music", "non_diegetic_music is N/A in all twenty seven; score goes on over the finished cut"],
        ],
        "groups": [{"id": t["id"], "title": t["title"], "note": t["note"]} for t in CHAIN_TAKES],
        "refs": list(refs.values()),
        "links": [
            {"label": "ComfyUI-H3-Continuous, the nodes and the chain workflow",
             "url": "https://github.com/loopforge0/ComfyUI-H3-Continuous"},
            {"label": "How the handoff works, and how every number was measured",
             "url": "https://github.com/loopforge0/ComfyUI-H3-Continuous/blob/main/docs/how-it-works.md"},
            {"label": "The five model files, from Comfy-Org", "url": "https://huggingface.co/Comfy-Org/MiniMax-H3"},
            {"label": "MiniMax's official prompt writing guide",
             "url": "https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md"},
        ],
        "prompts": prompts,
    })


# ---------------------------------------------------------------------------- first date

FD_SCENES = {"s1": "Arriving", "s2": "Dinner", "s3": "The walk home"}
FD_REF_FILES = {
    "3dview-bistro.png": ("Bistro", "Location: a 3D architectural view of the bistro"),
    "couplesittingdining-multi-view.png": ("The table", "Location: multi-view of the table for two"),
    "couple-table-single.png": ("One table", "Location: the single-table variant"),
    "street.png": ("Street", "Location: the residential street"),
    "mia-default.png": ("Mia", "Character turnaround sheet"),
    "mia-coat.png": ("Mia in her coat", "Character sheet, edited from Mia's default sheet"),
    "theo-default.png": ("Theo", "Character turnaround sheet"),
}


def fd_title(summary):
    m = re.search(r"Generate a single ([A-Z]+) shot(?: of [^—]+)? — (.+)", summary)
    if not m:
        return summary[:70]
    shot, rest = m.group(1), m.group(2).strip()
    rest = re.split(r"(?<=[.;])\s|, a detail-first| — ", rest)[0].rstrip(".;")
    rest = rest.replace("<Subject 1>", "").strip()
    if len(rest) > 72:
        rest = rest[:72].rsplit(" ", 1)[0] + "…"
    return rest[0].upper() + rest[1:]


def plural_clips(n):
    return f"{n} clip{'' if n == 1 else 's'}"


def import_first_date():
    slug = "h3-first-date"
    doc = read_text(FIRSTDATE / "PROMPTS-videos.md")
    refs = {}
    for fname, (label, note) in FD_REF_FILES.items():
        key = fname.rsplit(".", 1)[0]
        refs[key] = {"id": key, "label": label, "note": note,
                     "image": save_image(FIRSTDATE / "reference-images" / fname, f"ref-{key}", slug)}

    prompts = []
    clips = re.split(r"\n## `(s\d_\d\d_c\d)`\n", doc)
    for clip_id, body in zip(clips[1::2], clips[2::2]):
        body = body.split("\n# Scene")[0]
        meta = re.search(r"\*\*Purpose:\*\* (.+?) &nbsp;·&nbsp; \*\*Asked for:\*\* (\d+)s &nbsp;·&nbsp; "
                         r"\*\*Transition out:\*\* (.+)", body)
        attach = re.findall(r"\*\*<Picture (\d)>\*\* → `([^`]+)` \(`reference-images/([^`]+)`\), as <Subject (\d)>", body)
        speaks = re.search(r"\*\*Speaks:\*\* (.+)", body)
        blocks = re.findall(r"```text\n(.*?)\n```", body, re.S)
        if "**As generated**" in body:
            variants = [
                {"label": "As generated", "text": blocks[0],
                 "note": "Pulled out of the rendered clip. This is the prompt that made the shot in the film."},
                {"label": "Revised", "text": blocks[1],
                 "note": "Corrected after the clip was made, with each image cited inside its subject definition. "
                         "Start from this one."},
            ]
        else:
            variants = [{"label": "Prompt", "text": blocks[0],
                         "note": "Checked against the prompt embedded in the rendered clip: identical."}]
        summary = re.search(r"summary:\n(.+)", variants[-1]["text"]).group(1)
        clip_path = FIRSTDATE / "clips" / f"{clip_id}.mp4"
        still, info = mid_frame(clip_path)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        duration = float(info["format"]["duration"])
        techniques = ["Reference to video", "Character consistency"]
        if speaks:
            techniques.append("Speech")
        characters = sum(1 for a in attach if a[1].startswith("char_"))
        if characters > 1:
            techniques.append("Multiple characters")
        notes = []
        if clip_id.startswith("s3_02"):
            notes.append("Mia's coat reference is attached here. In the video this is where the difference between "
                         "citing an image inside a subject definition and giving it a standalone entry shows up.")
        prompts.append({
            "slug": slugify(fd_title(summary)),
            "title": fd_title(summary),
            "group": clip_id[:2],
            "still": save_image(still, slugify(fd_title(summary)), slug),
            "time": 501,
            "models": ["MiniMax H3"],
            "techniques": techniques,
            "facts": [
                ["Shot purpose", meta.group(1).capitalize()],
                ["Length", f"{duration:.2f}s (asked for {meta.group(2)}s)"],
                ["Resolution", f"{v['width']}×{v['height']}, 24fps"],
                ["Steps", "20, stock reference-to-video template"],
                ["Speaks", ", ".join(s.strip("` ").replace("char_", "").capitalize() for s in speaks.group(1).split(","))
                 if speaks else "Nobody"],
                ["Cut out", meta.group(3)],
            ],
            "refs": [{"tag": f"<Picture {p}>", "ref": f.rsplit(".", 1)[0], "subject": f"<Subject {s}>"}
                     for p, _, f, s in attach],
            "variants": variants,
            "notes": notes,
            "links": [],
        })

    # The reference image prompts, as their own group.
    img_doc = read_text(FIRSTDATE / "PROMPTS-images.md")
    for sec in re.split(r"\n## `", img_doc)[1:]:
        ref_id = sec.split("`", 1)[0]
        file = re.search(r"\*\*File:\*\* `reference-images/([^`]+)`", sec)
        block = re.search(r"```text\n(.*?)\n```", sec, re.S)
        if not file or not block:
            continue
        key = file.group(1).rsplit(".", 1)[0]
        kind = re.search(r"\*\*Type:\*\* (.+)", sec).group(1)
        method = re.search(r"\*\*Method:\*\* (.+)", sec).group(1)
        used = len(re.search(r"\*\*Used in shots:\*\* (.+)", sec).group(1).split(","))
        note = []
        if re.search(r"\*\*Generated from:\*\*", sec):
            note.append("Made by editing Mia's default character sheet, which is how the coat variant keeps the same face.")
        prompts.append({
            "slug": slugify(f"{FD_REF_FILES[file.group(1)][0]} reference image"),
            "title": f"{FD_REF_FILES[file.group(1)][0]}, reference image",
            "group": "images",
            "still": refs[key]["image"],
            "time": 146,
            "models": ["Online image model"],
            "techniques": ["Reference images"],
            "facts": [["Type", kind.capitalize()], ["Method", method], ["Used in", plural_clips(used)]],
            "refs": [],
            "variants": [{"label": "Prompt", "text": block.group(1)}],
            "notes": note + ["Made with an online service, not locally. Flux Kontext and Qwen Edit will both do this "
                             "part on your own machine."],
            "links": [],
        })

    write({
        "slug": slug,
        "title": "First Date, a short film with MiniMax H3",
        "short": "A one minute short film",
        "published": "2026-08-29",
        "video": {"id": "fQ8HZC_dTXs", "title": "MiniMax H3 reference to video: a short film"},
        "models": ["MiniMax H3"],
        "summary": [
            "A one minute short film made with ComfyUI's stock MiniMax H3 reference-to-video template, with two "
            "characters who stay the same person from shot to shot, in the same restaurant, with the same voice.",
            "A character turnaround sheet, a 3D layout of the room and a sample of the voice all go in at once, and "
            "the prompt says which subject is in which picture. Here are all twenty one clip prompts and the prompts "
            "for the reference images.",
        ],
        "facts": [
            ["Workflow", "ComfyUI's stock MiniMax H3 reference-to-video template, untouched"],
            ["Clips", "864×480, 24fps, 20 steps, on an RTX 3060 with 12GB"],
            ["Voice", "Mia's voice reference is attached on every clip where she speaks"],
            ["Music", "Turned off in the prompt on 20 of 21 clips and added in the edit instead"],
        ],
        "notice": "16 of the 21 clips were made before the way images are cited was fixed. Those pages show the "
                  "prompt as generated and the revised version, one tab each.",
        "groups": [{"id": k, "title": v} for k, v in FD_SCENES.items()] + [
            {"id": "images", "title": "Reference images",
             "note": "Character sheets and locations, the <Picture N> inputs to the clips."}],
        "refs": list(refs.values()),
        "links": [
            {"label": "The clips, the discarded takes and the DaVinci Resolve project, on Gumroad",
             "url": "https://loopforge0.gumroad.com/l/firstdate"},
            {"label": "The stock MiniMax H3 template in ComfyUI",
             "url": "https://docs.comfy.org/tutorials/video/minimax/minimax-h3"},
            {"label": "MiniMax's official prompt guide for reference mode",
             "url": "https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md"},
        ],
        "prompts": prompts,
    })


# ---------------------------------------------------------------------------- h3 vs ltx

LTX_ROUNDS = [
    # id, clip suffix, start image, title, chapter, winner, verdict
    ("0", "0", "start-t0.jpg", "Base test: one image, four workflows", 43, None,
     "The default MiniMax workflow takes nearly four times as long as the six step version. There is some quality "
     "drop, but it is a good trade for the speed. LTX's default and reduced-step versions differ in quality too, "
     "with not much difference in generation time."),
    ("1", "1", "start-01.jpg", "Individual, motion only", 209, "LTX 2.5",
     "LTX had better prompt adherence here, with no stray audio. With MiniMax the woman turned fully and there "
     "was not much wind."),
    ("2", "2", "start-02.jpg", "Couple", 247, "LTX 2.5",
     "MiniMax kept the camera still and had the right background sound, but it also added speech nobody asked "
     "for, and missed the glance and settling back against the bench. LTX zoomed in and had no background sound, "
     "but no hallucinated speech either."),
    ("2a", "2A", "start-02.jpg", "Bonus: the couple, taking turns to speak", 292, "MiniMax H3",
     "Both models read the mood very differently and both got the order of the lines right. MiniMax has the edge "
     "because both of them look away from each other at the end; in LTX they keep looking at each other."),
    ("3", "3", "start-03.jpg", "Landscape, no people", 335, "MiniMax H3",
     "MiniMax had some odd patterns in the water but was decent overall, and the ambient sound made sense. LTX "
     "replaced the ambience with music nobody asked for, and the water flow was too smooth in places."),
    ("4", "4", "start-04.jpg", "Animals", 382, "MiniMax H3",
     "MiniMax followed the prompt better: the dog shakes off the water and barks, though it barks more than once "
     "and the shake is slightly off. LTX missed the shake, and its single bark has no matching action."),
    ("5", "5", "start-05.jpg", "Vehicles", 426, "LTX 2.5",
     "MiniMax changed lanes, which is odd for a truck already moving, and a man appeared in the driver's seat. "
     "LTX animated it as a pull-away from standstill instead of continued motion, but was more consistent."),
    ("6", "6", "start-06.jpg", "Speaking, group", 472, "MiniMax H3",
     "MiniMax felt more natural: the two listeners turn to the speaker just as she starts, then nod and smile. In "
     "LTX both turn before she has started talking, with artifacts around her mouth on \"subscribing\"."),
    ("7", "7", "start-07.jpg", "Singing, individual", 521, "MiniMax H3",
     "A personal call. MiniMax chose a lovely tune and good expressions. LTX followed most of the prompt but did "
     "not keep the camera still, and its choice of tune was weaker."),
    ("8", "8", "start-08.jpg", "Singing, group", 567, "MiniMax H3",
     "Five seconds is too short for the whole verse. MiniMax got through the first line; LTX sang only the "
     "first three words."),
]


def ltx_settings(graph):
    seeds = [n["inputs"]["noise_seed"] for n in nodes_of(graph, "RandomNoise")]
    return next((s for s in seeds if s != 42), seeds[0] if seeds else None)


def import_ltx():
    slug = "h3-vs-ltx-2-5"
    clips = LTXCMP / "clips-manual"
    starts = LTXCMP / "comparison-video" / "assets"
    prompts = []
    refs = {}
    for rid, suffix, start, title, chapter, winner, verdict in LTX_ROUNDS:
        key = "start-" + start.split("-", 1)[1].rsplit(".", 1)[0]
        if key not in refs:
            refs[key] = {"id": key, "label": "Start image", "note": "The one still image both models were given",
                         "image": save_image(starts / start, key, slug)}
        runs = []
        if rid == "0":
            runs = [("MiniMax H3, 20 steps", clips / "MiniMax_clip0_.mp4"),
                    ("MiniMax H3, 6 steps with Turbo LoRA", clips / "MiniMax_clip0-6step_.mp4"),
                    ("LTX 2.5, default", clips / "LTX-clip0.mp4"),
                    ("LTX 2.5, 6 steps", clips / "LTX-clip0-6step_.mp4")]
        else:
            runs = [("MiniMax H3", clips / f"MiniMax_clip{suffix}_.mp4"), ("LTX 2.5", clips / f"LTX-clip{suffix}_.mp4")]

        variants, outputs, facts = [], [], []
        seen_texts = {}
        for label, path in runs:
            g = embedded_graph(path)
            info = probe(path)
            v = next(s for s in info["streams"] if s["codec_type"] == "video")
            still, _ = mid_frame(path)
            stem = f"round-{rid}-" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
            outputs.append({"label": label, "image": save_image(still, stem, slug)})
            if label.startswith("MiniMax"):
                text = nodes_of(g, "MiniMaxH3ImageToVideo")[0]["inputs"]["prompt"]
                steps = nodes_of(g, "BasicScheduler")[0]["inputs"]["steps"]
                turbo = bool(nodes_of(g, "MiniMaxH3TurboLoRA"))
                seed = nodes_of(g, "RandomNoise")[0]["inputs"]["noise_seed"]
                detail = f"{steps} steps{', Turbo LoRA' if turbo else ''}, seed {seed}, {v['width']}×{v['height']}"
            else:
                text = nodes_of(g, "PrimitiveStringMultiline")[0]["inputs"]["value"]
                # Two encoders: the positive is linked to the multiline primitive, the negative holds its own text.
                negative = next(n["inputs"]["text"] for n in nodes_of(g, "CLIPTextEncode")
                                if isinstance(n["inputs"]["text"], str))
                detail = f"Stock two-stage workflow, seed {ltx_settings(g)}, {v['width']}×{v['height']}"
            facts.append([label, detail])
            if text in seen_texts:
                prior = seen_texts[text]
                if not prior["label"].startswith(label.split(",")[0]):
                    prior["label"] = "Both models"
                continue
            # Round zero keeps the workflow in the label because its two H3 runs had different prompts.
            variant = {"label": label if rid == "0" and label.startswith("MiniMax") else label.split(",")[0],
                       "text": text}
            seen_texts[text] = variant
            variants.append(variant)
        variants.append({"label": "LTX 2.5 negative", "text": negative,
                         "note": "The stock negative prompt from the LTX template, left as it was."})

        techniques = ["Image to video", "Model comparison"]
        if rid in ("0", "2a", "6"):
            techniques.append("Speech")
        if rid in ("7", "8"):
            techniques.append("Singing")
        if rid in ("2", "2a", "6", "8"):
            techniques.append("Multiple characters")
        prompts.append({
            "slug": slugify(title),
            "title": title,
            # Named the way the video's chapters name them.
            "code": {"0": "Base test", "2a": "Bonus round"}.get(rid, f"Test {rid}"),
            "group": "rounds",
            "still": outputs[0]["image"],
            "outputs": outputs,
            "time": chapter,
            "models": ["MiniMax H3", "LTX 2.5"],
            "techniques": techniques,
            "facts": facts + [["Length", "5 seconds at 24fps"], ["Ran on", "RTX 3060, 12GB (local)"]],
            "refs": [{"tag": "Start image", "ref": key}],
            "variants": variants,
            "verdict": {"winner": winner, "text": verdict},
            "notes": [],
            "links": [],
        })

    write({
        "slug": slug,
        "title": "MiniMax H3 vs LTX 2.5",
        "short": "Nine rounds, head to head",
        "published": "2026-08-21",
        "video": {"id": "Cww3c0TQESc", "title": "MiniMax H3 vs LTX 2.5 in ComfyUI"},
        "models": ["MiniMax H3", "LTX 2.5"],
        "summary": [
            "MiniMax H3 and LTX 2.5 are both open-weight image to video models, and both generate their own speech "
            "and audio in the same pass. They ran head to head on one desktop, nine rounds each, with a winner "
            "called on every one.",
            "Each round has the prompt each model was given, taken from the metadata ComfyUI saved into the clip, "
            "plus a frame from both results. Final tally: MiniMax H3 five, LTX 2.5 three, plus a bonus round on "
            "turn-based speech outside the count.",
        ],
        "facts": [
            ["MiniMax H3", "6 steps with the Turbo LoRA, simple scheduler"],
            ["LTX 2.5", "The stock two-stage image to video template"],
            ["Clips", "Five seconds from a single still, 24fps, audio straight out of the model"],
            ["Ran on", "RTX 3060 with 12GB, i5-13400F, 32GB RAM, ComfyUI 0.33.0"],
        ],
        "groups": [{"id": "rounds", "title": "Rounds"}],
        "refs": list(refs.values()),
        "links": [
            {"label": "MiniMax H3 6 step workflow with the Turbo LoRA, on Civitai",
             "url": "https://civitai.com/api/download/models/3232626?fileId=3115029"},
            {"label": "MiniMax H3 stock template", "url": "https://docs.comfy.org/tutorials/video/minimax/minimax-h3"},
            {"label": "LTX 2.5 stock template", "url": "https://docs.comfy.org/tutorials/video/ltx/ltx-2-5"},
            {"label": "LTX's official prompting guide",
             "url": "https://docs.ltx.io/open-source-model/usage-guides/prompting-guide"},
        ],
        "prompts": prompts,
    })


# ---------------------------------------------------------------------------- turbo lora

def import_turbo():
    slug = "h3-turbo-lora"
    clip = TURBO / "output_spoken.mp4"
    g = embedded_graph(clip)
    text = nodes_of(g, "MiniMaxH3ImageToVideo")[0]["inputs"]["prompt"]
    steps = nodes_of(g, "BasicScheduler")[0]["inputs"]["steps"] if nodes_of(g, "BasicScheduler") else 6
    seed = nodes_of(g, "RandomNoise")[0]["inputs"]["noise_seed"] if nodes_of(g, "RandomNoise") else None
    still, info = mid_frame(clip)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    ref = {"id": "start", "label": "Start image", "note": "The still the clip was generated from",
           "image": save_image(TURBO / "input.jpeg", "start", slug)}
    write({
        "slug": slug,
        "title": "MiniMax H3 with the Turbo LoRA",
        "short": "Six steps, with speech",
        "published": "2026-08-15",
        "video": {"id": "97OYZMksJsQ", "title": "MiniMax H3 + Turbo LoRA: image to video with sound on low VRAM"},
        "models": ["MiniMax H3"],
        "summary": [
            "The Turbo LoRA setup for MiniMax H3: six steps instead of twenty plus, on a low VRAM card, entirely "
            "local in ComfyUI. The prompt carries a separate audio line, so the character says something and the "
            "model generates the speech along with the motion, from one still image.",
        ],
        "facts": [
            ["Base model", "minimax_h3_fl2va_pruned_int8_convrot"],
            ["Text encoder", "qwen3vl_32b_minimax_h3_nvfp4_awq"],
            ["Turbo LoRA", "minimax_h3_turbo_v4_step600_ema"],
            ["Sampling", "6 steps, simple scheduler"],
        ],
        "groups": [{"id": "example", "title": "The example"}],
        "refs": [ref],
        "links": [
            {"label": "The workflow, on Civitai", "url": "https://civitai.com/api/download/models/3232626?fileId=3115029"},
            {"label": "ComfyUI", "url": "https://github.com/comfyanonymous/ComfyUI"},
        ],
        "prompts": [{
            "slug": "six-steps-speech",
            "title": "Speaking to camera at six steps",
            "group": "example",
            "still": save_image(still, "six-steps-speech", slug),
            "time": 108,
            "models": ["MiniMax H3"],
            "techniques": ["Image to video", "Speech", "Turbo LoRA"],
            "facts": [
                ["Resolution", f"{v['width']}×{v['height']}, 24fps"],
                ["Steps", f"{steps}, Turbo LoRA"],
                ["Seed", str(seed)],
                ["Ran on", "RTX 3060, 12GB (local)"],
            ],
            "refs": [{"tag": "Start image", "ref": "start"}],
            "variants": [{"label": "Prompt", "text": text}],
            "notes": ["Whisper transcribes the generated audio back as exactly the line in the prompt. Nothing was "
                      "dubbed on afterwards."],
            "links": [],
        }],
    })


IMPORTERS = {"shots": import_shots, "chained": import_chained, "firstdate": import_first_date,
             "ltx": import_ltx, "turbo": import_turbo}

if __name__ == "__main__":
    for name in sys.argv[1:] or IMPORTERS:
        IMPORTERS[name]()
