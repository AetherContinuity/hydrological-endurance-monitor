"""HEM data fetcher — wwwi2 + FMI"""
import json, sys, re, os, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=365)).strftime('%Y-%m-%d')

FMI_BASE    = 'https://opendata.fmi.fi/wfs'
FMI_STATION = '101756'
WWWI2_BASE  = 'https://wwwi2.ymparisto.fi'

def get(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Accept':'*/*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def fetch_syke_wwwi2():
    """Kokeile wwwi2.ymparisto.fi eri URL-muodoilla"""

    # Tunnus 1403300 = Iisvesi (WSFS asematunnus)
    # Tunnus 0411200 = Saimaa Lauritsala (HYDRO-tunnus)
    tests = [
        # WSFS download-muodot
        f'{WWWI2_BASE}/i2/95/vesiA.html?tunnus=1403300&alku={START}&loppu={END}',
        f'{WWWI2_BASE}/i2/95/vesiA.html?id=1403300&startDate={START}&endDate={END}&format=csv',
        # SYKE avoin data -lataus
        f'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.0/Havainto?Tunniste=1403300&Suure=Vedenkorkeus&alkupvm={START}&loppupvm={END}',
        # Lyhyempi aikaväli testiksi
        f'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.0/Havainto?Tunniste=1403300&Suure=Vedenkorkeus&alkupvm=2026-01-01&loppupvm=2026-05-01',
    ]

    for url in tests:
        print(f'\nKokeillaan: {url[:100]}')
        try:
            raw = get(url, timeout=15)
            print(f'  OK: {len(raw)} bytes')
            print(f'  Preview: {raw[:300]}')
            return raw, url
        except Exception as e:
            print(f'  FAIL: {e}')

    return None, None

def parse_syke(raw, url):
    """Yritä jäsentää eri formaateista"""
    if not raw:
        return []
    text = raw.decode('utf-8', 'replace')

    # JSON?
    if text.strip().startswith('{') or text.strip().startswith('['):
        try:
            data = json.loads(text)
            values = data if isinstance(data, list) else data.get('value', data.get('results', []))
            if values and isinstance(values[0], dict):
                keys = list(values[0].keys())
                print(f'  JSON kentat: {keys}')
                ts  = next((k for k in keys if any(x in k.lower() for x in ['aika','time','pvm','date'])), None)
                val = next((k for k in keys if any(x in k.lower() for x in ['arvo','value','wl','korkeus'])), None)
                if ts and val:
                    return [{'date': str(v[ts])[:10], 'value': v[val]} for v in values]
        except: pass

    # CSV?
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) > 2:
        rows = []
        for line in lines[1:]:
            parts = re.split(r'[;,\t]', line)
            if len(parts) >= 2:
                try:
                    rows.append({'date': parts[0][:10], 'value': float(parts[1].replace(',','.'))})
                except: pass
        if rows:
            return rows
    return []

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
    return {'source':'FMI','station':FMI_STATION,'fetched':END,'n':len(rows),'rows':rows}

os.makedirs('data/cache', exist_ok=True)
errors = []

try:
    raw, url = fetch_syke_wwwi2()
    rows = parse_syke(raw, url)
    syke = {'source':'SYKE-wwwi2','url':url,'fetched':END,'n':len(rows),'rows':rows}
    with open('data/cache/syke.json','w') as f: json.dump(syke, f)
    print(f'\nOK syke.json ({len(rows)} rivejä)')
    if not rows:
        print('VAROITUS: Ei rivejä — SYKE ei palauta dataa Actionsin IP:ltä')
        # Ei virhettä — jatketaan ilman vedenkorkeusdataa
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
    print(f'ERRORS: {errors}')
    sys.exit(1)
print('DONE')
