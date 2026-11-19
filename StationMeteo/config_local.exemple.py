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
DB_USER = "votreIdentifiantPourMariaDB"
DB_PASSWORD = "remplacer_par_votre_mot_de_passe"
DB_NAME = "NomDeVotreBase"

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
# Mode nuit : voile sombre sur tout l'écran. Luminosité en % (5 à 100).
LUMINOSITE_NUIT = 35
# Mode nuit programmé (heure de Paris, "HH:MM", la plage peut passer
# minuit ; laisser "" pour ne pas programmer). Dans les deux affichages :
# à NUIT_DEBUT la page passe en mode nuit, à NUIT_FIN elle revient au mode
# jour si le mode nuit est toujours là. En affichage interactif, le bouton
# 🌙 de la case en bas à droite passe aussi en mode nuit, et un toucher
# n'importe où revient au mode jour.
NUIT_DEBUT = "22:30"
NUIT_FIN = "07:00"
# Mode nuit de l'écran (Raspberry, kiosque cage) :
#   "voile" : voile sombre (LUMINOSITE_NUIT), l'écran reste allumé ;
#   "hdmi"  : en plus, signal HDMI coupé (écran en veille). Le premier
#             toucher (ou NUIT_FIN) le rallume et revient au mode jour.
#             fonctionne seulement sous Linux, pas sur PC Windows.
ECRAN_VEILLE = "voile"
ECRAN_SORTIE = "HDMI-A-1"             # sortie vidéo (wlr-randr)
# Périphérique qui réveille l'écran ; "" = tous ceux de /dev/input/by-id
# (ex. "/dev/input/by-id/usb-QDtech_MPI1001-event-if00")
ECRAN_TACTILE = ""
# Affichage interactif (écran tactile) :
#   True  : tous les fournisseurs sont interrogés toutes les 3 h, le
#           fournisseur se change en touchant « Prévisions : ... » et une
#           case de prévision touchée s'ouvre en grand (heure par heure) ;
#   False : une seule source (SOURCE_PRINCIPALE), cases classiques avec
#           tous les détails, rien à toucher (mode nuit : uniquement aux
#           heures NUIT_DEBUT / NUIT_FIN).
AFFICHAGE_INTERACTIF = False
# Fournisseur : seule source si AFFICHAGE_INTERACTIF = False ; sinon
# fournisseur de départ tant qu'aucun n'a été choisi sur la page (le
# dernier choisi est repris après un redémarrage). open_meteo, meteofrance, ecmwf, gfs, met_norway ou
# openweathermap (ce dernier seulement avec une clé, voir plus bas).
SOURCE_PRINCIPALE = "open_meteo"

# --- Fournisseurs de prévisions (facultatifs) ---------------------------
# MET Norway demande une adresse de contact dans ses requêtes.
MET_NORWAY_CONTACT = "votre.adresse@exemple.fr"
# Clé gratuite sur https://openweathermap.org/api (laisser vide sinon).
OPENWEATHERMAP_API_KEY = ""

# --- Sauvegarde de la base (facultatif) ---------------------------------
# Destination de l'archive : nom d'un module de meteo/destinations/.
SAUVEGARDE_DESTINATION = "pcloud"
# pCloud : code du lien de dépôt (donnée personnelle, ne pas publier).
PCLOUD_UPLOAD_CODE = ""
SAUVEGARDE_AUTOMATIQUE = False
SAUVEGARDE_HEURE = "03:01"
SAUVEGARDE_PERIODICITE_HEURES = 24
