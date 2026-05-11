"""HEM data fetcher — GitHub Actions. URL rakennetaan käsin OData/WFS-yhteensopivuuden vuoksi."""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=365)).strftime('%Y-%m-%d')

SYKE_BASE     = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata/WaterLevelRegisters'
SYKE_LOCATION = '04.252.1.001'
FMI_BASE      = 'https://opendata.fmi.fi/wfs'
FMI_STATION   = '101756'

def fetch_syke():
    # Rakennetaan URL KÄSIN — requests enkoodaa $-merkit väärin
    filt = f"LocationId eq '{SYKE_LOCATION}' and Timestamp ge {START}T00:00:00Z and Timestamp le {END}T23:59:59Z"
    from urllib.parse import quote
    url = (f"{SYKE_BASE}"
           f"?$filter={quote(filt)}"
           f"&$orderby=Timestamp%20asc"
           f"&$top=5000"
           f"&$format=json")
    print(f'SYKE url: {url[:150]}')
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    print(f'SYKE status: 200, bytes: {len(raw)}')
    print(f'SYKE preview: {raw[:300]}')
    data = json.loads(raw)
    values = data.get('value', [])
    if not values:
        print('SYKE: tyhjä value-lista')
        return {'source': 'SYKE', 'n': 0, 'rows': [], 'fetched': END}
    sample = values[0]
    print(f'SYKE kentat: {list(sample.keys())}')
    ts  = next((k for k in ['Timestamp','Aika'] if k in sample), None)
    val = next((k for k in ['Wvalue','Arvo'] if k in sample), None)
    rows = [{'date': str(v[ts])[:10], 'value': v[val]} for v in values]
    print(f'SYKE: {len(rows)} riveja, esim: {rows[0]}')
    return {'source': 'SYKE', 'location': SYKE_LOCATION, 'fetched': END, 'n': len(rows), 'rows': rows}

def fetch_fmi():
    # FMI: storedquery_id sisältää :: jota ei saa enkoodata
    url = (f"{FMI_BASE}"
           f"?service=WFS&version=2.0.0&request=getFeature"
           f"&storedquery_id=fmi::observations::weather::daily::simple"
           f"&fmisid={FMI_STATION}"
           f"&parameters=tday,rrday"
           f"&starttime={START}T00:00:00Z"
           f"&endtime={END}T23:59:59Z")
    print(f'FMI url: {url[:150]}')
    req = urllib.request.Request(url, headers={'User-Agent': 'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        xml = r.read().decode('utf-8')
    print(f'FMI bytes: {len(xml)}, preview: {xml[:150]}')
    times  = [m[1][:10] for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>', xml)]
    pnames = [m[1]      for m in re.finditer(r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>', xml)]
    values = [m[1]      for m in re.finditer(r'<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', xml)]
    rows   = [{'date': times[i], 'param': pnames[i],
               'value': None if values[i] in ('NaN','') else float(values[i])}
              for i in range(len(times))]
    print(f'FMI: {len(rows)} riveja')
    return {'source': 'FMI', 'station': FMI_STATION, 'fetched': END, 'n': len(rows), 'rows': rows}

os.makedirs('data/cache', exist_ok=True)
errors = []

try:
    syke = fetch_syke()
    with open('data/cache/syke.json', 'w') as f: json.dump(syke, f)
    print('OK syke.json')
except Exception as e:
    print(f'FAIL SYKE: {e}')
    errors.append(f'SYKE: {e}')

try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json', 'w') as f: json.dump(fmi, f)
    print('OK fmi.json')
except Exception as e:
    print(f'FAIL FMI: {e}')
    errors.append(f'FMI: {e}')

if errors:
    print(f'ERRORS: {errors}')
    sys.exit(1)
print('ALL OK')
