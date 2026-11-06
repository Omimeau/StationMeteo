"""Nom de la ville correspondant aux coordonnées de la station.

Nominatim n'est interrogé qu'une fois : le résultat est conservé dans
donnees/ville.json tant que les coordonnées ne changent pas.
"""

import json

import requests

from . import config

FICHIER_VILLE = config.DOSSIER_DONNEES / "ville.json"

URL_GEOCODAGE = "https://nominatim.openstreetmap.org/reverse"

VILLE_INCONNUE = "Ville inconnue"


def obtenir_ville():

    # 1. Lire la ville déjà enregistrée
    if FICHIER_VILLE.exists():
        try:
            with open(FICHIER_VILLE, "r", encoding="utf-8") as f:
                cache = json.load(f)

            if (cache.get("latitude") == config.LATITUDE and
                    cache.get("longitude") == config.LONGITUDE):
                return cache["ville"]

        except (OSError, ValueError, KeyError):
            pass

    # 2. Interroger Nominatim une seule fois
    try:
        reponse = requests.get(
            URL_GEOCODAGE,
            params={
                "lat": config.LATITUDE,
                "lon": config.LONGITUDE,
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 10,
                "accept-language": "fr"
            },
            headers={
                "User-Agent": "AfficheMeteo/1.0 (usage personnel)"
            },
            timeout=15
        )

        reponse.raise_for_status()

        adresse = reponse.json().get("address", {})

        ville = (
            adresse.get("city")
            or adresse.get("town")
            or adresse.get("village")
            or adresse.get("municipality")
            or adresse.get("commune")
            or VILLE_INCONNUE
        )

        # 3. Enregistrer le résultat sur disque
        FICHIER_VILLE.parent.mkdir(parents=True, exist_ok=True)
        with open(FICHIER_VILLE, "w", encoding="utf-8") as f:
            json.dump({
                "latitude": config.LATITUDE,
                "longitude": config.LONGITUDE,
                "ville": ville
            }, f, ensure_ascii=False, indent=4)

        print("Ville détectée :", ville)

        return ville

    except (requests.RequestException, ValueError, OSError) as erreur:
        print("Erreur de géocodage :", erreur)
        return VILLE_INCONNUE
