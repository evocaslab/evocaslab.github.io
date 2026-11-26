# evocaslab.github.io

The root of <https://docs.evocaslab.com/>: one card per public EvoCAS Lab tool, the published schemas, and links back
to <https://evocaslab.com>. Each tool's own docs are its repo's Pages site at `https://docs.evocaslab.com/<tool>/`.

## Layout

- `tools.json`, `schemas.json`: the data. Generated in the HQ repo from the public registry entries; never edit them
  by hand. Refresh in `~/dev/hq`:

  ```bash
  just docs-site-tools write repos/evocaslab/evocaslab.github.io
  ```

- `build.py`: builds `_site/` (`index.html`, `schemas/`, `404.html`, `robots.txt`, `sitemap.xml`, `llms.txt`) and
  checks every page (meta CSP first in `<head>`, `rel=canonical`, no inline script or style, no third-party resource).
  Standard library only. Locally:

  ```bash
  python3 build.py && python3 -m http.server -d _site 8000
  ```

- `static/style.css`: the only stylesheet; system fonts, light and dark.
- `.github/workflows/pages.yml`: builds on every push and pull request, deploys from `main` (Pages source "GitHub
  Actions").

Schema URLs are `https://schemas.evocaslab.com/<tool>/<format>/<major>.<minor>.json`: a Cloudflare redirect to the file
at the tag `schema/<format>/<major>.<minor>` in the tool's repo. A published URL never changes.
