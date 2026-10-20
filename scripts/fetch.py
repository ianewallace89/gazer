import datetime, json, pathlib, urllib.request, urllib.parse, xml.etree.ElementTree as ET, re, html
FEEDS = {
"Top Stories":"HomePage","World":"World","U.S.":"US","Politics":"Politics","New York":"NYRegion",
"Business":"Business","Technology":"Technology","Science":"Science","Health":"Health",
"Arts":"Arts","Books":"Books","Movies":"Movies","Opinion":"Opinion"
}
headers={"User-Agent":"Mozilla/5.0 (compatible; GazerRSS/1.0)"}
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
            media_ns="{http://search.yahoo.com/mrss/}"
            image=""
            candidates=[]
            for tag in ("content","thumbnail"):
                for media in item.findall(media_ns+tag):
                    url=media.get("url","")
                    if url.startswith("https://") and ("nytimes.com" in urllib.parse.urlparse(url).hostname or ""):
                        width=int(media.get("width","0") or 0)
                        candidates.append((width,url))
            if candidates:
                image=max(candidates,key=lambda x:x[0])[1]
            stories.append({"title":field("title"),"url":link,"summary":summary[:260],"date":field("pubDate"),"image":image})
        sections[section]=stories
        print(section,len(stories))
    except Exception as exc:
        print("Feed error",section,exc)
        sections[section]=[]
path=pathlib.Path("headlines.json")
if path.exists():
    try:
        previous=json.loads(path.read_text())
        for section,items in sections.items():
            if not items: sections[section]=previous.get("sections",{}).get(section,[])
    except Exception: pass
if not any(sections.values()): raise SystemExit("No feeds available; keeping existing headlines")
path.write_text(json.dumps({"updated":datetime.datetime.now(datetime.timezone.utc).isoformat(),"sections":sections},ensure_ascii=False))
