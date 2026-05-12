"""Iisvesi WSFS — vedenkorkeus + sanallinen ennuste 14pv/90pv/365pv"""
import urllib.request, re, json, os, html as html_mod
from datetime import date

BASE = 'https://wwwi2.ymparisto.fi/i2/14/l147221001y'
os.makedirs('data/cache', exist_ok=True)

def get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'text/html,*/*'
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def parse_wsfs(raw):
    text = re.sub(r'<[^>]+>', ' ', raw.decode('utf-8','replace'))
    text = html_mod.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    d = {}
    m = re.search(r'Maksimivedenkorkeuden ajankohta on keskimäärin ([\d.]+\.\d{4})', text)
    if m: d['peak_date_mean'] = m.group(1)
    m = re.search(r'Maksimivedenkorkeus on keskimäärin ([\d.]+) m', text)
    if m: d['peak_wl_mean'] = float(m.group(1))
    m = re.search(r'90 % todennäköisyydellä välillä ([\d.]+) - ([\d.]+) m', text)
    if m: d['peak_p5'] = float(m.group(1)); d['peak_p95'] = float(m.group(2))
    m = re.search(r'Vuosien (\d{4}) - (\d{4}) välisenä aikana keskimääräinen vuoden maksimivedenkorkeus on ollut ([\d.]+) m', text)
    if m: d['ref_years'] = f"{m.group(1)}-{m.group(2)}"; d['ref_mean_max'] = float(m.group(3))
    m = re.search(r'Pienin havaittu vuoden maksimivedenkorkeus on ([\d.]+) m', text)
    if m: d['ref_min_max'] = float(m.group(1))
    m = re.search(r'Suurin havaittu vedenkorkeus on ([\d.]+) m.*?(\d{2}\.\d{2}\.\d{4})', text)
    if m: d['mhw_m'] = float(m.group(1)); d['mhw_date'] = m.group(2)
    forecasts = []
    for match in re.finditer(
        r'(\w[\w\s]+kuluttua,\s+eli\s+([\d.]+))\s+'
        r'vedenkorkeus on keskimäärin\s+([\d.]+)\s+m\s+'
        r'ja 50 % todennäköisyydellä vedenkorkeus on välillä\s+([\d.]+)\s+-\s+([\d.]+)\s+m', text):
        fc = {'label': match.group(1).strip(), 'date': match.group(2),
              'mean': float(match.group(3)), 'p25': float(match.group(4)), 'p75': float(match.group(5))}
        after = text[match.end():match.end()+250]
        m2 = re.search(r'5 % todennäköisyydellä yli ([\d.]+) m', after)
        m3 = re.search(r'5 % todennäköisyydellä alle ([\d.]+) m', after)
        if m2: fc['p95'] = float(m2.group(1))
        if m3: fc['p5'] = float(m3.group(1))
        forecasts.append(fc)
    d['forecasts'] = forecasts
    return d

result = {'source':'SYKE-WSFS','fetched':date.today().isoformat()}

# Pääsivu
try:
    raw = get(f'{BASE}/wqfi.html')
    with open('data/cache/iisvesi_wqfi.html','wb') as f: f.write(raw)
    d = parse_wsfs(raw)
    result.update(d)
    result['forecast_central_m'] = d.get('peak_wl_mean')
    print(f'wqfi: {d.get("peak_wl_mean")} m, huippu {d.get("peak_date_mean")}')
except Exception as e:
    print(f'wqfi virhe: {e}')

# Sanallinen 14pv / 90pv / 365pv
for page, key in [('wlsanafi.html','f14'), ('wksanafi.html','f90'), ('w3sanafi.html','f365')]:
    try:
        raw = get(f'{BASE}/{page}')
        with open(f'data/cache/iisvesi_{page}','wb') as f: f.write(raw)
        d = parse_wsfs(raw)
        result[key] = d
        print(f'{page}: huippu {d.get("peak_wl_mean")} m ({d.get("peak_date_mean")})')
        if d.get('forecasts'):
            for fc in d['forecasts']:
                print(f'  {fc["date"]}: {fc["mean"]} m (p25={fc.get("p25")} p75={fc.get("p75")})')
    except Exception as e:
        print(f'{page} virhe: {e}')

with open('data/cache/iisvesi.json','w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f'\nOK iisvesi.json')
