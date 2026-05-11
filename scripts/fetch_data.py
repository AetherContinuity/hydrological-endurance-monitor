"""HEM data fetcher — FMI päivittäinen + NVE viikkottainen"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=365)).strftime('%Y-%m-%d')

FMI_BASE    = 'https://opendata.fmi.fi/wfs'
FMI_STATION = '101756'  # Lappeenranta Lepola

def fetch_fmi():
    # Max 365 päivää kerrallaan FMI:lle
    url = (f"{FMI_BASE}?service=WFS&version=2.0.0&request=getFeature"
           f"&storedquery_id=fmi::observations::weather::daily::simple"
           f"&fmisid={FMI_STATION}&parameters=tday,rrday"
           f"&starttime={START}T00:00:00Z&endtime={END}T23:59:59Z")
    print(f'FMI: {url[:120]}')
    req = urllib.request.Request(url, headers={'User-Agent':'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        xml = r.read().decode('utf-8')
    times  = [m[1][:10] for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>', xml)]
    pnames = [m[1]      for m in re.finditer(r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>', xml)]
    values = [m[1]      for m in re.finditer(r'<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', xml)]
    rows   = [{'date':times[i],'param':pnames[i],
               'value':None if values[i] in ('NaN','') else float(values[i])}
              for i in range(len(times))]
    print(f'FMI: {len(rows)} rivejä ({START} → {END})')
    return {'source':'FMI','station':FMI_STATION,'fetched':END,'n':len(rows),'rows':rows}

os.makedirs('data/cache', exist_ok=True)

# SYKE ei ole saatavilla automaattisesti GitHub Actions -palvelimilta
# Vedenkorkeus lisätään manuaalisesti data/cache/water_level.csv
syke_note = {
    'source': 'SYKE-manual',
    'note': 'SYKE OData suljettu 31.3.2023. Vedenkorkeus lisätään manuaalisesti.',
    'fetched': END,
    'n': 0,
    'rows': []
}
# Lataa jos manuaalinen CSV on jo repossa
wl_file = 'data/cache/water_level.csv'
if os.path.exists(wl_file):
    rows = []
    with open(wl_file) as f:
        lines = f.read().strip().split('\n')
    for line in lines[1:]:
        parts = line.split(',')
        if len(parts) >= 2:
            try:
                rows.append({'date': parts[0].strip(), 'value': float(parts[1].strip())})
            except: pass
    syke_note = {'source':'SYKE-manual-csv','n':len(rows),'rows':rows,'fetched':END}
    print(f'SYKE manual CSV: {len(rows)} rivejä')
else:
    print('SYKE: ei manuaalista CSV:tä (data/cache/water_level.csv)')

with open('data/cache/syke.json', 'w') as f:
    json.dump(syke_note, f)

try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json', 'w') as f:
        json.dump(fmi, f)
    print(f'OK fmi.json ({fmi["n"]} rivejä)')
except Exception as e:
    print(f'FAIL FMI: {e}')
    sys.exit(1)

print('DONE')
