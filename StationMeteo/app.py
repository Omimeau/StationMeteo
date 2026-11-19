"""Application web Flask : page d'affichage et API JSON.

La logique se trouve dans la bibliothèque meteo/ ; ce fichier ne
contient que les routes. Lancement normal : python serveur.py
"""

import os

from flask import Flask, jsonify, render_template, request

from meteo import base_donnees, config, ecran, previsions

app = Flask(__name__)


@app.url_defaults
def version_fichier_statique(endpoint, valeurs):
    """Ajoute ?v=<date de modification> aux URL de static/.

    Le kiosque Chromium recharge ainsi app.js / style.css dès qu'ils
    changent après un déploiement, au lieu de garder sa copie en cache.
    """
    if endpoint == "static" and "filename" in valeurs:
        chemin = os.path.join(app.static_folder, valeurs["filename"])
        try:
            valeurs["v"] = int(os.path.getmtime(chemin))
        except OSError:
            pass


@app.route("/")
def accueil():
    return render_template("index.html")


@app.route("/api/config")
def api_config():
    return jsonify({
        "intervalle_capteurs": config.INTERVALLE_CAPTEURS,
        "intervalle_meteo": config.INTERVALLE_METEO,
        "periodes": config.PERIODES,
        "rotation_periodes": config.ROTATION_PERIODES,
        "luminosite_nuit": config.LUMINOSITE_NUIT,
        "interactif": config.AFFICHAGE_INTERACTIF,
        # Minutes depuis minuit (heure de Paris), None = non programmé
        "nuit_debut": config.NUIT_DEBUT,
        "nuit_fin": config.NUIT_FIN,
        # Mode nuit = écran éteint (option ECRAN_VEILLE = "hdmi")
        "veille_hdmi": ecran.disponible(),
        "fournisseurs": previsions.liste_fournisseurs()
    })


@app.route("/api/ecran", methods=["GET", "POST"])
def api_ecran():
    """Veille HDMI de l'écran. POST {"veille": true|false} ; GET : état
    et date du dernier réveil au toucher."""
    if not ecran.disponible():
        return jsonify({"erreur": "Veille HDMI non activée"}), 403

    if request.method == "POST":
        veille = bool((request.get_json(silent=True) or {}).get("veille"))
        reussi = ecran.mettre_en_veille() if veille else ecran.reveiller()
        if not reussi:
            return jsonify({"erreur": "Commande de l'écran impossible"}), 503

    return jsonify(ecran.etat())


@app.route("/api/capteurs")
def api_capteurs():
    try:
        derniere_date, capteurs = base_donnees.derniers_releves(
            config.HISTORIQUE_TEMPERATURE_HEURES
        )

    except base_donnees.Erreur as erreur:
        app.logger.error("Erreur MySQL : %s", erreur)
        return jsonify({
            "erreur": "Impossible de lire les capteurs"
        }), 503

    return jsonify({
        "date_releve": derniere_date.isoformat() if derniere_date else None,
        "seuil_ecart": config.SEUIL_ECART_TEMPERATURE,
        "historique_heures": config.HISTORIQUE_TEMPERATURE_HEURES,
        "capteurs": capteurs
    })


@app.route("/api/capteurs/historique")
def api_historique_capteur():
    """Graphiques d'un capteur : 24 dernières heures et moyennes
    journalières des 30 derniers jours (?capteur=<nom>)."""
    capteur = request.args.get("capteur", "").strip()

    if not capteur:
        return jsonify({"erreur": "Capteur non précisé"}), 400

    try:
        historique = base_donnees.historique_capteur(
            capteur, heures=24, jours=30
        )

    except base_donnees.Erreur as erreur:
        app.logger.error("Erreur MySQL : %s", erreur)
        return jsonify({
            "erreur": "Impossible de lire l'historique du capteur"
        }), 503

    return jsonify({"capteur": capteur, **historique})


@app.route("/api/fournisseur", methods=["POST"])
def api_fournisseur():
    identifiant = (request.get_json(silent=True) or {}).get("id")

    if not config.AFFICHAGE_INTERACTIF:
        return jsonify({
            "erreur": "Affichage non interactif : source unique"
        }), 403

    if not previsions.choisir_fournisseur(identifiant):
        return jsonify({"erreur": "Fournisseur inconnu"}), 400

    return jsonify({
        "fournisseur": previsions.description_fournisseur(identifiant)
    })


@app.route("/api/meteo")
def api_meteo():
    donnees, code = previsions.obtenir_previsions()
    return jsonify(donnees), code


if __name__ == "__main__":
    # Serveur de développement Flask, sans acquisition des capteurs
    app.run(
        host=config.SERVEUR_HOTE,
        port=config.SERVEUR_PORT,
        debug=False,
        threaded=True
    )
