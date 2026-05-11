"""HEM data fetcher — GitHub Actions"""
import json, sys, re, os
from datetime import datetime, timedelta

END   = datetime.utcnow().strftime('%Y-%m-%d')
START = (datetime.utcnow() - timedelta(days=400)).strftime('%Y-%m-%d')

SYKE_BASE     = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata/WaterLevelRegisters'
SYKE_LOCATION = '04.252.1.001'
FMI_BASE      = 'https://opendata.fmi.fi/wfs'
FMI_STATION   = '101756'

import subprocess, sys
subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests', '-q'])
import requests

def fetch_syke():
    params = {
        '$filter':   f"LocationId eq '{SYKE_LOCATION}' and Timestamp ge {START}T00:00:00Z and Timestamp le {END}T23:59:59Z",
        '$orderby':  'Timestamp asc',
        '$top':      5000,
        '$format':   'json',
    }
    print(f'SYKE params: {params}')
    r = requests.get(SYKE_BASE, params=params, timeout=30,
                     headers={'Accept': 'application/json', 'User-Agent': 'ACI-HEM/1.1'})
    print(f'SYKE status: {r.status_code}')
    print(f'SYKE url: {r.url}')
    print(f'SYKE body[0:400]: {r.text[:400]}')
    r.raise_for_status()
    data = r.json()
    values = data.get('value', [])
    if not values:
        # debug: hae top=3 ilman filteriä
        r2 = requests.get(SYKE_BASE, params={'$top': 3, '$format': 'json'},
                          timeout=30, headers={'Accept': 'application/json'})
        print(f'SYKE top=3 ({r2.status_code}): {r2.text[:500]}')
        return {'source': 'SYKE', 'n': 0, 'rows': [], 'fetched': END}
    sample = values[0]
    print(f'SYKE kentat: {list(sample.keys())}')
    ts  = next((k for k in ['Timestamp','Aika','timestamp'] if k in sample), None)
    val = next((k for k in ['Wvalue','Arvo','wvalue','arvo'] if k in sample), None)
    if not ts or not val:
        raise ValueError(f'Tuntematon kenttarakenne: {list(sample.keys())}')
    rows = [{'date': str(v[ts])[:10], 'value': v[val]} for v in values]
    print(f'SYKE: {len(rows)} riveja')
    return {'source': 'SYKE', 'location': SYKE_LOCATION, 'fetched': END, 'n': len(rows), 'rows': rows}

def fetch_fmi():
    params = {
        'service': 'WFS', 'version': '2.0.0', 'request': 'getFeature',
        'storedquery_id': 'fmi::observations::weather::daily::simple',
        'fmisid': FMI_STATION, 'parameters': 'tday,rrday',
        'starttime': f'{START}T00:00:00Z', 'endtime': f'{END}T23:59:59Z',
    }
    r = requests.get(FMI_BASE, params=params, timeout=30,
                     headers={'User-Agent': 'ACI-HEM/1.1'})
    print(f'FMI status: {r.status_code}')
    r.raise_for_status()
    xml = r.text
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
