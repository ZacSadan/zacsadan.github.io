#!/usr/bin/env python3
"""Static site builder.

    content/<lang>/data/*.yml   structured data (profile, publications, CV ...)
    content/<lang>/pages/**.md  pages: YAML front matter + Markdown body
    content/assets/             images and files (shared by all languages)
    theme/templates/*.html      Jinja2 templates (one per `layout`)
    theme/static/               CSS / JS / fonts of the theme

Usage:
    python build.py              # build into _site/
    python build.py --serve      # build and serve on http://localhost:8000
"""
from __future__ import annotations

import argparse
import datetime as dt
import functools
import http.server
import shutil
import sys
from pathlib import Path

import markdown
import yaml
from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def split_front_matter(text: str):
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        return yaml.safe_load(fm) or {}, body.strip()
    return {}, text


def md_to_html(text: str) -> Markup:
    return Markup(markdown.markdown(
        text or "", extensions=["extra", "sane_lists", "smarty"],
        output_format="html5"))


def page_url(rel: Path) -> str:
    """pages/research.md -> research/ ; pages/teaching/x/index.md -> teaching/x/"""
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "index":
        parts = parts[:-1]
    return "/".join(parts) + "/" if parts else ""


class Builder:
    def __init__(self):
        self.config = load_yaml(ROOT / "config.yml")
        theme = ROOT / self.config.get("theme", "theme")
        self.theme = theme
        self.env = Environment(
            loader=FileSystemLoader(theme / "templates"),
            autoescape=select_autoescape(["html"]),
            undefined=ChainableUndefined,   # optional data fields may be omitted
            trim_blocks=True, lstrip_blocks=True)
        self.env.filters["md"] = md_to_html
        # Escape an author list and bold the site owner's name in it.
        self.env.filters["highlight"] = lambda text, me: Markup(
            str(Markup.escape(text)).replace(str(Markup.escape(me)),
                                             f"<strong>{Markup.escape(me)}</strong>"))
        self.env.filters["mdinline"] = lambda s: Markup(
            str(md_to_html(s)).removeprefix("<p>").removesuffix("</p>"))
        self.built: list[str] = []

    # -------------------------------------------------------------- content
    def load_language(self, lang: dict):
        base = ROOT / "content" / lang["code"]
        data = {p.stem: load_yaml(p) for p in sorted((base / "data").glob("*.yml"))}
        pages = []
        for path in sorted((base / "pages").rglob("*.md")):
            rel = path.relative_to(base / "pages")
            meta, body = split_front_matter(path.read_text(encoding="utf-8"))
            meta.setdefault("layout", "page")
            meta.setdefault("title", "")
            pages.append({**meta, "url": page_url(rel), "src": rel.as_posix(),
                          "body": body, "section": rel.parts[0] if len(rel.parts) > 1 else None})
        return data, pages

    # -------------------------------------------------------------- render
    def build(self):
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir()
        langs = self.config["languages"]
        for i, lang in enumerate(langs):
            prefix = "" if i == 0 else lang["code"] + "/"
            self.build_language(lang, prefix, langs)
        shutil.copytree(self.theme / "static", OUT / "theme")
        if (ROOT / "content" / "assets").exists():
            shutil.copytree(ROOT / "content" / "assets", OUT / "assets")
        (OUT / ".nojekyll").write_text("")
        self.write_sitemap()
        print(f"Built {len(self.built)} pages into {OUT}")

    def build_language(self, lang, prefix, langs):
        data, pages = self.load_language(lang)
        by_url = {p["url"]: p for p in pages}
        today = dt.date.today()

        def children_of(url):
            if not url:
                return []
            return sorted(
                (p for p in pages if p["url"] != url and p["url"].startswith(url)
                 and p["url"][len(url):].count("/") == 1),
                key=lambda p: (p.get("order", 0), str(p.get("year", "")), p["title"]))

        def parent_of(url):
            if not url:
                return None
            up = "/".join(url.rstrip("/").split("/")[:-1])
            return by_url.get(up + "/" if up else "")

        for page in pages:
            out_rel = prefix + page["url"]
            depth = out_rel.count("/")
            root = "../" * depth                      # to site root (assets, theme)
            if page["layout"] == "404":               # served at any depth
                root = "/"
            home = root + prefix                      # to language root
            ctx = dict(
                config=self.config, lang=lang, languages=langs, data=data,
                site=data.get("site", {}), ui=data.get("ui", {}),
                page=page, pages=pages,
                children=children_of(page["url"]), parent=parent_of(page["url"]),
                children_of=children_of, parent_of=parent_of,
                root=root, home=home, today=today,
                url=lambda p, _h=home: _h + p,
                asset=lambda p, _r=root: _r + "assets/" + p,
                theme_url=lambda p, _r=root: _r + "theme/" + p,
            )
            # Markdown bodies may use {{ url('...') }} / {{ asset('...') }}.
            body = self.env.from_string(page["body"]).render(**ctx)
            ctx["content"] = md_to_html(body)
            html = self.env.get_template(page["layout"] + ".html").render(**ctx)
            dest = OUT / out_rel / "index.html" if out_rel else OUT / "index.html"
            if page["layout"] == "404":
                dest = OUT / (prefix + "404.html")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(html, encoding="utf-8")
            if page["layout"] != "404":
                self.built.append(out_rel)

    def write_sitemap(self):
        base = self.config["base_url"].rstrip("/")
        urls = "\n".join(f"  <url><loc>{base}/{u}</loc></url>" for u in self.built)
        (OUT / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}\n</urlset>\n", encoding="utf-8")
        (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="serve _site on localhost")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    Builder().build()
    if args.serve:
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        print(f"Serving on http://localhost:{args.port}  (Ctrl+C to stop)")
        http.server.ThreadingHTTPServer(("", args.port), handler).serve_forever()


if __name__ == "__main__":
    sys.exit(main())
