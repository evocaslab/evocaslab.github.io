#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Build the docs.evocaslab.com root site from tools.json and schemas.json, then check it.

Usage:
    python3 build.py [--out _site]      build into OUT and run the checks (CI: .github/workflows/pages.yml)
    python3 build.py --check-only DIR   only check an already built DIR

Standard library only, no network. tools.json and schemas.json are generated in the HQ repo
(`just docs-site-tools write`) from the public registry entries; never edit them by hand.

Every page gets the same meta Content-Security-Policy first in <head> (GitHub Pages cannot send headers) and a
rel=canonical on https://docs.evocaslab.com. The check fails on a page without them, on any <script>, <style> or
style= attribute, and on a resource (src=, <link href=) that is not served from this site.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
HOST = "https://docs.evocaslab.com"
LAB = "https://evocaslab.com"
SCHEMA_HOST = "https://schemas.evocaslab.com"
CSP = (
    "default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; "
    "upgrade-insecure-requests"
)


@dataclass(frozen=True)
class Page:
    path: str  # URL path, e.g. "/" or "/schemas/"
    file: str  # file under OUT
    title: str
    description: str
    body: str
    nav: str | None = None  # which nav entry is current
    index: bool = True  # false: noindex, not in the sitemap


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def https(url: object) -> str | None:
    """An https URL from the data, else None (a value that is not one never reaches an href)."""
    return url if isinstance(url, str) and url.startswith("https://") and '"' not in url else None


def layout(page: Page) -> str:
    def nav_link(key: str, href: str, label: str) -> str:
        current = ' aria-current="page"' if page.nav == key else ""
        return f'<li><a href="{href}"{current}>{label}</a></li>'

    robots = "" if page.index else '\n<meta name="robots" content="noindex">'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="color-scheme" content="light dark">
<title>{esc(page.title)}</title>
<meta name="description" content="{esc(page.description)}">{robots}
<link rel="canonical" href="{HOST}{page.path}">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-header">
<a class="lab" href="{LAB}">EvoCAS Lab</a>
<nav aria-label="Site">
<ul>
{nav_link("tools", "/", "Tools")}
{nav_link("schemas", "/schemas/", "Schemas")}
<li><a href="https://github.com/evocaslab">GitHub</a></li>
</ul>
</nav>
</header>
<main id="main">
{page.body}
</main>
<footer class="site-footer">
<p><a href="{LAB}">evocaslab.com</a> · Docs for the EvoCAS Lab public tools ·
<a href="/llms.txt">llms.txt</a> · <a href="https://github.com/evocaslab/evocaslab.github.io">Source</a></p>
</footer>
</body>
</html>
"""


def tool_card(tool: dict[str, Any]) -> str:
    name = esc(tool["name"])
    links: list[str] = []
    if guide := https(tool.get("guide")):
        links.append(f'<li><a href="{esc(guide)}">Guide</a></li>')
    if brand := https(tool.get("brand_book")):
        links.append(f'<li><a href="{esc(brand)}">Brand book</a></li>')
    count = int(tool.get("schemas") or 0)
    if count:
        noun = "schema" if count == 1 else "schemas"
        links.append(f'<li><a href="/schemas/#{name}">{count} {noun}</a></li>')
    if repo := https(tool.get("repo")):
        links.append(f'<li><a href="{esc(repo)}">Source on GitHub</a></li>')
    tags = "".join(f"<li>{esc(t)}</li>" for t in tool.get("tags") or [])
    tag_list = f'\n<ul class="tags" aria-label="Topics">{tags}</ul>' if tags else ""
    return f"""<article class="tool-card" id="{name}" aria-labelledby="{name}-title">
<h2 id="{name}-title">{name}</h2>
<p>{esc(tool["description"])}</p>
<ul class="links" aria-label="{name} links">{"".join(links)}</ul>{tag_list}
</article>"""


def index_page(tools: list[dict[str, Any]]) -> Page:
    cards = "\n".join(tool_card(t) for t in tools) or "<p>No public tool yet.</p>"
    body = f"""<h1>EvoCAS Lab docs</h1>
