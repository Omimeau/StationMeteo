"""Point d'entrée de la station météo.

Lance :
    - l'acquisition périodique des capteurs Tuya (si ACQUISITION_AUTOMATIQUE) ;
    - l'actualisation de fond des prévisions de tous les fournisseurs
      (si AFFICHAGE_INTERACTIF) ;
    - le réveil de l'écran au toucher (si ECRAN_VEILLE = "hdmi", Linux) ;
    - la sauvegarde planifiée de la base (si SAUVEGARDE_AUTOMATIQUE, Linux) ;
    - l'application web app.py, servie par Waitress.

Utilisation : python serveur.py
"""

from waitress import serve

from app import app
from meteo import acquisition, config, ecran, previsions, sauvegarde


def main():
    if config.ACQUISITION_AUTOMATIQUE:
        acquisition.demarrer_en_arriere_plan(config.INTERVALLE_ACQUISITION)

    # Affichage interactif : tous les fournisseurs, même non affichés.
    # Sinon seule la source principale est interrogée, à la demande.
    if config.AFFICHAGE_INTERACTIF:
        previsions.demarrer_en_arriere_plan()

    # Veille HDMI : réveil de l'écran au toucher (ECRAN_VEILLE = "hdmi")
    ecran.demarrer_en_arriere_plan()

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
