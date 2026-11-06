"""Prévisions météo : fournisseur actif, cache et heures passées.

Ce module ne dépend pas de Flask : les fonctions renvoient des
dictionnaires (et un code HTTP) que app.py transforme en JSON.
"""

import json
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from . import config
from .fournisseurs import FOURNISSEURS, FOURNISSEUR_PAR_DEFAUT
from .geocodage import obtenir_ville

FUSEAU = ZoneInfo("Europe/Paris")

# Durée de validité du cache : 60 minutes
DUREE_CACHE = 60 * 60

# Délai entre deux tentatives après un échec
DELAI_ERREUR = 60

# Un cache par fournisseur, partagé entre les navigateurs.
# Revenir à un fournisseur déjà consulté n'appelle pas son API.
caches_meteo = {
    identifiant: {
        "donnees": None,
        "date_recuperation": None,
        "date_recuperation_reelle": None,
        "prochaine_tentative": 0
    }
    for identifiant in FOURNISSEURS
}

# Empêche deux récupérations simultanées
verrou_cache = threading.Lock()


# =======================================
# FOURNISSEUR DE PRÉVISIONS ACTIF
# =======================================

FICHIER_FOURNISSEUR = config.DOSSIER_DONNEES / "fournisseur.json"


def lire_fournisseur():
    """Fournisseur choisi sur la page, conservé après un redémarrage."""
    try:
        with open(FICHIER_FOURNISSEUR, "r", encoding="utf-8") as f:
            identifiant = json.load(f)["fournisseur"]

        if identifiant in FOURNISSEURS:
            return identifiant

    except (OSError, ValueError, KeyError):
        pass

    return FOURNISSEUR_PAR_DEFAUT


def enregistrer_fournisseur(identifiant):
    FICHIER_FOURNISSEUR.parent.mkdir(parents=True, exist_ok=True)
    with open(FICHIER_FOURNISSEUR, "w", encoding="utf-8") as f:
        json.dump({"fournisseur": identifiant}, f, indent=4)


fournisseur_actif = lire_fournisseur()


def description_fournisseur(identifiant):
    return {
        "id": identifiant,
        "nom": FOURNISSEURS[identifiant]["nom"]
    }


def liste_fournisseurs():
    return [
        description_fournisseur(identifiant)
        for identifiant in FOURNISSEURS
    ]


def choisir_fournisseur(identifiant):
    """Change le fournisseur actif. Renvoie False s'il est inconnu."""
    global fournisseur_actif

    if identifiant not in FOURNISSEURS:
        return False

    with verrou_cache:
        fournisseur_actif = identifiant

        try:
            enregistrer_fournisseur(identifiant)
        except OSError as erreur:
            # Le choix reste actif jusqu'au prochain redémarrage
            print("Erreur d'enregistrement du fournisseur :", erreur)

    print("Météo : fournisseur choisi :", identifiant)
    return True


# =======================================
# HEURES PASSÉES DE LA JOURNÉE
# =======================================

# MET Norway et OpenWeatherMap ne renvoient que les heures à venir.
# Les heures d'aujourd'hui déjà reçues sont conservées dans ce
# fichier, pour continuer à afficher les périodes passées, même
# après un redémarrage. Il est vidé au changement de jour.
FICHIER_PREVISIONS_DU_JOUR = (
    config.DOSSIER_DONNEES / "previsions_du_jour.json"
)


def aujourdhui():
    return datetime.now(FUSEAU).date().isoformat()


def lire_previsions_du_jour():
    try:
        with open(FICHIER_PREVISIONS_DU_JOUR, "r", encoding="utf-8") as f:
            memoire = json.load(f)

        if (memoire.get("date") == aujourdhui() and
                isinstance(memoire.get("fournisseurs"), dict)):
            return memoire

    except (OSError, ValueError, AttributeError):
        pass

    return {"date": aujourdhui(), "fournisseurs": {}}


def enregistrer_previsions_du_jour():
    # Écriture dans un fichier temporaire puis remplacement, pour ne
    # jamais laisser un fichier à moitié écrit en cas de coupure.
    FICHIER_PREVISIONS_DU_JOUR.parent.mkdir(parents=True, exist_ok=True)
    temporaire = FICHIER_PREVISIONS_DU_JOUR.with_suffix(".tmp")

    with open(temporaire, "w", encoding="utf-8") as f:
        json.dump(previsions_du_jour, f, ensure_ascii=False)

    temporaire.replace(FICHIER_PREVISIONS_DU_JOUR)


