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

# Havaintoasema (vahvistettu 2026-09-17, kayttajan suora SYKE-tarkistus):
# Paikka_Id 1966 = Iisveden VEDENKORKEUS (Suure_Id 1, cm).
# Paikka_Id 1005 = Nokisenkoski VIRTAAMA (Suure_Id 2, m3/s) - Iisveden
# lasku-uoma (sama asematunnus 1403300 kuin 1966:lla, vahvistettu myos
# siita etta 2026 virtaamahuippu 27.2 m3/s osui samalle paivalle 17.6.
# kuin vedenkorkeuden huippu). EI SAMA PAIKKA kuin 1966 - eri Suure,
# eri fysikaalinen suure (virtaama vs. taso), kaytetaan RF-komponenttiin,
# EI lisakomponentiksi SD:n rinnalle (samat signaali, redundantti).
PAIKKA_ID_WL = 1966
SUURE_ID_WL = 1
PAIKKA_ID_Q = 1005
SUURE_ID_Q = 2

# Korkeusjarjestelma VAHVISTETTU 2026-09-17 (kayttaja, suora SYKE-tarkistus
# asemalta 1966): NN=96.88, N60=97.10, N2000=97.40 (nollakohta+Arvo/100).
# HEM:n NORM/MNW/MHW-vakiot ovat NN-jarjestelmassa - vahvistettu vuoden
# 1942 kevaan huipun kautta (NN 97.37 m havainnoista vs. HEM:n ennatys
# 97.36 m). Aiempi ZERO_POINT_M=96.92-hypoteesi oli 4 cm pielessa.
# Silti EI kovakoodattu kiinteaksi vakioksi: haetaan ajon aikana
# VedenkTasoTieto-entiteetista (ohje 2), NN_FALLBACK_ZERO_M kaytetaan
# vain jos dynaaminen haku/jasennys epaonnistuu (kenttanimet SYKE:n
# VedenkTasoTieto-vastauksessa eivat olleet tiedossa tata kirjoittaessa).
NN_FALLBACK_ZERO_M = 96.88

NORM_M = 98.01  # keskimaarainen vuotuinen kevathuippu, WSFS ka 1910-2025 (NN)

# SD_nyt-vertailujakso: kayttajan oma esimerkkilaskenta (1991-2020) -
# TAHALLAAN eri kuin FMI-komponenttien 1961-2010 (WMO-normaalikausi).
# Ei yhtenaistetty, koska kayttaja antoi taman jakson nimenomaan
# vedenkorkeuden day-of-year-vertailulle.
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
    """OData-haku aci-nve-proxyn /syke-reitin kautta, SIVUTETTUNA.
    Palvelin rajoittaa vastauksen enintaan 1000 riviin per kutsu $top:sta
    riippumatta (havaittu kayttajan omassa live-tarkistuksessa 2026-09-17) -
    tama iteroi $skip:lla kunnes sivu on vajaa tai max_pages tayttyy."""
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
    """Hakee NN-nollakohdan VedenkTasoTieto-entiteetista ajon aikana, EI
    kovakoodattuna (kayttajan ohje 2). Kenttanimet (jarjestelma/arvo)
    eivat olleet tiedossa tata kirjoittaessa - jos automaattinen
    tunnistus epaonnistuu, tulostetaan raaka vastaus lokiin JA kaytetaan
    NN_FALLBACK_ZERO_M:aa (vahvistettu 2026-09-17) jotta ajo ei kaadu."""
    filt = f"Paikka_Id eq {paikka_id}"
    rows = fetch_syke_paged('VedenkTasoTieto', filt, orderby=None, page_size=50, max_pages=1)
    if not rows:
        print(f'  VedenkTasoTieto tyhja/epaonnistui - fallback NN={NN_FALLBACK_ZERO_M}')
        return NN_FALLBACK_ZERO_M, False
    for row in rows:
        # etsi rivi/kentta joka merkitsee "NN"-jarjestelman, ja numeerinen
        # arvo samalta rivilta. Spekulatiivinen - loki nayttaa raa'an
        # rivin jos tama ei osu, jotta kentat voi tarkistaa kasin.
        if any(isinstance(v, str) and v.strip().upper() == 'NN' for v in row.values()):
            nums = [v for v in row.values() if isinstance(v, (int, float))]
            if nums:
                print(f'  VedenkTasoTieto: NN-nollakohta {nums[0]} (raaka rivi: {row})')
                return float(nums[0]), True
    print(f'  VedenkTasoTieto: NN-rivia ei tunnistettu automaattisesti, raaka vastaus: {rows} '
          f'- fallback NN={NN_FALLBACK_ZERO_M} (tarkista kentat kasin lokista)')
    return NN_FALLBACK_ZERO_M, False

