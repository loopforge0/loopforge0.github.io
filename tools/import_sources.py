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
HFCMP = REPOS / "minimaxref2vcomparison"

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


# ---------------------------------------------------------------------------- higgsfield vs h3

# Video order. (clip id, title, plate, Higgsfield kind, credits at today's price, H3 render minutes)
HF_ROUNDS = [
    ("04_amber_street-colossus", "Street colossus", "amber-main", "Effect", 70, 74.2),
    ("03_amber_set-on-fire", "Set on fire", "amber-main", "Motion preset", 10, 30.1),
    ("02_kate_disintegration", "Disintegration", "kate", "Motion preset", 10, 40.1),
    ("05_sofia_melting", "Melting", "sofia", "Motion preset", 10, 30.1),
    ("06_sofia_vanish", "Vanish", "sofia", "Effect", 22.5, 24.1),
    ("11_cyberpunk_thunder-god", "Thunder God", "cyberpunk", "Motion preset", 10, 39.6),
    ("07_allie_levitation", "Levitation", "allie", "Motion preset", 10, 30.1),
    ("12_cyberpunk_architecture-wave", "Architecture wave", "cyberpunk", "Effect", 49, 54.1),
    ("13_cowgirl_incline", "Incline", "cowgirl", "Effect", 49, 54.7),
    ("09_pirate_mighty-fighter", "Mighty fighter", "pirate", "Effect", 27.5, 149.3),
    ("01_kate_floating-fall", "Floating fall", "kate", "Effect", 84, 81.2),
]
HF_PLATES = {"amber-main": "Amber", "kate": "Kate", "sofia": "Sofia", "cyberpunk": "Cyberpunk",
             "allie": "Allie", "cowgirl": "Cowgirl", "pirate": "Pirate"}
HF_VIDEO = {"id": "xmE4JePAQUQ", "title": "Higgsfield Effects vs MiniMax H3 in ComfyUI: 11 tests"}
HF_CHAPTERS = [31, 64, 90, 114, 136, 159, 184, 209, 234, 263, 294]   # seconds, same order as HF_ROUNDS


