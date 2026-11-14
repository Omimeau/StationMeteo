# CLAUDE.md

Guide pour travailler dans ce dépôt. Le projet, le code, les commentaires et
la documentation sont **en français** : garder cette langue (noms de
fonctions/variables compris : `acquerir`, `derniers_releves`, `fournisseur_actif`…).

## Vue d'ensemble

Station météo domestique affichée en kiosque sur un **Raspberry Pi 3 B+**
(écran 1280x720, utilisateur `meteo`, hôte `StationMeteo.local`) :

- colonne de gauche : température/humidité des capteurs **Tuya** de la maison,
  relevées toutes les 5 min et stockées dans **MariaDB** (table `releves`) ;
- grille de droite : prévisions sur 5 jours (Open-Meteo, Météo-France/ECMWF/GFS
  via Open-Meteo, MET Norway, OpenWeatherMap si clé), découpées en périodes
  (matin / après-midi / soirée) ;
- sauvegarde planifiée de la base (dump `.sql.gz`) vers pCloud.

Développement sous **Windows** (PC), exécution en production sous
**Raspberry Pi OS / Debian 13** via systemd.

## Structure

```
StationMeteo/                 application (seul dossier publié avec le README)
  serveur.py                  point d'entrée : threads acquisition + sauvegarde, puis Waitress
  app.py                      routes Flask uniquement (aucune logique métier)
  config_local.exemple.py     modèle -> config_local.py (secrets, non versionné)
  tinytuya.exemple.json       modèle -> tinytuya.json (clés Tuya, non versionné)
  requirements.txt
  meteo/                      bibliothèque (indépendante de Flask)
    config.py                 SEULE source des réglages ; lit config_local.py
    base_donnees.py           accès MariaDB (mysql-connector), table releves
    acquisition.py            lecture du cloud Tuya -> enregistrer_releves()
    previsions.py             fournisseur actif, cache par fournisseur, heures passées
    geocodage.py              nom de la ville (Nominatim, mis en cache)
    sauvegarde.py             dump mariadb-dump + gzip + planification (Linux)
    fournisseurs/             un module par API de prévisions + registre FOURNISSEURS
    destinations/             plugins d'envoi des sauvegardes (pcloud.py)
  templates/index.html        page unique
  static/js/app.js            tout l'affichage (JS vanilla, appels /api/*)
  static/css/style.css
  donnees/                    état runtime recréé automatiquement (non versionné)
Deploiement_Meteo/            pack de déploiement Windows -> Raspberry (exclu de git
                              via .git/info/exclude ; voir plus bas)
```

## Lancer en local (Windows)

```
cd StationMeteo
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python serveur.py        # ou lancer_serveur.bat
```

Page sur http://localhost:5000. `.claude/launch.json` définit la configuration
`station-meteo`. Prérequis : `config_local.py` et `tinytuya.json` présents, base
MariaDB locale accessible (sur le PC : base `MeteoMaison`, compte root).

Commandes utiles :
- `python app.py` : serveur de dev Flask **sans** acquisition ni sauvegarde ;
- `python -m meteo.acquisition` : une acquisition Tuya unique ;
- `python -m meteo.sauvegarde` : une sauvegarde immédiate (Linux uniquement) ;
- `python -m tinytuya wizard` : génère `tinytuya.json` / `devices.json`.

Il n'y a **ni tests automatisés, ni linter, ni build** : vérifier en lançant le
serveur et en ouvrant la page.

## Architecture et conventions

- **Configuration** : tout module importe ses réglages depuis `meteo/config.py`,
  jamais directement depuis `config_local.py`. `parametre(*noms, defaut=...)`
  renvoie la première valeur non vide ; sans `defaut`, le paramètre est
  obligatoire. Les anciens noms `MYSQL_*` restent acceptés en secours de `DB_*`.
  Un **nouveau paramètre** doit : avoir un défaut sensé dans `config.py`
  (le mode `update` du déploiement ne recopie pas `config_local.py` sur le
  Raspberry), être ajouté à `config_local.exemple.py` et documenté.
  Si la page en a besoin, l'exposer via `/api/config` dans `app.py`.
- **API JSON** (`app.py`) : `GET /api/config`, `GET /api/capteurs`,
  `GET /api/capteurs/historique?capteur=<nom>` (relevés des 24 dernières heures
  et moyennes journalières des 30 derniers jours, `historique_capteur()`),
  `GET /api/meteo`, `POST /api/fournisseur` (`{"id": ...}`). Les erreurs
  base renvoient 503 avec `{"erreur": ...}`.
