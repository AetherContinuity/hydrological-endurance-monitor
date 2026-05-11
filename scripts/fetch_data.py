"""HEM data fetcher — SYKE hydra v1 OData (POST) + FMI"""
import json, sys, re, os, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=400)).strftime('%Y-%m-%d')

SYKE_URL    = 'https://rajapinnat.ymparisto.fi/api/hydra/v1/odata/WaterLevelRegisters'
SYKE_LOC    = '14.722.1.001'   # Virmasvesi/Iisvesi
FMI_BASE    = 'https://opendata.fmi.fi/wfs'
FMI_STATION = '101756'         # Lappeenranta Lepola

def post_json(url, data):
    body = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'ACI-HEM/1.1'
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def fetch_syke():
    print(f'SYKE hydra v1: {SYKE_URL}')
    all_rows = []
    params = {
        'filter': f"LocationId eq '{SYKE_LOC}' and Timestamp ge {START}T00:00:00Z and Timestamp le {END}T23:59:59Z",
        'orderby': 'Timestamp asc',
    }

    page = 0
    while True:
        print(f'  Sivu {page}...')
        try:
            resp = post_json(SYKE_URL, params)
        except Exception as e:
            print(f'  POST virhe: {e}')
            break

        print(f'  Avaimet: {list(resp.keys())}')

        values = resp.get('value', [])
        if not values:
            print(f'  Tyhjä vastaus: {str(resp)[:300]}')
            break

        if page == 0 and values:
            print(f'  Esimerkki: {values[0]}')

        all_rows.extend(values)
        print(f'  +{len(values)} riviä (yhteensä {len(all_rows)})')

        next_link = resp.get('@odata.nextLink')
        if not next_link:
            break

        # Seuraa nextLink-sivutusta
        skip_m = re.search(r'\$skip=(\d+)', next_link)
        if skip_m:
            params = {'$skip': int(skip_m.group(1))}
        else:
            break
        page += 1
        if page > 20:  # Turvaraja
            break

    print(f'SYKE: {len(all_rows)} riviä yhteensä')

    # Normalisoi
    rows = []
    for v in all_rows:
        ts  = v.get('Timestamp','')[:10]
        val = v.get('Wvalue')
        if ts and val is not None:
            rows.append({'date': ts, 'value': val})

    if rows:
        vals = [r['value'] for r in rows]
        print(f'  min={min(vals)} max={max(vals)} (tarkista yksikkö: cm/mm/m?)')
        print(f'  ensimmäinen: {rows[0]}')
        print(f'  viimeisin:   {rows[-1]}')

    return {'source':'SYKE-hydra-v1','location':SYKE_LOC,
            'fetched':END,'n':len(rows),'rows':rows}

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
    syke = fetch_syke()
    with open('data/cache/syke.json','w') as f: json.dump(syke, f)
    print(f'OK syke.json ({syke["n"]} rivejä)')
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
