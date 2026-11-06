"""Point d'entrée de la station météo.

Lance :
    - l'acquisition périodique des capteurs Tuya (si ACQUISITION_AUTOMATIQUE) ;
    - la sauvegarde planifiée de la base (si SAUVEGARDE_AUTOMATIQUE, Linux) ;
    - l'application web app.py, servie par Waitress.

Utilisation : python serveur.py
"""

from waitress import serve

from app import app
from meteo import acquisition, config, sauvegarde


def main():
    if config.ACQUISITION_AUTOMATIQUE:
        acquisition.demarrer_en_arriere_plan(config.INTERVALLE_ACQUISITION)

    if config.SAUVEGARDE_AUTOMATIQUE:
        sauvegarde.demarrer_en_arriere_plan(
            config.SAUVEGARDE_HEURE, config.SAUVEGARDE_PERIODICITE_HEURES
        )

    print(
        f"Serveur web : http://{config.SERVEUR_HOTE}:{config.SERVEUR_PORT}"
    )
    serve(app, host=config.SERVEUR_HOTE, port=config.SERVEUR_PORT)


if __name__ == "__main__":
    main()
