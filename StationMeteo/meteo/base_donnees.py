"""Accès à la base MySQL/MariaDB (table releves).

Table utilisée :
    releves (id, capteur, temperature, humidite, batterie, date_releve)
"""

from contextlib import contextmanager
from datetime import timedelta

import mysql.connector

from . import config

# Erreur levée par toutes les fonctions de ce module
Erreur = mysql.connector.Error

# Fenêtre de temps d'une même acquisition : interroger plusieurs
# appareils prend quelques secondes.
FENETRE_ACQUISITION = timedelta(seconds=60)


@contextmanager
def connexion():
    """Connexion ouverte pour la durée d'un bloc with, puis fermée."""
    cnx = mysql.connector.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
    )
    try:
        yield cnx
    finally:
        if cnx.is_connected():
            cnx.close()


# =======================================
# ÉCRITURE : ACQUISITION
# =======================================

def enregistrer_releves(releves):
    """Insère une liste de relevés (capteur, temperature, humidite, batterie).

    Renvoie le nombre de lignes enregistrées.
    """
    if not releves:
        return 0

    with connexion() as cnx:
        curseur = cnx.cursor()
        try:
            curseur.executemany(
                """
                INSERT INTO releves
                    (capteur, temperature, humidite, batterie)
                VALUES (%s, %s, %s, %s)
                """,
                releves,
            )
            cnx.commit()
        finally:
            curseur.close()

    return len(releves)


# =======================================
# LECTURE : AFFICHAGE
# =======================================

def derniers_releves(historique_heures):
    """Dernière mesure de chaque capteur et extrêmes de la période.

    Renvoie (date_derniere_acquisition, liste de capteurs).
    Seuls les capteurs ayant répondu lors de la dernière acquisition
    sont conservés. La date vaut None si la table est vide.
    """
    with connexion() as cnx:
        curseur = cnx.cursor(dictionary=True)
        try:
            curseur.execute("""
                SELECT MAX(date_releve) AS derniere_date
                FROM releves
            """)
            derniere_date = curseur.fetchone()["derniere_date"]

            if derniere_date is None:
                return None, []

            debut = derniere_date - FENETRE_ACQUISITION

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
            """, (debut, derniere_date, debut, derniere_date))

            capteurs = curseur.fetchall()

            # Températures extrêmes de la période d'historique
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
            """, (historique_heures,))

            extremes = {
                ligne["capteur"]: ligne
                for ligne in curseur.fetchall()
            }
        finally:
            curseur.close()

    return derniere_date, [
        {
            "nom": c["capteur"],
            "temperature": c["temperature"],
            "humidite": c["humidite"],
            "batterie": c["batterie"],
            "date_releve": c["date_releve"].isoformat(),
            "temperature_min": extremes.get(c["capteur"], {}).get(
                "temperature_min"
            ),
            "temperature_max": extremes.get(c["capteur"], {}).get(
                "temperature_max"
            ),
        }
        for c in capteurs
    ]
