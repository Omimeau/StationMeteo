"""Prévisions MET Norway (Locationforecast 2.0, api.met.no).

Gratuit et sans clé, mais un User-Agent identifiant l'application est
obligatoire. Données sous licence CC BY 4.0 : citer MET Norway.

Les prévisions sont horaires sur environ 2,5 jours, puis par pas de
6 heures. Elles sont converties dans le format commun d'Open-Meteo.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

URL_API = "https://api.met.no/weatherapi/locationforecast/2.0/complete"

NOM_APPLICATION = "AfficheMeteo/1.0"

FUSEAU = ZoneInfo("Europe/Paris")

NOMBRE_JOURS = 5


def code_wmo(symbole):
    """Convertit un symbole MET Norway (ex. « lightrain_day ») en code WMO."""

    if not symbole:
        return None

    # Retirer la variante jour / nuit / crépuscule polaire
    nom = symbole.split("_")[0]

    if "thunder" in nom:
        return 95       # Orage

    correspondances = {
        "clearsky": 0,
        "fair": 1,
        "partlycloudy": 2,
        "cloudy": 3,
        "fog": 45,
        "lightrain": 61,
        "rain": 63,
        "heavyrain": 65,
        "lightsleet": 67,
        "sleet": 67,
        "heavysleet": 67,
        "lightsnow": 71,
        "snow": 73,
        "heavysnow": 75,
        "lightrainshowers": 80,
        "rainshowers": 81,
        "heavyrainshowers": 82,
        "lightsleetshowers": 80,
        "sleetshowers": 81,
        "heavysleetshowers": 82,
        "lightsnowshowers": 85,
        "snowshowers": 85,
        "heavysnowshowers": 86
    }

    return correspondances.get(nom, 3)


def nouvelle_ligne(hourly, date):
    """Ajoute une heure vide (toutes les valeurs à None)."""

    for cle in hourly:
        hourly[cle].append(None)

    hourly["time"][-1] = date.strftime("%Y-%m-%dT%H:%M")


def convertir(donnees):
    """Transforme la réponse MET Norway au format commun."""

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

    jours = []

    try:
        for element in donnees["properties"]["timeseries"]:

            date = datetime.fromisoformat(
                element["time"].replace("Z", "+00:00")
            ).astimezone(FUSEAU)

            # Limiter aux 5 jours affichés par la page
            jour = date.date()
            if jour not in jours:
                if len(jours) == NOMBRE_JOURS:
                    break
                jours.append(jour)

            donnees_element = element["data"]
            instant = donnees_element["instant"]["details"]

            # Prévision de l'heure suivante, sinon des 6 heures suivantes
            suivante = (
                donnees_element.get("next_1_hours")
                or donnees_element.get("next_6_hours")
            )

            # La dernière échéance ne contient pas de prévision
            if suivante is None:
                continue

            details = suivante.get("details", {})
            vitesse = instant.get("wind_speed")

            nouvelle_ligne(hourly, date)
            hourly["temperature_2m"][-1] = instant.get("air_temperature")
            hourly["relative_humidity_2m"][-1] = instant.get(
                "relative_humidity"
            )
            hourly["precipitation"][-1] = details.get(
                "precipitation_amount"
            )
            # Non fourni pour la France, en général
            hourly["precipitation_probability"][-1] = details.get(
                "probability_of_precipitation"
            )
            # m/s vers km/h
            hourly["wind_speed_10m"][-1] = (
                None if vitesse is None else vitesse * 3.6
            )
            hourly["wind_direction_10m"][-1] = instant.get(
                "wind_from_direction"
            )
            hourly["pressure_msl"][-1] = instant.get(
                "air_pressure_at_sea_level"
            )
            hourly["weather_code"][-1] = code_wmo(
                suivante.get("summary", {}).get("symbol_code")
            )

            # Pas de 6 heures : une seule température par période.
            # Le minimum et le maximum prévus sont donc placés sur
            # deux heures de la même période, pour que la page
            # affiche un écart min / max réaliste.
            if "next_1_hours" not in donnees_element:
                minimum = details.get("air_temperature_min")
                maximum = details.get("air_temperature_max")

                if minimum is not None and maximum is not None:
                    hourly["temperature_2m"][-1] = minimum
                    nouvelle_ligne(hourly, date + timedelta(hours=3))
                    hourly["temperature_2m"][-1] = maximum

    except (KeyError, TypeError, ValueError) as erreur:
        raise ValueError(f"Réponse MET Norway inattendue : {erreur}")

    if not hourly["time"]:
        raise ValueError("Prévisions MET Norway absentes")

    return {"hourly": hourly}


def recuperer(latitude, longitude, contact=""):

    # MET Norway demande un moyen de contact dans le User-Agent
    user_agent = (
        f"{NOM_APPLICATION} ({contact})" if contact
        else f"{NOM_APPLICATION} (usage personnel)"
    )

    reponse = requests.get(
        URL_API,
        # MET Norway demande au plus 4 décimales
        params={
            "lat": round(latitude, 4),
            "lon": round(longitude, 4)
        },
        headers={"User-Agent": user_agent},
        timeout=20
    )

    reponse.raise_for_status()

    return convertir(reponse.json())
