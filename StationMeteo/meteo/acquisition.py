"""Acquisition des capteurs Tuya et enregistrement dans la base.

Utilisation :
    - par serveur.py, en tâche de fond (demarrer_en_arriere_plan) ;
    - seule, pour une acquisition unique : python -m meteo.acquisition

Économie d'appels API (quota de l'essai Tuya) :
    - la connexion au cloud (et donc le jeton) est créée une seule fois
      puis réutilisée ;
    - la liste des appareils est mise en cache (rafraîchie une fois par jour) ;
    - les appareils qui ne sont pas des capteurs sont écartés du cache ;
    - l'état de tous les capteurs est lu en un seul appel groupé
      (jusqu'à 20 appareils par appel).
    Résultat : environ 1 appel par acquisition au lieu de 2 + nombre d'appareils.
"""

import json
import threading
import time
from datetime import datetime

import tinytuya

from . import base_donnees, config

# Valeur renvoyée par certains capteurs en cas de mesure anormale
TEMPERATURE_INVALIDE = -200

# Codes Tuya qui identifient un capteur de température / humidité
CODES_CAPTEUR = {"va_temperature", "va_humidity"}

# Durée de validité du cache de la liste des appareils (en secondes)
DUREE_CACHE_APPAREILS = 24 * 3600

# Nombre maximal d'appareils par appel groupé (limite de l'API Tuya)
TAILLE_LOT = 20

# État conservé entre deux acquisitions
_cloud = None
_appareils = None          # {device_id: nom}
_date_appareils = 0.0
_verrou = threading.Lock()


def lire_config_tuya():
    with open(config.FICHIER_TINYTUYA, "r", encoding="utf-8") as fichier:
        return json.load(fichier)


def _reinitialiser():
    """Oublie la connexion et le cache (ils seront recréés au prochain relevé)."""
    global _cloud, _appareils, _date_appareils
    _cloud = None
    _appareils = None
    _date_appareils = 0.0


def _obtenir_cloud():
    """Crée la connexion au cloud une seule fois (1 appel pour le jeton)."""
    global _cloud
    if _cloud is None:
        config_tuya = lire_config_tuya()
        _cloud = tinytuya.Cloud(
            apiRegion=config_tuya["apiRegion"],
            apiKey=config_tuya["apiKey"],
            apiSecret=config_tuya["apiSecret"],
        )
    return _cloud


def _obtenir_appareils(cloud):
    """Liste des appareils, mise en cache pendant DUREE_CACHE_APPAREILS."""
    global _appareils, _date_appareils

    maintenant = time.monotonic()
    if (_appareils is not None
            and maintenant - _date_appareils < DUREE_CACHE_APPAREILS):
        return _appareils

    appareils = cloud.getdevices()

    if not isinstance(appareils, list):
        raise RuntimeError(
            "Réponse inattendue de l'API Tuya : "
            + json.dumps(appareils, ensure_ascii=False)
        )

    _appareils = {
        appareil["id"]: appareil.get("name", "Sans nom")
        for appareil in appareils
        if appareil.get("id")
    }
    _date_appareils = maintenant
    print(f"Liste des appareils Tuya rafraîchie : {len(_appareils)} appareil(s).")
    return _appareils


def _lire_etats(cloud, device_ids):
    """Lit l'état de plusieurs appareils en un appel par lot de 20.

    Renvoie {device_id: {code: valeur}}.
    """
    etats = {}

    for debut in range(0, len(device_ids), TAILLE_LOT):
        lot = device_ids[debut:debut + TAILLE_LOT]
        reponse = cloud.cloudrequest(
            "/v1.0/iot-03/devices/status",
            query={"device_ids": ",".join(lot)},
        )

        if not isinstance(reponse, dict) or not reponse.get("success", False):
            raise RuntimeError(
                "Échec de la lecture groupée Tuya : "
                + json.dumps(reponse, ensure_ascii=False)
            )

        for appareil in reponse.get("result", []):
            etats[appareil.get("id")] = {
                element["code"]: element["value"]
                for element in appareil.get("status", [])
                if "code" in element and "value" in element
            }

    return etats


def lire_capteurs():
    """Interroge le cloud Tuya.

    Renvoie une liste de tuples (capteur, temperature, humidite, batterie).
    """
    with _verrou:
        try:
            cloud = _obtenir_cloud()
            appareils = _obtenir_appareils(cloud)
            etats = _lire_etats(cloud, list(appareils))
        except Exception:
            # Connexion ou jeton peut-être invalide : on repartira de zéro
            # au prochain relevé (au lieu de réessayer en boucle).
            _reinitialiser()
            raise

        releves = []

        for device_id, nom in list(appareils.items()):
            valeurs = etats.get(device_id)

            if valeurs is None:
                print(f"Pas de réponse Tuya pour {nom}.")
                continue

            # Appareil qui n'est pas un capteur (prise, ampoule...) :
            # on le retire du cache pour ne plus l'interroger.
            # (un état vide ne prouve rien : on garde l'appareil.)
            if valeurs and not CODES_CAPTEUR & valeurs.keys():
                del appareils[device_id]
                continue

            temperature = valeurs.get("va_temperature")
            if temperature == TEMPERATURE_INVALIDE:
                temperature = None
            humidite = valeurs.get("va_humidity")
            batterie = valeurs.get("va_battery")

            if temperature is None and humidite is None:
                continue

            releves.append((nom, temperature, humidite, batterie))

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
