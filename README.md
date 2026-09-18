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

## SYKE-asemat (scripts/fetch_iisvesi.py, fetch_muonio.py)

Vahvistettu 2026-09-17 (kayttaja, suora SYKE Hydrologiarajapinta-tarkistus
aci-nve-proxyn `/syke`-reitin kautta):

| Paikka_Id | Suure | Kohde | Kaytossa |
|---|---|---|---|
| 1966 | 1 (vedenkorkeus, cm) | Iisvesi | SD_kevät/SD_nyt (fetch_iisvesi.py) |
| 1005 | 2 (virtaama, m³/s) | Nokisenkoski (Iisveden lasku-uoma) | RF (fetch_iisvesi.py) |
| 2532 | 1 (vedenkorkeus, cm) | Muonionjoki Muonio (=WSFS q6700800y) | SD_kevät/SD_nyt (fetch_muonio.py) |

Korkeusjärjestelmä asemalla 1966: NN = nollakohta + Arvo/100, nollakohta
96.88 m (VedenkTasoTieto). HEM:n NORM/MNW/MHW-vakiot (HEM-monitor.html)
ovat NN-järjestelmässä — EI N60 eikä N2000.

**Löydetty, ei vielä käytössä** (vesitase/BEM-E-jatkotyötä varten):

| Paikka_Id | Kohde | Mahdollinen käyttö |
|---|---|---|
| 1003 | Nilakka, Äyskoski (toiminnassa) | Iisveden päätulovirtaama — vesitase |
| 3969 | Haringan pato (toiminnassa) | Iisvesi–Virmasvesi-jakouoma — merkitys vesitaseessa selvitettävä |
| 3583 | Iisvesi, pintaveden lämpötila | BEM-E: NDCI-tulkinnan tuki (lämpötila vaikuttaa leväkasvuun) |
| 277 | Iisvesi, jäätymis-/jäänlähtöpäivät | WEM-kytkentä (talvikauden pituus) |
| 450 | Iisvesi, jäänpaksuus | — |

Vesitase (tulovirtaama − lähtövirtaama ≈ varaston muutos + sadanta−haihdunta)
ei ole toteutettu — seuraavan vaiheen työ.

## Status

Research prototype — not an operational forecasting system.

## License

MIT — see LICENSE
