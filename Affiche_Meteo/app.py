import mysql.connector

from config_local import (
    MYSQL_HOST,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
    LATITUDE,
    LONGITUDE,
    SEUIL_ECART_TEMPERATURE,
    HISTORIQUE_TEMPERATURE_HEURES,
    INTERVALLE_CAPTEURS,
    INTERVALLE_METEO,
    PERIODES,
    ROTATION_PERIODES
)
from datetime import timedelta
from flask import Flask, jsonify, render_template, request
import requests
import time
import threading

from datetime import datetime
from zoneinfo import ZoneInfo
import json
from pathlib import Path

from fournisseurs import FOURNISSEURS, FOURNISSEUR_PAR_DEFAUT

app = Flask(__name__)

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

FICHIER_FOURNISSEUR = Path(__file__).resolve().parent / "fournisseur.json"


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
    with open(FICHIER_FOURNISSEUR, "w", encoding="utf-8") as f:
        json.dump({"fournisseur": identifiant}, f, indent=4)


fournisseur_actif = lire_fournisseur()


def description_fournisseur(identifiant):
    return {
        "id": identifiant,
        "nom": FOURNISSEURS[identifiant]["nom"]
    }


# =======================================
# HEURES PASSÉES DE LA JOURNÉE
# =======================================

# MET Norway et OpenWeatherMap ne renvoient que les heures à venir.
# Les heures d'aujourd'hui déjà reçues sont conservées dans ce
# fichier, pour continuer à afficher les périodes passées, même
# après un redémarrage. Il est vidé au changement de jour.
FICHIER_PREVISIONS_DU_JOUR = (
    Path(__file__).resolve().parent / "previsions_du_jour.json"
)


def aujourdhui():
    return datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()


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


@app.route("/")
def accueil():
    return render_template("index.html")


FICHIER_VILLE = Path(__file__).resolve().parent / "ville.json"

URL_GEOCODAGE = "https://nominatim.openstreetmap.org/reverse"


def obtenir_ville():

    # 1. Lire la ville déjà enregistrée
    if FICHIER_VILLE.exists():
        try:
            with open(FICHIER_VILLE, "r", encoding="utf-8") as f:
                cache = json.load(f)

            if (cache.get("latitude") == LATITUDE and
                    cache.get("longitude") == LONGITUDE):
                return cache["ville"]

        except (OSError, ValueError, KeyError):
            pass

    # 2. Interroger Nominatim une seule fois
    try:
        reponse = requests.get(
            URL_GEOCODAGE,
            params={
                "lat": LATITUDE,
                "lon": LONGITUDE,
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
            or "Ville inconnue"
        )

        # 3. Enregistrer le résultat sur disque
        with open(FICHIER_VILLE, "w", encoding="utf-8") as f:
            json.dump({
                "latitude": LATITUDE,
                "longitude": LONGITUDE,
                "ville": ville
            }, f, ensure_ascii=False, indent=4)

        print("Ville détectée :", ville)

        return ville

    except (requests.RequestException, ValueError, OSError) as erreur:
        print("Erreur de géocodage :", erreur)
        return "Ville inconnue"




def reponse_meteo(identifiant, etat="valide"):

    cache_meteo = caches_meteo[identifiant]
    donnees = cache_meteo["donnees"]

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

    return jsonify({
        **donnees,
        "ville": obtenir_ville(),
        "fournisseur": description_fournisseur(identifiant),
        "cache_info": {
            "etat": etat,
            "date_recuperation": cache_meteo[
                "date_recuperation_reelle"
            ],
            "secondes_restantes": restant,
            "secondes_avant_tentative": attente
        }
    })

@app.route("/api/capteurs")
def api_capteurs():
    connexion = None
    curseur = None

    try:
        connexion = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE
        )

        curseur = connexion.cursor(dictionary=True)

        # Dernier relevé enregistré dans la base
        curseur.execute("""
            SELECT MAX(date_releve) AS derniere_date
            FROM releves
        """)

        resultat = curseur.fetchone()
        derniere_date = resultat["derniere_date"]

        if derniere_date is None:
            return jsonify({
                "date_releve": None,
                "seuil_ecart": SEUIL_ECART_TEMPERATURE,
                "historique_heures": HISTORIQUE_TEMPERATURE_HEURES,
                "capteurs": []
            })

        # Conserver uniquement les périphériques ayant
        # envoyé une mesure lors de la dernière acquisition.
        # Fenêtre de 60 secondes pour tenir compte du temps
        # nécessaire pour interroger plusieurs appareils.
        curseur.execute("""
            SELECT r.capteur,
                   r.temperature,
                   r.humidite,
                   r.batterie,
                   r.date_releve
            FROM releves r
            WHERE r.date_releve >= %s
              AND r.date_releve <= %s
              AND r.id = (
                  SELECT r2.id
                  FROM releves r2
                  WHERE r2.capteur = r.capteur
                    AND r2.date_releve >= %s
                    AND r2.date_releve <= %s
                  ORDER BY r2.date_releve DESC, r2.id DESC
                  LIMIT 1
              )
            ORDER BY r.capteur
        """, (
            derniere_date - timedelta(seconds=60),
            derniere_date,
            derniere_date - timedelta(seconds=60),
            derniere_date
        ))

        capteurs = curseur.fetchall()
        # Températures extrêmes des dernières 24 heures
        curseur.execute("""
            SELECT capteur,
                MIN(temperature) AS temperature_min,
                MAX(temperature) AS temperature_max
            FROM releves
            WHERE date_releve >= NOW() - INTERVAL %s HOUR
                AND date_releve <= NOW()
                AND temperature IS NOT NULL
                AND temperature > -100
                AND temperature < 100
            GROUP BY capteur
        """, (HISTORIQUE_TEMPERATURE_HEURES,))

        extremes = {
            ligne["capteur"]: ligne
            for ligne in curseur.fetchall()
        }
        return jsonify({
            "date_releve": derniere_date.isoformat(),
            "seuil_ecart": SEUIL_ECART_TEMPERATURE,
            "historique_heures": HISTORIQUE_TEMPERATURE_HEURES,
            "capteurs": [
                {
                    "nom": c["capteur"],
                    "temperature": c["temperature"],
                    "humidite": c["humidite"],
                    "batterie": c["batterie"],
                    "date_releve": c["date_releve"].isoformat(),

                    "temperature_min": (
                        extremes[c["capteur"]]["temperature_min"]
                        if c["capteur"] in extremes else None
                    ),

                    "temperature_max": (
                        extremes[c["capteur"]]["temperature_max"]
                        if c["capteur"] in extremes else None
                    )
                }
                for c in capteurs
            ]
        })

    except mysql.connector.Error as erreur:
        app.logger.error("Erreur MySQL : %s", erreur)
        return jsonify({
            "erreur": "Impossible de lire les capteurs"
        }), 503

    finally:
        if curseur is not None:
            curseur.close()
        if connexion is not None and connexion.is_connected():
            connexion.close()

