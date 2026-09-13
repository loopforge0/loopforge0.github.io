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

# (clip, start seconds). Every piece runs SEGMENT seconds.
SEGMENTS = [
    (SHOTS / "C-02.mp4", 0.0),                                                  # camera shots: whip pan
    (REPOS / "h3-walking" / "runpod" / "out" / "shot-07.mp4", 7.0),             # chained renders: clock tower
    (REPOS / "ltxminimaxcomparison" / "clips-manual" / "MiniMax_clip3_.mp4", 1.0),  # H3 vs LTX: waterfall
    (SHOTS / "C-08.mp4", 3.0),                                                  # camera shots: yo-yo zoom
    (REPOS / "local-director" / "firstdate-video" / "share" / "clips" / "s2_00_c1.mp4", 1.5),  # First Date
    (REPOS / "ltxminimaxcomparison" / "clips-manual" / "LTX-clip5_.mp4", 1.5),  # H3 vs LTX: truck
    (SHOTS / "K-06n.mp4", 1.0),                                                 # camera shots: stage
    (REPOS / "ltxminimaxcomparison" / "clips-manual" / "MiniMax_clip4_.mp4", 2.5),  # H3 vs LTX: dog
    (REPOS / "h3-walking" / "runpod" / "out" / "shot-04.mp4", 5.5),             # chained renders: selfie
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
