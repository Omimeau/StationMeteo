"""Paramètres de la station, lus dans config_local.py.

Toutes les autres parties du code importent leurs réglages d'ici.
Les anciens noms MYSQL_* (ancien projet Affiche_Meteo) restent acceptés
en secours des noms DB_*.
"""

from pathlib import Path

import config_local

# Racine du projet (dossier contenant serveur.py)
RACINE = Path(__file__).resolve().parent.parent

# Fichiers d'état de l'affichage (fournisseur choisi, ville, prévisions)
DOSSIER_DONNEES = RACINE / "donnees"

_ABSENT = object()


def parametre(*noms, defaut=_ABSENT):
    """Première valeur non vide parmi les noms donnés."""
    for nom in noms:
        valeur = getattr(config_local, nom, None)
        if valeur is not None and str(valeur) != "":
            return valeur

    if defaut is _ABSENT:
        raise ValueError(
            "Paramètre manquant dans config_local.py : " + " ou ".join(noms)
        )
    return defaut


# Base de données
DB_HOST = parametre("DB_HOST", "MYSQL_HOST", defaut="localhost")
DB_PORT = int(parametre("DB_PORT", defaut=3306))
DB_USER = parametre("DB_USER", "MYSQL_USER")
DB_PASSWORD = parametre("DB_PASSWORD", "MYSQL_PASSWORD")
DB_NAME = parametre("DB_NAME", "MYSQL_DATABASE")

# Serveur web
SERVEUR_HOTE = parametre("SERVEUR_HOTE", defaut="0.0.0.0")
SERVEUR_PORT = int(parametre("SERVEUR_PORT", defaut=5000))

# Acquisition Tuya
ACQUISITION_AUTOMATIQUE = bool(parametre("ACQUISITION_AUTOMATIQUE", defaut=True))
INTERVALLE_ACQUISITION = int(parametre("INTERVALLE_ACQUISITION", defaut=300))
FICHIER_TINYTUYA = RACINE / "tinytuya.json"

# Localisation
LATITUDE = parametre("LATITUDE")
LONGITUDE = parametre("LONGITUDE")

# Affichage
PERIODES = parametre("PERIODES")
ROTATION_PERIODES = parametre("ROTATION_PERIODES", defaut=12)
SEUIL_ECART_TEMPERATURE = parametre("SEUIL_ECART_TEMPERATURE", defaut=2.0)
HISTORIQUE_TEMPERATURE_HEURES = parametre(
    "HISTORIQUE_TEMPERATURE_HEURES", defaut=24
)
INTERVALLE_CAPTEURS = parametre("INTERVALLE_CAPTEURS", defaut=300)
INTERVALLE_METEO = parametre("INTERVALLE_METEO", defaut=3600)

# Fournisseurs de prévisions (facultatifs)
MET_NORWAY_CONTACT = parametre("MET_NORWAY_CONTACT", defaut="")
OPENWEATHERMAP_API_KEY = parametre("OPENWEATHERMAP_API_KEY", defaut="")

# Sauvegarde. Les paramètres propres à chaque destination (par exemple
# PCLOUD_UPLOAD_CODE) sont lus par son module dans meteo/destinations/,
# uniquement au lancement d'une sauvegarde.
SAUVEGARDE_DESTINATION = parametre("SAUVEGARDE_DESTINATION", defaut="pcloud")
SAUVEGARDE_AUTOMATIQUE = bool(parametre("SAUVEGARDE_AUTOMATIQUE", defaut=True))
SAUVEGARDE_HEURE = parametre("SAUVEGARDE_HEURE", defaut="03:01")
SAUVEGARDE_PERIODICITE_HEURES = int(parametre("SAUVEGARDE_PERIODICITE_HEURES", defaut=24))
