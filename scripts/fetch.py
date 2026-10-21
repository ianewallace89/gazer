import datetime, json, pathlib, urllib.request, urllib.parse, xml.etree.ElementTree as ET, re, html
FEEDS = {
"Top Stories":"HomePage","World":"World","U.S.":"US","Politics":"Politics","New York":"NYRegion",
"Business":"Business","Technology":"Technology","Science":"Science","Health":"Health",
"Arts":"Arts","Books":"Books","Movies":"Movies","Opinion":"Opinion"
}
headers={"User-Agent":"Mozilla/5.0 (compatible; GazerRSS/1.0)"}
EXTRA = {
"The Guardian US":"https://www.theguardian.com/us/rss",
"The Intercept":"https://theintercept.com/feed/?lang=en",
"The Nation":"https://www.thenation.com/feed/?post_type=article",
"Jacobin":"https://jacobin.com/feed/",
"ProPublica":"https://www.propublica.org/feeds/propublica/main",
"In These Times":"https://inthesetimes.com/rss",
"Al Jazeera":"https://www.aljazeera.com/xml/rss/all.xml",
"taz":"https://taz.de/!p4608;rss/",
"Mediapart":"https://www.mediapart.fr/articles/feed",
"L’Humanité":"https://www.humanite.fr/feed",
"Le Monde diplomatique":"https://mondediplo.com/rss/"
}
def author_name(item):
    names=[]
    for element in item.iter():
        tag=element.tag.rsplit("}",1)[-1].lower()
        if tag in ("creator","author"):
            name=" ".join((element.text or element.findtext("{http://www.w3.org/2005/Atom}name") or "").split())
            if name and name not in names: names.append(name)
    return ", ".join(names[:6])
sections={}
for section, slug in FEEDS.items():
    try:
        req=urllib.request.Request(f"https://rss.nytimes.com/services/xml/rss/nyt/{slug}.xml",headers=headers)
        with urllib.request.urlopen(req,timeout=25) as response: xml=response.read()
        root=ET.fromstring(xml)
        stories=[]
        for item in root.findall("./channel/item")[:35]:
            def field(name): return (item.findtext(name) or "").strip()
            link=field("link")
            if not link.startswith("https://www.nytimes.com/"): continue
            summary=re.sub(r"<[^>]+>","",html.unescape(field("description")))
            image=""
            candidates=[]
            for media in item.iter():
                tag=media.tag.rsplit("}",1)[-1].lower()
                if tag not in ("content","thumbnail","enclosure"): continue
                candidate=media.attrib.get("url","").strip()
                host=urllib.parse.urlparse(candidate).hostname or ""
                if candidate.startswith("https://") and (host.endswith(".nytimes.com") or host=="nytimes.com" or host.endswith(".nyt.com")):
                    try: width=int(media.attrib.get("width","0"))
                    except ValueError: width=0
                    candidates.append((width,candidate))
            if candidates: image=max(candidates,key=lambda x:x[0])[1]
            stories.append({"title":field("title"),"url":link,"summary":summary[:260],"date":field("pubDate"),"image":image,"source":"NYT","author":author_name(item)})
        sections[section]=stories
        print(section,len(stories))
    except Exception as exc:
        print("Feed error",section,exc)
        sections[section]=[]
for source,feed_url in EXTRA.items():
    try:
        req=urllib.request.Request(feed_url,headers=headers)
        with urllib.request.urlopen(req,timeout=25) as response: xml=response.read()
        root=ET.fromstring(xml)
        stories=[]
        for item in (root.findall("./channel/item") or root.findall("{http://www.w3.org/2005/Atom}entry"))[:40]:
            def field(name): return (item.findtext(name) or item.findtext("{http://www.w3.org/2005/Atom}"+name) or "").strip()
            link=field("link") or next((el.attrib.get("href","") for el in item.findall("{http://www.w3.org/2005/Atom}link") if el.attrib.get("rel","alternate")=="alternate"),"")
            if not link.startswith("https://"): continue
            raw=html.unescape(field("description") or field("summary") or field("content"))
            summary=re.sub(r"<[^>]+>"," ",raw)
            summary=re.sub(r"\\s+"," ",summary).strip()[:260]
            candidates=[]
            for media in item.iter():
                tag=media.tag.rsplit("}",1)[-1].lower()
                if tag not in ("content","thumbnail","enclosure"): continue
                candidate=media.attrib.get("url","").strip()
                if candidate.startswith("https://") and (media.attrib.get("type","").startswith("image/") or re.search(r"\\.(jpg|jpeg|png|webp)(\\?|$)",candidate,re.I) or "width" in media.attrib):
                    try: width=int(media.attrib.get("width","0"))
                    except ValueError: width=0
                    candidates.append((width,candidate))
            if not candidates:
                match=re.search(r"<img[^>]+src=[^>]*?(https://[^\\s\\\"'>]+)",raw,re.I)
                if match: candidates.append((0,match.group(1)))
            image=max(candidates,key=lambda x:x[0])[1] if candidates else ""
            tags=[(el.text or el.attrib.get("term","")).strip() for el in item if el.tag.rsplit("}",1)[-1]=="category"]
            stories.append({"title":field("title"),"url":link,"summary":summary,"date":field("pubDate") or field("published") or field("updated"),"image":image,"source":source,"tags":tags,"author":author_name(item)})
        sections[source]=stories
        print(source,len(stories))
    except Exception as exc:
        print("Feed error",source,exc)
        sections[source]=[]
path=pathlib.Path("headlines.json")
if path.exists():
    try:
        previous=json.loads(path.read_text())
        for section,items in sections.items():
            if not items: sections[section]=previous.get("sections",{}).get(section,[])
    except Exception: pass
if not any(sections.values()): raise SystemExit("No feeds available; keeping existing headlines")
path.write_text(json.dumps({"updated":datetime.datetime.now(datetime.timezone.utc).isoformat(),"sections":sections},ensure_ascii=False))
