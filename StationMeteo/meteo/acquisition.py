"""Acquisition des capteurs Tuya et enregistrement dans la base.

Utilisation :
    - par serveur.py, en tâche de fond (demarrer_en_arriere_plan) ;
    - seule, pour une acquisition unique : python -m meteo.acquisition
"""

import json
import threading
from datetime import datetime

import tinytuya

from . import base_donnees, config

# Valeur renvoyée par certains capteurs en cas de mesure anormale
TEMPERATURE_INVALIDE = -200


def lire_config_tuya():
    with open(config.FICHIER_TINYTUYA, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def lire_capteurs():
    """Interroge le cloud Tuya.

    Renvoie une liste de tuples (capteur, temperature, humidite, batterie).
    """
    config_tuya = lire_config_tuya()

    cloud = tinytuya.Cloud(
        apiRegion=config_tuya["apiRegion"],
        apiKey=config_tuya["apiKey"],
        apiSecret=config_tuya["apiSecret"],
    )

    appareils = cloud.getdevices()

    if not isinstance(appareils, list):
        raise RuntimeError(
            "Réponse inattendue de l'API Tuya : "
            + json.dumps(appareils, ensure_ascii=False)
        )

    releves = []

    for appareil in appareils:
        device_id = appareil.get("id")
        nom = appareil.get("name", "Sans nom")

        if not device_id:
            continue

        try:
            reponse = cloud.getstatus(device_id)

            if not reponse.get("success", False):
                print(f"Échec de lecture Tuya pour {nom}.")
                continue

            valeurs = {
                element["code"]: element["value"]
                for element in reponse.get("result", [])
                if "code" in element and "value" in element
            }

            temperature = valeurs.get("va_temperature")
            if temperature == TEMPERATURE_INVALIDE:
                temperature = None
            humidite = valeurs.get("va_humidity")
            batterie = valeurs.get("va_battery")

            # Ignorer les appareils qui ne sont pas des capteurs
            if temperature is None and humidite is None:
                continue

            releves.append((nom, temperature, humidite, batterie))

        except Exception as erreur:
            print(f"Erreur pour {nom} : {erreur}")

    return releves


def acquerir():
    """Une acquisition complète : capteurs Tuya puis base de données.

    Renvoie le nombre de relevés enregistrés. Lève une exception en cas
    d'échec global (fichier Tuya absent, base injoignable...).
    """
    print("\n******************************")
    print(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

    releves = lire_capteurs()
    nombre = base_donnees.enregistrer_releves(releves)

    print(f"{nombre} enregistrement(s).")
    return nombre


def _boucle(intervalle, arret):
    while not arret.is_set():
        try:
            acquerir()
        except Exception as erreur:
            # Une erreur ne doit pas arrêter les acquisitions suivantes
            print(f"Erreur d'acquisition : {erreur}")

        arret.wait(intervalle)


def demarrer_en_arriere_plan(intervalle=None):
    """Lance les acquisitions périodiques dans un thread.

    Renvoie un threading.Event : appeler .set() pour arrêter la boucle.
    """
    intervalle = intervalle or config.INTERVALLE_ACQUISITION
    arret = threading.Event()

    threading.Thread(
        target=_boucle,
        args=(intervalle, arret),
        name="acquisition-tuya",
        daemon=True,
    ).start()

    print(f"Acquisition Tuya : toutes les {intervalle} s")
    return arret


if __name__ == "__main__":
    import sys

    try:
        acquerir()
    except (OSError, ValueError, KeyError, RuntimeError,
            base_donnees.Erreur) as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        sys.exit(1)
