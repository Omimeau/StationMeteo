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
# Mode nuit (bouton 🌙 de la case d'information) : luminosité en %,
# limitée entre 5 et 100 pour que l'écran ne devienne jamais tout noir.
LUMINOSITE_NUIT = min(100, max(5, int(parametre("LUMINOSITE_NUIT", defaut=35))))


def _heure_en_minutes(nom):
    """Heure "HH:MM" convertie en minutes depuis minuit ; None si vide
    ou invalide (le paramètre est alors ignoré)."""
    valeur = str(parametre(nom, defaut="")).strip()
    if not valeur:
        return None

    try:
        heures, minutes = (int(x) for x in valeur.split(":"))
        if 0 <= heures < 24 and 0 <= minutes < 60:
            return heures * 60 + minutes
    except ValueError:
        pass

    print(f"{nom} invalide (attendu HH:MM) : {valeur!r}, ignoré")
    return None


# Mode nuit programmé (heure de Paris, "HH:MM", la plage peut passer
# minuit). À NUIT_DEBUT la page passe en mode nuit ; à NUIT_FIN elle
# revient au mode jour si le mode nuit est toujours là. Vides (défaut) :
# pas de programmation. Les deux sont nécessaires et doivent différer.
NUIT_DEBUT = _heure_en_minutes("NUIT_DEBUT")
NUIT_FIN = _heure_en_minutes("NUIT_FIN")
if NUIT_DEBUT is None or NUIT_FIN is None or NUIT_DEBUT == NUIT_FIN:
    NUIT_DEBUT = NUIT_FIN = None

# Mode nuit de l'écran : "voile" = voile sombre (LUMINOSITE_NUIT), l'écran
# reste allumé ; "hdmi" = signal HDMI coupé (écran en veille, Linux /
# kiosque cage), rallumé au premier toucher ou à NUIT_FIN.
ECRAN_VEILLE = str(parametre("ECRAN_VEILLE", defaut="voile")).strip().lower()
if ECRAN_VEILLE not in ("voile", "hdmi"):
    print(f"ECRAN_VEILLE invalide (voile ou hdmi) : {ECRAN_VEILLE!r}, voile utilisé")
    ECRAN_VEILLE = "voile"
# Sortie vidéo coupée (nom donné par wlr-randr)
ECRAN_SORTIE = parametre("ECRAN_SORTIE", defaut="HDMI-A-1")
# Périphérique qui réveille l'écran ; vide = tous ceux de /dev/input/by-id
# (tactile, souris, clavier USB)
ECRAN_TACTILE = parametre("ECRAN_TACTILE", defaut="")

# Affichage interactif (écran tactile) : True = tous les fournisseurs sont
# interrogés en arrière-plan, le fournisseur se change sur la page et une
# case touchée s'ouvre en grand. False = une seule source, SOURCE_PRINCIPALE,
# et l'affichage classique des cases (tous les détails, rien à toucher).
AFFICHAGE_INTERACTIF = bool(parametre("AFFICHAGE_INTERACTIF", defaut=True))
# Identifiant du fournisseur : seule source si l'affichage n'est pas
# interactif, fournisseur de départ sinon (open_meteo, meteofrance, ecmwf,
# gfs, met_norway, openweathermap).
SOURCE_PRINCIPALE = parametre("SOURCE_PRINCIPALE", defaut="open_meteo")

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
