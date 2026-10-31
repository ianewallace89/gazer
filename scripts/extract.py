"""Collect readable public article bodies for -30-.

Article discovery and extraction happen in the same publishing run. Never
misrepresent a blocked or truncated article as complete.
"""
import concurrent.futures
import datetime
import html
import json
import pathlib
import re
import urllib.request
from html.parser import HTMLParser

import trafilatura

ROOT = pathlib.Path(".")
catalog = ROOT / "articles.json"
try:
    existing = json.loads(catalog.read_text())
except (OSError, ValueError):
    existing = {}
sections = json.loads((ROOT / "headlines.json").read_text())["sections"]

# Insert newest articles first while deduplicating URLs across sections.
items = {}
for articles in sections.values():
    for item in articles:
        url = item.get("url", "")
        if url.startswith("https://") and item.get("source") != "NYT":
            items[url] = item
pending = [a for url, a in items.items() if not existing.get(url, {}).get("text")]
pending.sort(key=lambda a: a.get("date") or "", reverse=True)

class Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.chunk, self.in_p, self.blocked = [], [], False, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header", "aside", "form"):
            self.blocked += 1
        if tag == "p" and not self.blocked:
            self.chunk, self.in_p = [], True

    def handle_endtag(self, tag):
        if tag == "p" and self.in_p:
            p = " ".join("".join(self.chunk).split())
            if len(p) > 45 and not re.search(
                r"cookie policy|subscribe to|sign up for|all rights reserved", p, re.I
            ):
                self.parts.append(p)
            self.in_p = False
        if tag in ("script", "style", "nav", "footer", "header", "aside", "form") and self.blocked:
            self.blocked -= 1

    def handle_data(self, data):
        if self.in_p and not self.blocked:
            self.chunk.append(data)

def get_text(raw):
    # Trafilatura identifies the actual article body, excluding navigation,
    # related stories, and subscription prompts far more reliably than <p> tags.
    try:
        body = trafilatura.extract(
            raw, include_comments=False, include_tables=False,
            favor_recall=True, output_format="txt"
        ) or ""
    except Exception:
        body = ""
    if len(body.strip()) >= 450:
        return body.strip(), "trafilatura"
    parser = Paragraphs()
    try:
        parser.feed(raw)
    except Exception:
        pass
    fallback = "\n\n".join(dict.fromkeys(parser.parts))
    if len(fallback) >= 500 and len(parser.parts) >= 3:
        return fallback, "paragraphs"
    return "", "insufficient_text"

def fetch(a):
    url = a["url"]
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml"
        })
        with urllib.request.urlopen(req, timeout=13) as res:
            if "html" not in res.headers.get("Content-Type", "").lower():
                return url, None, "non_html"
            raw = res.read(1100000).decode("utf-8", "replace")
        text, method = get_text(raw)
        if len(text) < 450:
            return url, None, method
        return url, {
            "title": a.get("title", ""),
            "source": a.get("source", ""),
            "author": a.get("author", ""),
            "text": text[:90000],
        }, method
    except Exception as error:
        return url, None, type(error).__name__

# Prioritize new articles, then circulate through older failures so that a
# few inaccessible publishers cannot monopolize extraction capacity.
batch_size = 100
priority_count = min(65, len(pending))
recent = pending[:priority_count]
older = pending[priority_count:]
slot = int(datetime.datetime.now(datetime.timezone.utc).timestamp() // 900)
offset = (slot * (batch_size - priority_count)) % len(older) if older else 0
todo = (recent + (older[offset:] + older[:offset])[:batch_size-priority_count])

outcomes = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    for url, article, method in pool.map(fetch, todo):
        outcomes[method] = outcomes.get(method, 0) + 1
        if article:
            existing[url] = article

for url, article in existing.items():
    feed = items.get(url)
    if feed and feed.get("author") and not article.get("author"):
        article["author"] = feed["author"]

# Retain readable articles still in the current feed, then recent older ones.
# Keep enough history to cover the expanded source list.
if len(existing) > 1400:
    active = {u: a for u, a in existing.items() if u in items}
    archived = [(u, a) for u, a in existing.items() if u not in items]
    existing = dict((archived[-max(0, 1400-len(active)):] if len(active) < 1400 else []) + list(active.items()))

catalog.write_text(json.dumps(existing, ensure_ascii=False))
print("Readable articles:", len(existing), "attempted:", len(todo),
      "pending:", len(pending), "extraction outcomes:", outcomes, flush=True)
