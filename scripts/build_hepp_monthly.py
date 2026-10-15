"""Jatkaa §05-sarjaa (data/cache/hepp_monthly_v2.json) kokonaisilla kuukausilla.

Lisatty 2026-10-15. v2-sarja (2026-09-24) laskettiin kertaajona ja paattyi
2026-05:een, jonka arvo oli lisaksi laskettu kesken olevasta kuukaudesta
(v1 laskettu 12.5.2026: sademaara 6 mm -> RF 0,838). Tama skripti:

- laskee uudelleen sarjan viimeisen kuukauden ja lisaa puuttuvat kokonaiset
  kuukaudet (kuluva kuukausi ei koskaan mukana)
- SD: v2:n kaava. Kuukauden paivien ka( clamp((normaali_pv - havaittu)/0,90) ),
  normaali = saman kalenteripaivan keskiarvo 1991-2020, Iisvesi (SYKE
  Paikka_Id 1966), NN = 96,88 + Arvo/100. Kuukausi mukana vain jos
  vahintaan 20 havaintoa.
- EP ja RF: v1-sarjan kaava (scripts/hepp_components.py, validoitu v1:ta vasten)
- HEPP = (0,35 SD + 0,25 EP + 0,25 RF) / 0,85 (HSP puuttuu historiasta)
- Sademaara puuttuu FMI Kuopion sarjasta 2001-06 .. 2005-06 (49 kk). v1/v2
  kasittelivat puuttuvan sateen nollana -> RF = 1,0 koko jaksolle, mika nosti
  HEPP:ia +0,29 ja teki 2000-luvusta naennaisen kuivuusvuosikymmenen.
  Nyt: RF = null, rf_missing = true, HEPP = (0,35 SD + 0,25 EP) / 0,60.
- zero_distribution.percentiles lasketaan jokaisella ajolla uudelleen.

Ajo: python scripts/build_hepp_monthly.py  (repon juuresta, fmi.json oltava ajan tasalla)
"""
import json, sys, os, urllib.parse, urllib.request, time
from datetime import date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from hepp_components import (monthly_from_fmi, climatological_heat_index, pet_normals,
                             precip_medians, ep_anom, rf)

PATH = 'data/cache/hepp_monthly_v2.json'
PROXY = 'https://aci-nve-proxy.ruotsalainen-marko.workers.dev/syke'
PAIKKA_ID = 1966
ZERO_NN = 96.88  # vahvistettu 2026-09-17 (VedenkTasoTieto, NN)
PAGE = 500       # SYKE OData palauttaa enintaan 500 rivia per kutsu
MIN_DAYS = 20


def odata(filt):
    out, skip = [], 0
    while True:
        qs = (f"entity=Vedenkorkeus&$filter={urllib.parse.quote(filt)}&$top={PAGE}&$skip={skip}"
              f"&$orderby={urllib.parse.quote('Aika asc')}")
        for attempt in range(3):
            try:
                req = urllib.request.Request(f'{PROXY}?{qs}', headers={'User-Agent': 'ACI-HEM'})
                rows = json.loads(urllib.request.urlopen(req, timeout=60).read()).get('value') or []
                break
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(f'SYKE-haku epaonnistui (skip={skip}): {e}')
                time.sleep(3 * (attempt + 1))
        out.extend(rows)
        if len(rows) < PAGE:
            return out
        skip += PAGE


def levels(start, end):
    filt = (f"Paikka_Id eq {PAIKKA_ID} and Aika ge datetime'{start}T00:00:00'"
            f" and Aika le datetime'{end}T23:59:59'")
    out = {}
    for r in odata(filt):
        try:
            out[r['Aika'][:10]] = ZERO_NN + float(r['Arvo']) / 100.0
        except (TypeError, ValueError, KeyError):
            continue
    return out


