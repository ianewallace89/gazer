import json,re,html,pathlib,urllib.request,urllib.parse,concurrent.futures,datetime
from html.parser import HTMLParser
class Metadata(HTMLParser):
 def __init__(self):super().__init__();self.author=""
 def handle_starttag(self,tag,attrs):
  if tag!="meta" or self.author:return
  d=dict(attrs)
  key=(d.get("name") or d.get("property") or "").lower()
  if key in ("author","article:author","parsely-author","dc.creator","twitter:creator"):
   value=" ".join(html.unescape(d.get("content","")).split())
   if value and not value.startswith(("http:","https:","@")):self.author=value[:200]
class Reader(HTMLParser):
 def __init__(self): super().__init__();self.depth=0;self.active=False;self.parts=[];self.current=[];self.tag=None
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag in ('script','style','nav','footer','header','aside'):self.depth+=1
  if tag=='p' and self.depth==0:self.active=True;self.current=[]
 def handle_endtag(self,tag):
  if tag=='p' and self.active:
   t=' '.join(''.join(self.current).split())
   if len(t)>45 and not re.search(r'cookie policy|subscribe to|sign up for|all rights reserved',t,re.I):self.parts.append(t)
   self.active=False
  if tag in ('script','style','nav','footer','header','aside') and self.depth:self.depth-=1
 def handle_data(self,data):
  if self.active and not self.depth:self.current.append(data)
path=pathlib.Path('articles.json')
try: existing=json.loads(path.read_text())
except: existing={}
feeds=json.loads(pathlib.Path('headlines.json').read_text())['sections']
items={a['url']:a for arr in feeds.values() for a in arr if a.get('url') and a.get('source')!='NYT'}
# Spread attempts across the entire outstanding feed, rather than getting stuck
# on the same first 24 URLs whose publishers block extraction.
pending=[a for u,a in items.items() if u not in existing]
batch_size=48
slot=int(datetime.datetime.now(datetime.timezone.utc).timestamp()//900)
start=(slot*batch_size)%len(pending) if pending else 0
todo=(pending[start:]+pending[:start])[:batch_size]
def fetch(a):
 try:
  req=urllib.request.Request(a['url'],headers={'User-Agent':'Mozilla/5.0 (compatible; ThirtyOfflineReader/1.0)'})
  with urllib.request.urlopen(req,timeout=9) as res:
   if 'text/html' not in res.headers.get('Content-Type',''):return None
   raw=res.read(650000).decode('utf-8','replace')
  metadata=Metadata();metadata.feed(raw)
  parser=Reader();parser.feed(raw)
  parts=[];seen=set()
  for p in parser.parts:
   if p not in seen:parts.append(p);seen.add(p)
  content='\n\n'.join(parts)
  if len(content)<500 or len(parts)<2:return None
  return a['url'],{'title':a['title'],'source':a.get('source'),'author':a.get('author') or metadata.author,'text':content[:90000]}
 except Exception:return None
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
 for result in pool.map(fetch,todo):
  if result:existing[result[0]]=result[1]
# Refresh bylines for already-extracted articles whenever feed metadata has them.
for url,article in existing.items():
 source=items.get(url)
 if source and source.get('author') and not article.get('author'):article['author']=source['author']
# Limit total published file size and preserve newer saves.
if len(existing)>400:existing=dict(list(existing.items())[-400:])
path.write_text(json.dumps(existing,ensure_ascii=False))
print('Offline readable:',len(existing),'attempted:',len(todo),'outstanding:',len(pending))
