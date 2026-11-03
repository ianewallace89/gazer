"""Public art/visual-culture index entries for Equator and Tablet.

Equator publishes a public article index; Tablet blocks direct automated requests,
so use a public text rendering of its tagged indexes. We extract only metadata
and link readers to the canonical publisher page (never proxy article bodies).
"""
import datetime as dt
import json
import pathlib
from email.utils import parsedate_to_datetime
import html
import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

AGENT = {"User-Agent": "Mozilla/5.0 (compatible; GazerRSS/1.0)"}
ART = re.compile(r"\b(?:arts?|artworld|artforum|artists?|artworks?|aesthetic(?:s)?|sculptur(?:e|es|al)|paintings?|photograph(?:y|ic|s|ers)?|photo\s*essay|museums?|exhibitions?|galler(?:y|ies)|curat(?:or|ors|orial)|visual\s+cultur(?:e|al)|architectur(?:e|al)|surrealis(?:m|t)|modernis(?:m|t)|art\s+world|design|drawings?|printmaking|portraits?|film|cinema)\b", re.I)
MONTHS = {name.lower(): i for i, name in enumerate(('January','February','March','April','May','June','July','August','September','October','November','December'), 1)}

def text_at(url, timeout=20):
    request = urllib.request.Request(url, headers=AGENT)
    with urllib.request.urlopen(request, timeout=timeout, context=SSL_CONTEXT) as response:
        return response.read(7000000).decode('utf-8', 'replace')

def normalize(s):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', s or '')).split())

def key(s):
    return re.sub(r'[^a-z0-9]+', '', s.lower())

def news_dates(query):
    dates = {}
    url = 'https://news.google.com/rss/search?' + urllib.parse.urlencode({'q': query, 'hl':'en-US', 'gl':'US', 'ceid':'US:en'})
    try:
        root = ET.fromstring(text_at(url))
        for item in root.findall('./channel/item'):
            title = (item.findtext('title') or '').rsplit(' - ', 1)[0].strip()
            stamp = parsedate_to_datetime(item.findtext('pubDate') or '')
            dates[key(title)] = stamp.astimezone(dt.timezone.utc).isoformat()
    except Exception as exc:
        print('Magazine date metadata unavailable:', str(exc)[:110], flush=True)
    return dates

def equator():
    listing = text_at('https://www.equator.org/articles')
    dates = news_dates('site:equator.org/articles/ (art OR artist OR photo OR museum OR exhibition OR architecture)')
    records=[]
    for card in re.findall(r'<article\b[^>]*>(.*?)</article>', listing, flags=re.S|re.I):
        link = re.search(r'<a[^>]+href="(/articles/[a-z0-9-]+)"', card, re.I)
        h2 = re.search(r'<h2\b[^>]*>(.*?)</h2>', card, re.I|re.S)
        h3 = re.search(r'<h3\b[^>]*>(.*?)</h3>', card, re.I|re.S)
        h4 = re.search(r'<h4\b[^>]*>(.*?)</h4>', card, re.I|re.S)
        if not all((link, h2, h3, h4)):
            continue
        title = re.sub(r'\s+(Essay|Photo Essay|Photo|Translation|Dispatch|Conversation|Artist Project|Editorial)$', '', normalize(h2[1]))
        author, summary = normalize(h3[1]), normalize(h4[1])
        is_photo_essay = 'Photo Essay' in normalize(h2[1])
        if not title or not author or len(summary)<38 or not (is_photo_essay or ART.search(title+' '+summary)):
            continue
        # Only date articles when an actual publication date is discoverable.
        date=dates.get(key(title), '')
        if not date: continue
        if dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(date) > dt.timedelta(days=365): continue
        records.append({'title':title,'url':'https://www.equator.org'+link[1],
            'summary':summary[:260],'date':date,'source':'Equator','language':'en',
            'author':author,'image':'','tags':['art','visual culture']})
    print('Equator:',len(records),'art-related entries',flush=True)
    return records[:40]

def prior_tablet_dates():
    try:
        sections=json.loads(pathlib.Path('headlines.json').read_text())['sections']
        return {story['url']:story['date'] for story in sections.get('Tablet',[]) if story.get('url') and story.get('date')}
    except (OSError,ValueError,KeyError):
        return {}

def published_at(url):
    try:
        listing=text_at('https://r.jina.ai/'+url,timeout=18)[:2000]
        match=re.search(r'^Published Time: (\d{4}-\d{2}-\d{2}T[^\s]+)', listing, re.M)
        return match[1] if match else ''
    except Exception:
        return ''

def tablet():
    previous=prior_tablet_dates()
    dates=news_dates('site:tabletmag.com/sections/arts-letters/articles (art OR museum OR photography OR painting OR sculpture OR architecture)')
    records={}
    for tag in ('art','architecture','photography'):
        try:
            page=text_at('https://r.jina.ai/https://www.tabletmag.com/tags/'+tag)
        except Exception as exc:
            print('Tablet index unavailable',tag,str(exc)[:110],flush=True)
            continue
        for line in page.splitlines():
            if not line.startswith('*   '):continue
            matches=re.findall(r'\[([^\[\]]{4,180})\]\((https://www\.tabletmag\.com/(?:sections|the-scroll)/[^)]*/articles/[^)]+)\)',line)
            if not matches:continue
            title,link=matches[0]
            summary=next((label for label,u in matches[1:] if u==link), '')
            byline=re.search(r'by\[([^\]]+)\]\(https://www\.tabletmag\.com/contributors/',line)
            issue=re.search(r'\[([A-Z]+) (20\d\d) PRINT EDITION\]',line)
            # Tagged pages include many old stories: use dated entries from the last 18 months.
            if not issue:continue
            month=MONTHS.get(issue[1].lower());year=int(issue[2]);
            if not month:continue
            age=(dt.datetime.now(dt.timezone.utc).year-year)*12+dt.datetime.now(dt.timezone.utc).month-month
            if not 0<=age<=18:continue
            if len(summary)<20 or not (ART.search(title+' '+summary) or tag in ('photography','architecture')):continue
            image_match=re.search(r'!\[Image \d+(?:[^\]]*)\]\((https://tablet-mag-images\.b-cdn\.net/[^)]+)\)',line)
            story={'title':html.unescape(title),'url':link,'summary':html.unescape(summary)[:260],
                'date':dates.get(key(title)) or previous.get(link) or published_at(link) or f'{year:04d}-{month:02d}-01T12:00:00+00:00',
                'source':'Tablet','language':'en','author':html.unescape(byline[1]) if byline else '',
                'image':html.unescape(image_match[1]) if image_match else '',
                'tags':['art',tag]}
            records[link]=story
    print('Tablet:',len(records),'art-related entries',flush=True)
    return sorted(records.values(),key=lambda a:a['date'],reverse=True)[:40]

def magazine_feeds():
    feeds={}
    for name,fn in (('Equator',equator),('Tablet',tablet)):
        try:feeds[name]=fn()
        except Exception as exc:
            print('Magazine fetch error',name,str(exc)[:180],flush=True);feeds[name]=[]
    return feeds