@app.route("/api/config")
def api_config():
    return jsonify({
        "intervalle_capteurs": INTERVALLE_CAPTEURS,
        "intervalle_meteo": INTERVALLE_METEO,
        "periodes": PERIODES,
        "rotation_periodes": ROTATION_PERIODES,
        "fournisseurs": [
            description_fournisseur(identifiant)
            for identifiant in FOURNISSEURS
        ]
    })

@app.route("/api/fournisseur", methods=["POST"])
def changer_fournisseur():
    global fournisseur_actif

    identifiant = (request.get_json(silent=True) or {}).get("id")

    if identifiant not in FOURNISSEURS:
        return jsonify({"erreur": "Fournisseur inconnu"}), 400

    with verrou_cache:
        fournisseur_actif = identifiant

        try:
            enregistrer_fournisseur(identifiant)
        except OSError as erreur:
            # Le choix reste actif jusqu'au prochain redémarrage
            print("Erreur d'enregistrement du fournisseur :", erreur)

    print("Météo : fournisseur choisi :", identifiant)

    return jsonify({"fournisseur": description_fournisseur(identifiant)})

@app.route("/api/meteo")
def meteo():

    with verrou_cache:

        identifiant = fournisseur_actif
        fournisseur = FOURNISSEURS[identifiant]
        cache_meteo = caches_meteo[identifiant]

        maintenant = time.monotonic()

        # 1. Cache encore valide
        if cache_meteo["donnees"] is not None:

            age = (
                maintenant -
                cache_meteo["date_recuperation"]
            )

            if age < DUREE_CACHE:
                print("Météo : utilisation du cache", identifiant)

                return reponse_meteo(identifiant, "valide")

        # 2. Attente après un échec
        if maintenant < cache_meteo["prochaine_tentative"]:

            if cache_meteo["donnees"] is not None:
                return reponse_meteo(identifiant, "attente")

            return jsonify({
                "erreur": "Service météo temporairement indisponible",
                "fournisseur": description_fournisseur(identifiant)
            }), 503

        # 3. Nouvelle récupération des prévisions
        print("Météo : interrogation de", fournisseur["nom"])

        try:
            donnees = conserver_heures_passees(
                identifiant,
                fournisseur["recuperer"](LATITUDE, LONGITUDE)
            )

            cache_meteo["donnees"] = donnees

            cache_meteo["date_recuperation"] = (
                time.monotonic()
            )

            cache_meteo["date_recuperation_reelle"] = (
                datetime.now(
                    ZoneInfo("Europe/Paris")
                ).isoformat()
            )

            cache_meteo["prochaine_tentative"] = 0

            print("Météo : prévisions actualisées")

            return reponse_meteo(identifiant, "valide")

        except (requests.RequestException, ValueError) as erreur:

            print("Erreur météo :", erreur)

            cache_meteo["prochaine_tentative"] = (
                time.monotonic() + DELAI_ERREUR
            )

            # Conservation des anciennes prévisions
            if cache_meteo["donnees"] is not None:

                print("Météo : anciennes prévisions utilisées")

                return reponse_meteo(identifiant, "attente")

            return jsonify({
                "erreur": "Impossible de récupérer les prévisions",
                "fournisseur": description_fournisseur(identifiant)
            }), 502


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        threaded=True
    )
