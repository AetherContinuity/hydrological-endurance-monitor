"""Muonionjoki Muonio WSFS — vedenkorkeus + sanallinen ennuste
Sama rakenne kuin fetch_iisvesi.py, eri BASE-URL ja vesistöalue.

HEM-korjaus 2026-09 (§02b): sama vuodenaikavirhe kuin Iisvedessä (item 1) —
forecast_central_m kaytettiin "nykyisena" arvona. EI KORJATTU TASSA: Muonion
havaintoasema Paikka_Id ei ole tiedossa (WSFS-pisteen 'q6700800y' ja SYKE
Hydrologiarajapinnan numeerisen Paikka_Id:n valilla ei ole suoraa yhteytta,
ja tata ei voitu selvittaa tasta ymparistosta - verkkoyhteys
rajapinnat.ymparisto.fi:hyn on estetty). Selvita Paikka_Id ajamalla:

    GET {proxy}/syke/paikat  (jos reitti listaa Muonion)
  tai suoraan:
    {proxy}/syke?entity=Paikka&$filter=substringof('Muonio',Nimi)

kun Paikka_Id on selvinnyt, kopioi fetch_iisvesi.py:n arvo_to_m/
fetch_syke_series/compute_observed-mekanismi tahan samalla kaavalla (nollakohta
on todennakoisesti ERI kuin Iisvedella - Muonion MNW/MHW on n. 231-234 m,
ei 97-98 m, joten ZERO_POINT_M-hypoteesi pitaa maarittaa erikseen)."""
import urllib.request, re, json, os, html as html_mod
from datetime import date

BASE = 'https://wwwi2.ymparisto.fi/i2/67/q6700800y'
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
    return d

result = {'source':'SYKE-WSFS','station':'q6700800y',
          'river':'Muonionjoki','location':'Muonio',
          'basin':'Tornionjoki 67','fetched':date.today().isoformat()}

for page, key in [('wqfi.html','main'), ('wlsanafi.html','f14'),
                  ('wksanafi.html','f90'), ('wsanafi.html','f365')]:
    try:
        raw = get(f'{BASE}/{page}')
        with open(f'data/cache/muonio_{page}','wb') as f: f.write(raw)
        d = parse_wsfs(raw)
        if key == 'main':
            result.update(d)
            result['forecast_central_m'] = d.get('peak_wl_mean')
            print(f'wqfi: {d.get("peak_wl_mean")} m, huippu {d.get("peak_date_mean")}')
        else:
            result[key] = d
            print(f'{page}: {d.get("peak_wl_mean")} m ({d.get("peak_date_mean")})')
    except Exception as e:
        print(f'{page} virhe: {e}')

if not result.get('forecast_central_m') and result.get('f14'):
    result['forecast_central_m'] = result['f14'].get('peak_wl_mean')
    result['peak_date_mean']     = result['f14'].get('peak_date_mean')

with open('data/cache/muonio.json','w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f'\nOK muonio.json')
