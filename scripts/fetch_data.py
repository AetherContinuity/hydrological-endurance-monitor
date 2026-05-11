"""HEM data fetcher — FMI 10 vuotta + Iisvesi WSFS"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
# 10 vuotta taaksepäin
START = f"{NOW.year - 10}-{NOW.month:02d}-01"

FMI_BASE    = 'https://opendata.fmi.fi/wfs'
# Asemat prioriteettijärjestyksessä — lähimpänä Iisvettä ensin
FMI_STATIONS = [
    ('101928', 'Suonenjoki'),       # ~15km Iisvedestä
    ('101680', 'Kuopio Maaninka'),  # ~25km, maatalousasema
    ('101590', 'Kuopio Savilahti'), # ~30km
    ('101756', 'Lappeenranta'),     # fallback
]
FMI_STATION = FMI_STATIONS[0][0]   # Käytä ensisijaisesti Suonenjokea

def fetch_fmi_chunk(start, end):
    """Hae yksi aikaikkuna FMI:stä"""
    url = (f"{FMI_BASE}?service=WFS&version=2.0.0&request=getFeature"
           f"&storedquery_id=fmi::observations::weather::daily::simple"
           f"&fmisid={FMI_STATION}&parameters=tday,rrday"
           f"&starttime={start}T00:00:00Z&endtime={end}T23:59:59Z")
    req = urllib.request.Request(url, headers={'User-Agent':'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=60) as r:
        xml = r.read().decode('utf-8')
    times  = [m[1][:10] for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>', xml)]
    pnames = [m[1]      for m in re.finditer(r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>', xml)]
    values = [m[1]      for m in re.finditer(r'<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', xml)]
    return [{'date':times[i],'param':pnames[i],
             'value':None if values[i] in ('NaN','') else float(values[i])}
            for i in range(len(times))]

def fetch_fmi():
    """Hae FMI-data 2-vuoden paloissa (FMI ei tykkää liian pitkistä hauista)"""
    all_rows = []
    # Jaetaan 2-vuoden paloihin
    chunk_start = datetime.strptime(START, '%Y-%m-%d')
    chunk_end_dt = datetime.now(timezone.utc).replace(tzinfo=None)

    while chunk_start < chunk_end_dt:
        cs = chunk_start.strftime('%Y-%m-%d')
        ce = min(chunk_start + timedelta(days=730), chunk_end_dt).strftime('%Y-%m-%d')
        print(f'  FMI: {cs} → {ce}')
        try:
            rows = fetch_fmi_chunk(cs, ce)
            all_rows.extend(rows)
            print(f'    +{len(rows)} riviä')
        except Exception as e:
            print(f'    FAIL: {e}')
        chunk_start += timedelta(days=731)

    # Poista duplikaatit, järjestä
    seen = set()
    unique = []
    for r in all_rows:
        k = f"{r['date']}-{r['param']}"
        if k not in seen:
            seen.add(k)
            unique.append(r)
    unique.sort(key=lambda x: (x['date'], x['param']))
    print(f'FMI yhteensä: {len(unique)} riviä ({START} → {END})')
    return {'source':'FMI','station':FMI_STATION,'fetched':END,'n':len(unique),'rows':unique}

os.makedirs('data/cache', exist_ok=True)

# FMI
try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json','w') as f: json.dump(fmi, f)
    print(f'OK fmi.json ({fmi["n"]} riviä)')
except Exception as e:
    print(f'FAIL FMI: {e}')
    sys.exit(1)

print('DONE')
