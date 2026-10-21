"""Optional editorial home-page placement and public Hacker News engagement signals."""
import json, pathlib, urllib.request, urllib.parse, re, html
from html.parser import HTMLParser
PAGES={
 'NYT':'https://www.nytimes.com/',
 'The Guardian US':'https://www.theguardian.com/us',
 'The Intercept':'https://theintercept.com/',
 'The Nation':'https://www.thenation.com/',
 'Jacobin':'https://jacobin.com/',
 'ProPublica':'https://www.propublica.org/',
 'In These Times':'https://inthesetimes.com/',
 'Al Jazeera':'https://www.aljazeera.com/',
 'taz':'https://taz.de/',
 'Mediapart':'https://www.mediapart.fr/',
 'L’Humanité':'https://www.humanite.fr/',
 'Le Monde diplomatique':'https://mondediplo.com/'
}
def canonical(url):
 p=urllib.parse.urlsplit(url)
 return (p.hostname or '').removeprefix('www.')+p.path.rstrip('/')
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a':
   href=dict(attrs).get('href','')
   if href:self.links.append(href)
data=json.loads(pathlib.Path('headlines.json').read_text())['sections']
articles={canonical(a['url']):a['url'] for feed in data.values() for a in feed if a.get('url')}
scores={}
for source,homepage in PAGES.items():
 try:
  req=urllib.request.Request(homepage,headers={'User-Agent':'Mozilla/5.0 (compatible; ThirtyReader/1.0)','Accept':'text/html'})
  with urllib.request.urlopen(req,timeout=10) as resp:markup=resp.read(1250000).decode('utf-8','replace')
  parser=Links();parser.feed(markup)
  found=set();position=0
  for href in parser.links:
   url=urllib.parse.urljoin(homepage,html.unescape(href))
   key=canonical(url)
   if key not in articles or key in found:continue
   found.add(key);position+=1
   scores.setdefault(articles[key],{})['homepageRank']=position
  print(source,'matched homepage stories:',len(found))
 except Exception as e:print('Homepage unavailable',source,str(e)[:120])
# Public HN front-page vote and comment counts; no unsupported social share estimates.
try:
 req=urllib.request.Request('https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=100',headers={'User-Agent':'ThirtyReader/1.0'})
 with urllib.request.urlopen(req,timeout=10) as resp:hits=json.load(resp).get('hits',[])
 for hit in hits:
  key=canonical(hit.get('url') or '')
  if key in articles:
   scores.setdefault(articles[key],{}).update({'hnPoints':max(0,int(hit.get('points') or 0)),'hnComments':max(0,int(hit.get('num_comments') or 0))})
except Exception as e:print('HN popularity unavailable',str(e)[:120])
pathlib.Path('signals.json').write_text(json.dumps(scores,ensure_ascii=False))
print('Signals matched articles:',len(scores))
