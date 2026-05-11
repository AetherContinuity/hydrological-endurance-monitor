"""
HEM data fetcher — ajettava GitHub Actionsin kautta.
Hakee SYKE vedenkorkeus + FMI sää suoraan ja tallentaa JSON-cacheen.
"""
import urllib.request, urllib.parse, json, sys
from datetime import datetime, timedelta

# ── Config ───────────────────────────────────────────────────────
END   = datetime.utcnow().strftime('%Y-%m-%d')
START = (datetime.utcnow() - timedelta(days=365)).strftime('%Y-%m-%d')

SYKE_BASE = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata/WaterLevelRegisters'
FMI_BASE  = 'https://opendata.fmi.fi/wfs'

# Saimaa Lauritsala — LocationId '04.112.1.001', Tunnus 0411200
SYKE_LOCATION = '04.112.1.001'
FMI_STATION   = '101756'  # Lappeenranta Lepola

def fetch_syke():
    filt = f"LocationId eq '{SYKE_LOCATION}' and Timestamp ge {START}T00:00:00Z and Timestamp le {END}T23:59:59Z"
    params = urllib.parse.urlencode({
        '$filter': filt,
        '$orderby': 'Timestamp asc',
        '$top': 5000,
        '$format': 'json',
        '$select': 'Timestamp,Wvalue'
    })
    url = f'{SYKE_BASE}?{params}'
    print(f'SYKE: {url[:100]}...')
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    rows = [{'date': v['Timestamp'][:10], 'value': v['Wvalue']} for v in data.get('value', [])]
    print(f'  → {len(rows)} rivejä')
    return {'source': 'SYKE', 'location': SYKE_LOCATION, 'fetched': END, 'n': len(rows), 'rows': rows}

def fetch_fmi():
    params = urllib.parse.urlencode({
        'service': 'WFS', 'version': '2.0.0', 'request': 'getFeature',
        'storedquery_id': 'fmi::observations::weather::daily::simple',
        'fmisid': FMI_STATION,
        'parameters': 'tday,rrday',
        'starttime': f'{START}T00:00:00Z',
        'endtime':   f'{END}T23:59:59Z',
    })
    url = f'{FMI_BASE}?{params}'
    print(f'FMI: {url[:100]}...')
    req = urllib.request.Request(url, headers={'User-Agent': 'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        xml = r.read().decode('utf-8')

    import re
    times  = [m[1][:10] for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>', xml)]
    pnames = [m[1]      for m in re.finditer(r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>', xml)]
    values = [m[1]      for m in re.finditer(r'<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', xml)]

    rows = [{'date': times[i], 'param': pnames[i],
             'value': None if values[i] == 'NaN' else float(values[i])}
            for i in range(len(times))]
    print(f'  → {len(rows)} rivejä')
    return {'source': 'FMI', 'station': FMI_STATION, 'fetched': END, 'n': len(rows), 'rows': rows}

# ── Aja ──────────────────────────────────────────────────────────
errors = []

try:
    syke = fetch_syke()
    with open('data/cache/syke.json', 'w') as f:
        json.dump(syke, f)
    print('✓ data/cache/syke.json kirjoitettu')
except Exception as e:
    print(f'✗ SYKE virhe: {e}')
    errors.append(f'SYKE: {e}')

try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json', 'w') as f:
        json.dump(fmi, f)
    print('✓ data/cache/fmi.json kirjoitettu')
except Exception as e:
    print(f'✗ FMI virhe: {e}')
    errors.append(f'FMI: {e}')

if errors:
    print('\nVirheitä:', errors)
    sys.exit(1)
print('\nKaikki OK.')
