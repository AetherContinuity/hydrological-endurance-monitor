"""HEM data fetcher — FMI 10v lyhyemmissä paloissa"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START_YEAR = NOW.year - 10

FMI_BASE = 'https://opendata.fmi.fi/wfs'

# Asemat: Lappeenranta toimii varmasti, muut kokeillaan
FMI_STATIONS = [
    ('101680', 'Kuopio Maaninka'),       # ~20km Iisvedestä, maaseutu ✓
    ('101590', 'Kuopio Savilahti'),      # ~25km, kaupunkiasema
    ('101928', 'Suonenjoki'),            # ~15km, uudempi asema
    ('101756', 'Lappeenranta Lepola'),   # fallback, kaukana mutta pitkä historia
]

def fetch_chunk(station, start, end):
    url = (f"{FMI_BASE}?service=WFS&version=2.0.0&request=getFeature"
           f"&storedquery_id=fmi::observations::weather::daily::simple"
           f"&fmisid={station}&parameters=tday,rrday"
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
    # Kokeile asemia järjestyksessä
    for station_id, station_name in FMI_STATIONS:
        print(f'Kokeillaan: {station_name} ({station_id})')
        # Testaa 1 kuukausi ensin
        test_start = (NOW - timedelta(days=30)).strftime('%Y-%m-%d')
        try:
            test = fetch_chunk(station_id, test_start, END)
            if len(test) > 20:
                print(f'  Toimii: {len(test)} riviä viimeiseltä kuulta')
                break
            else:
                print(f'  Vain {len(test)} riviä — kokeillaan seuraavaa')
        except Exception as e:
            print(f'  Virhe: {e}')
    else:
        print('Kaikki asemat epäonnistuivat!')
        return None

    # Hae 10 vuotta 1-vuoden paloissa
    all_rows = []
    for year in range(START_YEAR, NOW.year + 1):
        ys = f'{year}-01-01'
        ye = f'{year}-12-31' if year < NOW.year else END
        print(f'  {year}: {ys} → {ye}')
        try:
            rows = fetch_chunk(station_id, ys, ye)
            all_rows.extend(rows)
            print(f'    +{len(rows)} riviä')
        except Exception as e:
            print(f'    FAIL: {e}')

    # Deduploi
    seen = set()
    unique = []
    for r in all_rows:
        k = f"{r['date']}-{r['param']}"
        if k not in seen:
            seen.add(k)
            unique.append(r)
    unique.sort(key=lambda x: (x['date'], x['param']))
    print(f'FMI {station_name}: {len(unique)} riviä ({START_YEAR} → {NOW.year})')
    return {'source':'FMI','station':station_id,'station_name':station_name,
            'fetched':END,'n':len(unique),'rows':unique}

os.makedirs('data/cache', exist_ok=True)

try:
    fmi = fetch_fmi()
    if fmi:
        with open('data/cache/fmi.json','w') as f: json.dump(fmi, f)
        print(f'OK fmi.json ({fmi["n"]} riviä)')
    else:
        sys.exit(1)
except Exception as e:
    print(f'FAIL: {e}')
    sys.exit(1)

print('DONE')
# Lisäinfo: Kuopio-asemien testaus
# 101590 Kuopio Savilahti — kaupunkiasema
# 101680 Kuopio Maaninka — maaseutuasema, ~20km Iisvedeltä pohjoiseen
# 101928 Suonenjoki — ~15km Iisvedestä etelään, perustettu myöhemmin
