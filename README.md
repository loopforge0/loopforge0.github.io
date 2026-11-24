# loopforge.cc

The Loop Forge hub site, served at **https://loopforge.cc** from GitHub Pages.

## Building

```sh
python tools/build.py           # index, projects/**, 404, sitemap, robots, llms.txt
python tools/build_shootout.py  # /projects/video-upscaler/ (must run after build.py)
python tools/build_gta6.py      # /projects/gta6-style/ (must run after build.py)
python tools/check.py           # every prompt reads back exactly, every local link resolves
```

Everything at the repository root is generated. Edit `content/` or `tools/`, never
the built HTML.

`tools/build.py` clears and rewrites `projects/` and `sitemap.xml` on every run, and
the video-upscaler page lives *inside* `projects/`, so `tools/build_shootout.py` must
go second. Running `build.py` alone leaves the projects index pointing at nothing;
`tools/check.py` reports that as a broken link rather than letting it ship.

## Standalone pages

`/projects/gta6-style/` is a prompt builder plus a 37-image showcase. Its content, images and
`assets/gta6-style/gta6_prompt.js` (a port of the ComfyUI nodes, parity-tested) come from
`next-video-research/gta6-tests/build_site_content.py`; the page's own `gta6.js`/`gta6.css` live here.

If `../h3-upscaling` isn't on the machine, `build.py` still wipes `projects/video-upscaler/workflows/`;
restore it with `git checkout -- projects/video-upscaler/workflows` before committing.

`/projects/video-upscaler/` is not a prompt collection, so it does not fit build.py's
project generator. It is a comparison player over 83 video clips with the
workflows, models and measurements behind them, and it has its own builder,
stylesheet and script. It is listed in `EXTRA_PAGES` in `tools/build.py` so the
projects index and the sitemap link to it.

Its clips are **not in this repository** — they are about 550 MB, served from
Cloudflare R2 at `media.loopforge.cc`. The content file
(`content/video-upscaler.json`) is generated in the experiment repository by
`scripts/build_site_content.py`; see `docs/PUBLISHING.md` there for the full
pipeline, including the R2 setup and the upload script.
