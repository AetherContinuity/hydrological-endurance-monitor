"""ERA5-Land: hakee yhden kuukauden per ajo, akkumuloi cacheen"""
import cdsapi, json, os, sys, zipfile
from datetime import datetime, timezone

NOW = datetime.now(timezone.utc)
YEAR  = str(NOW.year)
MONTH = f'{NOW.month:02d}'

os.makedirs('data/cache', exist_ok=True)
os.makedirs('data/era5_raw', exist_ok=True)

# Iisvesi/Virmasvesi alue (pieni bbox)
AREA = [63.2, 26.5, 62.5, 27.2]

print(f'ERA5: {YEAR}-{MONTH} → area {AREA}')

c = cdsapi.Client()
nc_file = f'data/era5_raw/era5_{YEAR}_{MONTH}.nc'

if os.path.exists(nc_file.replace('.nc','_x.nc')):
    print('Tiedosto jo olemassa, ohitetaan haku')
    nc_file = nc_file.replace('.nc','_x.nc')
else:
    try:
        c.retrieve(
            'reanalysis-era5-land',
            {
                'variable': ['2m_temperature', 'total_precipitation'],
                'year': YEAR, 'month': [MONTH],
                'day': [f'{d:02d}' for d in range(1,32)],
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

    if zipfile.is_zipfile(nc_file):
        with zipfile.ZipFile(nc_file) as z:
            nc_name = next((n for n in z.namelist() if n.endswith('.nc')), None)
            if nc_name:
                xf = nc_file.replace('.nc','_x.nc')
                with z.open(nc_name) as s, open(xf,'wb') as d: d.write(s.read())
                nc_file = xf
                print(f'Purettu: {nc_file}')

# Lue NetCDF
results = []
try:
    from netCDF4 import Dataset, num2date
    with Dataset(nc_file) as ds:
        tv = 'valid_time' if 'valid_time' in ds.variables else 'time'
        t2m = next((v for v in ['t2m','VAR_2T'] if v in ds.variables), None)
        tp  = next((v for v in ['tp','VAR_TP']  if v in ds.variables), None)
        times = ds.variables[tv][:]
        units = ds.variables[tv].units
        dates = [num2date(t, units).strftime('%Y-%m-%d') for t in times]
        import numpy as np
        t_v = ds.variables[t2m][:].mean(axis=(-1,-2)) - 273.15 if t2m else []
        p_v = ds.variables[tp][:].mean(axis=(-1,-2)) * 1000    if tp  else []
        for i, date in enumerate(dates):
            results.append({
                'date': date,
                'temp_c':    round(float(t_v[i]), 2) if i < len(t_v) else None,
                'precip_mm': round(float(p_v[i])*24, 2) if i < len(p_v) else None,
            })
    print(f'Jäsennetty: {len(results)} päivää')
except Exception as e:
    print(f'NetCDF virhe: {e}')
    sys.exit(1)

# Lue olemassa oleva cache ja yhdistä
existing = []
cache = 'data/cache/era5_daily.json'
if os.path.exists(cache):
    with open(cache) as f:
        existing = json.load(f).get('rows', [])

by_date = {r['date']: r for r in existing}
for r in results:
    by_date[r['date']] = r
merged = sorted(by_date.values(), key=lambda x: x['date'])

with open(cache, 'w') as f:
    json.dump({'source':'ERA5-Land','area':AREA,'fetched':NOW.strftime('%Y-%m-%d'),
               'n':len(merged),'rows':merged}, f)

print(f'OK: {len(merged)} päivää cachessa ({merged[0]["date"] if merged else "—"} → {merged[-1]["date"] if merged else "—"})')
