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
