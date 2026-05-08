"""
HEM v1.1 MVP - Virmasvesi First Case Run
Hydrological Endurance Monitor

Inputs:
- water_level.csv (date, water_level_cm)
- precipitation.csv (date, precipitation_mm)
- temperature.csv (date, temperature_c)

If data missing → synthetic fallback model is used.

Outputs:
- results/virmasvesi_hepp.csv
- results/virmasvesi_plot.png
"""

import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# -----------------------------
# CONFIG
# -----------------------------

DATA_PATH = "data/raw/"
RESULT_PATH = "results/virmasvesi/"

os.makedirs(RESULT_PATH, exist_ok=True)

START_DATE = "2020-01-01"
END_DATE = "2026-04-30"

# -----------------------------
# SYNTHETIC FALLBACK (if no data)
# -----------------------------

def generate_synthetic_virmasvesi():
    dates = pd.date_range(START_DATE, END_DATE, freq="D")
    n = len(dates)

    np.random.seed(42)

    # slow hydrological drift + drought cycles
    water = 300 + np.cumsum(np.random.normal(-0.01, 0.5, n))
    precip = np.random.gamma(2, 2, n)  # mm/day
    temp = 5 + 15*np.sin(np.linspace(0, 10*np.pi, n)) + np.random.normal(0, 2, n)

    return pd.DataFrame({
        "date": dates,
        "water_level": water,
        "precip": precip,
        "temp": temp
    })


# -----------------------------
# DATA LOADING
# -----------------------------

def load_or_fallback():

    try:
        wl = pd.read_csv(DATA_PATH + "water_level.csv", parse_dates=["date"])
        pr = pd.read_csv(DATA_PATH + "precipitation.csv", parse_dates=["date"])
        tp = pd.read_csv(DATA_PATH + "temperature.csv", parse_dates=["date"])

        df = wl.merge(pr, on="date").merge(tp, on="date")

        print("✅ Real SYKE/FMI data loaded")

    except Exception as e:
        print("⚠️ Using synthetic fallback data:", e)
        df = generate_synthetic_virmasvesi()

    df = df.sort_values("date")
    df = df.set_index("date")

    return df


# -----------------------------
# HEM CORE (MVP)
# -----------------------------

def compute_hepp(df):

    # Normal baselines (rolling climatology)
    water_norm = df["water_level"].rolling(365, min_periods=30).mean()
    water_std = df["water_level"].rolling(365, min_periods=30).std()

    precip_norm = df["precip"].rolling(30, min_periods=10).mean()

    # -------------------------
    # SD - Storage Deficit
    # -------------------------
    sd = (df["water_level"] - water_norm) / (water_std + 1e-6)
    sd = 1 / (1 + np.exp(-sd))  # sigmoid

    # -------------------------
    # HSP - Stress Persistence
    # -------------------------
    stress = df["water_level"] < water_norm
    hsp = stress.rolling(168).sum() / 90.0
    hsp = np.clip(hsp, 0, 1)

    # -------------------------
    # RF - Recharge Failure
    # -------------------------
    rf_raw = precip_norm - df["precip"].rolling(30).mean()
    rf = 1 / (1 + np.exp(-rf_raw / (np.nanstd(rf_raw) + 1e-6)))

    # -------------------------
    # HEPP (MVP)
    # -------------------------
    hepp = 0.40*sd + 0.35*rf + 0.25*hsp

    return sd, hsp, rf, hepp


# -----------------------------
# PLOTTING
# -----------------------------

def plot_results(df, hepp):

    plt.figure(figsize=(12,6))
    plt.plot(df.index, hepp, label="HEPP (MVP)", linewidth=1.5)
    plt.title("HEM v1.1 MVP - Virmasvesi Hydrological Endurance Pressure")
    plt.ylabel("HEPP (0–1)")
    plt.xlabel("Time")
    plt.legend()
    plt.grid()

    outpath = RESULT_PATH + "virmasvesi_hepp.png"
    plt.savefig(outpath, dpi=200)
    plt.close()

    print(f"📊 Plot saved → {outpath}")


# -----------------------------
# MAIN
# -----------------------------

def main():

    print("\n🌊 HEM v1.1 MVP - Virmasvesi Run Starting...\n")

    df = load_or_fallback()

    sd, hsp, rf, hepp = compute_hepp(df)

    results = pd.DataFrame({
        "SD": sd,
        "HSP": hsp,
        "RF": rf,
        "HEPP": hepp
    }, index=df.index)

    out_csv = RESULT_PATH + "virmasvesi_hepp.csv"
    results.to_csv(out_csv)

    print(f"💾 Results saved → {out_csv}")

    plot_results(df, hepp)

    print("\n✅ RUN COMPLETE - HEM MVP generated\n")


if __name__ == "__main__":
    main()
