"""
HEM data fetcher — GitHub Actions pipeline.
Hakee SYKE vedenkorkeus + FMI sää päivittäin.
"""
import urllib.request, urllib.parse, json, sys, re, os
from datetime import datetime, timedelta

END   = datetime.utcnow().strftime('%Y-%m-%d')
START = (datetime.utcnow() - timedelta(days=400)).strftime('%Y-%m-%d')

SYKE_BASE     = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata/WaterLevelRegisters'
SYKE_LOCATION = '04.112.1.001'
FMI_BASE      = 'https://opendata.fmi.fi/wfs'
FMI_STATION   = '101756'

def fetch_syke():
    filt = (f"LocationId eq '{SYKE_LOCATION}' "
            f"and Timestamp ge {START}T00:00:00Z "
            f"and Timestamp le {END}T23:59:59Z")
    params = urllib.parse.urlencode({'$filter':filt,'$orderby':'Timestamp asc','$top':5000,'$format':'json'})
    url = f'{SYKE_BASE}?{params}'
    print(f'SYKE: {url[:120]}')
    req = urllib.request.Request(url, headers={'Accept':'application/json','User-Agent':'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    print(f'SYKE raw[0:400]: {raw[:400]}')
    data = json.loads(raw)
    values = data.get('value', [])
    if not values:
        # Debug: hae top=3 ilman filteriä
        url2 = f'{SYKE_BASE}?$top=3&$format=json'
        req2 = urllib.request.Request(url2, headers={'Accept':'application/json','User-Agent':'ACI-HEM/1.1'})
        with urllib.request.urlopen(req2, timeout=30) as r2:
            print(f'SYKE top=3: {r2.read()[:500]}')
        return {'source':'SYKE','n':0,'rows':[],'fetched':END}
    sample = values[0]
    print(f'SYKE kentat: {list(sample.keys())}')
    ts  = next((k for k in ['Timestamp','Aika','timestamp'] if k in sample), None)
    val = next((k for k in ['Wvalue','Arvo','wvalue','arvo','value'] if k in sample), None)
    if not ts or not val:
        raise ValueError(f'Tuntematon rakenne: {list(sample.keys())}')
    rows = [{'date':str(v[ts])[:10],'value':v[val]} for v in values]
    print(f'SYKE: {len(rows)} riveja')
    return {'source':'SYKE','location':SYKE_LOCATION,'fetched':END,'n':len(rows),'rows':rows}

def fetch_fmi():
    params = urllib.parse.urlencode({
        'service':'WFS','version':'2.0.0','request':'getFeature',
        'storedquery_id':'fmi::observations::weather::daily::simple',
        'fmisid':FMI_STATION,'parameters':'tday,rrday',
        'starttime':f'{START}T00:00:00Z','endtime':f'{END}T23:59:59Z',
    })
    url = f'{FMI_BASE}?{params}'
    print(f'FMI: {url[:120]}')
    req = urllib.request.Request(url, headers={'User-Agent':'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        xml = r.read().decode('utf-8')
    print(f'FMI XML[0:200]: {xml[:200]}')
    times  = [m[1][:10] for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>', xml)]
    pnames = [m[1]      for m in re.finditer(r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>', xml)]
    values = [m[1]      for m in re.finditer(r'<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', xml)]
    rows   = [{'date':times[i],'param':pnames[i],'value':None if values[i] in ('NaN','') else float(values[i])} for i in range(len(times))]
    print(f'FMI: {len(rows)} riveja')
    return {'source':'FMI','station':FMI_STATION,'fetched':END,'n':len(rows),'rows':rows}

os.makedirs('data/cache', exist_ok=True)
errors = []

try:
    syke = fetch_syke()
    with open('data/cache/syke.json','w') as f: json.dump(syke, f)
    print('OK data/cache/syke.json')
except Exception as e:
    print(f'FAIL SYKE: {e}')
    errors.append(str(e))

try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json','w') as f: json.dump(fmi, f)
    print('OK data/cache/fmi.json')
except Exception as e:
    print(f'FAIL FMI: {e}')
    errors.append(str(e))

if errors:
    print(f'ERRORS: {errors}')
    sys.exit(1)
print('ALL OK')
