"""Check the built site: every prompt on a page must read back as exactly the text in content/.

    python tools/check.py

The Copy button copies the prompt block's text content, so this is the check that what someone copies is
what the model was given. Also checks that every local link and image resolves to a file.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts, self.refs = [], []
        self._depth = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "pre" and "script" in a.get("class", ""):
            self._depth = 1
            self.scripts.append("")
        elif self._depth:
            self._depth += tag not in ("br", "img")
        for key in ("href", "src"):
            if a.get(key):
                self.refs.append(a[key])

    def handle_endtag(self, tag):
        if self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if self._depth:
            self.scripts[-1] += data


def main():
    problems = 0
    checked = 0
    for col_file in sorted((ROOT / "content").glob("*.json")):
        col = json.loads(col_file.read_text(encoding="utf-8"))
        # site.json, findings.json and the standalone pages are not prompt collections
        if "prompts" not in col:
            continue
        for p in col["prompts"]:
            path = ROOT / "projects" / col["slug"] / p["slug"] / "index.html"
            parser = Page()
            parser.feed(path.read_text(encoding="utf-8"))
            expected = [v["text"] for v in p["variants"]]
            if parser.scripts != expected:
                problems += 1
                print(f"MISMATCH {path.relative_to(ROOT)}")
            checked += len(expected)

    for page in ROOT.glob("**/*.html"):
        if any(part in ("node_modules", "tools", "content") for part in page.parts):
            continue
        parser = Page()
        parser.feed(page.read_text(encoding="utf-8"))
        for ref in parser.refs:
            u = urlparse(ref)
            if u.scheme or u.netloc or not u.path.startswith("/"):
                continue
            target = ROOT / u.path.lstrip("/")
            if u.path.endswith("/"):
                target = target / "index.html"
            if not target.exists():
                problems += 1
                print(f"BROKEN {page.relative_to(ROOT)} -> {ref}")

    print(f"{checked} prompt blocks checked, {problems} problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
