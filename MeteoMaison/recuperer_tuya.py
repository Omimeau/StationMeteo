
import json
from pathlib import Path
from getpass import getpass
from datetime import datetime

import mysql.connector
import tinytuya
import config_local



def main():
    # Charger la configuration Tuya
    fichier_config = Path("tinytuya.json")

    if not fichier_config.exists():
        print("Erreur : fichier tinytuya.json introuvable.")
        return

    with fichier_config.open("r", encoding="utf-8") as fichier:
        config = json.load(fichier)


    # Connexion à MySQL
    try:
        db = mysql.connector.connect(
            host=config_local.DB_HOST,
            port=config_local.DB_PORT,
            user=config_local.DB_USER,
            password=config_local.DB_PASSWORD,
            database=config_local.DB_NAME,
        )
        print("Connexion à MySQL réussie.")

    except mysql.connector.Error as erreur:
        print(f"Erreur de connexion MySQL : {erreur}")
        return


    try:
        db = mysql.connector.connect(
            host=config_local.DB_HOST,
            port=config_local.DB_PORT,
            user=config_local.DB_USER,
            password=config_local.DB_PASSWORD,
            database=config_local.DB_NAME,
        )
    except mysql.connector.Error as erreur:
        print(f"Erreur de connexion MySQL : {erreur}")
        return

    # Connexion au cloud Tuya
    try:
        cloud = tinytuya.Cloud(
            apiRegion=config["apiRegion"],
            apiKey=config["apiKey"],
            apiSecret=config["apiSecret"],
        )

        appareils = cloud.getdevices()

        if not isinstance(appareils, list):
            print("Réponse inattendue de l'API Tuya :")
            print(json.dumps(appareils, indent=2, ensure_ascii=False))
            return

        curseur = db.cursor()
        nombre_enregistrements = 0
        
        maintenant = datetime.now()
        print(f"\n******************************")
        print(f"{maintenant.strftime("%d/%m/%Y %H:%M:%S")}")
        for appareil in appareils:
            device_id = appareil.get("id")
            nom = appareil.get("name", "Sans nom")

            if not device_id:
                continue

            # print(f"{nom}")

            try:
                reponse = cloud.getstatus(device_id)

                if not reponse.get("success", False):
                    print("Échec de lecture Tuya.")
                    continue

                valeurs = {
                    element["code"]: element["value"]
                    for element in reponse.get("result", [])
                    if "code" in element and "value" in element
                }

                temperature = valeurs.get("va_temperature")
                    # -200 correspond ici à une valeur anormale du capteur
                if temperature == -200:
                    temperature = None
                humidite = valeurs.get("va_humidity")
                batterie = valeurs.get("va_battery")

                # Ignorer les appareils qui ne fournissent
                # ni température ni humidité.
                if temperature is None and humidite is None:
                    # print("Aucune donnée disponible.")
                    continue
                
                curseur.execute(
                    """
                    INSERT INTO releves
                        (capteur, temperature, humidite, batterie)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (nom, temperature, humidite, batterie),
                )

                
                nombre_enregistrements += 1

            except Exception as erreur:
                print(f"Erreur pour {nom} : {erreur}")

        db.commit()
        print(f"{nombre_enregistrements} enregistrement(s).")

    except Exception as erreur:
        print(f"Erreur Tuya : {erreur}")

    finally:
        if "curseur" in locals():
            curseur.close()
        db.close()


if __name__ == "__main__":
    main()
