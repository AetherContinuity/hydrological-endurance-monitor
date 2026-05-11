# HEM v1.1 — Hydrological Endurance Monitor

A diagnostic framework for multi-basin hydrological endurance stress analysis.

## Concept

HEM does **not** predict water levels or weather. It measures:

> Hydrological system endurance depletion over time.

Core output: **HEPP** (Hydrological Endurance Pressure Proxy) — a composite index of three components:

| Component | Description | Default weight |
|-----------|-------------|---------------|
| SD | Storage Deficit (rate of change) | 0.40 |
| HSP | Hydrological Stress Persistence (90-day) | 0.35 |
| RF | Recharge Flux (precipitation–evaporation proxy) | 0.25 |

## Basins

- **Saimaa** multi-basin system (primary: Lauritsala gauge, SYKE 04200)
- Virmasvesi (extension, `scripts/run_virmasvesi.py`)
- Pielinen (comparison basin, planned)

## WEM Coupling

HEM's WR (Water Reservoir) component feeds into the
[Winter Endurance Monitor](https://aethercontinuity.org/tools/ACI-INSTRUMENT-v2.html)
EPP calculation. Saimaa hydrology is one of seven concurrent risk pressures
documented in [TN-009](https://aethercontinuity.org/supplements/tn-009-compound-risk-analysis.html).

## Installation

```bash
git clone https://github.com/AetherContinuity/hydrological-endurance-monitor.git
cd hydrological-endurance-monitor
pip install -r requirements.txt
```

## Data

Place CSV files in `data/raw/`:

```
data/raw/
├── water_level.csv   # columns: date, water_level
├── precip.csv        # columns: date, precip
└── temp.csv          # columns: date, temp
```

SYKE Open Data: https://www.syke.fi/avointieto

## Run

```bash
python main.py
```

Outputs: `reports/figures/hepp.png`, `outputs/metrics.json`

## Status

Research prototype — not an operational forecasting system.

## License

MIT — see LICENSE
