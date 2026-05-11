import pandas as pd

def backtest(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Flag stress events above alert threshold."""
    threshold = config["threshold"]["alert"]
    df["signal"] = df["HEPP"] > threshold
    return df
