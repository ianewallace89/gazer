import json,re,html,pathlib,urllib.request,urllib.parse,concurrent.futures
from html.parser import HTMLParser
class Reader(HTMLParser):
 def __init__(self): super().__init__();self.depth=0;self.active=False;self.parts=[];self.current=[];self.tag=None
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag in ('script','style','nav','footer','header','aside'):self.depth+=1
  if tag=='p' and self.depth==0:self.active=True;self.current=[]
 def handle_endtag(self,tag):
  if tag=='p' and self.active:
   t=' '.join(''.join(self.current).split())
   if len(t)>75 and not re.search(r'cookie policy|subscribe to|sign up for|all rights reserved',t,re.I):self.parts.append(t)
   self.active=False
  if tag in ('script','style','nav','footer','header','aside') and self.depth:self.depth-=1
 def handle_data(self,data):
  if self.active and not self.depth:self.current.append(data)
path=pathlib.Path('articles.json')
try: existing=json.loads(path.read_text())
except: existing={}
feeds=json.loads(pathlib.Path('headlines.json').read_text())['sections']
items={a['url']:a for arr in feeds.values() for a in arr if a.get('url') and a.get('source')!='NYT'}
# Keep previously extracted articles and only fetch a limited number each run.
todo=[a for u,a in items.items() if u not in existing][:24]
def fetch(a):
 try:
  req=urllib.request.Request(a['url'],headers={'User-Agent':'Mozilla/5.0 (compatible; ThirtyOfflineReader/1.0)'})
  with urllib.request.urlopen(req,timeout=9) as res:
   if 'text/html' not in res.headers.get('Content-Type',''):return None
   raw=res.read(650000).decode('utf-8','replace')
  parser=Reader();parser.feed(raw)
  parts=[];seen=set()
  for p in parser.parts:
   if p not in seen:parts.append(p);seen.add(p)
  content='\\n\\n'.join(parts)
  if len(content)<1600 or len(parts)<5:return None
  return a['url'],{'title':a['title'],'source':a.get('source'),'text':content[:90000]}
 except Exception:return None
with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
 for result in pool.map(fetch,todo):
  if result:existing[result[0]]=result[1]
# Limit total published file size and preserve newer saves.
if len(existing)>400:existing=dict(list(existing.items())[-400:])
path.write_text(json.dumps(existing,ensure_ascii=False))
print('Offline readable:',len(existing),'new attempts:',len(todo))
