# loopforge.cc

The Loop Forge hub site. Serves at **https://loopforge.cc** from GitHub Pages.

## Why this repo exists

A GitHub account gets **one** user site (`loopforge0.github.io`), and a custom domain can be
attached to **one** repository. Attaching `loopforge.cc` here rather than to a project repo is
what makes every other path work:

> When a user site has a custom domain, GitHub serves every **project** Pages site owned by the
> same account under that domain, at `<domain>/<repo-name>/`.

So turning Pages on for any repo in this account publishes it at `loopforge.cc/<repo-name>/`
with no further configuration, no redirects and no per-repo DNS.

| Path | Comes from |
| --- | --- |
| `loopforge.cc/` | this repo |
| `loopforge.cc/minimaxh3-shots-skills/` | `loopforge0/minimaxh3-shots-skills` → `/docs` |
| `loopforge.cc/<anything-else>/` | any repo here with Pages turned on |

## Adding a page

1. Turn Pages on for the repo (`main` branch, `/docs` or `/` root).
2. Copy one `<a class="page">` block in `index.html`, change the tone class, href, title,
   blurb and path.

The href is just the repository name. Nothing else needs to change.

## DNS

Apex `loopforge.cc` → four A records and four AAAA records at the GitHub Pages addresses.
`www.loopforge.cc` → CNAME to `loopforge0.github.io`. The `CNAME` file in this repo must keep
matching the domain set in the repository's Pages settings, or GitHub unsets the domain.
