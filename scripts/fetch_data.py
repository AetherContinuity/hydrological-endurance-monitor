"""HEM data fetcher — SYKE oikea endpoint löydetty (1.0/Havainto)"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=365)).strftime('%Y-%m-%d')

# SYKE oikea muoto: 1.0/Havainto + Tunniste (ei OData)
SYKE_BASE   = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.0/Havainto'
SYKE_TUNNUS = '1403300'  # Iisvesi
# Vaihtoehto Saimaa Lauritsala: tunnus selvitetään myöhemmin

FMI_BASE    = 'https://opendata.fmi.fi/wfs'
FMI_STATION = '101756'

def fetch_syke():
    url = (f"{SYKE_BASE}"
           f"?Tunniste={SYKE_TUNNUS}"
           f"&Suure=Vedenkorkeus"
           f"&alkupvm={START}"
           f"&loppupvm={END}")
    print(f'SYKE url: {url}')
    req = urllib.request.Request(url, headers={
        'Accept': 'application/json', 'User-Agent': 'ACI-HEM/1.1'
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    print(f'SYKE status: 200, bytes: {len(raw)}')
    print(f'SYKE preview: {raw[:400]}')

    data = json.loads(raw)
    # Rakenne voi olla lista tai dict results-avaimella
    rows_raw = data if isinstance(data, list) else data.get('results', data.get('value', []))
    print(f'SYKE rivejä raakana: {len(rows_raw)}')
    if not rows_raw:
        return {'source': 'SYKE', 'n': 0, 'rows': [], 'fetched': END}

    sample = rows_raw[0]
    print(f'SYKE kentat: {list(sample.keys()) if isinstance(sample, dict) else sample}')

    # Tunnista aika ja arvo -sarakkeet
    if isinstance(sample, dict):
        keys = [k.lower() for k in sample.keys()]
        orig_keys = list(sample.keys())
        ts_key  = next((orig_keys[i] for i,k in enumerate(keys) if any(x in k for x in ['aika','time','pvm'])), None)
        val_key = next((orig_keys[i] for i,k in enumerate(keys) if any(x in k for x in ['arvo','value','wl'])), None)
        print(f'SYKE ts={ts_key} val={val_key}')
        rows = [{'date': str(r[ts_key])[:10], 'value': r[val_key]} for r in rows_raw if ts_key and val_key]
    else:
        rows = []

    print(f'SYKE: {len(rows)} rivejä')
    return {'source': 'SYKE', 'tunnus': SYKE_TUNNUS, 'fetched': END, 'n': len(rows), 'rows': rows}

def fetch_fmi():
    url = (f"{FMI_BASE}?service=WFS&version=2.0.0&request=getFeature"
           f"&storedquery_id=fmi::observations::weather::daily::simple"
           f"&fmisid={FMI_STATION}&parameters=tday,rrday"
           f"&starttime={START}T00:00:00Z&endtime={END}T23:59:59Z")
    print(f'FMI url: {url[:120]}')
    req = urllib.request.Request(url, headers={'User-Agent': 'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        xml = r.read().decode('utf-8')
    times  = [m[1][:10] for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>', xml)]
    pnames = [m[1]      for m in re.finditer(r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>', xml)]
    values = [m[1]      for m in re.finditer(r'<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', xml)]
    rows   = [{'date': times[i], 'param': pnames[i],
               'value': None if values[i] in ('NaN','') else float(values[i])}
              for i in range(len(times))]
    print(f'FMI: {len(rows)} rivejä')
    return {'source': 'FMI', 'station': FMI_STATION, 'fetched': END, 'n': len(rows), 'rows': rows}

os.makedirs('data/cache', exist_ok=True)
errors = []

try:
    syke = fetch_syke()
    with open('data/cache/syke.json', 'w') as f: json.dump(syke, f)
    print(f'OK syke.json ({syke["n"]} rivejä)')
except Exception as e:
    print(f'FAIL SYKE: {e}')
    errors.append(str(e))

try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json', 'w') as f: json.dump(fmi, f)
    print(f'OK fmi.json ({fmi["n"]} rivejä)')
except Exception as e:
    print(f'FAIL FMI: {e}')
    errors.append(str(e))

if errors:
    print(f'ERRORS: {errors}')
    sys.exit(1)
print('ALL OK')
