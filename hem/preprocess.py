import pandas as pd

def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by date and forward-fill missing values."""
    df = df.sort_values("date").reset_index(drop=True)
    df = df.fillna(method="ffill")
    return df
