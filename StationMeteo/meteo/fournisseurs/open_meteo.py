"""Prévisions Open-Meteo, avec le choix du modèle météorologique.

Open-Meteo renvoie directement le format commun attendu par la page :
aucune conversion n'est nécessaire.
"""

import requests

URL_API = "https://api.open-meteo.com/v1/forecast"

VARIABLES_HORAIRES = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "precipitation_probability",
    "wind_speed_10m",
    "wind_direction_10m",
    "pressure_msl",
    "sunshine_duration",
    "shortwave_radiation",
    "weather_code"
]


def recuperer(latitude, longitude, modele=None):

    parametres = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": VARIABLES_HORAIRES,
        "forecast_days": 5,
        "timezone": "Europe/Paris"
    }

    # Sans modèle, Open-Meteo choisit le meilleur pour la position
    if modele:
        parametres["models"] = modele

    reponse = requests.get(
        URL_API,
        params=parametres,
        timeout=20
    )

    reponse.raise_for_status()

    donnees = reponse.json()

    if not donnees.get("hourly", {}).get("time"):
        raise ValueError("Prévisions horaires absentes")

    return {"hourly": donnees["hourly"]}
