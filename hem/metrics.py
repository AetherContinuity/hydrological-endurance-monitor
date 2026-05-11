import numpy as np
import pandas as pd

def evaluate(df: pd.DataFrame) -> dict:
    """Compute lead-time metrics between signals and low-water events."""
    events = df[df["water_level"] < df["water_level"].quantile(0.1)]
    signals = df[df["signal"] == True]

    lead_times = []
    for idx in events.index:
        prior = signals[signals.index < idx]
        if len(prior) > 0:
            lead_times.append((idx - prior.index[-1]))

    return {
        "n_events": len(events),
        "n_signals": len(signals),
        "signal_rate": round(len(signals) / len(df), 3),
        "median_lead_days": float(np.median(lead_times)) if lead_times else None,
        "signal_coverage": round(len(lead_times) / len(events), 3) if len(events) > 0 else None,
    }