def import_higgsfield():
    slug = "higgsfield-vs-h3"
    clips = HFCMP / "comparison-video" / "assets" / "clips"   # the exact files the video used
    refs_dir = HFCMP / "higgsfield-effects" / "refs"
    dl = ROOT / "assets" / "dl" / slug
    dl.mkdir(parents=True, exist_ok=True)
    refs = []
    for stem, name in HF_PLATES.items():
        src = refs_dir / f"{stem}.png"
        image = save_image(src, f"ref-{stem}", slug)
        # The original PNG, byte for byte: H3 ran with ref_image_size max, so the full file is the input.
        (dl / src.name).write_bytes(src.read_bytes())
        image.update({"dl": f"dl/{slug}/{src.name}", "bytes": src.stat().st_size})
        refs.append({"id": stem, "label": name, "note": "Character photo, given to both sides", "image": image})

    # Motion presets take a prompt; read from the Higgsfield asset history. Effects take none.
    hf_prompts = json.loads((HFCMP / "higgsfield-effects" / "prompts" / "higgsfield_motion_prompts.json")
                            .read_text(encoding="utf-8"))
    prompts = []
    for n, (cid, title, plate, kind, credits, minutes) in enumerate(HF_ROUNDS):
        hf, h3 = clips / f"hf-{cid}.mp4", clips / f"h3-{cid}.mp4"
        g = embedded_graph(h3)
        node = nodes_of(g, "MiniMaxH3ReferenceToVideo")[0]["inputs"]
        seed = nodes_of(g, "RandomNoise")[0]["inputs"]["noise_seed"]
        steps = nodes_of(g, "BasicScheduler")[0]["inputs"]["steps"]
        outputs, specs = [], {}
        for label, path in (("Higgsfield", hf), ("MiniMax H3", h3)):
            still, info = mid_frame(path)
            v = next(x for x in info["streams"] if x["codec_type"] == "video")
            fps = round(eval(v["r_frame_rate"]))
            audio = any(x["codec_type"] == "audio" for x in info["streams"])
            specs[label] = f"{v['width']}×{v['height']}, {fps}fps{'' if audio else ', no audio'}"
            stem = f"{slugify(title)}-{'higgsfield' if label == 'Higgsfield' else 'h3'}"
            image = save_image(still, stem, slug)
            still.convert("RGB").save(dl / f"{stem}.jpg", quality=92, optimize=True)
            image.update({"dl": f"dl/{slug}/{stem}.jpg", "bytes": (dl / f"{stem}.jpg").stat().st_size})
            outputs.append({"label": label, "image": image})
        p = {
            "slug": slugify(title),
            "title": title,
            "code": f"Round {n + 1}",
            "group": "rounds",
            "still": outputs[1]["image"],
            "outputs": outputs,
            "models": ["Higgsfield", "MiniMax H3"],
            "techniques": ["Reference to video", "Effects"],
            "facts": [
                ["Higgsfield", f"{kind}, {credits:g} credits, {specs['Higgsfield']}"],
                ["MiniMax H3", f"{specs['MiniMax H3']}, {steps} steps, seed {seed}"],
                ["H3 render", f"{minutes:.0f} min on an RTX 3060, 12GB"],
            ],
            "refs": [{"tag": "<Picture 1>", "ref": plate}],
            "variants": [{"label": "MiniMax H3", "text": node["prompt"]}],
            "notes": [],
            "links": [],
        }
        # The exact API graph embedded in the H3 clip, with the local image path swapped for a stock
        # LoadImage of the character photo downloaded above, so the two together rerun the round.
        for nd in g.values():
            if nd["class_type"] == "VHS_LoadImagePath":
                nd["class_type"], nd["inputs"] = "LoadImage", {"image": f"{plate}.png"}
            if nd["class_type"] == "SaveVideo":
                nd["inputs"]["filename_prefix"] = f"video/{slug}/{p['slug']}"
        wf_path = ROOT / "assets" / "workflows" / slug / f"{p['slug']}.json"
        wf_path.parent.mkdir(parents=True, exist_ok=True)
        wf_path.write_text(json.dumps(g, indent=1), encoding="utf-8")
        p["workflow"] = {"url": f"/assets/workflows/{slug}/{p['slug']}.json", "bytes": wf_path.stat().st_size}
        if cid in hf_prompts:
            p["variants"].append({"label": "Higgsfield", "text": hf_prompts[cid]["prompt"],
                                  "note": "As Higgsfield stored it, after its Enhance option rewrote the short prompt "
                                          "that was typed."})
        if HF_VIDEO:
            p["time"] = HF_CHAPTERS[n]
        prompts.append(p)

    # The hero strip is about 3.3:1, so the banner is cut wide and from the top of each frame, where her head is.
    bw, bh = 2400, 760
    banner = Image.new("RGB", (bw, bh))
    for i, side in enumerate(("hf", "h3")):
        path = clips / f"{side}-13_cowgirl_incline.mp4"   # sharp on both sides, mid-tilt
        info = probe(path)
        v = next(x for x in info["streams"] if x["codec_type"] == "video")
        fr = frame_at(path, round(3.5 * eval(v["r_frame_rate"]))).convert("RGB")
        fr = fr.resize((1500, round(fr.height * 1500 / fr.width)), Image.LANCZOS)
        x0 = (fr.width - bw // 2) // 2
        banner.paste(fr.crop((x0, 0, x0 + bw // 2, bh)), (i * bw // 2, 0))
    banner.paste((7, 9, 12), (bw // 2 - 3, 0, bw // 2 + 3, bh))   # a thin seam between the two sides
    banner_img = save_image(banner, "banner", slug)
    # The hero shows the large file full width, so it keeps the full 2400 px rather than the 1280 still size.
    banner.save(IMG / slug / "banner.jpg", quality=86, optimize=True, progressive=True)
    banner.save(dl / "banner.jpg", quality=90, optimize=True)
    banner_img.update({"dl": f"dl/{slug}/banner.jpg", "bytes": (dl / "banner.jpg").stat().st_size})

    col = {
        "slug": slug,
        "title": "Higgsfield effects vs MiniMax H3",
        "short": "Eleven effects, side by side",
        "published": "2026-10-03",
        "models": ["Higgsfield", "MiniMax H3"],
        "summary": [
            "Eleven Higgsfield effects and motion presets, remade locally with MiniMax H3 Ref2VA in ComfyUI from "
            "the same character photo. Each round has the H3 prompt, the photo and a frame from both sides.",
        ],
        "facts": [
            ["MiniMax H3", "minimax_h3_ref2va_pruned_int8_convrot, 20 steps, res_multistep, simple"],
            ["Reference", "One character photo, ref_image_size max"],
            ["Higgsfield", "Effects need no prompt; motion presets take a short one"],
            ["Ran on", "RTX 3060 with 12GB, i5-13400F, 32GB RAM, PyTorch on CUDA 13"],
        ],
        "groups": [{"id": "rounds", "title": "Rounds"}],
        "refs": refs,
        "links": [
            {"label": "The H3 Ref2VA workflow (json)", "url": f"/assets/workflows/{slug}.json"},
            {"label": "MiniMax's official prompt writing guide",
             "url": "https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md"},
            {"label": "Higgsfield effects", "url": "https://higgsfield.ai/"},
        ],
        "prompts": prompts,
        "banner": banner_img,
    }
    if HF_VIDEO:
        col["video"] = HF_VIDEO
    write(col)
    # Until the video is up the cards use the recommended YouTube thumbnail.
    Image.open(HFCMP / "comparison-video" / "thumbs" / "thumb_a.png").convert("RGB").save(
        IMG / slug / "card.jpg", quality=86, optimize=True, progressive=True)

    # The workflow from the video's graph tour, with a pointer in place of a prompt.
    wf = json.loads((HFCMP / "comparison-video" / "assets" / "graph-h3-ui.json").read_text(encoding="utf-8"))
    for nd in wf["nodes"]:
        if nd["type"] == "MiniMaxH3ReferenceToVideo":
            nd["widgets_values"][0] = f"Paste a prompt from https://loopforge.cc/projects/{slug}/"
        if nd["type"] == "SaveVideo":
            nd["widgets_values"][0] = "video/higgsfield-vs-h3"
    (ROOT / "assets" / "workflows" / f"{slug}.json").write_text(json.dumps(wf, indent=1), encoding="utf-8")


# ---------------------------------------------------------------------------- ltx 2.5 loras

LORAS = REPOS / "ltx-2.5-bestloras"
# Not published yet. Set to {"id": "<YouTube id>", "title": "..."} once the video is up: that turns
# on the Watch button, the YouTube thumbnail on the cards and the per-test chapter links below.
LORAS_VIDEO = {"id": "ZE9kvCCHlNk", "title": "LTX 2.5 Official LoRAs: All 14 LoRAs tested"}
# Seconds into the video where each test's first narration line starts, in shortlist order. Taken
# from video/VO_CUES.md (the timeline built from the recorded takes); check against the final cut.
LORAS_CHAPTERS = [33, 49, 68, 86, 114, 137, 156, 187, 228, 266, 285, 318, 347, 388, 413, 437, 479, 513,
                  549, 587, 630, 664, 713, 781, 828, 890, 932, 976, 1029, 1051, 1084]

# Every input a published workflow loads, with what it is and where it came from.
LORAS_INPUTS = {
    "ingredient_sheet3_subject.png": ("Rooftop sheet", "Ingredients sheet: character, camera and rooftop panels on black"),
    "ingredient_sheet3_studio.png": ("Stage sheet", "Ingredients sheet: character, guitar and stage panels on black"),
    "ingredient_sheet18_faces.png": ("Two-face sheet", "Two face crops, a guitar and a jazz club, 2×2 on black"),
    "still14_amber_tokyo.png": ("Tokyo still", "Start still, made with Qwen-Image 2.1"),
    "still19_dove.png": ("Dove still", "Start still, made with Qwen-Image 2.1"),
    "char_kate.png": ("Kate", "Character photo"),
    "char_allie.png": ("Allie", "Character photo"),
    "still4_autumn.png": ("Autumn tree", "First frame of a clip generated with LTX 2.5"),
    "layout28_look.png": ("Look still", "Qwen-Image 2.1 edit of the layout's first frame, with a character photo"),
    "layout28_plaza_clay.mp4": ("Clay layout", "Rendered in Blender from primitives with clay shading"),
    "src5_crossing_129.mp4": ("Umbrella clip", "Generated with LTX 2.5, no LoRA. 129 frames at 25fps"),
    "src4_canal_dolly.mp4": ("Canal clip", "Generated with LTX 2.5, no LoRA"),
    "src2_day_park_hd.mp4": ("Park clip", "Generated with LTX 2.5, no LoRA"),
    "src13_sandbox_two.mp4": ("Sandbox clip", "Generated with LTX 2.5, no LoRA"),
    "src2_dry_stairs_hd.mp4": ("Stairs clip", "Generated with LTX 2.5, no LoRA"),
    "colorization2_gray_hd.mp4": ("Grayscale market", "A generated market clip, desaturated with FFmpeg"),
    "decompression2_blocky_960.mp4": ("Blocky market", "A generated market clip, re-encoded at 120 kbps"),
    "restore5_gray_blocky_960.mp4": ("Grayscale, blocky market", "A generated market clip, grayscale and at 120 kbps"),
    "bucket1959_gray_121.mp4": ("A Bucket of Blood", "Roger Corman, 1959. Public domain, via Wikimedia Commons"),
    "superman1941_4x3_896_161.mp4": ("Superman", "Fleischer Studios, 1941. Public domain, via the Internet Archive. "
                                                 "Scaled to 896×672"),
    "pexels_854040_blur_161_1536.mp4": ("Clowns walking", "By Coverr on Pexels, Pexels License. First 161 frames, "
                                                          "scaled to 1536×864"),
    "npc74_blur_a_161.mp4": ("Japanese Bride School", "US Navy, 1956, National Archives 75330. Public domain, via "
                                                      "the Internet Archive"),
    "restore26_market_st_1906.mp4": ("A Trip Down Market Street", "Miles Brothers, 1906. Public domain, via the "
                                                                  "Internet Archive. 640×480"),
    "hdr27_diana_creek.mp4": ("Diana Creek", "By Extemporalist, CC0, via Wikimedia Commons"),
    "alpha25_run.mp4": ("Tokyo run", "The Slow Motion LoRA result from this project"),
    "alpha25_kate.mp4": ("Kate portrait", "The Cinemagraph LoRA result from this project"),
}

LORAS_CREDITS = {
    "bucket": ("A Bucket of Blood (Roger Corman, 1959), public domain, on Wikimedia Commons",
               "https://commons.wikimedia.org/wiki/File:A_Bucket_of_Blood_(1959)_by_Roger_Corman_2.webm"),
    "superman": ("Superman (Fleischer Studios, 1941), public domain, on the Internet Archive",
                 "https://archive.org/details/superman_1941"),
    "clowns": ("Clowns walking, by Coverr on Pexels, Pexels License",
               "https://www.pexels.com/video/clowns-walking-854040/"),
    "navy": ("Japanese Bride School, Yokosuka, Japan (US Navy, 1956), public domain, on the Internet Archive",
             "https://archive.org/details/NPC-74"),
    "market": ("A Trip Down Market Street Before the Fire (Miles Brothers, 1906), public domain, on the Internet Archive",
               "https://archive.org/details/TripDown1905"),
    "creek": ("Golden hour rays break through mist on Diana Creek, by Extemporalist, CC0, on Wikimedia Commons",
              "https://commons.wikimedia.org/wiki/File:Golden_hour_rays_break_through_mist_on_Diana_Creek.webm"),
}

# Page title, verdict, notes and footage credit for each test, keyed by (LoRA id, shortlist title).
# The verdicts are the shortlist captions and the narration, rewritten for the page.
LORAS_TESTS = {
    ("ingr", "Character, prop and location"): (
        "Character, prop and location",
        "The woman, her yellow camera and the rooftop each come from a separate panel of the sheet, and they end "
        "up together in a new moving shot.",
        ["The sheet follows the Lightricks demo layout: a 1536×896 black canvas, 16 px gutters and plain photo "
         "panels. Keeping to that sizing and those margins gave me better results."], None),
    ("ingr", "Guitarist on a stage"): (
        "Guitarist on a stage",
        "The woman, the red guitar and the curtained stage with its piano are each taken from their own panel. LTX "
        "2.5 generates audio as well, so the clip comes with sound that fits the scene.",
        [], None),
    ("ingr", "Two characters from one sheet"): (
        "Two characters from one sheet",
        "I put two faces on one sheet to see whether both would hold. The scene, the guitar and the outfits came "
        "through. The guitarist's face stays hidden behind her hair, the singer does not clearly match the woman on "
        "the sheet, and her freckles turn into red marks on her arm.",
        ["This run used large face panels, the prompt format from the model card and the outfits described in the "
         "prompt."], None),
    ("ingr", "The sheet comes through"): (
        "The sheet comes through",
        "The sheet is clean and evenly spaced with one character on it, and the output still reproduces the sheet "
        "panel by panel. When this happened, a small prompt change and a new seed usually cleared it.",
        ["This run also had the Slow Motion LoRA chained in. The same failure shows up in the chaining tests at the "
         "end of the page."], None),
    ("color", "Market"): (
        "Grayscale market",
        "I took a generated market clip, turned it grayscale and gave that to the LoRA. The colours it picked for "
        "the fruit, the vegetables, the awning and the clothes came out close to the original.",
        ["The trigger is COLORIZE. The colours you name in the prompt are the colours you get."], None),
    ("color", "A Bucket of Blood, 1959 (public domain)"): (
        "A Bucket of Blood, 1959",
        "This is a real black-and-white film, so there is no colour original to check against. Every colour I named "
        "in the prompt lands, from the dusty-rose cardigan to the yellow lampshade, and the faces hold through the "
        "shot. The cane comes out red without being asked for.",
        ["The film's own soundtrack is put back on the result after generation."], "bucket"),
    ("slow", "Running through Tokyo rain"): (
        "Running through Tokyo rain",
        "The LoRA clip uses a plain caption of a normal-speed run, as the model card asks, and speed 0.2 alone slows "
        "it down. The clip without the LoRA has slow motion written into the prompt instead. That one runs faster "
        "and the effect comes and goes, while the LoRA holds it steady through the shot.",
        ["Speed is set through the conditioning frame rate, which is 24 divided by the speed, so 120 here. Playback "
         "stays at 24fps. There is no trigger word."], None),
    ("slow", "Dove in flight"): (
        "Dove in flight",
        "Both clips have the same start still and the same caption. Without the LoRA the wings beat faster and the "
        "feather tips blur. With it each frame moves a little, and the flight feathers stay sharp and separate "
        "through the stroke.",
        ["The clip without the LoRA mixed slow wings with a neck moving at normal speed, which looked unnatural to "
         "me."], None),
    ("cine", "Portrait, hair in the breeze"): (
        "Portrait, hair in the breeze",
        "Only a few strands of hair move and the head stays still. I could not get this without the LoRA, whatever "
        "I changed in the prompt.",
        ["Writing the prompt in the card's order, with what is frozen first and then what moves, made the face "
         "slightly stiller than my first prompt did. The trigger is CINEMAGRAPH_MOTION, at strength 1.5."], None),
    ("cine", "Standing figure"): (
        "Standing figure",
        "Her head, her body and the wall stay locked while the hem of the dress and the ends of her hair sway. The "
        "eyes still shift slightly, and neither strength 1.5 nor the card's prompt order removed that.",
        ["If the face has to be completely frozen, mask it in the edit."], None),
    ("cine", "Tree full of falling leaves"): (
        "Tree full of falling leaves",
        "A tree has thousands of small moving parts, and the whole frame drifts instead of only the leaves moving. "
        "I rewrote the prompt in the card's order and asked for just three falling leaves, with every leaf on the "
        "tree frozen, and it changed nothing.",
        ["The LoRA was trained at 512×704 with 25 frames. The two people above held far better at 121 frames than "
         "this did."], None),
    ("plate", "Woman with umbrella"): (
        "Woman with umbrella",
        "She and her umbrella are removed from every frame and the graffiti behind her is rebuilt. The bus in the "
        "opening frames is left where it was.",
        ["Describe the empty scene in the prompt, and name what to remove in both the prompt and the negative. The "
         "LoRA was trained at 1024×576 and 25fps, so this runs 129 frames."], None),
    ("plate", "Moving camera"): (
        "Couple on a canal, moving camera",
        "The camera dollies along a canal while a couple walks through the shot. Both of them are removed along "
        "with their shadows, and the rest of the scene stays as it was.",
        [], None),
    ("night", "Park with fountain"): (
        "Park with fountain",
        "The lamps come on and the sky goes dark, and the jogger and the pigeons keep to their original paths. At "
        "1152×640 this needed strength 1.5.",
        [], None),
    ("night", "Canal, moving camera"): (
        "Canal at night, moving camera",
        "The dolly move and the boats are kept and the windows and lamps light up. The reflections in the water "
        "follow the new lights.",
        [], None),
    ("night", "Same park at strength 1.0"): (
        "Same park at strength 1.0",
        "At 1152×640 the default strength only lights the lamps. The scene stays partly in daylight, with some "
        "parts of it day and some night.",
        ["The LoRA was trained at 768×448 with 97 frames. At the larger size used here it needed a strength of 1.3 "
         "to 1.5."], None),
    ("water", "Water into a sandbox"): (
        "Water into a sandbox",
        "This uses the card's prompt template on a clip of a dry sandbox. Water pools around their knees and the "
        "bucket pours water instead of sand. The sand around the edges stays dry, and the cream trousers on the "
        "right come out as light jeans.",
        ["I also tried to replace all of the sand with water and could not get that to work. This LoRA is strict "
         "about the prompt format it expects. The trigger is ADD WATER."], None),
    ("water", "Wave"): (
        "Wave over the steps",
        "Spray bursts over the balustrade and a shallow wave washes over the lower steps. The way the water meets "
        "the steps looked more natural than I expected.",
        ["At 1152×640 it needed strength 1.3. At 1.0 the water barely showed."], None),
    ("decomp", "Heavily macroblocked market"): (
        "Heavily macroblocked market",
        "I re-encoded a generated market clip at 120 kbps to break it into blocks. The LoRA removes the blocks, and "
        "the fruit and the crowd come back clean and close to the original.",
        ["It came out so close to the original that I tried footage that was never clean next. The trigger is "
         "ENHANCE QUALITY, and it only helps footage that is badly damaged."], None),
    ("decomp", "1941 Fleischer Superman (public domain)"): (
        "Superman, 1941",
        "This is an old analogue transfer of the 1941 Fleischer cartoon. The colour smear and noise are cleaned up "
        "and the ink lines sharpen. It also invents detail, with extra lines on the face and the blurry "
        "handwriting redrawn.",
        ["This ran at strength 1.3 and at 896×672, which keeps the cartoon's 4:3 shape. The original soundtrack is "
         "put back on after generation."], "superman"),
    ("deblur", "Clowns on a city street (Pexels)"): (
        "Clowns on a city street",
        "This is phone footage that is out of focus from start to finish. The clowns' costumes, the cars, the "
        "police motorcycle and the brickwork come back sharp. The shop signs are redrawn as new lettering that "
        "does not say anything.",
        ["I ran it at 1536×864, since the card suggests about 1536 wide for more detail. The trigger is DEBLUR, and "
         "it is meant for defocus only."], "clowns"),
    ("deblur", "1956 Navy film: diploma handover"): (
        "1956 Navy film, diploma handover",
        "The National Archives catalogues this shot as out of focus. Her face, earring, collar and buttons come "
        "into focus and she stays the same woman, while the background stays soft.",
        ["Together with Decompression, I think this is a good option for old footage."], "navy"),
    ("restore", "Market Street, 1906 (public domain)"): (
        "A Trip Down Market Street, 1906",
        "This is a 640×480 web copy of a film shot from the front of a cable car in San Francisco in 1906. One "
        "pass adds colour, removes the scratches and the flicker and adds detail, and the SIGHT lettering on the "
        "cable car survives. The far background, the distant people and the building fronts are rebuilt rather "
        "than recovered, because there was little detail there to begin with.",
        ["The source is resized to the 1440×1088 canvas with lanczos and nothing else, then processed in 960×544 "
         "tiles. The prompt names the period, the place, the light and the clothing, and the negative names "
         "modern objects."], "market"),
    ("refine", "Generated canal clip, 2x"): (
        "Generated canal clip at 2x",
        "I took a 960×544 clip generated with LTX 2.5 up to 1920×1088. Both frames show the same 960×544 crop, one "
        "from a plain lanczos upscale and one from Refine Details. The brickwork, the window bars and the faces "
        "have real texture in the refined version, where the plain upscale is smeared.",
        ["Refine Details is for footage that is clean but soft, such as LTX output. Deblur is for footage that is "
         "out of focus, and Decompression is for blocky, compressed footage.",
         "The crops were cut after generation. The workflow produces the full 1920×1088 clip."], None),
    ("hdr", "Forest creek, sun through mist"): (
        "Forest creek, sun through mist",
        "Both versions are pulled down 2.5 stops so that an SDR screen can show the highlights. The SDR source has "
        "nothing above white, so the sunlit water turns flat grey. The HDR version keeps the glints and the light "
        "shafts. That headroom is the model's estimate of what was there, not recovered data.",
        ["The output is ACEScg EXR frames and a 10-bit HLG "
         "master, and the exposure was pulled down on both versions after generation."], "creek"),
    ("alpha", "Curly hair in the rain"): (
        "Curly hair in the rain",
        "The matte keeps single strands of curly hair against a busy neon street. I composited her over a forest "
        "creek, and a few strands keep the pink of the neon they were lit by. That pink is in the source footage, "
        "not in the matte.",
        ["The output is a grayscale matte, white for the subject. The composite multiplies the source by the matte "
         "and the background by its inverse, and was made after generation."], "creek"),
    ("alpha", "Portrait, hair in the wind"): (
        "Portrait, hair in the wind",
        "This one is in portrait orientation, with loose wavy hair against a bright bookshelf. The flyaway strands "
        "stay soft in the matte instead of being cut off.",
        [], None),
    ("layout", "Town square, camera arc"): (
        "Town square, camera arc",
        "I built the layout in Blender from primitives and made the look still from its first frame with "
        "Qwen-Image 2.1. The camera arc, the fountain, the tree and the lamp land where the layout put them. The "
        "box mannequin has no front, so she turns her back mid-shot. The nearest bench smears, and the empty sky in "
        "the layout became more houses.",
        ["I have seen more side effects like these on busier layout animations, so I expect it to work better with "
         "simpler camera moves. The prompt matches the look still and leaves out the words clay and 3D."], None),
    ("chain", "Clean Plate + Day-to-Night"): (
        "Clean Plate with Day-to-Night",
        "Both walkers are removed and the street turns to night in one pass. The dolly move, the boats and the "
        "buildings hold.",
        ["The two LoRA loaders sit in series on one graph, and one prompt carries what both of them need."], None),
    ("chain", "Colorization + Decompression"): (
        "Colorization with Decompression",
        "I gave it the market clip in grayscale and at 120 kbps. One pass brings back full colour and removes the "
        "blocks. The colour runs hot, and it invents some crowd and stall detail.",
        [], None),
    ("chain", "Ingredients + Slow Motion"): (
        "Ingredients with Slow Motion",
        "I ran the same sheet and the same prompt on three seeds. She should hold the yellow camera to her eye on "
        "the rooftop, take a shot and lower it. One result copies the reference sheet panel by panel, one is a "
        "black void with no camera or rooftop, and one invents a second woman.",
        ["This combination was frustrating. For me, chaining LoRAs came down to trial and error."], None),
}


def loras_run(name):
    """What ran for one result: the API graph, the prompts and the settings, from the run's own records."""
    d = LORAS / "results" / "comfy" / name
    if (d / "attempt.json").exists():
        a = json.loads((d / "attempt.json").read_text(encoding="utf-8"))
        g = json.loads((d / "workflow_api.json").read_text(encoding="utf-8"))
        prm = a["parameters"]
        info = {"graph": g, "prompt": a["prompt"], "negative": a["negative_prompt"],
                "w": prm["width"], "h": prm["height"], "frames": prm["frames"], "fps": prm["fps"],
                "seed": prm["seed"], "loras": [(x["file"], x["strength"], x["ic"]) for x in a["adapters"]],
                "repo": a["adapter_repo"], "minutes": a["elapsed_s"] / 60, "vram": a.get("peak_vram_gib")}
        # The prompt shown must be the one in the graph that ran.
        texts = {v for nd in g.values() for v in nd["inputs"].values() if isinstance(v, str)}
        for t in (info["prompt"], info["negative"]):
            assert not t or t in texts, f"{name}: prompt not in its graph"
        return info
    # One run was queued by hand; only ComfyUI's history records it.
    h = json.loads((d / "history.json").read_text(encoding="utf-8"))
    entry = next(iter(h.values()))
    g = entry["prompt"][2]

    def one(t):
        return nodes_of(g, t)[0]["inputs"]
    pos, neg = (nd["inputs"]["text"] for nd in nodes_of(g, "CLIPTextEncode"))
    stamps = [m[1]["timestamp"] for m in entry["status"]["messages"]
              if m[0] in ("execution_start", "execution_success")]
    lora = one("LTXICLoRALoaderModelOnly")
    return {"graph": g, "prompt": pos, "negative": neg, "w": one("EmptyLTXVLatentVideo")["width"],
            "h": one("EmptyLTXVLatentVideo")["height"], "frames": one("EmptyLTXVLatentVideo")["length"],
            "fps": round(one("CreateVideo")["fps"]), "seed": one("RandomNoise")["noise_seed"],
            "loras": [(lora["lora_name"], lora["strength_model"], True)], "repo": None,
            "minutes": (stamps[-1] - stamps[0]) / 60000, "vram": None}


def loras_sampling(g):
    steps = [len(nd["inputs"]["sigmas"].split(",")) - 1 for nd in nodes_of(g, "ManualSigmas")]
    samplers = sorted({nd["inputs"]["sampler_name"] for nd in nodes_of(g, "KSamplerSelect")})
    return f"{' + '.join(map(str, steps))} steps, {' / '.join(samplers)}"


def and_list(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# What a reader needs to rerun a test. Checked against the install the runs used (E:/Flux/ComfyUI/ComfyUI):
# ComfyUI v0.37.0 plus one commit (0f74f7fb, frontend 1.53.6) and ComfyUI-LTXVideo at 3bf3ca6. Every
# class_type in the published graphs is a core node except the ones below, which ComfyUI-LTXVideo provides.
LORAS_COMFY = "ComfyUI 0.37.0 (commit 0f74f7fb, frontend 1.53.6)"
LORAS_PACK = ("ComfyUI-LTXVideo", "3bf3ca62595f1764c47d01c35c8e5dfe47e1a88f",
              "https://github.com/Lightricks/ComfyUI-LTXVideo/tree/3bf3ca62595f1764c47d01c35c8e5dfe47e1a88f")
LORAS_PACK_CLASSES = {
    "GemmaAPITextEncode", "LTXAddVideoICLoRAGuide", "LTXICLoRALoaderModelOnly", "LTXVGetTilingSizes",
    "LTXVHDRDecodePostprocess", "LTXVLoadConditioning", "LTXVSDRToHDRWorkingSpace", "LTXVSaveHLG",
    "LTXVSetAudioRefTokens", "LTXVTiledFusionSampler", "LTXVVAEForceFloat32",
}
LOCAL_MODELS = Path("E:/Flux/ComfyUI/ComfyUI/models")   # only read for file sizes
# Loader node -> (input holding the file name, ComfyUI models subfolder)
LORAS_LOADERS = {
    "UNETLoader": ("unet_name", "diffusion_models"),
    "CLIPLoader": ("clip_name", "text_encoders"),
    "VAELoader": ("vae_name", "vae"),
    "LatentUpscaleModelLoader": ("model_name", "latent_upscale_models"),
    "LoraLoaderModelOnly": ("lora_name", "loras"),
    "LTXICLoRALoaderModelOnly": ("lora_name", "loras"),
    "LTXVLoadConditioning": ("file_name", "embeddings"),
}
# Where the files that are not LoRAs come from, as repo and path inside it.
LORAS_SOURCES = {
    "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors":
        ("Lightricks/LTX-2.5", "diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"),
    "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors":
        ("Lightricks/LTX-2.5", "text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors"),
    "ltx-2.5-video-vae-bf16.safetensors": ("Lightricks/LTX-2.5", "vae/ltx-2.5-video-vae-bf16.safetensors"),
    "ltx-2.5-audio-vae-bf16.safetensors": ("Lightricks/LTX-2.5", "vae/ltx-2.5-audio-vae-bf16.safetensors"),
    "ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors":
        ("Lightricks/LTX-2.5", "latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors"),
    "gemma4_e2b_it_bf16.safetensors": ("Comfy-Org/gemma-4", "text_encoders/gemma4_e2b_it_bf16.safetensors"),
    "ltx-2.5-22b-ic-lora-sdr-to-hdr-scene-emb.safetensors":
        ("Lightricks/LTX-2.5-22b-IC-LoRA-SDR-To-HDR", "ltx-2.5-22b-ic-lora-sdr-to-hdr-scene-emb.safetensors"),
}
ZIP_TIME = (2026, 1, 1, 0, 0, 0)   # fixed, so a rebuild writes byte-identical zips


def loras_models(graphs, names):
    """Every model file the graphs load, with its folder, size and download URL, in loader order."""
    found = {}
    for g in graphs:
        for nd in g.values():
            spec = LORAS_LOADERS.get(nd["class_type"])
            if not spec:
                continue
            fname = nd["inputs"][spec[0]]
            if fname in found:
                continue
            if fname in LORAS_SOURCES:
                repo, path = LORAS_SOURCES[fname]
            else:
                repo, path = names[fname][1], fname   # the LoRAs sit at the root of their repos
            local = LOCAL_MODELS / spec[1] / fname
            found[fname] = {"file": fname, "folder": spec[1], "repo": repo,
                            "url": f"https://huggingface.co/{repo}/resolve/main/{path}",
                            "bytes": local.stat().st_size,
                            "gated": repo.startswith("Lightricks/LTX-2.5")}  # the base repo and every LoRA repo need a login and accepted terms (401 without)
    order = ["diffusion_models", "text_encoders", "vae", "latent_upscale_models", "loras", "embeddings"]
    return sorted(found.values(), key=lambda m: order.index(m["folder"]))


def gb(n):
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def loras_readme(title, page_url, workflows, inputs, models, needs_pack, ran):
    lines = [f"{title}", "From LTX 2.5 Creative Lab LoRAs, tested locally", page_url, "",
             "IN THIS ZIP", ""]
    lines += [f"  {w}  ComfyUI workflow, API format, exactly as it ran" for w in workflows]
    lines += [f"  {f}  input the workflow loads" for f in inputs]
    lines += ["", "HOW TO RUN IT", "",
              "  1. Copy the input files into ComfyUI/input, keeping their names.",
              "  2. Download the models below into the ComfyUI/models subfolders shown.",
              "  3. Drag the workflow .json onto the ComfyUI window, or open it from the Workflow menu.",
              "     It is in API format. The ComfyUI frontend I used (1.53.6) opens that directly and",
              "     lays the nodes out itself, so the graph looks plain but runs the same.",
              "  4. Queue it. The result is saved under ComfyUI/output/video/ltx-2-5-loras/.", "",
              "MODELS", ""]
    for m in models:
        lines += [f"  models/{m['folder']}/{m['file']}  ({gb(m['bytes'])})", f"    {m['url']}"]
    if any(m["gated"] for m in models):
        lines += ["", "  The Lightricks repositories on Hugging Face (the base model and every LoRA) are gated. Log in, open each",
                  "  repository page and accept its terms first, or the download links return an error."]
    lines += ["", "SOFTWARE", "", f"  {LORAS_COMFY}"]
    if needs_pack:
        lines += [f"  {LORAS_PACK[0]} at commit {LORAS_PACK[1][:7]}", f"    {LORAS_PACK[2]}"]
    else:
        lines += ["  No custom nodes. Every node in this workflow is part of ComfyUI itself."]
    lines += ["", "WHAT I RAN IT ON", "", f"  {ran}", ""]
    return "\r\n".join(lines)


def write_zip(path, members):
    """members: [(name, bytes)]. Sorted, fixed timestamps, stored when the data is already compressed."""
    import zipfile
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, data in sorted(members):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.create_system = 0
            info.external_attr = 0o644 << 16
            packed = name.endswith((".mp4", ".png", ".jpg"))
            info.compress_type = zipfile.ZIP_STORED if packed else zipfile.ZIP_DEFLATED
            z.writestr(info, data, compresslevel=9 if not packed else None)


def import_loras():
    slug = "ltx-2-5-loras"
    video = LORAS / "video"   # manifest paths are relative to the video project
    shortlist = json.loads((LORAS / "report" / "shortlist.json").read_text(encoding="utf-8"))["loras"]
    manifest = json.loads((video / "assets" / "manifest.json").read_text(encoding="utf-8"))["loras"]
    assert [x["id"] for x in shortlist] == [x["id"] for x in manifest]
    wf_dir = ROOT / "assets" / "workflows" / slug
    in_dir = wf_dir / "inputs"
    in_dir.mkdir(parents=True, exist_ok=True)

    # LoRA file -> (its name on this page, its Hugging Face repo), from the single-LoRA runs.
    extra_runs = {"refine": ["refine29_canal_lora_s42"], "hdr": ["hdr27_creek_lora_s42"]}
    names = {}
    for lo in shortlist:
        if lo["id"] == "chain":
            continue
        for it in lo["items"]:
            for name in [c["run"] for c in it["clips"] if c.get("run")] + extra_runs.get(lo["id"], []):
                r = loras_run(name)
                # Some run records carry a note such as "Lightricks (plate)" where the repo id goes.
                if len(r["loras"]) == 1 and re.fullmatch(r"Lightricks/LTX-2\.5-22b-[\w-]+", r["repo"] or ""):
                    names[r["loras"][0][0]] = (lo["name"], r["repo"])
    # The repo ids the downloads came from (model-manifest.json in the experiment), for any LoRA whose
    # run records never named one.
    manifest_repos = json.loads((LORAS / "model-manifest.json").read_text(encoding="utf-8"))
    for lo in shortlist:
        for it in lo["items"]:
            for name in [c["run"] for c in it["clips"] if c.get("run")]:
                for f, _, _ in loras_run(name)["loras"]:
                    if f not in names and lo["id"] != "chain":
                        repo = next(m.group(0) for m in re.finditer(r"Lightricks/LTX-2\.5-22b-[\w-]+",
                                                                     json.dumps(manifest_repos))
                                    if m.group(0).lower().endswith(lo["name"].lower().replace(" ", "-")))
                        names[f] = (lo["name"], repo)

    refs = {}

    def ref_for(fname):
        if fname not in refs:
            src = LORAS / "inputs" / fname
            label, note = LORAS_INPUTS[fname]
            stem = "in-" + Path(fname).stem.replace("_", "-")
            image = save_image(mid_frame(src)[0] if fname.endswith(".mp4") else src, stem, slug)
            # The exact file the workflow loads, byte for byte, so the graph and this rerun it.
            (in_dir / fname).write_bytes(src.read_bytes())
            image.update({"dl": f"workflows/{slug}/inputs/{fname}", "bytes": src.stat().st_size})
            refs[fname] = {"id": Path(fname).stem, "label": label, "note": note, "image": image}
        return refs[fname]["id"]

    def publish(run, pslug, wf_name):
        """Write the run's API graph with its loaders pointed at the published copies of its inputs."""
        g = json.loads(json.dumps(run["graph"]))
        loads = []
        for nd in g.values():
            key = {"LoadImage": "image", "LoadVideo": "file"}.get(nd["class_type"])
            if key:
                fname = nd["inputs"][key].removeprefix("bestloras_")
                nd["inputs"][key] = fname
                loads.append((nd["class_type"], fname))
            for k, v in nd["inputs"].items():
                if k in ("filename_prefix", "output_dir") and isinstance(v, str) and "bestloras_" in v:
                    nd["inputs"][k] = re.sub(r"bestloras_.*?(?=_ltxvsavehlg$|_exr$|$)", f"{slug}/{pslug}", v)
        path = wf_dir / f"{wf_name}.json"
        path.write_text(json.dumps(g, indent=1, ensure_ascii=False), encoding="utf-8")
        return {"url": f"/assets/workflows/{slug}/{wf_name}.json", "bytes": path.stat().st_size}, loads

    prompts, groups, minutes, vram_seen = [], [], [], []
    works = limits = 0
    for lo, lm in zip(shortlist, manifest):
        group_title = "Chained LoRAs" if lo["id"] == "chain" else lo["name"]
        groups.append({"id": lo["id"], "title": group_title})
        for it, im in zip(lo["items"], lm["items"]):
            title, verdict, notes, credit = LORAS_TESTS[(lo["id"], it["title"])]
            pslug = slugify(title)
            good = it["kind"] == "good"
            works += good
            limits += not good

            # A frame from every clip the video showed, from the exact files it used, in its order.
            outputs, lora_still = [], None
            for j, c in enumerate(im["clips"]):
                src = video / c["src"]
                still = mid_frame(src)[0] if c["kind"] == "video" else src
                image = save_image(still, f"{pslug}-{j + 1}", slug)
                outputs.append({"label": c["label"], "image": image})
                if c["is_lora"]:
                    lora_still = image

            # The runs behind the generated clips. Composites and exposure views come from a named run.
            run_names = [c["run"] for c in it["clips"] if c.get("run")]
            run_names += [c["file"].split("/")[2] for c in it["clips"]
                          if c.get("file", "").startswith("results/comfy/")]
            run_names += extra_runs.get(lo["id"], [])
            runs = {r: loras_run(r) for r in dict.fromkeys(run_names)}
            lora_runs = [r for r in runs if "_control_" not in r]
            control_runs = [r for r in runs if "_control_" in r]
            main = runs[lora_runs[0]]
            minutes += [x["minutes"] for x in runs.values()]
            vram_seen += [x["vram"] for x in runs.values() if x["vram"]]

            # One tab per distinct text. A text both runs shared is labelled for both.
            def tabs(field, plain, lora_label, control_label):
                texts = {}
                for r in lora_runs + control_runs:
                    texts.setdefault(runs[r][field], []).append(r)
                out = []
                for text, who in texts.items():
                    if field == "negative" and not text:
                        continue
                    shared = not control_runs or len(who) == len(runs)
                    out.append({"label": plain if shared else (control_label if who[0] in control_runs else lora_label),
                                "text": text})
                return out
            variants = tabs("prompt", "Prompt", "With the LoRA", "No LoRA")
            variants += tabs("negative", "Negative", "Negative, with the LoRA", "Negative, no LoRA")
            for v in variants:
                if not v["text"]:
                    v["note"] = ("SDR to HDR takes no prompt. A scene embedding goes in its place." if lo["id"] == "hdr"
                                 else "Alpha Gen runs with an empty prompt. The source clip is the only guide.")

            facts = [["LoRA" if len(main["loras"]) == 1 else "LoRAs",
                      and_list(f"{names[f][0]} at {s:.1f}" for f, s, _ in main["loras"])],
                     ["Output", f"{main['w']}×{main['h']}, {main['frames']} frames at {main['fps']}fps"],
                     ["Sampling", loras_sampling(main["graph"])],
                     ["Seed" if len(lora_runs) == 1 else "Seeds", and_list(str(runs[r]["seed"]) for r in lora_runs)],
                     ["Generated in", (f"{runs[lora_runs[0]]['minutes']:.0f} min each"
                                       if len({round(runs[r]["minutes"]) for r in lora_runs}) == 1 < len(lora_runs)
                                       else and_list(f"{runs[r]['minutes']:.0f} min" for r in lora_runs))]]
            if main["vram"]:
                facts.append(["Peak VRAM", f"{main['vram']:.1f} GiB"])
            for r in control_runs:
                c = runs[r]
                facts.append(["No LoRA run", f"Same graph without the LoRA, seed {c['seed']}, {c['minutes']:.0f} min"])
            facts.append(["Ran on", "RTX 3060, 12GB (local)"])

            workflow, loads = publish(main, pslug, pslug)
            links = []
            for r in control_runs:
                wf, extra = publish(runs[r], pslug, f"{pslug}-no-lora")
                loads += extra
                links.append({"label": "Download the workflow without the LoRA (json)", "url": wf["url"]})
            for f, _, _ in main["loras"]:
                links.append({"label": f"The {names[f][0]} LoRA on Hugging Face",
                              "url": f"https://huggingface.co/{names[f][1]}"})
            if credit:
                links.append({"label": f"Source footage: {LORAS_CREDITS[credit][0]}", "url": LORAS_CREDITS[credit][1]})

            wiring = []
            for kind, fname in dict.fromkeys(loads):
                if kind == "LoadVideo":
                    tag = "Guide video" if main["loras"][0][2] else "Video"
                elif lo["id"] == "layout":
                    tag = "Look still"
                elif fname.startswith("ingredient_"):
                    tag = "Reference sheet"
                else:
                    tag = "Start image"
                wiring.append({"tag": tag, "ref": ref_for(fname)})
            if lo["id"] == "hdr":
                wiring.append({"tag": "Scene embedding",
                               "text": "ltx-2.5-22b-ic-lora-sdr-to-hdr-scene-emb.safetensors, in place of a prompt"})

            from_video = any(k == "LoadVideo" for k, _ in loads)

            # Everything needed to rerun this test, in one zip, plus the same list for the page.
            graphs = [main["graph"]] + [runs[r]["graph"] for r in control_runs]
            models = loras_models(graphs, names)
            needs_pack = any(nd["class_type"] in LORAS_PACK_CLASSES for g in graphs for nd in g.values())
            input_files = list(dict.fromkeys(f for _, f in loads))
            wf_files = [f"{pslug}.json"] + [f"{pslug}-no-lora.json" for _ in control_runs]
            took = and_list(f"{runs[r]['minutes']:.0f} min" for r in lora_runs)
            ran = (f"An RTX 3060 with 12GB, i5-13400F and 32GB RAM. Generated in {took}"
                   + (f", peak VRAM {main['vram']:.1f} GiB" if main["vram"] else "") + ".")
            readme = loras_readme(title, f"https://loopforge.cc/projects/{slug}/{pslug}/", wf_files, input_files,
                                  models, needs_pack, ran)
            zip_path = wf_dir / "bundles" / f"{pslug}.zip"
            write_zip(zip_path, [(f, (wf_dir / f).read_bytes()) for f in wf_files]
                      + [(f, (in_dir / f).read_bytes()) for f in input_files]
                      + [("README.txt", readme.encode("utf-8"))])
            run_it = {
                "bundle": {"url": f"/assets/workflows/{slug}/bundles/{pslug}.zip", "bytes": zip_path.stat().st_size},
                "models": models,
                "pack": {"name": LORAS_PACK[0], "commit": LORAS_PACK[1][:7], "url": LORAS_PACK[2]} if needs_pack else None,
                "comfy": LORAS_COMFY,
            }
            p = {
                "slug": pslug,
                "title": title,
                "code": "Works" if good else "Limit",
                "group": lo["id"],
                "still": lora_still or outputs[-1]["image"],
                "outputs": outputs,
                "workflow": workflow,
                "models": ["LTX 2.5"],
                "techniques": ["Video to video" if from_video else "Image to video", "LoRA", group_title],
                "facts": facts,
                "refs": wiring,
                "variants": variants,
                "verdict": {"winner": None, "label": "Works" if good else "Limit", "text": verdict},
                "notes": notes,
                "links": links,
                "run_it": run_it,
            }
            if LORAS_VIDEO:
                p["time"] = LORAS_CHAPTERS[len(prompts)]
            prompts.append(p)
    assert len(prompts) == len(LORAS_CHAPTERS)
    assert len({p["slug"] for p in prompts}) == len(prompts)

    # Hero and card were made by hand in the video project: a text-free strip of five LoRA results, and the
    # recommended YouTube thumbnail as the card until the video is up. Copied, never regenerated.
    site = video / "site"
    out = IMG / slug
    for name in ("banner.jpg", "banner-t.jpg", "card.jpg"):
        (out / name).write_bytes((site / name).read_bytes())
    bw, bh = Image.open(site / "banner.jpg").size
    banner_img = {"src": f"img/{slug}/banner.jpg", "thumb": f"img/{slug}/banner-t.jpg", "w": bw, "h": bh}

    # The project page's "Run it yourself": every model any test loads, and what each one is for.
    all_models = {}
    for pr in prompts:
        for m in pr["run_it"]["models"]:
            all_models.setdefault(m["file"], dict(m, used=0))["used"] += 1
    order = ["diffusion_models", "text_encoders", "vae", "latent_upscale_models", "loras", "embeddings"]
    ic = sum("-ic-lora-" in f for f in names)
    col = {
        "slug": slug,
        "title": "LTX 2.5 Creative Lab LoRAs, tested locally",
        "short": "Fourteen LoRAs and three chains",
        "published": "2026-10-09",
        "models": ["LTX 2.5"],
        "summary": [
            "Lightricks has released a set of official LoRAs for LTX 2.5 that add things the base model does not do "
            "on its own, from building a shot out of a reference sheet to colouring a black-and-white film. I ran "
            f"{len(names)} of them in ComfyUI on my own desktop, plus three tests that chain two LoRAs in one "
            "generation.",
            f"Each test has a frame from every clip in it, the exact prompt, the workflow that ran and the inputs it "
            f"was given. {works} of the {works + limits} tests worked, and the other {limits} show where a LoRA "
            "reached its limit.",
        ],
        "facts": [
            ["Base model", "LTX 2.5 22B distilled, int8 (ltx-2.5-22b-distilled-transformer-comfy-int8-convrot)"],
            ["Text encoder", "gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot"],
            ["LoRAs", f"{len(names)} official Lightricks LoRAs, of which {ic} are IC-LoRAs guided by a video or an "
                      "image"],
            ["Clips", "About 5 seconds each, mostly 121 frames at 24fps, at each LoRA's trained size or the "
                      "largest size that worked"],
            ["Render times", f"{min(minutes):.0f} to {max(minutes):.0f} minutes per clip"],
            ["Ran on", "My RTX 3060 with 12GB, i5-13400F, 32GB RAM, PyTorch on CUDA 13"],
        ],
        "groups": groups,
        "refs_title": "Inputs",
        "refs": list(refs.values()),
        "links": [
            {"label": "LTX 2.5 on Hugging Face", "url": "https://huggingface.co/Lightricks/LTX-2.5"},
            {"label": "ComfyUI-LTXVideo, the LTX nodes and the official workflows",
             "url": "https://github.com/Lightricks/ComfyUI-LTXVideo"},
            {"label": "ComfyUI", "url": "https://github.com/comfyanonymous/ComfyUI"},
        ] + [{"label": f"Footage: {label}", "url": url} for label, url in LORAS_CREDITS.values()],
        "prompts": prompts,
        "banner": banner_img,
        "og_image": f"img/{slug}/card.jpg",
        "findings_last": True,  # the user wants "What we found" at the bottom of this page
        "run_it": {
            "paragraphs": [
                "Every test page has a zip with its workflow, every input it loads and a README listing the "
                "models it needs. Unzip it, copy the inputs into ComfyUI/input, put the models in the folders "
                "shown below and drag the workflow onto ComfyUI.",
                "The workflows are in ComfyUI's API format, exactly as they ran. The ComfyUI frontend I used, "
                "1.53.6, opens API files by drag and drop and lays the nodes out itself, so the graphs look plain "
                "but run the same.",
                "The Lightricks repositories on Hugging Face, the LTX 2.5 base model and every LoRA, are gated. Log in, open each repository page and "
                "accept its terms before downloading, or the links return an error.",
                f"I ran everything on an RTX 3060 with 12GB of VRAM, an i5-13400F and 32GB of RAM. Peak VRAM "
                f"across the tests was {min(vram_seen):.1f} to {max(vram_seen):.1f} GiB and each clip took "
                f"{min(minutes):.0f} to {max(minutes):.0f} minutes.",
            ],
            "software": [
                {"label": LORAS_COMFY, "url": "https://github.com/comfyanonymous/ComfyUI"},
                {"label": f"{LORAS_PACK[0]} at commit {LORAS_PACK[1][:7]}, for the tests that use its nodes",
                 "url": LORAS_PACK[2]},
            ],
            "models": sorted(all_models.values(), key=lambda m: (order.index(m["folder"]), m["file"])),
        },
    }
    if LORAS_VIDEO:
        col["video"] = LORAS_VIDEO
    write(col)


IMPORTERS = {"shots": import_shots, "chained": import_chained, "firstdate": import_first_date,
             "ltx": import_ltx, "turbo": import_turbo,
             "higgsfield": import_higgsfield, "loras": import_loras}

if __name__ == "__main__":
    for name in sys.argv[1:] or IMPORTERS:
        IMPORTERS[name]()
