"""HEM data fetcher — debug HTML rakenne"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=365)).strftime('%Y-%m-%d')

FMI_BASE    = 'https://opendata.fmi.fi/wfs'
FMI_STATION = '101756'
SYKE_TUNNUS = '1403300'

def fetch_syke():
    url = (f'https://wwwi2.ymparisto.fi/i2/95/vesiA.html'
           f'?tunnus={SYKE_TUNNUS}&alku={START}&loppu={END}')
    print(f'SYKE: {url}')
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'text/html,*/*'
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()

    html = raw.decode('utf-8', 'replace')

    # Tallenna raaka HTML debuggausta varten
    with open('data/cache/syke_debug.html', 'w') as f:
        f.write(html)

    # Tutki rakennetta
    print(f'  bytes: {len(raw)}')
    print(f'  <td>-soluja: {len(re.findall("<td", html, re.I))}')
    print(f'  <tr>-rivejä: {len(re.findall("<tr", html, re.I))}')
    print(f'  <table>: {len(re.findall("<table", html, re.I))}')

    # Etsi kaikki numerosekvenssit taulukon sisällä
    all_cells = re.findall(r'<td[^>]*>(.*?)</td>', html, re.I|re.S)
    clean = [re.sub(r'<[^>]+>','',c).strip() for c in all_cells]
    print(f'  TD-solujen sisältö (50 ensimmäistä):')
    for i, c in enumerate(clean[:50]):
        if c: print(f'    [{i}] {repr(c[:60])}')

    # Etsi JavaScript-muuttujia
    js_vars = re.findall(r'var\s+\w+\s*=\s*[\[\{].*?[\]\}]', html, re.S)
    print(f'  JS-muuttujia: {len(js_vars)}')
    for v in js_vars[:3]:
        print(f'    {v[:150]}')

    return {'source':'SYKE-wwwi2','n':0,'rows':[],'fetched':END}

def fetch_fmi():
    url = (f"{FMI_BASE}?service=WFS&version=2.0.0&request=getFeature"
           f"&storedquery_id=fmi::observations::weather::daily::simple"
           f"&fmisid={FMI_STATION}&parameters=tday,rrday"
           f"&starttime={START}T00:00:00Z&endtime={END}T23:59:59Z")
    req = urllib.request.Request(url, headers={'User-Agent':'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        xml = r.read().decode('utf-8')
    times  = [m[1][:10] for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>', xml)]
    pnames = [m[1]      for m in re.finditer(r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>', xml)]
    values = [m[1]      for m in re.finditer(r'<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', xml)]
    rows   = [{'date':times[i],'param':pnames[i],
               'value':None if values[i] in ('NaN','') else float(values[i])}
              for i in range(len(times))]
    return {'source':'FMI','station':FMI_STATION,'fetched':END,'n':len(rows),'rows':rows}

os.makedirs('data/cache', exist_ok=True)
errors = []

try:
    syke = fetch_syke()
    with open('data/cache/syke.json','w') as f: json.dump(syke, f)
    print(f'OK syke.json (debug-mode)')
except Exception as e:
    print(f'FAIL SYKE: {e}')
    errors.append(str(e))

try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json','w') as f: json.dump(fmi, f)
    print(f'OK fmi.json ({fmi["n"]} rivejä)')
except Exception as e:
    print(f'FAIL FMI: {e}')
    errors.append(str(e))

if errors:
    sys.exit(1)
print('DONE')
