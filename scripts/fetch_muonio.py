"""Muonionjoki Muonio WSFS — vedenkorkeus + sanallinen ennuste
+ havaittu vedenkorkeus (SYKE OData, aci-nve-proxy /syke) SD:n laskentaan.
Sama rakenne kuin fetch_iisvesi.py, eri BASE-URL ja vesistoalue.

HEM-korjaus 2026-09 (§02b): sama vuodenaikavirhe kuin Iisvedessa - korjattu
samalla mekanismilla. Muonion havaintoasema (Paikka_Id 2532, kayttajan
2026-09-17 SYKE-tarkistus - sama asema kuin WSFS q6700800y) loytyi, MUTTA:
- Korkeusjarjestelman nollakohtaa EI ole vahvistettu Muoniolle (vain
  Iisvedelle/1966). Haetaan dynaamisesti VedenkTasoTieto:sta ajon aikana;
  EI turvallista fallback-vakiota kuten Iisvedella (NN_FALLBACK_ZERO_M),
  koska sita ei ole riippumattomasti tarkistettu - jos dynaaminen haku
  epaonnistuu, observed_m jaa None:ksi (ei arvausta).
- Ei tiedossa vastaavaa lasku-uoman virtaama-asemaa kuin Iisveden
  Nokisenkoski (Paikka_Id 1005) - RF pysyy NVE-fallbackissa Muoniolle."""
import urllib.request, urllib.parse, re, json, os, html as html_mod
from datetime import date, timedelta

BASE = 'https://wwwi2.ymparisto.fi/i2/67/q6700800y'
PROXY_BASE = 'https://aci-nve-proxy.ruotsalainen-marko.workers.dev'

PAIKKA_ID_WL = 2532
SUURE_ID_WL = 1  # oletus (sama kuin Iisvedella) - EI VARMISTETTU Muoniolle

DOY_REF_START_YEAR = 1991
DOY_REF_END_YEAR = 2020

os.makedirs('data/cache', exist_ok=True)

