"""
ERA5-Land historical data fetcher.
Hakee päivittäisen lämpötilan ja sateen Saimaa-alueelta 2020-2026.
Ajettava GitHub Actionsin kautta (CDS_API_KEY secret tarvitaan).

Output: data/cache/era5_daily.json
"""
import cdsapi, json, os, sys
import numpy as np
from datetime import datetime, timezone

NOW = datetime.now(timezone.utc)
print(f"ERA5 fetch käynnistetty: {NOW.strftime('%Y-%m-%d %H:%M UTC')}")

# Saimaa-alue: [N, W, S, E] — Lauritsala/Lappeenranta
AREA = [62.0, 28.0, 61.5, 28.5]
YEARS = [str(y) for y in range(2020, NOW.year + 1)]

os.makedirs('data/cache', exist_ok=True)
os.makedirs('data/era5_raw', exist_ok=True)

c = cdsapi.Client()
results = []

for year in YEARS:
    nc_file = f'data/era5_raw/era5_{year}.nc'
    if os.path.exists(nc_file):
        print(f'{year}: tiedosto jo olemassa, ohitetaan')
    else:
        print(f'{year}: ladataan ERA5-Land...')
        try:
            c.retrieve(
                'reanalysis-era5-land',
                {
                    'variable': ['2m_temperature', 'total_precipitation'],
                    'year': year,
                    'month': [f'{m:02d}' for m in range(1, 13)],
                    'day':   [f'{d:02d}' for d in range(1, 32)],
                    'time':  ['12:00'],     # Päivän arvo klo 12 UTC
                    'area':  AREA,
                    'format': 'netcdf',
                },
                nc_file
            )
            print(f'{year}: OK ({os.path.getsize(nc_file)/1024:.0f} KB)')
        except Exception as e:
            print(f'{year}: VIRHE — {e}')
            continue

    # Lue NetCDF → päivittäiset arvot
    try:
        from netCDF4 import Dataset
        import numpy as np
        with Dataset(nc_file) as ds:
            # Muuttujanimet ERA5-Land: t2m (lämpötila K), tp (sade m)
            t2m_var = next((v for v in ['t2m','VAR_2T'] if v in ds.variables), None)
            tp_var  = next((v for v in ['tp','VAR_TP'] if v in ds.variables), None)
            times   = ds.variables['time'][:]
            time_units = ds.variables['time'].units

            from netCDF4 import num2date
            dates = [num2date(t, time_units).strftime('%Y-%m-%d') for t in times]

            t_vals = ds.variables[t2m_var][:].mean(axis=(-1,-2)) - 273.15 if t2m_var else [None]*len(dates)
            p_vals = ds.variables[tp_var][:].mean(axis=(-1,-2)) * 1000 if tp_var else [None]*len(dates)  # m→mm

            for i, date in enumerate(dates):
                results.append({
                    'date': date,
                    'temp_c': round(float(t_vals[i]), 2) if t_vals[i] is not None else None,
                    'precip_mm': round(float(p_vals[i]) * 24, 2) if p_vals[i] is not None else None,
                })
    except Exception as e:
        print(f'{year} NetCDF-luku: VIRHE — {e}')

# Poista duplikaatit, järjestä
seen = set()
unique = []
for r in sorted(results, key=lambda x: x['date']):
    if r['date'] not in seen:
        seen.add(r['date'])
        unique.append(r)

output = {
    'source': 'ERA5-Land ECMWF',
    'area': AREA,
    'fetched': NOW.strftime('%Y-%m-%d'),
    'n': len(unique),
    'rows': unique
}

with open('data/cache/era5_daily.json', 'w') as f:
    json.dump(output, f)

print(f'\nOK: {len(unique)} päivää tallennettu → data/cache/era5_daily.json')
if unique:
    print(f'  Ensimmäinen: {unique[0]}')
    print(f'  Viimeisin:   {unique[-1]}')