- **Fournisseurs de prévisions** : chaque module de récupération
  (`meteo/fournisseurs/*.py`) expose `recuperer(lat, lon, ...)` et renvoie ses
  données dans le **format de sortie d'Open-Meteo** `{"hourly": {"time": [...],
  "temperature_2m": [...], "weather_code": [...], ...}}` (valeur absente = `None`,
  codes météo convertis en WMO). Open-Meteo est repris tel quel ; MET Norway et
  OpenWeatherMap sont convertis (`convertir()`, `code_wmo()`). Ces données passent
  sans changement de structure par `/api/meteo` jusqu'à `app.js`, qui lit
  `donnees.hourly` et construit seul le HTML. Inscrire le nouveau fournisseur dans
  `FOURNISSEURS` de `fournisseurs/__init__.py`. Fuseau : `Europe/Paris`.
- **Cache des prévisions** (`previsions.py`) : un cache par fournisseur (60 min),
  nouvel essai 60 s après un échec, un verrou par fournisseur contre les
  récupérations simultanées. Si `AFFICHAGE_INTERACTIF` (défaut True), un thread
  de fond (`demarrer_en_arriere_plan()`, lancé par `serveur.py`) interroge
  **tous** les fournisseurs au démarrage puis
  toutes les 3 h (0 h, 3 h … 21 h, heure de Paris : deux fois par période de 6 h),
  sauf ceux dont le cache a moins de 30 min. Sinon seule `SOURCE_PRINCIPALE`
  est utilisée et `POST /api/fournisseur` renvoie 403.
  Le fournisseur choisi et les heures passées du jour (MET Norway / OWM ne
  renvoient que le futur) sont persistés dans `donnees/` (écriture atomique).
- **Destinations de sauvegarde** : un module dans `meteo/destinations/` avec
  `NOM`, `verifier()`, `envoyer(archive)` (lève une exception si échec), inscrit
  dans `DESTINATIONS`, choisi par `SAUVEGARDE_DESTINATION`. Aucune logique propre
  à un hébergeur dans `sauvegarde.py`. Paramètres propres à la destination
  (ex. `PCLOUD_UPLOAD_CODE`) lus par le module lui-même, au moment de l'envoi.
- **Threads de fond** (`acquisition`, `previsions`, `sauvegarde`) : threads démons ; une erreur
  est affichée (`print`, visible dans `journalctl`) mais n'arrête jamais la boucle.
- **Base** : table `releves (id, capteur, temperature, humidite, batterie,
  date_releve)`. Une « acquisition » = relevés dans une fenêtre de 60 s ;
  seuls les capteurs de la dernière acquisition sont affichés. Température
  Tuya `-200` = mesure invalide -> `None`.
- **Front-end** : JS vanilla sans framework ni bundler ; l'écran cible est un
  tactile 1280x720 (vérifier que rien ne déborde). Mode nuit = voile noir
  (`#voile-nuit`, opacité tirée de `LUMINOSITE_NUIT`), l'écran n'ayant pas de DDC/CI.
  Deux affichages selon `interactif` (`/api/config`) : interactif =
  `construireJour()`, une case touchée s'ouvre en grand (`#detail-prevision`,
  sous le voile de nuit : détails + 24 heures du jour sur deux colonnes,
  fournisseur modifiable en touchant son nom, fermeture au toucher ou après
  60 s), une case de capteur touchée ouvre ses graphiques de température
  (`#detail-capteur`, SVG dessiné par `dessinerGraphique()`, sans
  bibliothèque), fournisseur modifiable, bouton 🌙 ; classique =
  `construireJourClassique()` (styles `.case.classique`), rien à toucher.
  `construireInformation()` sert aux deux. `calculerPeriode()` fait les calculs
  communs à toutes les cases. Mode nuit programmé (`NUIT_DEBUT` / `NUIT_FIN`,
  envoyés en minutes) : `verifierPlageNuit()` ne bascule qu'aux passages
  d'heure, pour laisser le bouton et le toucher libres entre les deux.
- **Icônes** : le choix actuel des icônes (émojis météo de `symbole()`,
  icônes des détails, des capteurs, des états ✅ ⚠️ ⏳, bouton 🌙…) est
  validé : ne pas les changer sauf demande explicite.
- **Couleurs** : les couleurs affichées (fonds, textes, bordures, températures
  min/max, états… dans `style.css` et `app.js`) sont validées : ne plus les
  modifier sauf demande explicite, y compris lors d'autres changements de style.

## Secrets et fichiers non versionnés

Ne jamais committer ni afficher : `config_local.py`, `tinytuya.json`,
`devices.json`, `snapshot.json`, `tuya-raw.json`, `.mariadb_credentials`,
`donnees/`, dumps `*.sql*`, `PbWifiStationMeteo.txt`. Ne mettre que des valeurs
d'exemple dans les fichiers `*.exemple.*`.

## Déploiement (`Deploiement_Meteo/`)

Pack local (non versionné) : `deployer_meteo.cmd install|update [--dry-run]`
copie `StationMeteo/` (dossier voisin, chemin `C:\Projets\StationMeteoV1\StationMeteo`)
et les scripts `*.sh` sur le Raspberry par SSH. Le mode `update` ne remplace jamais
`config_local.py`, les fichiers Tuya ni `donnees/`, et ne supprime rien à distance.
Côté Raspberry : `installer_raspberry.sh`, `configurer_stationmeteo.sh`,
`configurer_services.sh` (service `stationmeteo.service`), `configurer_ecran.sh`
(kiosque Chromium sous `cage`, service `stationmeteo-kiosque`, splash Plymouth),
`restaurer_base.sh`, `nettoyer_ancienne_version.sh`. Procédures détaillées dans
`Deploiement_Meteo/README.txt`.

**Règle** : toute modification du pack de déploiement — ou de l'application qui
change son déploiement/configuration — doit être reportée dans
`Deploiement_Meteo/README.txt` **et** `Deploiement_Meteo/VERSION.txt` (nouvelle
entrée datée, numéro de version incrémenté). Les fichiers du pack sont en ASCII
sans accents ; les scripts `.sh` doivent garder des fins de ligne LF et les
`.cmd`/`.ps1`/`.bat` des fins CRLF (le pack étant hors git, `.gitattributes`
ne le garantit pas : y veiller à l'écriture).

`Affiche_Meteo` / `MeteoMaison` sont les anciens projets retirés (V3) ; des
références subsistent (`.claude/launch.json`, `.gitignore`, `ancien_pack_V3/`,
nom de base `meteomaison`, dossier `~/sauvegardes/MeteoMaison`) — ne pas les
renommer sans adapter les scripts de déploiement.
