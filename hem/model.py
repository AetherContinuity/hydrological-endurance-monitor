import pandas as pd
from hem.features import compute_features

def compute_hepp(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Compute HEPP from raw data using configured weights."""
    df = compute_features(df)

    w = config["weights"]
    df["HEPP"] = (
        w["SD"]  * df["SD"].fillna(0) +
        w["HSP"] * df["HSP"].fillna(0) +
        w["RF"]  * df["RF"].fillna(0)
    ).clip(0, 1)

    return df
