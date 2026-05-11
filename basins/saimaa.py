"""
Saimaa multi-basin configuration.

Sub-basins: Lappeenranta, Imatra, Puumala, Savonlinna
Primary gauge: Lauritsala (SYKE station 04200)
NTC coupling: SE1→FI via WEM §12 DS 60 (Aurora Line)
"""

SAIMAA_CONFIG = {
    "name": "Saimaa",
    "primary_gauge": "Lauritsala",
    "syke_station": "04200",
    "sub_basins": ["Lappeenranta", "Imatra", "Puumala", "Savonlinna"],
    "catchment_km2": 68_500,
    "regulation": {
        "operator": "Imatran Voima / Fortum",
        "outlet": "Imatra power plant",
        "upper_limit_m": 76.60,
        "lower_limit_m": 75.10,
    },
    "hem_coupling": {
        "wem_component": "WR",  # Water Reservoir index in WEM EPP
        "weight_in_wem": 0.20,
    }
}
