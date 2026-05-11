"""
hem/fetch.py — Live data fetcher via aci-hem-proxy Cloudflare Worker.

Same pattern as WEM's Fingrid proxy: all API calls go through
https://aci-hem-proxy.ruotsalainen-marko.workers.dev

Usage:
    from hem.fetch import fetch_water_level, fetch_fmi
    df_wl   = fetch_water_level(paikka=200, start='2024-01-01', end='2024-12-31')
    df_fmi  = fetch_fmi(station=101756, start='2024-01-01', end='2024-12-31')
"""

import requests
import pandas as pd
from datetime import datetime, timedelta

PROXY_BASE = 'https://aci-hem-proxy.ruotsalainen-marko.workers.dev'

# SYKE station IDs for Saimaa system
STATIONS = {
    'lauritsala':  200,   # Saimaa primary gauge
    'puumala':     320,
    'savonlinna':  380,
    'virmasvesi':  520,
    'pielinen':    610,
}

# FMI station IDs
FMI_STATIONS = {
    'lappeenranta': 101756,
    'savonlinna':   101533,
    'joensuu':      101339,
    'kuopio':       101756,  # Lappeenranta Lepola as fallback
}

# SYKE variable (Suure) IDs
SUURE = {
    'vedenkorkeus': 1,
    'virtaama':     2,
    'lumi':         5,
}


def fetch_water_level(
    paikka: int = 200,
    start: str = None,
    end: str = None,
    days: int = 365,
) -> pd.DataFrame:
    """
    Fetch daily water level from SYKE via aci-hem-proxy.

    Returns DataFrame with columns: date (datetime), water_level (float).
    """
    if end is None:
        end = datetime.utcnow().strftime('%Y-%m-%d')
    if start is None:
        start = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

    url = f'{PROXY_BASE}/syke'
    params = {
        'paikka': paikka,
        'suure': SUURE['vedenkorkeus'],
        'start': start,
        'end': end,
    }

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    rows = data.get('rows', [])
    if not rows:
        raise ValueError(f'No water level data for paikka={paikka} {start}→{end}')

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df = df.rename(columns={'value': 'water_level'})
    df = df.dropna(subset=['water_level'])
    df = df.sort_values('date').reset_index(drop=True)

    return df[['date', 'water_level']]


def fetch_fmi(
    station: int = 101756,
    start: str = None,
    end: str = None,
    days: int = 365,
    params: str = 'temperature,precipitation',
) -> pd.DataFrame:
    """
    Fetch daily weather observations from FMI via aci-hem-proxy.

    Returns DataFrame with columns: date, temperature, precipitation.
    """
    if end is None:
        end = datetime.utcnow().strftime('%Y-%m-%d')
    if start is None:
        start = (datetime.utcnow() - timedelta(days=days)).strftime('%Y-%m-%d')

    url = f'{PROXY_BASE}/fmi'
    qparams = {
        'station': station,
        'param': params,
        'start': start,
        'end': end,
    }

    resp = requests.get(url, params=qparams, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    rows = data.get('rows', [])
    if not rows:
        raise ValueError(f'No FMI data for station={station} {start}→{end}')

    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])

    # Pivot long → wide
    df_wide = df.pivot_table(index='date', columns='param', values='value', aggfunc='mean')
    df_wide = df_wide.reset_index()
    df_wide.columns.name = None

    # Rename to standard names
    rename = {'temperature': 'temp', 'precipitation': 'precip'}
    df_wide = df_wide.rename(columns=rename)

    return df_wide.sort_values('date').reset_index(drop=True)


def fetch_saimaa_composite(
    start: str = None,
    end: str = None,
    days: int = 365,
) -> pd.DataFrame:
    """
    Fetch and merge water level (Lauritsala) + FMI weather (Lappeenranta).
    Returns merged DataFrame ready for HEPP computation.
    """
    print(f'  Fetching water level (Lauritsala)...')
    df_wl = fetch_water_level(paikka=STATIONS['lauritsala'], start=start, end=end, days=days)

    print(f'  Fetching FMI weather (Lappeenranta)...')
    df_fmi = fetch_fmi(station=FMI_STATIONS['lappeenranta'], start=start, end=end, days=days)

    df = df_wl.merge(df_fmi, on='date', how='inner')

    print(f'  Merged: {len(df)} days')
    return df
