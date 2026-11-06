# Station Météo

Affichage météo pour Raspberry Pi : températures et humidité des capteurs
Tuya de la maison (enregistrées dans MariaDB) et prévisions sur 5 jours
(Open-Meteo, MET Norway ou OpenWeatherMap).

## Contenu

| Dossier | Rôle |
|---|---|
| `StationMeteo/` | Application actuelle (serveur web, acquisition Tuya, sauvegarde) |
| `Affiche_Meteo/`, `MeteoMaison/` | Anciennes versions, conservées pour référence |

## Configuration (fichiers non publiés)

Les mots de passe et clés ne sont pas dans le dépôt. Avant le premier
lancement, créer deux fichiers à partir des modèles :

1. `StationMeteo/config_local.exemple.py` → copier en `StationMeteo/config_local.py`
   et renseigner la base de données, la latitude/longitude, etc.
2. `StationMeteo/tinytuya.exemple.json` → copier en `StationMeteo/tinytuya.json`,
   ou mieux, le générer avec l'assistant TinyTuya (il crée aussi `devices.json`) :

   ```
   cd StationMeteo
   python -m tinytuya wizard
   ```

   Les identifiants (Access ID / Access Secret) se trouvent dans le projet
   Cloud créé sur https://iot.tuya.com.

## Lancement sur PC (Windows)

```
cd StationMeteo
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python serveur.py
```

Puis ouvrir http://localhost:5000.