def fetch_syke_series(paikka_id, suure_id, start_dt, end_dt, zero_point_m=None, is_flow=False):
    """Hakee havaitun sarjan (vedenkorkeus tai virtaama) aci-nve-proxyn
    /syke-reitin kautta, sivutettuna. OData v3: EI $format-parametria,
    paivamaarat datetime'YYYY-MM-DDTHH:MM:SS'. Palauttaa myos raakarivin
    (raw) jotta esim. Lippu_Id-tyyppiset laatumerkinnat nakyvat (ohje 5)."""
    filt = (
        f"Paikka_Id eq {paikka_id} and Suure_Id eq {suure_id}"
        f" and Aika ge datetime'{start_dt:%Y-%m-%d}T00:00:00'"
        f" and Aika le datetime'{end_dt:%Y-%m-%d}T23:59:59'"
    )
    rows = fetch_syke_paged('Vedenkorkeus', filt)  # entiteetin nimi olettaen sama myos virtaamalle - EI VARMISTETTU
    out = []
    for r in rows:
        arvo, aika = r.get('Arvo'), r.get('Aika')
        if arvo is None or aika is None:
            continue
        try:
            val = float(arvo)  # Arvo voi palautua merkkijonona (Decimal)
        except (TypeError, ValueError):
            continue
        if is_flow:
            m_or_q = round(val, 2)  # m3/s, ei muunnosta
        else:
            m_or_q = round(zero_point_m + val / 100.0, 2)
        out.append({'date': str(aika)[:10], 'value': m_or_q, 'raw': r})
    return out

def flag_provisional(rows):
    """Ohje 5: tuoreimmalla rivilla nahty Lippu_Id=108 -> todennakoisesti
    alustava/tarkistamaton arvo. Kenttanimi ei varmistettu - etsitaan mika
    tahansa 'lippu'-alkuinen avain viimeisimmalta rivilta ja merkitaan
    nakyviin sellaisenaan, EI tulkita arvon merkitysta."""
    if not rows:
        return None
    last_raw = rows[-1].get('raw', {})
    for k, v in last_raw.items():
        if 'lippu' in k.lower() and v not in (None, 0, '0'):
            return {'field': k, 'value': v}
    return None

