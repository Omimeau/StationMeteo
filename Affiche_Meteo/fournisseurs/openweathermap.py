"""Prévisions OpenWeatherMap (offre gratuite « 5 day / 3 hour »).

Les prévisions sont fournies toutes les 3 heures. Elles sont converties
dans le format commun d'Open-Meteo, avec les codes météo WMO utilisés
par la page pour choisir l'icône.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import requests

URL_API = "https://api.openweathermap.org/data/2.5/forecast"

FUSEAU = ZoneInfo("Europe/Paris")


def code_wmo(identifiant):
    """Convertit un code de condition OpenWeatherMap en code WMO."""

    if identifiant is None:
        return None
    if 200 <= identifiant < 300:
        return 95       # Orage
    if 300 <= identifiant < 400:
        return 51       # Bruine
    if identifiant == 500:
        return 61       # Pluie faible
    if identifiant == 501:
        return 63       # Pluie modérée
    if 502 <= identifiant <= 504:
        return 65       # Pluie forte
    if identifiant == 511:
        return 66       # Pluie verglaçante
    if 520 <= identifiant < 600:
        return 80       # Averses
    if identifiant == 600:
        return 71       # Neige faible
    if identifiant == 601:
        return 73       # Neige
    if identifiant == 602:
        return 75       # Neige forte
    if 611 <= identifiant <= 616:
        return 77       # Neige mêlée de pluie
    if 620 <= identifiant < 700:
        return 85       # Averses de neige
    if 700 <= identifiant < 800:
        return 45       # Brouillard, brume, fumée...
    if identifiant == 800:
        return 0        # Ciel dégagé
    if identifiant == 801:
        return 1
    if identifiant == 802:
        return 2
    return 3            # Couvert


def convertir(donnees):
    """Transforme la réponse OpenWeatherMap au format commun."""

    hourly = {
        "time": [],
        "temperature_2m": [],
        "relative_humidity_2m": [],
        "precipitation": [],
        "precipitation_probability": [],
        "wind_speed_10m": [],
        "wind_direction_10m": [],
        "pressure_msl": [],
        "sunshine_duration": [],
        "shortwave_radiation": [],
        "weather_code": []
    }

    try:
        for element in donnees["list"]:

            date = datetime.fromtimestamp(element["dt"], FUSEAU)
            principal = element.get("main", {})
            vent = element.get("wind", {})
            conditions = element.get("weather") or [{}]

            # Pluie et neige cumulées sur les 3 heures
            precipitation = (
                element.get("rain", {}).get("3h", 0) +
                element.get("snow", {}).get("3h", 0)
            )

            vitesse = vent.get("speed")
            probabilite = element.get("pop")

            hourly["time"].append(date.strftime("%Y-%m-%dT%H:%M"))
            hourly["temperature_2m"].append(principal.get("temp"))
            hourly["relative_humidity_2m"].append(principal.get("humidity"))
            hourly["precipitation"].append(precipitation)
            hourly["precipitation_probability"].append(
                None if probabilite is None else probabilite * 100
            )
            # m/s vers km/h
            hourly["wind_speed_10m"].append(
                None if vitesse is None else vitesse * 3.6
            )
            hourly["wind_direction_10m"].append(vent.get("deg"))
            hourly["pressure_msl"].append(
                principal.get("sea_level", principal.get("pressure"))
            )
            # Non fournis par l'offre gratuite
            hourly["sunshine_duration"].append(None)
            hourly["shortwave_radiation"].append(None)
            hourly["weather_code"].append(
                code_wmo(conditions[0].get("id"))
            )

    except (KeyError, TypeError) as erreur:
        raise ValueError(f"Réponse OpenWeatherMap inattendue : {erreur}")

    if not hourly["time"]:
        raise ValueError("Prévisions OpenWeatherMap absentes")

    return {"hourly": hourly}


def recuperer(latitude, longitude, cle_api):

    # Les messages d'erreur de requests contiennent l'URL complète,
    # donc la clé : ils sont remplacés pour ne pas la journaliser.
    try:
        reponse = requests.get(
            URL_API,
            params={
                "lat": latitude,
                "lon": longitude,
                "appid": cle_api,
                "units": "metric",
                "lang": "fr"
            },
            timeout=20
        )
    except requests.RequestException as erreur:
        raise requests.RequestException(
            f"OpenWeatherMap injoignable ({type(erreur).__name__})"
        ) from None

    if reponse.status_code == 401:
        raise ValueError(
            "Clé OpenWeatherMap refusée (invalide ou pas encore active)"
        )

    if not reponse.ok:
        raise requests.RequestException(
            f"OpenWeatherMap : erreur HTTP {reponse.status_code}"
        )

    return convertir(reponse.json())
