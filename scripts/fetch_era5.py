"""ERA5-Land timeseries fetcher — ARCO-formaatti yhdelle pisteelle"""
import cdsapi, json, os, sys, zipfile
from datetime import datetime, timezone

NOW = datetime.now(timezone.utc)
os.makedirs('data/cache', exist_ok=True)
os.makedirs('data/era5_raw', exist_ok=True)

# Iisvesi/Virmasvesi koordinaatit (lähimpänä gridipiste)
LAT, LON = 62.9, 26.8
YEARS = list(range(2016, NOW.year + 1))

print(f'ERA5 timeseries: {LAT}°N {LON}°E · {YEARS[0]}–{YEARS[-1]}')

c = cdsapi.Client()
nc_file = f'data/era5_raw/era5_timeseries_{YEARS[0]}_{YEARS[-1]}.nc'

if not os.path.exists(nc_file):
    print('Haetaan Copernicuksesta...')
    try:
        c.retrieve(
            'reanalysis-era5-land-timeseries',
            {
                'variable': ['2m_temperature', 'total_precipitation'],
                'year': [str(y) for y in YEARS],
                'month': [f'{m:02d}' for m in range(1, 13)],
                'day': [f'{d:02d}' for d in range(1, 32)],
                'time': ['12:00'],
                'location': {'lon': LON, 'lat': LAT},
                'format': 'netcdf',
            },
            nc_file
        )
        print(f'Ladattu: {os.path.getsize(nc_file)/1024:.0f} KB')
    except Exception as e:
        print(f'timeseries virhe: {e}')
        print('Kokeillaan tavallista ERA5-Land...')
        # Fallback: tavallinen ERA5-Land kuukausittain
        c.retrieve(
            'reanalysis-era5-land',
            {
                'variable': ['2m_temperature', 'total_precipitation'],
                'year': [str(NOW.year)],
                'month': [f'{NOW.month:02d}'],
                'day': [f'{d:02d}' for d in range(1, 32)],
                'time': ['12:00'],
                'area': [LAT+0.5, LON-0.5, LAT-0.5, LON+0.5],
                'format': 'netcdf',
            },
            nc_file
        )
        print(f'Fallback ladattu: {os.path.getsize(nc_file)/1024:.0f} KB')

# Pura ZIP jos tarpeen
actual = nc_file
if zipfile.is_zipfile(nc_file):
    print('Puretaan ZIP...')
    with zipfile.ZipFile(nc_file) as z:
        names = z.namelist()
        print(f'  Sisältää: {names}')
        nc_name = next((n for n in names if n.endswith('.nc')), None)
        if nc_name:
            actual = nc_file.replace('.nc', '_x.nc')
            with z.open(nc_name) as src, open(actual, 'wb') as dst:
                dst.write(src.read())
            print(f'  Purettu: {actual}')

# Lue NetCDF
results = []
try:
    from netCDF4 import Dataset, num2date
    import numpy as np
    with Dataset(actual) as ds:
        print(f'Muuttujat: {list(ds.variables.keys())}')
        tv = 'valid_time' if 'valid_time' in ds.variables else 'time'
        t2m_v = next((v for v in ['t2m','VAR_2T'] if v in ds.variables), None)
        tp_v  = next((v for v in ['tp','VAR_TP']  if v in ds.variables), None)
        times = ds.variables[tv][:]
        units = ds.variables[tv].units
        dates = [num2date(t, units).strftime('%Y-%m-%d') for t in times]

        # Timeseries on 1D (ei grid), tavallinen on 3D
        def flatten(arr):
            a = np.array(arr)
            return a.flatten() if a.ndim > 1 else a

        t_vals = flatten(ds.variables[t2m_v][:]) - 273.15 if t2m_v else []
        p_vals = flatten(ds.variables[tp_v][:]) * 1000    if tp_v  else []

        for i, date in enumerate(dates):
            results.append({
                'date':     date,
                'temp_c':   round(float(t_vals[i]), 2) if i < len(t_vals) else None,
                'precip_mm':round(float(p_vals[i]) * 24, 2) if i < len(p_vals) else None,
            })
    print(f'Jäsennetty: {len(results)} päivää')
except Exception as e:
    print(f'NetCDF virhe: {e}')
    sys.exit(1)

# Tallenna
seen = set()
unique = [r for r in sorted(results, key=lambda x: x['date'])
          if r['date'] not in seen and not seen.add(r['date'])]

output = {
    'source': 'ERA5-Land ECMWF',
    'lat': LAT, 'lon': LON,
    'fetched': NOW.strftime('%Y-%m-%d'),
    'n': len(unique),
    'rows': unique
}
with open('data/cache/era5_daily.json', 'w') as f:
    json.dump(output, f)

print(f'OK: {len(unique)} päivää → data/cache/era5_daily.json')
if unique:
    print(f'  {unique[0]["date"]} → {unique[-1]["date"]}')
    print(f'  Esim: {unique[-1]}')
