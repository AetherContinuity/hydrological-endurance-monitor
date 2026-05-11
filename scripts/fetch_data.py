"""HEM data fetcher — testaa SYKE tunnuksia"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=30)).strftime('%Y-%m-%d')  # Lyhyt testi

SYKE_BASE   = 'https://rajapinnat.ymparisto.fi/api/Hydrologiarajapinta/1.0/Havainto'
FMI_BASE    = 'https://opendata.fmi.fi/wfs'
FMI_STATION = '101756'

def try_syke(tunnus, suure='Vedenkorkeus'):
    url = f"{SYKE_BASE}?Tunniste={tunnus}&Suure={suure}&alkupvm={START}&loppupvm={END}"
    try:
        req = urllib.request.Request(url, headers={'Accept':'application/json','User-Agent':'ACI-HEM/1.1'})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
        preview = raw[:200].decode('utf-8','replace')
        print(f'  {tunnus}: OK ({len(raw)}b) — {preview}')
        return True
    except Exception as e:
        print(f'  {tunnus}: {e}')
        return False

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

# Kokeile tunnettuja asematunnuksia
print('=== SYKE asematunnisteiden testaus ===')
candidates = [
    '1403300',  # Iisvesi DeepSeek
    '1900',     # Saimaa Lauritsala (PaikkaId)
    '1901',     # Saimaa Lauritsala vanha
    '0411200',  # Tunnus-muoto
    '1898',     # Saimaa Ristiina
    '1889',     # Haukivesi Oravi
    '1851',     # Kallavesi Itkonniemi
]
working = None
for t in candidates:
    if try_syke(t):
        working = t
        break

# Kokeile myös ilman Suure-rajausta
if not working:
    print('\n=== Ilman Suure-rajausta ===')
    for t in ['1403300', '1900']:
        url = f"{SYKE_BASE}?Tunniste={t}&alkupvm={START}&loppupvm={END}"
        try:
            req = urllib.request.Request(url, headers={'Accept':'application/json','User-Agent':'ACI-HEM/1.1'})
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
            print(f'  {t} (no suure): OK — {raw[:200]}')
            working = t
            break
        except Exception as e:
            print(f'  {t} (no suure): {e}')

# Kirjoita tulos
if working:
    print(f'\n✓ Toimiva tunnus: {working}')
    with open('data/cache/syke.json','w') as f:
        json.dump({'source':'SYKE','tunnus':working,'status':'found','fetched':END}, f)
else:
    print('\n✗ Ei toimivaa tunnusta löydetty')
    with open('data/cache/syke.json','w') as f:
        json.dump({'source':'SYKE','status':'not_found','fetched':END,'n':0,'rows':[]}, f)

# FMI aina
try:
    fmi = fetch_fmi()
    with open('data/cache/fmi.json','w') as f: json.dump(fmi, f)
    print(f'OK fmi.json ({fmi["n"]} rivejä)')
except Exception as e:
    print(f'FAIL FMI: {e}')
    sys.exit(1)

print('DONE')
