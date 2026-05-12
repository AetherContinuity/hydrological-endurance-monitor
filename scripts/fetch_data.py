"""HEM data fetcher — place=Kuopio tday+rrday + Iisvesi"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW        = datetime.now(timezone.utc)
END        = NOW.strftime('%Y-%m-%d')
START_YEAR = 1940  # Historiallinen data — 1940-luvun kuivuusjakso vertailua varten
FMI_BASE   = 'https://opendata.fmi.fi/wfs'
FMI_PLACE  = 'Kuopio'   # FMI valitsee synoptisen aseman

def wfs_chunk(place, start, end):
    """Hae FMI daily simple yhdelle aikavälille"""
    url = (f"{FMI_BASE}?service=WFS&version=2.0.0&request=getFeature"
           f"&storedquery_id=fmi::observations::weather::daily::simple"
           f"&place={place}&parameters=tday,rrday"
           f"&starttime={start}T00:00:00Z&endtime={end}T23:59:59Z")
    req = urllib.request.Request(url, headers={'User-Agent':'ACI-HEM/1.1'})
    with urllib.request.urlopen(req, timeout=60) as r:
        xml = r.read().decode('utf-8')
    name_m  = re.search(r'<gml:name[^>]*>([^<]+)</gml:name>', xml)
    times   = [m[1][:10] for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>', xml)]
    pnames  = [m[1]      for m in re.finditer(r'<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>', xml)]
    values  = [m[1]      for m in re.finditer(r'<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', xml)]
    rows    = [{'date':times[i],'param':pnames[i],
                'value': None if values[i] in ('NaN','') else float(values[i])}
               for i in range(len(times))]
    station = name_m.group(1).strip() if name_m else place
    return rows, station

def fetch_fmi():
    print(f'FMI place={FMI_PLACE} 10 vuotta ({START_YEAR}-{NOW.year})')
    # Testihaku
    t_start = (NOW - timedelta(days=10)).strftime('%Y-%m-%d')
    rows, sname = wfs_chunk(FMI_PLACE, t_start, END)
    tday_ok = sum(1 for r in rows if r['param']=='tday' and r['value'] is not None)
    print(f'  Testi: {sname}: {len(rows)} riviä, tday={tday_ok}/{len(rows)//2}')

    all_rows = []
    for year in range(START_YEAR, NOW.year + 1):
        ys = f'{year}-01-01'
        ye = f'{year}-12-31' if year < NOW.year else END
        try:
            rows, sn = wfs_chunk(FMI_PLACE, ys, ye)
            all_rows.extend(rows)
            tday = sum(1 for r in rows if r['param']=='tday' and r['value'] is not None)
            print(f'  {year}: +{len(rows)} riviä (tday={tday})')
        except Exception as e:
            print(f'  {year}: FAIL — {e}')

    seen, unique = set(), []
    for r in all_rows:
        k = f"{r['date']}-{r['param']}"
        if k not in seen:
            seen.add(k)
            unique.append(r)
    unique.sort(key=lambda x: (x['date'], x['param']))
    print(f'FMI {sname}: {len(unique)} riviä')
    return {'source':'FMI','station':FMI_PLACE,'station_name':sname,
            'fetched':END,'n':len(unique),'rows':unique}

os.makedirs('data/cache', exist_ok=True)

try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json','w') as f: json.dump(fmi, f)
    print(f'OK fmi.json ({fmi["n"]} riviä · {fmi["station_name"]})')
except Exception as e:
    print(f'FAIL: {e}')
    sys.exit(1)

print('DONE')