def get(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'text/html,application/json,*/*'
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()

def fetch_syke_paged(entity, filt, orderby='Aika asc', page_size=1000, max_pages=50):
    """Ks. fetch_iisvesi.py - sama sivutuslogiikka (palvelin rajoittaa
    1000 riviin/kutsu $top:sta riippumatta)."""
    out = []
    skip = 0
    for _ in range(max_pages):
        qs = f"entity={entity}&$filter={urllib.parse.quote(filt)}&$top={page_size}&$skip={skip}"
        if orderby:
            qs += f"&$orderby={urllib.parse.quote(orderby)}"
        url = f"{PROXY_BASE}/syke?{qs}"
        try:
            raw = get(url)
            data = json.loads(raw)
        except Exception as e:
            print(f'  SYKE-sivu skip={skip} epaonnistui: {e}')
            break
        rows = data.get('value') if isinstance(data, dict) else None
        if rows is None and isinstance(data, dict):
            rows = data.get('d', {}).get('results', [])
        rows = rows or []
        out.extend(rows)
        if len(rows) < page_size:
            break
        skip += page_size
    return out

def fetch_zero_point_m(paikka_id):
    """Kentat vahvistettu Iisvedelle 2026-09-17 (Paikka_Id, Korkeustaso_Id,
    TasoKoordinaatisto, Tasokorjaus cm) - oletetaan sama skeema Muoniolle,
    EI erikseen vahvistettu. Ei turvallista fallback-arvoa - epaonnistuessa
    palauttaa (None, False), ei arvausta."""
    filt = f"Paikka_Id eq {paikka_id}"
    rows = fetch_syke_paged('VedenkTasoTieto', filt, orderby=None, page_size=50, max_pages=1)
    if not rows:
        print(f'  VAROITUS: Muonio VedenkTasoTieto tyhja (Paikka_Id={paikka_id}) - ei nollakohtaa')
        return None, False
    for row in rows:
        if str(row.get('TasoKoordinaatisto', '')).strip().upper() == 'NN':
            tasokorjaus = row.get('Tasokorjaus')
            if tasokorjaus is not None:
                try:
                    zero_m = float(tasokorjaus) / 100.0
                    print(f'  Muonio VedenkTasoTieto: NN-nollakohta {zero_m} m (Tasokorjaus={tasokorjaus} cm)')
                    return zero_m, True
                except (TypeError, ValueError):
                    pass
    print(f'  VAROITUS: Muonio VedenkTasoTieto ei sisaltanyt NN-rivia, raaka vastaus: {rows}')
    return None, False

def fetch_syke_series(paikka_id, suure_id, start_dt, end_dt, zero_point_m):
    filt = (
        f"Paikka_Id eq {paikka_id} and Suure_Id eq {suure_id}"
        f" and Aika ge datetime'{start_dt:%Y-%m-%d}T00:00:00'"
        f" and Aika le datetime'{end_dt:%Y-%m-%d}T23:59:59'"
    )
    rows = fetch_syke_paged('Vedenkorkeus', filt)
    out = []
    for r in rows:
        arvo, aika = r.get('Arvo'), r.get('Aika')
        if arvo is None or aika is None:
            continue
        try:
            val = float(arvo)
        except (TypeError, ValueError):
            continue
        out.append({'date': str(aika)[:10], 'm': round(zero_point_m + val / 100.0, 2), 'raw': r})
    return out

def compute_observed(today, norm_m):
    """Sama SD_kevat/SD_nyt-mekanismi kuin Iisvedessa (fetch_iisvesi.py).
    norm_m annetaan kutsujalta (WSFS-sivulta skreipattu ref_mean_max),
    ei erillista NORM_M-vakiota kuten Iisvedella."""
    result = {
        'zero_point_m': None, 'zero_point_verified': False,
        'observed_m': None, 'observed_date': None,
        'spring_peak_m': None, 'spring_peak_locked': False,
        'sd_kevat': None,
        'doy_avg_m': None, 'doy_ref_years': f'{DOY_REF_START_YEAR}-{DOY_REF_END_YEAR}',
        'doy_ref_n_years': 0, 'sd_nyt': None,
        'data_errors': [],
    }
    zero_point_m, verified = fetch_zero_point_m(PAIKKA_ID_WL)
    result['zero_point_m'], result['zero_point_verified'] = zero_point_m, verified
    if zero_point_m is None:
        result['data_errors'].append('zero_point_m: VedenkTasoTieto ei antanut NN-riviä')
        return result  # ei arvausta - kaikki muu jaa None:ksi

    recent = fetch_syke_series(PAIKKA_ID_WL, SUURE_ID_WL, today - timedelta(days=14), today, zero_point_m)
    if recent:
        result['observed_m'] = recent[-1]['m']
        result['observed_date'] = recent[-1]['date']
    else:
        result['data_errors'].append('observed_m: Vedenkorkeus-haku tyhjä (viim. 14pv)')

    if norm_m is not None:
        spring_start = date(today.year, 3, 1)
        spring_end = min(date(today.year, 7, 31), today)
        if spring_end >= spring_start:
            spring = fetch_syke_series(PAIKKA_ID_WL, SUURE_ID_WL, spring_start, spring_end, zero_point_m)
            if spring:
                peak = max(spring, key=lambda r: r['m'])
                result['spring_peak_m'] = peak['m']
                result['spring_peak_locked'] = today > date(today.year, 7, 31)
                result['sd_kevat'] = round(max(0, min(1, (norm_m - peak['m']) / 0.90)), 3)
            else:
                result['data_errors'].append(f'spring_peak_m: Vedenkorkeus-haku tyhjä ({spring_start}..{spring_end})')

    doy_filt = (
        f"Paikka_Id eq {PAIKKA_ID_WL} and Suure_Id eq {SUURE_ID_WL}"
        f" and month(Aika) eq {today.month} and day(Aika) eq {today.day}"
        f" and year(Aika) ge {DOY_REF_START_YEAR} and year(Aika) le {DOY_REF_END_YEAR}"
    )
    doy_rows = fetch_syke_paged('Vedenkorkeus', doy_filt)
    if not doy_rows:
        result['data_errors'].append(f'doy_avg_m: Vedenkorkeus-haku tyhjä ({doy_filt})')
    doy_values = []
    for r in doy_rows:
        try:
            doy_values.append(zero_point_m + float(r.get('Arvo')) / 100.0)
        except (TypeError, ValueError):
            continue
    if doy_values:
        result['doy_avg_m'] = round(sum(doy_values) / len(doy_values), 2)
        result['doy_ref_n_years'] = len(doy_values)
        if result['observed_m'] is not None:
            result['sd_nyt'] = round(max(0, min(1, (result['doy_avg_m'] - result['observed_m']) / 0.90)), 3)

    if result['data_errors']:
        print(f"  data_errors: {result['data_errors']}")

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

# Havaittu vedenkorkeus + SD_kevat/SD_nyt (§02b-korjaus)
print('\nSYKE havaintosarja (Paikka_Id 2532):')
try:
    norm_m = result.get('ref_mean_max')  # WSFS-sivulta skreipattu, ei erillista vakiota
    obs = compute_observed(date.today(), norm_m)
    result['observed'] = obs
    print(f"  observed_m={obs['observed_m']} ({obs['observed_date']}, nollakohta={obs['zero_point_m']}) "
          f"sd_kevat={obs['sd_kevat']} sd_nyt={obs['sd_nyt']}")
except Exception as e:
    print(f'  havaintohaku epaonnistui: {e}')
    result['observed'] = None

with open('data/cache/muonio.json','w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f'\nOK muonio.json')
