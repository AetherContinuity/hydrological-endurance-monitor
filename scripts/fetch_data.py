"""HEM data fetcher — wwwi2 HTML parser korjattu + FMI"""
import json, sys, re, os, urllib.request
from datetime import datetime, timedelta, timezone

NOW   = datetime.now(timezone.utc)
END   = NOW.strftime('%Y-%m-%d')
START = (NOW - timedelta(days=365)).strftime('%Y-%m-%d')

FMI_BASE    = 'https://opendata.fmi.fi/wfs'
FMI_STATION = '101756'
# Iisvesi tunnus 1403300, Saimaa Lauritsala tunnus 1900
SYKE_TUNNUS = '1403300'

def parse_wwwi2_html(html_bytes):
    """Parsii wwwi2.ymparisto.fi HTML-taulukon vedenkorkeusdata"""
    html = html_bytes.decode('utf-8', 'replace') if isinstance(html_bytes, bytes) else html_bytes

    rows = []
    # Hae kaikki <td>-solut puhtaana tekstinä
    cells = re.findall(r'<td[^>]*>(.*?)</td>', html, re.IGNORECASE|re.DOTALL)
    cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]

    i = 0
    while i < len(cells) - 1:
        c = cells[i]
        # Tunnista fi-päivämäärä dd.mm.yyyy
        dm = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', c)
        if dm:
            d, m, y = dm.groups()
            date_str = f"{y}-{int(m):02d}-{int(d):02d}"
            val_raw = cells[i+1].replace(',','.').replace(' ','')
            val_m = re.match(r'^-?(\d+\.?\d*)$', val_raw)
            if val_m:
                rows.append({'date': date_str, 'value': float(val_raw)})
                i += 2
                continue
        i += 1

    return sorted(rows, key=lambda x: x['date'])

def fetch_syke():
    url = (f'https://wwwi2.ymparisto.fi/i2/95/vesiA.html'
           f'?tunnus={SYKE_TUNNUS}&alku={START}&loppu={END}')
    print(f'SYKE: {url}')
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; ACI-HEM/1.1)',
        'Accept': 'text/html,*/*'
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
    print(f'  bytes: {len(raw)}')

    rows = parse_wwwi2_html(raw)
    print(f'  parsed rows: {len(rows)}')

    if rows:
        print(f'  ensimmäinen: {rows[0]}')
        print(f'  viimeisin:   {rows[-1]}')
        # Tarkista onko arvoissa järkeä (vedenkorkeus ~97-99m NN)
        vals = [r['value'] for r in rows]
        print(f'  min={min(vals):.2f} max={max(vals):.2f} mean={sum(vals)/len(vals):.2f}')

    return {'source':'SYKE-wwwi2','tunnus':SYKE_TUNNUS,
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
    if syke['n'] == 0:
        print('HUOM: 0 riviä — tarkista HTML-rakenne')
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
