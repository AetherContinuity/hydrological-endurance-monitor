"""Iisvesi WSFS: https://wwwi2.ymparisto.fi/i2/14/l147221001y/wqfi.html"""
import urllib.request, re, json, os

URL = 'https://wwwi2.ymparisto.fi/i2/14/l147221001y/wqfi.html'
os.makedirs('data/cache', exist_ok=True)

print(f'GET {URL}')
req = urllib.request.Request(URL, headers={'User-Agent':'Mozilla/5.0','Accept':'*/*'})
with urllib.request.urlopen(req, timeout=20) as r:
    raw = r.read()
html = raw.decode('utf-8','replace')
print(f'  {len(raw)} bytes')

# Tallenna raaka HTML
with open('data/cache/iisvesi_wqfi.html','wb') as f:
    f.write(raw)

# Parsii nykyennuste ja historiatiedot
result = {'source':'SYKE-WSFS-Iisvesi','url':URL,'fetched':__import__('datetime').date.today().isoformat()}

# Nykyennuste (97.51 m tyyppiset)
vals_97 = re.findall(r'(97\.\d{2})', html)
vals_98 = re.findall(r'(98\.\d{2})', html)
all_vals = vals_97 + vals_98
if all_vals:
    floats = sorted(set(float(v) for v in all_vals))
    forecast = floats[len(floats)//2]  # mediaani
    result['forecast_m'] = forecast
    result['forecast_range'] = [min(floats), max(floats)]
    print(f'  Ennustearvot: {floats}')
    print(f'  Mediaani: {forecast} m')

# Lyhyt sanallinen ennuste
txt_match = re.search(r'vedenkorkeus on keskimäärin\s+([\d.]+)&nbsp;m', html, re.I)
if txt_match:
    result['forecast_central_m'] = float(txt_match.group(1))
    print(f'  Keskiennuste: {result["forecast_central_m"]} m')

# Huipun ajankohta
peak_match = re.search(r'Suurimman vedenkorkeuden ajankohta on\s+([^<]+)', html)
if peak_match:
    result['peak_timing'] = peak_match.group(1).strip()
    print(f'  Huippuajankohta: {result["peak_timing"]}')

# MHW historiallinen
mhw_match = re.search(r'Korkein havaittu ([\d.]+) m ([\d.]+)', html)
if mhw_match:
    result['mhw_m'] = float(mhw_match.group(1))
    result['mhw_date'] = mhw_match.group(2)
    print(f'  MHW: {result["mhw_m"]} m ({result["mhw_date"]})')

with open('data/cache/iisvesi.json','w') as f:
    json.dump(result, f, indent=2)
print(f'OK: data/cache/iisvesi.json')
print(json.dumps(result, indent=2))
