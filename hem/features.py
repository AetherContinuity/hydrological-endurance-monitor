import pandas as pd

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute derived features for HEPP calculation."""
    # Storage Deficit: rate of change in water level
    df["SD"] = df["water_level"].pct_change().clip(-1, 1)

    # Hydrological Stress Persistence: fraction of below-mean days (90-day window)
    df["HSP"] = df["water_level"].rolling(90).apply(
        lambda x: (x < x.mean()).sum() / len(x), raw=True
    )

    # Recharge Flux: precipitation minus temperature-adjusted evaporation proxy
    df["RF"] = (df["precip"] - (df["temp"] - 5).clip(0)).rolling(30).mean()

    return df
