# Station Météo

Affichage météo pour Raspberry Pi : températures et humidité des capteurs
Tuya / Smart Home de la maison (enregistrées dans MariaDB) et prévisions sur 5 jours
(Open-Meteo, MET Norway ou OpenWeatherMap).

Deux affichages, au choix (`AFFICHAGE_INTERACTIF` dans `config_local.py`) :

- **interactif** (écran tactile, par défaut) : le serveur interroge tous les
  fournisseurs de prévisions toutes les 3 heures, même ceux qui ne sont pas
  affichés, et le fournisseur se change sur la page. Toucher une case de
  prévision l'affiche en grand, avec tous les détails et les prévisions heure
  par heure de la période ;
- **classique** : une seule source (`SOURCE_PRINCIPALE`), cases avec tous les
  détails, rien à toucher.

Dans les deux cas, le mode nuit (écran assombri) peut être programmé avec
`NUIT_DEBUT` et `NUIT_FIN` ; en affichage interactif, le bouton 🌙 l'active
aussi à tout moment.

## Contenu

L'application se trouve dans `StationMeteo/` : serveur web, acquisition
des capteurs Tuya et sauvegarde de la base (envoi vers pCloud via le
plugin `meteo/destinations/pcloud.py`).

## Configuration (fichiers non publiés)

Les mots de passe et clés ne sont pas dans le dépôt. Avant le premier
lancement, créer deux fichiers à partir des modèles :

1. `StationMeteo/config_local.exemple.py` → copier en `StationMeteo/config_local.py`
   et renseigner la base de données, la latitude/longitude, etc.
2. `StationMeteo/tinytuya.exemple.json` → copier en `StationMeteo/tinytuya.json`,
   ou mieux, le générer avec l'assistant TinyTuya  :

   ```
   cd StationMeteo
   python -m tinytuya wizard
   ```

## Lancement sur PC (Windows)

```
cd StationMeteo
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python serveur.py
```

Puis ouvrir http://localhost:5000.
