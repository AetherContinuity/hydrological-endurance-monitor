"""HEM data fetcher — CKAN API + FMI"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=365)).strftime('%Y-%m-%d')

CKAN_BASE   = 'https://ckan.ymparisto.fi/api/3/action'
FMI_BASE    = 'https://opendata.fmi.fi/wfs'
FMI_STATION = '101756'

def get_json(url):
    req = urllib.request.Request(url, headers={'Accept':'application/json','User-Agent':'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def fetch_syke_via_ckan():
    """Etsi SYKE vedenkorkeus-resursseja CKAN API:n kautta"""
    print('CKAN: etsitään vedenkorkeus-resursseja...')

    # Hae HYDRO-datasetti
    search_url = f'{CKAN_BASE}/package_search?q=vedenkorkeus+hydrologinen&rows=10'
    print(f'  Haku: {search_url}')
    result = get_json(search_url)
    packages = result.get('result', {}).get('results', [])
    print(f'  Löytyi {len(packages)} pakettia')

    rows = []
    for pkg in packages:
        print(f'  Paketti: {pkg.get("name")} — {pkg.get("title","")}')
        for res in pkg.get('resources', []):
            fmt = res.get('format','').upper()
            url = res.get('url','')
            print(f'    Resurssi: {res.get("name","")} [{fmt}] → {url[:80]}')

            # Kokeile CSV-lataus
            if fmt in ('CSV','JSON') or url.endswith('.csv') or url.endswith('.json'):
                try:
                    req = urllib.request.Request(url, headers={'User-Agent':'ACI-HEM/1.1'})
                    with urllib.request.urlopen(req, timeout=15) as r:
                        content = r.read()
                    print(f'      OK: {len(content)} bytes — {content[:200]}')
                    rows.append({'url': url, 'format': fmt, 'size': len(content), 'preview': content[:100].decode('utf-8','replace')})
                except Exception as e:
                    print(f'      FAIL: {e}')

    return {'source':'SYKE-CKAN','n':len(rows),'resources':rows,'fetched':END}

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
    print(f'FMI: {len(rows)} rivejä')
    return {'source':'FMI','station':FMI_STATION,'fetched':END,'n':len(rows),'rows':rows}

os.makedirs('data/cache', exist_ok=True)
errors = []

try:
    syke = fetch_syke_via_ckan()
    with open('data/cache/syke.json','w') as f: json.dump(syke, f)
    print(f'OK syke.json ({syke["n"]} resursseja)')
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
    print(f'ERRORS: {errors}')
    sys.exit(1)
print('DONE')
