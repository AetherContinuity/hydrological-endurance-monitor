"""ERA5-Land fetcher — yksi kuukausi kerrallaan"""
import cdsapi, json, os, sys, re
from datetime import datetime, timezone

NOW  = datetime.now(timezone.utc)
YEAR = str(NOW.year)
os.makedirs('data/cache', exist_ok=True)
os.makedirs('data/era5_raw', exist_ok=True)

# Saimaa-alue Virmasveden lähistöllä
AREA = [63.5, 27.0, 62.5, 28.5]

c = cdsapi.Client()
results = []

# Hae vain viimeisin kuukausi — pieni ja nopea
month = f'{NOW.month:02d}'
nc_file = f'data/era5_raw/era5_{YEAR}_{month}.nc'

print(f'ERA5: {YEAR}-{month} → {nc_file}')
try:
    c.retrieve(
        'reanalysis-era5-land',
        {
            'variable': ['2m_temperature', 'total_precipitation'],
            'year': YEAR,
            'month': [month],
            'day': [f'{d:02d}' for d in range(1, 32)],
            'time': ['12:00'],
            'area': AREA,
            'format': 'netcdf',
        },
        nc_file
    )
    print(f'Ladattu: {os.path.getsize(nc_file)/1024:.0f} KB')
except Exception as e:
    print(f'ERA5 virhe: {e}')
    sys.exit(1)

# Lue NetCDF
try:
    from netCDF4 import Dataset, num2date
    import numpy as np
    with Dataset(nc_file) as ds:
        t2m = next((v for v in ['t2m','VAR_2T'] if v in ds.variables), None)
        tp  = next((v for v in ['tp','VAR_TP']  if v in ds.variables), None)
        times = ds.variables['time'][:]
        units = ds.variables['time'].units
        dates = [num2date(t, units).strftime('%Y-%m-%d') for t in times]
        t_vals = ds.variables[t2m][:].mean(axis=(-1,-2)) - 273.15 if t2m else []
        p_vals = ds.variables[tp][:].mean(axis=(-1,-2)) * 1000 if tp else []
        for i, date in enumerate(dates):
            results.append({
                'date': date,
                'temp_c': round(float(t_vals[i]), 2) if len(t_vals) > i else None,
                'precip_mm': round(float(p_vals[i]) * 24, 2) if len(p_vals) > i else None,
            })
    print(f'Jäsennetty: {len(results)} päivää')
except Exception as e:
    print(f'NetCDF virhe: {e}')

# Lisää/päivitä olemassa oleva cache
existing = []
cache_file = 'data/cache/era5_daily.json'
if os.path.exists(cache_file):
    with open(cache_file) as f:
        d = json.load(f)
        existing = d.get('rows', [])

# Yhdistä — uudet päivät korvaa vanhat
by_date = {r['date']: r for r in existing}
for r in results:
    by_date[r['date']] = r
merged = sorted(by_date.values(), key=lambda x: x['date'])

output = {
    'source': 'ERA5-Land ECMWF',
    'area': AREA,
    'fetched': NOW.strftime('%Y-%m-%d'),
    'n': len(merged),
    'rows': merged
}
with open(cache_file, 'w') as f:
    json.dump(output, f)

print(f'OK: {len(merged)} päivää → {cache_file}')
if merged:
    print(f'  {merged[0]["date"]} → {merged[-1]["date"]}')