previsions_du_jour = lire_previsions_du_jour()


def conserver_heures_passees(identifiant, donnees):
    """Complète les prévisions avec les heures d'aujourd'hui déjà reçues."""
    global previsions_du_jour

    jour = aujourdhui()

    if previsions_du_jour["date"] != jour:
        previsions_du_jour = {"date": jour, "fournisseurs": {}}

    hourly = donnees["hourly"]
    cles = [cle for cle in hourly if cle != "time"]

    lignes = {
        heure: {cle: hourly[cle][i] for cle in cles}
        for i, heure in enumerate(hourly["time"])
    }

    memoire = previsions_du_jour["fournisseurs"].setdefault(identifiant, {})

    # Une heure à venir : la nouvelle prévision remplace l'ancienne
    for heure, ligne in lignes.items():
        if heure.startswith(jour):
            memoire[heure] = ligne

    # Une heure passée, absente de la réponse : reprise de la mémoire
    for heure, ligne in memoire.items():
        lignes.setdefault(heure, ligne)

    heures = sorted(lignes)

    fusion = {"time": heures}
    for cle in cles:
        fusion[cle] = [lignes[heure].get(cle) for heure in heures]

    try:
        enregistrer_previsions_du_jour()
    except OSError as erreur:
        # Les heures restent conservées en mémoire jusqu'au redémarrage
        print("Erreur d'enregistrement des prévisions du jour :", erreur)

    return {**donnees, "hourly": fusion}


# =======================================
# PRÉVISIONS DU FOURNISSEUR ACTIF
# =======================================

def _reponse(identifiant, etat="valide"):

    cache_meteo = caches_meteo[identifiant]
    maintenant = time.monotonic()

    date_recuperation = cache_meteo["date_recuperation"]

    if date_recuperation is not None:
        age = maintenant - date_recuperation
        restant = max(0, int(DUREE_CACHE - age))
    else:
        restant = 0

    attente = max(
        0,
        int(cache_meteo["prochaine_tentative"] - maintenant)
    )

    return {
        **cache_meteo["donnees"],
        "ville": obtenir_ville(),
        "fournisseur": description_fournisseur(identifiant),
        "cache_info": {
            "etat": etat,
            "date_recuperation": cache_meteo["date_recuperation_reelle"],
            "secondes_restantes": restant,
            "secondes_avant_tentative": attente
        }
    }


def _erreur(identifiant, message):
    return {
        "erreur": message,
        "fournisseur": description_fournisseur(identifiant)
    }


def obtenir_previsions():
    """Prévisions du fournisseur actif, depuis le cache si possible.

    Renvoie (dictionnaire, code HTTP).
    """
    with verrou_cache:

        identifiant = fournisseur_actif
        fournisseur = FOURNISSEURS[identifiant]
        cache_meteo = caches_meteo[identifiant]

        maintenant = time.monotonic()

        # 1. Cache encore valide
        if cache_meteo["donnees"] is not None:
            age = maintenant - cache_meteo["date_recuperation"]

            if age < DUREE_CACHE:
                print("Météo : utilisation du cache", identifiant)
                return _reponse(identifiant, "valide"), 200

        # 2. Attente après un échec
        if maintenant < cache_meteo["prochaine_tentative"]:

            if cache_meteo["donnees"] is not None:
                return _reponse(identifiant, "attente"), 200

            return _erreur(
                identifiant, "Service météo temporairement indisponible"
            ), 503

        # 3. Nouvelle récupération des prévisions
        print("Météo : interrogation de", fournisseur["nom"])

        try:
            donnees = conserver_heures_passees(
                identifiant,
                fournisseur["recuperer"](config.LATITUDE, config.LONGITUDE)
            )

            cache_meteo["donnees"] = donnees
            cache_meteo["date_recuperation"] = time.monotonic()
            cache_meteo["date_recuperation_reelle"] = (
                datetime.now(FUSEAU).isoformat()
            )
            cache_meteo["prochaine_tentative"] = 0

            print("Météo : prévisions actualisées")

            return _reponse(identifiant, "valide"), 200

        except (requests.RequestException, ValueError) as erreur:

            print("Erreur météo :", erreur)

            cache_meteo["prochaine_tentative"] = (
                time.monotonic() + DELAI_ERREUR
            )

            # Conservation des anciennes prévisions
            if cache_meteo["donnees"] is not None:
                print("Météo : anciennes prévisions utilisées")
                return _reponse(identifiant, "attente"), 200

            return _erreur(
                identifiant, "Impossible de récupérer les prévisions"
            ), 502
