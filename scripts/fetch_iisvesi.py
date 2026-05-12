"""Iisvesi WSFS — haetaan vedenkorkeus + historiallinen data"""
import urllib.request, re, json, os

BASE = 'https://wwwi2.ymparisto.fi/i2/14/l147221001y'
os.makedirs('data/cache', exist_ok=True)

def get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; ACI-HEM/1.1)',
        'Accept': 'text/html,*/*'
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(), r.geturl()

# 1. Pääsivu — nykyennuste
print(f'GET {BASE}/wqfi.html')
raw, _ = get(f'{BASE}/wqfi.html')
html = raw.decode('utf-8','replace')
with open('data/cache/iisvesi_wqfi.html', 'wb') as f: f.write(raw)
print(f'  {len(raw)} bytes')

# 2. Testaa sanallinen ennuste -sivut — saattavat sisältää historiaa
result = {'source':'SYKE-WSFS','fetched':__import__('datetime').date.today().isoformat()}

for page, desc in [
    ('wlsanafi.html',   'Vedenkorkeus lyhyt sanallinen'),
    ('wksanafi.html',   'Vedenkorkeus kuukausi sanallinen'),
    ('w3sanafi.html',   'Vedenkorkeus 3kk sanallinen'),
    ('qoutsanafi.html', 'Lähtövirtaama sanallinen'),
    ('psanafi.html',    'Sade sanallinen'),
    ('mvssanafi.html',  'Maavesivarasto sanallinen'),
]:
    url = f'{BASE}/{page}'
    try:
        raw2, _ = get(url)
        text = raw2.decode('utf-8','replace')
        print(f'  OK {page}: {len(raw2)}b')
        # Tallenna
        with open(f'data/cache/iisvesi_{page}', 'wb') as f: f.write(raw2)
        # Etsi numerodataa
        wl_vals = re.findall(r'9[78]\.\d{2}', text)
        if wl_vals:
            print(f'    Vedenkorkeus-arvoja: {wl_vals[:10]}')
        # Etsi taulukkodata
        td_cells = [re.sub(r'<[^>]+>','',c).strip() 
                    for c in re.findall(r'<td[^>]*>(.*?)</td>', text, re.I|re.S)]
        num_cells = [c for c in td_cells if re.match(r'^\d{4}-\d{2}|^\d{1,2}\.\d{1,2}\.\d{4}|^9[78]\.\d', c)]
        if num_cells:
            print(f'    Numerosoluia: {num_cells[:10]}')
    except Exception as e:
        print(f'  FAIL {page}: {e}')

# 3. Parsii nykyennuste pääsivulta
txt_match = re.search(r'vedenkorkeus on keskimäärin\s+([\d.]+)&nbsp;m', html, re.I)
peak_match = re.search(r'Suurimman vedenkorkeuden ajankohta on\s+([^<]+)', html)
mhw_match = re.search(r'Korkein havaittu ([\d.]+) m ([\d.]+)', html)
vals = sorted(set(float(v) for v in re.findall(r'(97\.\d{2})', html)))

if txt_match: result['forecast_central_m'] = float(txt_match.group(1))
if peak_match: result['peak_timing'] = peak_match.group(1).strip()
if mhw_match:
    result['mhw_m'] = float(mhw_match.group(1))
    result['mhw_date'] = mhw_match.group(2)
if vals: result['forecast_values_m'] = vals

with open('data/cache/iisvesi.json', 'w') as f:
    json.dump(result, f, indent=2)
print(f'\nOK: {json.dumps(result, indent=2)}')
