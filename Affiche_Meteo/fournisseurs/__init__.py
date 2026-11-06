"""Liste des fournisseurs de prévisions météo.

Chaque fournisseur renvoie le même format commun (celui d'Open-Meteo) :
{"hourly": {"time": [...], "temperature_2m": [...], ...}}
Une valeur non fournie vaut None ; la page affiche alors « — ».
"""

import config_local

from . import met_norway, open_meteo, openweathermap

# Clé OpenWeatherMap facultative dans config_local.py
CLE_OPENWEATHERMAP = getattr(config_local, "OPENWEATHERMAP_API_KEY", "")

# Adresse de contact facultative, transmise à MET Norway
CONTACT_MET_NORWAY = getattr(config_local, "MET_NORWAY_CONTACT", "")

FOURNISSEURS = {
    "open_meteo": {
        "nom": "Open-Meteo",
        "recuperer": lambda lat, lon: open_meteo.recuperer(lat, lon)
    },
    "meteofrance": {
        "nom": "Météo-France AROME/ARPEGE (Open-Meteo)",
        "recuperer": lambda lat, lon: open_meteo.recuperer(
            lat, lon, "meteofrance_seamless"
        )
    },
    "ecmwf": {
        "nom": "ECMWF IFS (Open-Meteo)",
        "recuperer": lambda lat, lon: open_meteo.recuperer(
            lat, lon, "ecmwf_ifs"
        )
    },
    "gfs": {
        "nom": "NOAA GFS (Open-Meteo)",
        "recuperer": lambda lat, lon: open_meteo.recuperer(
            lat, lon, "gfs_seamless"
        )
    },
    "met_norway": {
        "nom": "MET Norway",
        "recuperer": lambda lat, lon: met_norway.recuperer(
            lat, lon, CONTACT_MET_NORWAY
        )
    }
}

# OpenWeatherMap n'est proposé que si une clé est configurée
if CLE_OPENWEATHERMAP:
    FOURNISSEURS["openweathermap"] = {
        "nom": "OpenWeatherMap",
        "recuperer": lambda lat, lon: openweathermap.recuperer(
            lat, lon, CLE_OPENWEATHERMAP
        )
    }

FOURNISSEUR_PAR_DEFAUT = "open_meteo"