<p class="lead">Guides, brand books and file-format schemas for the public tools of
<a href="{LAB}">EvoCAS Lab</a>. Each tool's own docs live at <code>docs.evocaslab.com/&lt;tool&gt;/</code>.</p>
<section class="tools" aria-label="Tools">
{cards}
</section>"""
    return Page("/", "index.html", "EvoCAS Lab docs", "Docs for the EvoCAS Lab public tools.", body, nav="tools")


def schemas_page(tools: list[dict[str, Any]], schemas: list[dict[str, Any]]) -> Page:
    groups: list[str] = []
    for tool in tools:
        rows = [s for s in schemas if s.get("tool") == tool["name"]]
        if not rows:
            continue
        name = esc(tool["name"])
        items = "\n".join(
            f'<tr><td>{esc(s["name"])}</td><td>{esc(s["version"])}</td>'
            f'<td><a href="{esc(https(s.get("url")) or "")}"><code>{esc(s["url"])}</code></a></td>'
            f'<td><a href="{esc(https(s.get("source")) or "")}">tagged file</a></td></tr>'
            for s in rows
        )
        groups.append(f"""<section id="{name}" aria-labelledby="{name}-schemas">
<h2 id="{name}-schemas">{name}</h2>
<table>
<thead><tr><th scope="col">Format</th><th scope="col">Version</th><th scope="col">Schema URL</th>
<th scope="col">Source</th></tr></thead>
<tbody>
{items}
</tbody>
</table>
</section>""")
    listing = "\n".join(groups) or '<p class="empty">No schema is published yet. The first one appears here when a tool tags it.</p>'
    body = f"""<h1>Schemas</h1>
<p class="lead">JSON Schemas (dialect 2020-12) for the file formats of the EvoCAS Lab tools, for editors and validators.</p>
<h2>How the versions work</h2>
<ul class="rules">
<li>Every schema has one URL per version, which is also its <code>$id</code>:
<code>{SCHEMA_HOST}/&lt;tool&gt;/&lt;format&gt;/&lt;major&gt;.&lt;minor&gt;.json</code>.</li>
<li>A published URL never changes. It redirects to the file at the git tag
<code>schema/&lt;format&gt;/&lt;major&gt;.&lt;minor&gt;</code> in the tool's repo; a tag is never moved or deleted.</li>
<li>A file names its format and major version in a top-level key, for example <code>format: brand/1</code>.
The format version is independent of the tool's own version.</li>
<li>A new minor only adds: a new optional key or value. Anything that makes a valid old file invalid or changes its
meaning is a new major; tools refuse a newer major and read older ones through <code>migrate</code>.</li>
</ul>
<h2>Published schemas</h2>
{listing}"""
    return Page(
        "/schemas/",
        "schemas/index.html",
        "Schemas · EvoCAS Lab docs",
        "Versioned JSON Schemas of the EvoCAS Lab tools and the rule for their URLs.",
        body,
        nav="schemas",
    )


def not_found_page() -> Page:
    body = """<h1>Page not found</h1>
