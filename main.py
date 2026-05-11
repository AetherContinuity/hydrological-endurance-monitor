"""
HEM v1.1 — Hydrological Endurance Monitor
Main entry point.

Usage:
    python main.py

Outputs:
    reports/figures/hepp.png
    outputs/metrics.json
"""

import yaml
import json
from hem.io import load_data
from hem.preprocess import preprocess
from hem.model import compute_hepp
from hem.backtest import backtest
from hem.metrics import evaluate
from hem.visualization import plot_hepp


def main():
    print("HEM v1.1 — Hydrological Endurance Monitor")
    print("=" * 45)

    config = yaml.safe_load(open("config.yaml"))

    print("Loading data...")
    df = load_data("data/raw/")

    print("Preprocessing...")
    df = preprocess(df)

    print("Computing HEPP...")
    df = compute_hepp(df, config)

    print("Backtesting...")
    df = backtest(df, config)

    print("Evaluating...")
    metrics = evaluate(df)
    print("\nMetrics:")
    for k, v in metrics.items():
        print(f"  {k}: {v}")

    with open("outputs/metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print("\nPlotting...")
    plot_hepp(df)

    print("\nDone.")


if __name__ == "__main__":
    main()
