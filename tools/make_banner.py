"""Cut the home page banner: a short silent loop with a few seconds from each video.

    python tools/make_banner.py

Writes assets/banner/reel.mp4 (H.264; a VP9 WebM came out larger, so there is none) and assets/banner/reel-poster.jpg
(the first frame, shown before the video loads and to anyone who prefers reduced motion). Like the importer,
it reads the project folders the clips were rendered in, so it runs on the machine that made them.
Edit SEGMENTS to change what is in the reel; keep each piece landscape.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOS = ROOT.parent
OUT = ROOT / "assets" / "banner"
SHOTS = REPOS / "ytideas" / "h3-shot-library" / "tests" / "results" / "runpod"
PART2 = REPOS / "h3-shots-2" / "assets" / "clips"   # camera shots, Part 2 (October 2026)

# (clip, start seconds). Every piece runs SEGMENT seconds. Since Part 2 the reel is all camera shots,
# each cut at the point its move happens; the earlier mix of projects is in git history.
SEGMENTS = [
    (PART2 / "rooftop-swing.mp4", 0.3),      # the swing off the ledge
    (PART2 / "fisheye.mp4", 2.6),            # the push into the fisheye
    (PART2 / "jib-up.mp4", 2.5),             # rising over her in the temple
    (PART2 / "hero-spin.mp4", 1.5),          # the low orbit on Mars
    (PART2 / "slow-pan-reveal.mp4", 2.6),    # the pan finding her in the loft
    (PART2 / "fpv-drone.mp4", 2.5),          # the dive onto the pier
    (PART2 / "tilt-up-reveal.mp4", 2.6),     # the tilt up to her face
    (PART2 / "time-lapse.mp4", 1.0),         # the street in time-lapse
]
SEGMENT = 2.5
FADE = 0.4
W, H, FPS = 1280, 720, 24


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    inputs, chains = [], []
    for i, (clip, start) in enumerate(SEGMENTS):
        inputs += ["-ss", str(start), "-t", str(SEGMENT), "-i", str(clip)]
        chains.append(f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
                      f"setsar=1,format=yuv420p,trim=duration={SEGMENT},setpts=PTS-STARTPTS[s{i}]")
    # Crossfade each piece into the next.
    last, offset = "s0", SEGMENT - FADE
    for i in range(1, len(SEGMENTS)):
        chains.append(f"[{last}][s{i}]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[x{i}]")
        last, offset = f"x{i}", offset + SEGMENT - FADE
    graph = ";".join(chains)

    base = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", f"[{last}]", "-an"]
    subprocess.run(base + ["-c:v", "libx264", "-preset", "slow", "-crf", "30", "-movflags", "+faststart",
                           str(OUT / "reel.mp4")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(OUT / "reel.mp4"), "-frames:v", "1", "-q:v", "3",
                    str(OUT / "reel-poster.jpg")], check=True)
    for f in ("reel.mp4", "reel-poster.jpg"):
        print(f"{f}: {(OUT / f).stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
