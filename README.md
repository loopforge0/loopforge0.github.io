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

## Analytics

[Cloudflare Web Analytics](https://developers.cloudflare.com/web-analytics/) — free, cookieless,
sets nothing on the visitor's device and does not fingerprint, so **no cookie consent banner is
required** under the EU/UK ePrivacy Directive. (GA4 would require one; that is why it is not used.)

The beacon `<script>` sits just above `</body>`. The **same site token** is used across every repo
served under this domain, so `loopforge.cc/` and `loopforge.cc/<repo-name>/` report into one
dashboard rather than showing up as separate properties.

**When adding a page (see above), also paste the beacon block into that repo's HTML**, or its
traffic will be invisible — which matters, since the linked-from-a-video pages are usually the
busiest ones.

The token is generated at Cloudflare dashboard → Analytics & Logs → Web Analytics → Add a site
(`loopforge.cc`). It is a public site identifier, not a secret — it ships in the page source by
design. No DNS change and no Cloudflare proxying needed; the JS beacon works on GitHub Pages as-is.