def compute_observed(today):
    """SD_kevat (lukittu kevaan jalkeen) ja SD_nyt (vertailu saman
    vuodenpaivan pitkan aikavalin keskiarvoon, yksi OData-kutsu
    month()/day()-suodattimella - ohje 4, ei enaa 10x pieni otanta).
    RF virtaamasta (ohje 9): Q / saman vuodenpaivan mediaani 1994-2025."""
    zero_point_m, zero_point_verified = fetch_zero_point_m(PAIKKA_ID_WL)
    result = {
        'zero_point_m': zero_point_m, 'zero_point_verified': zero_point_verified,
        'observed_m': None, 'observed_date': None, 'observed_provisional': None,
        'spring_peak_m': None, 'spring_peak_locked': False,
        'sd_kevat': None,
        'doy_avg_m': None, 'doy_ref_years': f'{DOY_REF_START_YEAR}-{DOY_REF_END_YEAR}',
        'sd_nyt': None,
        'flow_m3s': None, 'flow_date': None, 'flow_doy_median_m3s': None,
        'flow_doy_n_years': 0, 'rf_flow': None,
    }

    # 1) Viimeisin havainto (viim. 14 pv) + laatumerkinta
    recent = fetch_syke_series(PAIKKA_ID_WL, SUURE_ID_WL, today - timedelta(days=14), today, zero_point_m)
    if recent:
        last = recent[-1]
        result['observed_m'] = last['value']
        result['observed_date'] = last['date']
        result['observed_provisional'] = flag_provisional(recent)

    # 2) Kevaan huippu (maalis-heinakuu, kuluva vuosi). Lukittu automaattisesti
    #    heinakuun jalkeen, koska ikkunan ulkopuolelle ei enaa tule havaintoja.
    spring_start = date(today.year, 3, 1)
    spring_end = min(date(today.year, 7, 31), today)
    if spring_end >= spring_start:
        spring = fetch_syke_series(PAIKKA_ID_WL, SUURE_ID_WL, spring_start, spring_end, zero_point_m)
        if spring:
            peak = max(spring, key=lambda r: r['value'])
            result['spring_peak_m'] = peak['value']
            result['spring_peak_locked'] = today > date(today.year, 7, 31)
            result['sd_kevat'] = round(max(0, min(1, (NORM_M - peak['value']) / 0.90)), 3)

    # 3) Saman vuodenpaivan pitka aikavali - YKSI kutsu month()/day()-
    #    suodattimella koko 116v sarjaan, rajattuna referenssikauteen
    #    (ohje 4 - ei enaa 10 vuoden +-5pv-otantaa, n=10 oli liian pieni).
    doy_filt = (
        f"Paikka_Id eq {PAIKKA_ID_WL} and Suure_Id eq {SUURE_ID_WL}"
        f" and month(Aika) eq {today.month} and day(Aika) eq {today.day}"
        f" and year(Aika) ge {DOY_REF_START_YEAR} and year(Aika) le {DOY_REF_END_YEAR}"
    )
    doy_rows = fetch_syke_paged('Vedenkorkeus', doy_filt)
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

    # 4) Virtaama (Nokisenkoski, Paikka_Id 1005) - RF-komponentiksi, EI
    #    erilliseksi SD-tyyppiseksi komponentiksi (sama signaali kuin
    #    vedenkorkeus saannostelemattomassa jarvessa - ohje 9).
    flow_recent = fetch_syke_series(PAIKKA_ID_Q, SUURE_ID_Q, today - timedelta(days=14), today, is_flow=True)
    if flow_recent:
        last_q = flow_recent[-1]
        result['flow_m3s'] = last_q['value']
        result['flow_date'] = last_q['date']

    flow_doy_filt = (
        f"Paikka_Id eq {PAIKKA_ID_Q} and Suure_Id eq {SUURE_ID_Q}"
        f" and month(Aika) eq {today.month} and day(Aika) eq {today.day}"
        f" and year(Aika) ge 1994"
    )
    flow_doy_rows = fetch_syke_paged('Vedenkorkeus', flow_doy_filt)
    flow_doy_values = []
    for r in flow_doy_rows:
        try:
            flow_doy_values.append(float(r.get('Arvo')))
        except (TypeError, ValueError):
            continue
    if flow_doy_values:
        flow_doy_values.sort()
        n = len(flow_doy_values)
        median = flow_doy_values[n // 2] if n % 2 else (flow_doy_values[n // 2 - 1] + flow_doy_values[n // 2]) / 2
        result['flow_doy_median_m3s'] = round(median, 2)
        result['flow_doy_n_years'] = n
        if result['flow_m3s'] is not None and median > 0:
            result['rf_flow'] = round(max(0, min(1, 1 - result['flow_m3s'] / median)), 3)

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
    print(f"  observed_m={obs['observed_m']} ({obs['observed_date']}, provisional={obs['observed_provisional']}) "
          f"spring_peak_m={obs['spring_peak_m']} sd_kevat={obs['sd_kevat']} "
          f"doy_avg_m={obs['doy_avg_m']} sd_nyt={obs['sd_nyt']} "
          f"flow_m3s={obs['flow_m3s']} flow_doy_median={obs['flow_doy_median_m3s']} rf_flow={obs['rf_flow']}")
except Exception as e:
    print(f'  havaintohaku epaonnistui: {e}')
    result['observed'] = None

with open('data/cache/iisvesi.json','w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f'\nOK iisvesi.json')
