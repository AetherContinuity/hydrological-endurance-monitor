import matplotlib.pyplot as plt
import pandas as pd
import os

def plot_hepp(df: pd.DataFrame, output_dir: str = "reports/figures") -> None:
    """Plot HEPP time series with signal flags."""
    os.makedirs(output_dir, exist_ok=True)

    fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)

    axes[0].plot(df["date"], df["water_level"], color="#4a90d9", linewidth=0.8)
    axes[0].set_ylabel("Water level (m)")
    axes[0].set_title("Water Level")

    axes[1].plot(df["date"], df["HEPP"], color="#c0392b", linewidth=1.2)
    axes[1].axhline(0.6, color="orange", linestyle="--", linewidth=0.8, label="Alert threshold")
    axes[1].set_ylabel("HEPP")
    axes[1].set_title("Hydrological Endurance Pressure Proxy (HEPP)")
    axes[1].legend()

    signal_dates = df[df["signal"] == True]["date"]
    axes[2].scatter(signal_dates, [1] * len(signal_dates),
                    marker="|", color="#e67e22", s=50)
    axes[2].set_ylabel("Signal")
    axes[2].set_title("Stress Signals")
    axes[2].set_ylim(0, 2)

    plt.tight_layout()
    plt.savefig(f"{output_dir}/hepp.png", dpi=150)
    plt.close()
    print(f"  Saved: {output_dir}/hepp.png")
