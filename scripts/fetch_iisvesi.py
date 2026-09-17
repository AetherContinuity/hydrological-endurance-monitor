"""Iisvesi WSFS — vedenkorkeus + sanallinen ennuste 14pv/90pv/365pv
+ havaittu vedenkorkeus (SYKE OData, aci-nve-proxy /syke) SD:n laskentaan.

HEM-korjaus 2026-09 (§02): forecast_central_m (WSFS-ennusteen kevathuipun
keskiarvo) oli aiemmin virheellisesti kaytossa "nykyisena" vedenkorkeutena
ympari vuoden -> SD-vaje laskettiin syyskuun arvosta kevathuippukaavalla
(vuodenaikavirhe). Tama skripti hakee nyt myos HAVAITUN vedenkorkeuden
SYKE:n Hydrologiarajapinnasta ja laskee SD_kevat/SD_nyt havainnoista.
forecast_central_m/f14/f90/f365 sailyvat ENNUSTEKENTTINA, ei muuteta."""
import urllib.request, urllib.parse, re, json, os, html as html_mod
from datetime import date, datetime, timedelta

BASE = 'https://wwwi2.ymparisto.fi/i2/14/l147221001y'
PROXY_BASE = 'https://aci-nve-proxy.ruotsalainen-marko.workers.dev'

# Havaintoasema: Paikka_Id 1966 (asema 1403300), Suure_Id 1 = vedenkorkeus.
PAIKKA_ID = 1966
SUURE_ID = 1

# HYPOTEESI, EI VAHVISTETTU: nollakohta 96.92 m NN, yksikko senttia
# (Arvo/100). Nykyinen havaintoarvo 47 -> 96.92+0.47 = 97.39 m, joka
# tasmaa WSFS-sivun nykyhavaintoon. Tata EI ole varmistettu SYKE:n omasta
# Korkeustaso/VedenkTasoTieto-metadatasta (ei verkkoyhteytta siihen tasta
# ymparistosta) - tarkista ensimmaisen live-ajon tulos ennen kuin
# luotetaan tahan arvoon tuotannossa.
ZERO_POINT_M = 96.92

NORM_M = 98.01  # keskimaarainen vuotuinen kevathuippu, WSFS ka 1910-2025

os.makedirs('data/cache', exist_ok=True)

def get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'text/html,application/json,*/*'
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def arvo_to_m(arvo):
    """Vedenkorkeus.Arvo (kokonaisluku) -> metria NN. Ks. ZERO_POINT_M-huomautus."""
    return round(ZERO_POINT_M + arvo / 100.0, 2)

def fetch_syke_series(paikka_id, suure_id, start_dt, end_dt):
    """Hakee havaitun vedenkorkeussarjan aci-nve-proxyn /syke-reitin kautta.
    OData v3: EI $format-parametria, paivamaarat datetime'YYYY-MM-DDTHH:MM:SS'."""
    filt = (
        f"Paikka_Id eq {paikka_id} and Suure_Id eq {suure_id}"
        f" and Aika ge datetime'{start_dt:%Y-%m-%d}T00:00:00'"
        f" and Aika le datetime'{end_dt:%Y-%m-%d}T23:59:59'"
    )
    url = f"{PROXY_BASE}/syke?entity=Vedenkorkeus&$filter={urllib.parse.quote(filt)}&$orderby=Aika+asc&$top=5000"
    try:
        raw = get(url)
    except Exception as e:
        print(f'SYKE-haku epaonnistui ({start_dt.date()}..{end_dt.date()}): {e}')
        return []
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f'SYKE-vastaus ei JSON: {e}')
        return []
    rows = data.get('value') if isinstance(data, dict) else None
    if rows is None and isinstance(data, dict):
        rows = data.get('d', {}).get('results', [])
    out = []
    for r in rows or []:
        arvo, aika = r.get('Arvo'), r.get('Aika')
        if arvo is None or aika is None:
            continue
        out.append({'date': str(aika)[:10], 'm': arvo_to_m(arvo)})
    return out

