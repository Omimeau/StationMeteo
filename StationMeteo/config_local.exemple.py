"""Modèle de configuration locale de la station météo.

Copier ce fichier sous le nom config_local.py (dans le même dossier),
puis remplacer les valeurs d'exemple par les vôtres.
config_local.py n'est jamais publié sur GitHub (voir .gitignore).
"""

# --- Base de données MariaDB / MySQL ------------------------------------
# Sur le Raspberry Pi, configurer_stationmeteo.sh remplit ces valeurs
# automatiquement à partir de ~/StationMeteo/.mariadb_credentials.
DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "meteomaison"
DB_PASSWORD = "remplacer_par_votre_mot_de_passe"
DB_NAME = "meteomaison"

# --- Serveur web ---------------------------------------------------------
SERVEUR_HOTE = "0.0.0.0"
SERVEUR_PORT = 5000

# --- Acquisition des capteurs Tuya --------------------------------------
# Les identifiants Tuya sont dans tinytuya.json (voir tinytuya.exemple.json).
ACQUISITION_AUTOMATIQUE = True
INTERVALLE_ACQUISITION = 300          # secondes

# --- Localisation (pour les prévisions) ---------------------------------
# Exemple : Paris. Mettre les coordonnées de votre domicile.
LATITUDE = 48.8566
LONGITUDE = 2.3522

# --- Affichage -----------------------------------------------------------
PERIODES = [
    {"nom": "Matin", "debut": 6, "fin": 12},
    {"nom": "Après-midi", "debut": 12, "fin": 18},
    {"nom": "Soirée", "debut": 18, "fin": 24},
]
ROTATION_PERIODES = 12                # secondes entre deux périodes
SEUIL_ECART_TEMPERATURE = 2.0         # °C
HISTORIQUE_TEMPERATURE_HEURES = 24
INTERVALLE_CAPTEURS = 300             # secondes
INTERVALLE_METEO = 3600               # secondes

# --- Fournisseurs de prévisions (facultatifs) ---------------------------
# MET Norway demande une adresse de contact dans ses requêtes.
MET_NORWAY_CONTACT = "votre.adresse@exemple.fr"
# Clé gratuite sur https://openweathermap.org/api (laisser vide sinon).
OPENWEATHERMAP_API_KEY = ""

# --- Sauvegarde de la base vers pCloud (facultatif) ---------------------
PCLOUD_UPLOAD_CODE = ""
SAUVEGARDE_AUTOMATIQUE = False
SAUVEGARDE_HEURE = "03:01"
SAUVEGARDE_PERIODICITE_HEURES = 24
