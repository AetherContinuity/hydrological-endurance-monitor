"""HEM data fetcher v2 — löytää SYKE OData entiteetin automaattisesti"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=365)).strftime('%Y-%m-%d')

SYKE_ROOT = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.1/odata'
FMI_BASE  = 'https://opendata.fmi.fi/wfs'
FMI_STATION = '101756'

HDR = {'Accept': 'application/json', 'User-Agent': 'ACI-HEM/1.1'}

def get(url):
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def fetch_syke():
    # 1. Hae juuri — näyttää saatavilla olevat entiteetit
    print(f'SYKE root: {SYKE_ROOT}/')
    try:
        raw = get(f'{SYKE_ROOT}/')
        print(f'SYKE root response: {raw[:600]}')
    except Exception as e:
        print(f'SYKE root error: {e}')

    # 2. Hae metadata — listaa kaikki EntitySet-nimet
    print(f'SYKE metadata: {SYKE_ROOT}/$metadata')
    try:
        raw = get(f'{SYKE_ROOT}/$metadata')
        entities = re.findall(r'EntitySet Name="([^"]+)"', raw.decode('utf-8','replace'))
        print(f'SYKE entities: {entities}')
    except Exception as e:
        print(f'SYKE metadata error: {e}')
        entities = []

    # 3. Kokeile tunnettuja entiteettinimiä
    candidates = entities or ['Havainto','WaterLevelRegisters','VedenkorkeusHavainto',
                               'WaterLevel','Observation','Vedenkorkeus']
    for entity in candidates:
        url = f'{SYKE_ROOT}/{entity}?$top=2&$format=json'
        try:
            raw = get(url)
            print(f'OK {entity}: {raw[:200]}')
            # Jos toimii, hae oikea data
            from urllib.parse import quote
            filt = f"LocationId eq '04.252.1.001' and Timestamp ge {START}T00:00:00Z and Timestamp le {END}T23:59:59Z"
            data_url = f'{SYKE_ROOT}/{entity}?$filter={quote(filt)}&$orderby=Timestamp%20asc&$top=5000&$format=json'
            raw2 = get(data_url)
            data = json.loads(raw2)
            values = data.get('value', [])
            print(f'SYKE {entity} data: {len(values)} riveja')
            if values:
                ts  = next((k for k in ['Timestamp','Aika'] if k in values[0]), None)
                val = next((k for k in ['Wvalue','Arvo'] if k in values[0]), None)
                rows = [{'date': str(v[ts])[:10], 'value': v[val]} for v in values]
                return {'source':'SYKE','entity':entity,'n':len(rows),'rows':rows,'fetched':END}
        except Exception as e:
            print(f'FAIL {entity}: {e}')

    return {'source':'SYKE','n':0,'rows':[],'fetched':END,'error':'entity not found'}

def fetch_fmi():
    url = (f"{FMI_BASE}?service=WFS&version=2.0.0&request=getFeature"
           f"&storedquery_id=fmi::observations::weather::daily::simple"
           f"&fmisid={FMI_STATION}&parameters=tday,rrday"
           f"&starttime={START}T00:00:00Z&endtime={END}T23:59:59Z")
    print(f'FMI url: {url[:120]}')
    req = urllib.request.Request(url, headers={'User-Agent':'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=30) as r:
        xml = r.read().decode('utf-8')
    times  = [m[1][:10] for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>', xml)]
    pnames = [m[1]      for m in re.finditer(r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>', xml)]
    values = [m[1]      for m in re.finditer(r'<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', xml)]
    rows   = [{'date':times[i],'param':pnames[i],
               'value':None if values[i] in ('NaN','') else float(values[i])}
              for i in range(len(times))]
    print(f'FMI: {len(rows)} riveja')
    return {'source':'FMI','station':FMI_STATION,'fetched':END,'n':len(rows),'rows':rows}

os.makedirs('data/cache', exist_ok=True)
errors = []

try:
    syke = fetch_syke()
    with open('data/cache/syke.json','w') as f: json.dump(syke, f)
    print(f'OK syke.json ({syke["n"]} riveja)')
except Exception as e:
    print(f'FAIL SYKE: {e}')
    errors.append(str(e))

try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json','w') as f: json.dump(fmi, f)
    print(f'OK fmi.json ({fmi["n"]} riveja)')
except Exception as e:
    print(f'FAIL FMI: {e}')
    errors.append(str(e))

if errors:
    print(f'ERRORS: {errors}')
    sys.exit(1)
print('ALL OK')