def month_iter(y, m, y2, m2):
    while (y, m) <= (y2, m2):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def main():
    v2 = json.load(open(PATH))
    rows = v2['rows']
    last = rows[-1]['month']
    ly, lm = int(last[:4]), int(last[5:7])
    today = date.today()
    ey, em = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    targets = list(month_iter(ly, lm, ey, em))  # viimeinen lasketaan aina uudelleen
    mm = monthly_from_fmi()
    new = compute_months(targets, mm, today) if targets else []
    if new:
        keep = [r for r in rows if r['month'] < new[0]['month']]
        for r in rows:
            if r['month'] >= new[0]['month']:
                print(f"  korvattu: {r['month']} HEPP {r['hepp']} (SD {r['sd_obs']} EP {r['ep_anom']} RF {r['rf']})")
        rows = keep + new
    n_fixed = apply_missing_precip(rows, mm)
    v2['rows'] = rows
    v2['n'] = len(rows)
    v2['updated'] = today.isoformat()
    v2['method']['coverage'] = (f"{v2['n']} kuukautta {rows[0]['month']} – {rows[-1]['month']}; "
                                f"kuukausi mukana vain jos vähintään {MIN_DAYS} vedenkorkeushavaintoa. "
                                "Jatketaan kokonaisilla kuukausilla (scripts/build_hepp_monthly.py, 2026-10-15 alkaen).")
    v2['method']['rf_missing'] = ('Sademäärä puuttuu FMI Kuopion sarjasta 2001-06 – 2005-06. Näille kuukausille '
                                  'RF = null ja HEPP = (0,35·SD + 0,25·EP) / 0,60. Korjattu 2026-10-15: aiemmin '
                                  'puuttuva sade luettiin nollaksi → RF = 1,0.')
    update_percentiles(v2)
    with open(PATH, 'w') as f:
        json.dump(v2, f, ensure_ascii=False, separators=(',', ':'))
    print(f'OK {PATH}: {v2["n"]} kk, viimeinen {rows[-1]["month"]}, rf_missing {n_fixed} kk')


def apply_missing_precip(rows, mm):
    n = 0
    for r in rows:
        y, m = int(r['month'][:4]), int(r['month'][5:7])
        if mm.get((y, m), {}).get('p') is None:
            r['rf'] = None
            r['rf_missing'] = True
            r['hepp'] = round((0.35 * r['sd_obs'] + 0.25 * r['ep_anom']) / 0.60, 3)
            n += 1
    return n


def _pct(v, q):
    v = sorted(v)
    k = (len(v) - 1) * q
    f = int(k)
    c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def update_percentiles(v2):
    h = [r['hepp'] for r in v2['rows']]
    zd = v2.setdefault('zero_distribution', {})
    zd['percentiles'] = {f'p{q}': round(_pct(h, q / 100), 3) for q in (10, 25, 50, 75, 80, 90, 95, 99)}
    zd['percentiles_computed'] = v2['updated']


def compute_months(targets, mm, today):

    print(f'Lasketaan {targets[0][0]}-{targets[0][1]:02d} .. {targets[-1][0]}-{targets[-1][1]:02d}')
    ref = levels('1991-01-01', '2020-12-31')
    by_md = defaultdict(list)
    for d, v in ref.items():
        by_md[d[5:10]].append(v)
    normal = {k: sum(v) / len(v) for k, v in by_md.items()}
    print(f'  normaali: {len(ref)} paivaa 1991-2020, {len(normal)} kalenteripaivaa')

    obs = levels(f'{targets[0][0]}-{targets[0][1]:02d}-01', today.isoformat())
    I = climatological_heat_index(mm)
    nrm, med = pet_normals(mm, I), precip_medians(mm)

    new = []
    for y, m in targets:
        key = f'{y}-{m:02d}'
        days = sorted(d for d in obs if d.startswith(key))
        if len(days) < MIN_DAYS:
            print(f'  {key}: vain {len(days)} havaintoa (< {MIN_DAYS}), ohitetaan')
            continue
        sd_vals = [max(0.0, min(1.0, (normal[d[5:10]] - obs[d]) / 0.90)) for d in days if d[5:10] in normal]
        sd = sum(sd_vals) / len(sd_vals)
        ep, r = ep_anom(mm, nrm, I, y, m), rf(mm, med, y, m)
        if ep is None:
            print(f'  {key}: FMI-lampotila puuttuu, ohitetaan')
            continue
        hepp = (0.35 * sd + 0.25 * ep + 0.25 * r) / 0.85 if r is not None else (0.35 * sd + 0.25 * ep) / 0.60
        row = {'month': key, 'sd_obs': round(sd, 3), 'ep_anom': round(ep, 3), 'rf': None if r is None else round(r, 3),
               'hepp': round(hepp, 3), 'level_m': round(sum(obs[d] for d in days) / len(days), 3),
               'n_days': len(days), 'hepp_old': None, 'sd_old': None}
        new.append(row)
        print(f"  {key}: SD {row['sd_obs']} EP {row['ep_anom']} RF {row['rf']} -> HEPP {row['hepp']} "
              f"(taso {row['level_m']} m, {len(days)} pv)")

    return new


if __name__ == '__main__':
    main()