def compute_observed(today):
    """SD_kevat (lukittu kevaan jalkeen, koska maalis-heinakuu-ikkuna ei
    enaa kasva) ja SD_nyt (vertailu saman vuodenpaivan pitkan aikavalin
    keskiarvoon). Palauttaa None-kentat jos SYKE-haku ei onnistu -
    ei arvausta puuttuvan datan tilalle."""
    result = {
        'zero_point_hypothesis_m': ZERO_POINT_M,
        'zero_point_verified': False,
        'observed_m': None, 'observed_date': None,
        'spring_peak_m': None, 'spring_peak_locked': False,
        'sd_kevat': None,
        'doy_avg_m': None, 'doy_avg_years': 0,
        'sd_nyt': None,
    }

    # 1) Viimeisin havainto (viim. 14 pv)
    recent = fetch_syke_series(PAIKKA_ID, SUURE_ID, today - timedelta(days=14), today)
    if recent:
        last = recent[-1]
        result['observed_m'] = last['m']
        result['observed_date'] = last['date']

    # 2) Kevaan huippu (maalis-heinakuu, kuluva vuosi). Lukittu automaattisesti
    #    heinakuun jalkeen, koska ikkunan ulkopuolelle ei enaa tule havaintoja.
    spring_start = date(today.year, 3, 1)
    spring_end = min(date(today.year, 7, 31), today)
    if spring_end >= spring_start:
        spring = fetch_syke_series(PAIKKA_ID, SUURE_ID, spring_start, spring_end)
        if spring:
            peak = max(spring, key=lambda r: r['m'])
            result['spring_peak_m'] = peak['m']
            result['spring_peak_locked'] = today > date(today.year, 7, 31)
            result['sd_kevat'] = round(max(0, min(1, (NORM_M - peak['m']) / 0.90)), 3)

    # 3) Saman vuodenpaivan pitka aikavalin keskiarvo: +-5 pv ikkuna,
    #    viimeiset 10 vuotta. Pieni maara pienia hakuja per vuosi, ei
    #    yhta valtavaa monen vuosikymmenen hakua (OData-sivutusta valtellaan).
    doy_values = []
    for years_back in range(1, 11):
        try:
            center = today.replace(year=today.year - years_back)
        except ValueError:
            center = today.replace(year=today.year - years_back, day=28)  # 29.2.
        win_start = center - timedelta(days=5)
        win_end = center + timedelta(days=5)
        window = fetch_syke_series(PAIKKA_ID, SUURE_ID, win_start, win_end)
        doy_values.extend(r['m'] for r in window)
    if doy_values:
        result['doy_avg_m'] = round(sum(doy_values) / len(doy_values), 2)
        result['doy_avg_years'] = 10
        if result['observed_m'] is not None:
            result['sd_nyt'] = round(max(0, min(1, (result['doy_avg_m'] - result['observed_m']) / 0.90)), 3)

    return result

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
    result['forecast_central_m'] = d.get('peak_wl_mean')  # päivitetään f14:stä jos None
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

# 4. Kokeile graafiSivu historiallisella periodilla
print('\nGraafiSivu-testaus:')
for period in ['100x365','50x365','10x365']:
    url = f'https://wwwi2.ymparisto.fi/i2/graafiSivu.html?pointId=l147221001y&variable=w2&lang=fi&period={period}'
    try:
        raw = get(url)
        text = raw.decode('utf-8','replace')
        import re
        nums = re.findall(r'9[78]\.\d{2}', text)
        years = re.findall(r'(?:19[3-9]\d|20[01]\d|202[0-6])', text)
        print(f'  period={period}: {len(raw)}b, wl:{len(nums)}, vuosia:{len(set(years))}')
        if nums: print(f'    WL: {nums[:10]}')
        if years: print(f'    Vuodet: {sorted(set(years))[:15]}')
        fname = f'data/cache/iisvesi_graafi_{period}.html'
        with open(fname,'wb') as f: f.write(raw)
    except Exception as e:
        print(f'  period={period}: FAIL {e}')

# Varmista forecast_central_m f14:stä
if not result.get('forecast_central_m') and result.get('f14'):
    result['forecast_central_m'] = result['f14'].get('peak_wl_mean')
    result['peak_date_mean']     = result['f14'].get('peak_date_mean')
    result['ref_mean_max']       = result['f14'].get('ref_mean_max')
    result['ref_min_max']        = result['f14'].get('ref_min_max')
    result['mhw_m']              = result['f14'].get('mhw_m')
    result['mhw_date']           = result['f14'].get('mhw_date')

# Havaittu vedenkorkeus + SD_kevat/SD_nyt (§02-korjaus, ei WSFS-ennuste)
print('\nSYKE havaintosarja (Paikka_Id 1966, Suure_Id 1):')
try:
    obs = compute_observed(date.today())
    result['observed'] = obs
    print(f"  observed_m={obs['observed_m']} ({obs['observed_date']}) "
          f"spring_peak_m={obs['spring_peak_m']} sd_kevat={obs['sd_kevat']} "
          f"doy_avg_m={obs['doy_avg_m']} sd_nyt={obs['sd_nyt']}")
except Exception as e:
    print(f'  havaintohaku epaonnistui: {e}')
    result['observed'] = None

with open('data/cache/iisvesi.json','w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f'\nOK iisvesi.json')
