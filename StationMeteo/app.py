"""Application web Flask : page d'affichage et API JSON.

La logique se trouve dans la bibliothèque meteo/ ; ce fichier ne
contient que les routes. Lancement normal : python serveur.py
"""

from flask import Flask, jsonify, render_template, request

from meteo import base_donnees, config, previsions

app = Flask(__name__)


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
        "fournisseurs": previsions.liste_fournisseurs()
    })


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


@app.route("/api/fournisseur", methods=["POST"])
def api_fournisseur():
    identifiant = (request.get_json(silent=True) or {}).get("id")

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
