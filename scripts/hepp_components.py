"""HEPP-komponentit EP ja RF FMI Kuopion paivasarjasta (data/cache/fmi.json).

Sama kaava kuin historiallinen v1-sarja (hepp_monthly.json, 2026-05-12),
josta v2 (hepp_monthly_v2.json) kopioi EP:n ja RF:n. HUOM: HEM-sivun live-EP
kaytti 15.10.2026 asti eri kaavaa (paivanpituuskorjattu PET, z-pisteet). Lisatty 2026-10-15, jotta §05-sarja voidaan
jatkaa automaattisesti; validointi v1-sarjaa vasten: validate_against_v1().
"""
import json, math, statistics

KUOPIO_LAT = 62.90
DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MID_MONTH_DOY = [15, 45, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349]
REF = (1961, 2010)


def day_length_hours(lat_deg, doy):
    lat = math.radians(lat_deg)
    decl = 0.4093 * math.sin(2 * math.pi * (284 + doy) / 365)
    cos_h = max(-1, min(1, -math.tan(lat) * math.tan(decl)))
    return (24 / math.pi) * math.acos(cos_h)


def thornthwaite_pet(temps, months=None):
    cal = months or list(range(1, 13))
    I = sum((t / 5) ** 1.514 for t in temps if t > 0)
    if I <= 0:
        return [0.0] * len(temps)
    a = 6.75e-7 * I ** 3 - 7.71e-5 * I ** 2 + 1.792e-2 * I + 0.49239
    out = []
    for t, m in zip(temps, cal):
        if t <= 0:
            out.append(0.0)
            continue
        L = day_length_hours(KUOPIO_LAT, MID_MONTH_DOY[m - 1])
        out.append(16 * (10 * t / I) ** a * (L / 12) * (DAYS_IN_MONTH[m - 1] / 30))
    return out


def monthly_from_fmi(path='data/cache/fmi.json'):
    """Palauttaa {(y,m): {'t': keskilampo, 'p': sadesumma, 'nt': n, 'np': n}}."""
    rows = json.load(open(path))['rows']
    acc = {}
    for r in rows:
        y, m = int(r['date'][:4]), int(r['date'][5:7])
        v = r['value']
        if v is None:
            continue
        a = acc.setdefault((y, m), {'t': [], 'p': []})
        if r['param'] == 'tday' and v > -50:
            a['t'].append(v)
        elif r['param'] == 'rrday' and v >= 0:
            a['p'].append(v)
    out = {}
    for k, a in acc.items():
        out[k] = {'t': sum(a['t']) / len(a['t']) if a['t'] else None,
                  'p': sum(a['p']) if a['p'] else None,
                  'nt': len(a['t']), 'np': len(a['p'])}
    return out


def climatological_heat_index(mm):
    """I 1961-2010 kuukausinormaaleista (v1-sarjan tapa, vahvistettu
    2026-10-15: PET-erot v1:n ep_mm-sarakkeeseen mediaani 0,04 mm)."""
    norm_t = []
    for m in range(1, 13):
        v = [mm[(y, m)]['t'] for y in range(REF[0], REF[1] + 1)
             if (y, m) in mm and mm[(y, m)]['t'] is not None]
        norm_t.append(sum(v) / len(v))
    return sum((t / 5) ** 1.514 for t in norm_t if t > 0)


def pet_v1(t, I):
    """Thornthwaite ilman paivanpituus- ja kuukausipituuskorjausta, kiintea I.
    Nain v1-sarja (hepp_monthly.json) on laskettu; ei 'oikea' Thornthwaite,
    mutta sarjan sisainen vertailu edellyttaa samaa kaavaa."""
    if t is None or t <= 0:
        return 0.0
    a = 6.75e-7 * I ** 3 - 7.71e-5 * I ** 2 + 1.792e-2 * I + 0.49239
    return 16 * (10 * t / I) ** a


def pet_normals(mm, I):
    out = []
    for m in range(1, 13):
        v = [pet_v1(mm[(y, m)]['t'], I) for y in range(REF[0], REF[1] + 1)
             if (y, m) in mm and mm[(y, m)]['t'] is not None]
        out.append(sum(v) / len(v))
    return out


def precip_medians(mm):
    out = []
    for m in range(1, 13):
        vals = [mm[(y, m)]['p'] for y in range(REF[0], REF[1] + 1)
                if (y, m) in mm and mm[(y, m)]['p'] is not None]
        out.append(statistics.median(vals))
    return out


def ep_anom(mm, normals, I, y, m):
    """EP = clamp((PET - normaali_m) / normaali_m, 0, 1); talvikuukausina
    (normaali 0) EP = 0."""
    t = mm.get((y, m), {}).get('t')
    if t is None:
        return None
    n = normals[m - 1]
    if n <= 0:
        return 0.0
    return max(0.0, min(1.0, (pet_v1(t, I) - n) / n))


def rf(mm, medians, y, m):
    p = mm.get((y, m), {}).get('p')
    if p is None or medians[m - 1] <= 0:
        return None
    return max(0.0, min(1.0, 1 - p / medians[m - 1]))


def validate_against_v1(v1_path='data/cache/hepp_monthly.json', fmi_path='data/cache/fmi.json'):
    mm = monthly_from_fmi(fmi_path)
    I = climatological_heat_index(mm)
    nrm, med = pet_normals(mm, I), precip_medians(mm)
    rows = json.load(open(v1_path))['rows']
    de, dr = [], []
    for r in rows:
        y, m = int(r['month'][:4]), int(r['month'][5:7])
        e, f = ep_anom(mm, nrm, I, y, m), rf(mm, med, y, m)
        if e is not None and r.get('ep_anom') is not None:
            de.append(abs(e - r['ep_anom']))
        if f is not None and r.get('rf') is not None:
            dr.append(abs(f - r['rf']))
    return de, dr


if __name__ == '__main__':
    de, dr = validate_against_v1()
    for name, d in (('EP', de), ('RF', dr)):
        d.sort()
        print(f'{name}: n={len(d)} median|diff|={statistics.median(d):.4f} '
              f'p95={d[int(0.95 * len(d))]:.4f} max={d[-1]:.4f}')