<p>This address has no page. The <a href="/">list of tools</a> links to every tool's docs, and
<a href="/schemas/">Schemas</a> lists the published file formats.</p>"""
    return Page("/404.html", "404.html", "Not found · EvoCAS Lab docs", "Page not found.", body, index=False)


def sitemap(pages: list[Page], tools: list[dict[str, Any]]) -> str:
    urls = [f"{HOST}{p.path}" for p in pages if p.index]
    urls += [g for t in tools if (g := https(t.get("guide"))) and g.startswith(HOST + "/")]
    entries = "\n".join(f"  <url><loc>{esc(u)}</loc></url>" for u in urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{entries}\n</urlset>\n"
    )


def llms_txt(tools: list[dict[str, Any]], schemas: list[dict[str, Any]]) -> str:
    lines = [
        "# EvoCAS Lab docs",
        "",
        "> Docs for the public tools of EvoCAS Lab (https://evocaslab.com): one guide per tool at "
        "https://docs.evocaslab.com/<tool>/, brand books, and versioned JSON Schemas at "
        "https://schemas.evocaslab.com/<tool>/<format>/<major>.<minor>.json (immutable, one git tag each).",
        "",
        "## Tools",
        "",
    ]
    for tool in tools:
        target = https(tool.get("guide")) or https(tool.get("repo")) or HOST + "/"
        lines.append(f"- [{tool['name']}]({target}): {tool['description']}")
    lines += ["", "## Schemas", ""]
    lines += [f"- [{s['tool']} {s['name']} {s['version']}]({s['url']})" for s in schemas] or [
        f"- [Schemas page]({HOST}/schemas/): none published yet",
    ]
    return "\n".join(lines) + "\n"


def robots_txt() -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {HOST}/sitemap.xml\n"


def build(out: Path) -> None:
    tools: list[dict[str, Any]] = json.loads((HERE / "tools.json").read_text(encoding="utf-8"))
    schemas: list[dict[str, Any]] = json.loads((HERE / "schemas.json").read_text(encoding="utf-8"))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    pages = [index_page(tools), schemas_page(tools, schemas), not_found_page()]
    for page in pages:
        target = out / page.file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(layout(page), encoding="utf-8")
    shutil.copy(HERE / "static" / "style.css", out / "style.css")
    shutil.copy(HERE / "CNAME", out / "CNAME")
    (out / "robots.txt").write_text(robots_txt(), encoding="utf-8")
    (out / "sitemap.xml").write_text(sitemap(pages, tools), encoding="utf-8")
    (out / "llms.txt").write_text(llms_txt(tools, schemas), encoding="utf-8")


_HEAD_FIRST = re.compile(r"<head>\s*<meta http-equiv=\"Content-Security-Policy\" content=\"([^\"]*)\">")
_CANONICAL = re.compile(r'<link rel="canonical" href="https://docs\.evocaslab\.com/[^"]*">')
_RESOURCE = re.compile(r'\ssrc="([^"]*)"|<link\s(?![^>]*rel="canonical")[^>]*href="([^"]*)"')


def check(out: Path) -> list[str]:
    problems: list[str] = []
    pages = sorted(out.rglob("*.html"))
    if not pages:
        problems.append(f"{out}: no HTML page")
    for page in pages:
        where = page.relative_to(out)
        text = page.read_text(encoding="utf-8")
        head = _HEAD_FIRST.search(text)
        if not head or head.group(1) != CSP:
            problems.append(f"{where}: the CSP meta tag is missing, changed or not first in <head>")
        if not _CANONICAL.search(text):
            problems.append(f"{where}: no rel=canonical on {HOST}")
        if re.search(r"<script|<style|\sstyle=|\son[a-z]+=", text, re.IGNORECASE):
            problems.append(f"{where}: inline script, style or event handler")
        for m in _RESOURCE.finditer(text):
            url = m.group(1) or m.group(2)
            if not url.startswith("/") or url.startswith("//"):
                problems.append(f"{where}: resource {url} is not served from this site")
    for name in ("404.html", "robots.txt", "sitemap.xml", "llms.txt", "CNAME"):
        if not (out / name).is_file():
            problems.append(f"{out}: {name} is missing")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=HERE / "_site", help="output directory (default _site)")
    parser.add_argument("--check-only", type=Path, metavar="DIR", help="only check a built site")
    args = parser.parse_args()
    out: Path = args.check_only or args.out
    if args.check_only is None:
        build(out)
    problems = check(out)
    for line in problems:
        print(f"build: {line}", file=sys.stderr)
    if problems:
        return 1
    print(f"build: {out} ok ({len(list(out.rglob('*.html')))} pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
