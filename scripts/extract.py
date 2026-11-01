"""Collect readable public article bodies for -30-.

Article discovery and extraction happen in the same publishing run. Never
misrepresent a blocked or truncated article as complete.
"""
import concurrent.futures
import datetime
from email.utils import parsedate_to_datetime
import html
import json
import pathlib
import re
import urllib.request
import urllib.parse
import urllib.error
import time
from html.parser import HTMLParser

import trafilatura

ROOT = pathlib.Path(".")
catalog = ROOT / "articles.json"
status_path = ROOT / "extraction-status.json"
try:
    statuses = json.loads(status_path.read_text())
except (OSError, ValueError):
    statuses = {}
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
def publication_time(a):
    try:
        return parsedate_to_datetime(a.get("date") or "").timestamp()
    except Exception:
        try:
            return datetime.datetime.fromisoformat(a.get("date") or "").timestamp()
        except Exception:
            return 0
pending.sort(key=publication_time, reverse=True)

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
    if len(body.strip()) >= 300:
        return body.strip(), "trafilatura"
    parser = Paragraphs()
    try:
        parser.feed(raw)
    except Exception:
        pass
    fallback = "\n\n".join(dict.fromkeys(parser.parts))
    if len(fallback) >= 350 and len(parser.parts) >= 2:
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
        if len(text) < 300:
            return url, None, method
        return url, {
            "title": a.get("title", ""),
            "source": a.get("source", ""),
            "author": a.get("author", ""),
            "text": text[:90000],
        }, method
    except Exception as error:
        return url, None, type(error).__name__

# Persistent per-URL retry state avoids exhausting each run on the same failures.
# Refresh batches cover sources fairly, rather than biasing toward RSS order.
now = int(time.time())
eligible = [a for a in pending if statuses.get(a["url"], {}).get("retry_after", 0) <= now]
by_source = {}
for a in eligible:
    by_source.setdefault(a.get("source", ""), []).append(a)
for group in by_source.values():
    group.sort(key=publication_time, reverse=True)
todo = []
while by_source and len(todo) < 120:
    for source in list(by_source):
        if by_source[source]:
            todo.append(by_source[source].pop(0))
        if not by_source[source]:
            del by_source[source]
        if len(todo) >= 120:
            break

outcomes = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    for url, article, method in pool.map(fetch, todo):
        outcomes[method] = outcomes.get(method, 0) + 1
        if article:
            existing[url] = article
            statuses[url] = {"status": "ready", "method": method, "updated": now}
        else:
            old = statuses.get(url, {})
            attempts = old.get("attempts", 0) + 1
            # Retry transient failures more quickly, slow down persistent failures.
            delay = min(86400, 900 * 2 ** min(attempts - 1, 7))
            statuses[url] = {"status": method, "attempts": attempts,
                             "updated": now, "retry_after": now + delay}

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
# Keep diagnostics bounded to currently known URLs, including successful ones.
statuses = {u: v for u, v in statuses.items() if u in items}
status_path.write_text(json.dumps(statuses, ensure_ascii=False))
print("Readable articles:", len(existing), "attempted:", len(todo),
      "pending:", len(pending), "eligible:", len(eligible), "extraction outcomes:", outcomes, flush=True)
