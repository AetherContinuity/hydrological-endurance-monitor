"""Iisvesi WSFS-asema: https://wwwi2.ymparisto.fi/i2/14/l147221001y/wqfi.html"""
import urllib.request, re, json, os

BASE = 'https://wwwi2.ymparisto.fi/i2/14/l147221001y'

def get(path):
    url = BASE + path
    print(f'GET {url}')
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Accept':'*/*'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(), r.headers.get('Content-Type','')

os.makedirs('data/cache', exist_ok=True)

# Kokeile eri sub-sivuja
paths = [
    '/wqfi.html',
    '/wqfi.html#wl',
    '/wl_fi.html',
    '/obs_fi.html',
    '/data.csv',
    '/havainnotfi.html',
]

for p in paths:
    try:
        raw, ct = get(p)
        print(f'  OK: {len(raw)}b [{ct}]')
        print(f'  Preview: {raw[:300]}')
        # Tallenna debug
        fname = 'data/cache/iisvesi_' + p.strip('/').replace('/','_').replace('#','_')
        with open(fname, 'wb') as f:
            f.write(raw)
        print(f'  Tallennettu: {fname}')
        break
    except Exception as e:
        print(f'  FAIL: {e}')
