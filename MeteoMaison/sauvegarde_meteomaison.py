#!/usr/bin/env python3
"""Sauvegarde la base MeteoMaison en SQL.gz puis l'envoie vers le lien pCloud.

Installation : placer ce fichier dans /home/meteo/MeteoMaison/, a cote de
config_local.py, et ajouter PCLOUD_UPLOAD_CODE dans config_local.py.

Prerequis : mysql/mariadb-dump, curl, Python 3 (bibliotheque standard).
"""

from __future__ import annotations

import fcntl
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta

import config_local

# Le domaine eapi.pcloud.com correspond aux comptes pCloud en Europe.
PCLOUD_UPLOAD_URL = "https://eapi.pcloud.com/uploadtolink"
REPERTOIRE_SAUVEGARDES = Path.home() / "sauvegardes" / "MeteoMaison"
CONSERVATION_LOCALE_JOURS = 14


def parametre(*noms: str):
    """Prend les parametres du projet, DB_* en priorite."""
    for nom in noms:
        valeur = getattr(config_local, nom, None)
        if valeur is not None and str(valeur) != "":
            return valeur
    raise ValueError("Parametre manquant dans config_local.py : " + " ou ".join(noms))


def option_mysql(valeur: object) -> str:
    """Echappement du format de configuration des clients MySQL/MariaDB."""
    texte = str(valeur)
    if "\n" in texte or "\r" in texte:
        raise ValueError("Une valeur de configuration SQL contient un retour de ligne")
    return '"' + texte.replace("\\", "\\\\").replace('"', '\\"') + '"'


def verification_gzip(chemin: Path) -> None:
    if chemin.stat().st_size == 0:
        raise RuntimeError("Le fichier de sauvegarde est vide")
    with gzip.open(chemin, "rb") as fichier:
        if not fichier.read(1):
            raise RuntimeError("Le dump SQL est vide apres decompression")
        while fichier.read(1024 * 1024):
            pass  # Force la verification CRC du fichier gzip.


def main() -> int:
    os.umask(0o077)
    REPERTOIRE_SAUVEGARDES.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Evite deux sauvegardes simultanees (par exemple cron + lancement manuel).
    with (REPERTOIRE_SAUVEGARDES / ".sauvegarde.lock").open("a+") as verrou:
        try:
            fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Une autre sauvegarde est deja en cours.", file=sys.stderr)
            return 1

        hote = parametre("DB_HOST", "MYSQL_HOST")
        port = parametre("DB_PORT") if hasattr(config_local, "DB_PORT") else 3306
        utilisateur = parametre("DB_USER", "MYSQL_USER")
        mot_de_passe = parametre("DB_PASSWORD", "MYSQL_PASSWORD")
        base = str(parametre("DB_NAME", "MYSQL_DATABASE"))
        code_pcloud = str(parametre("PCLOUD_UPLOAD_CODE")).strip()
        if not re.fullmatch(r"[a-zA-Z0-9]+", code_pcloud):
            raise ValueError("PCLOUD_UPLOAD_CODE contient des caracteres inattendus")

        outil_dump = shutil.which("mariadb-dump") or shutil.which("mysqldump")
        if not outil_dump:
            raise RuntimeError("Installer un client SQL : sudo apt install mariadb-client")
        if not shutil.which("curl"):
            raise RuntimeError("Installer curl : sudo apt install curl")

        horodatage = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        nom_base = re.sub(r"[^a-zA-Z0-9_-]", "_", base)
        archive = REPERTOIRE_SAUVEGARDES / f"{nom_base}_{horodatage}.sql.gz"
        provisoire = archive.with_name(archive.name + ".tmp")

        # Les identifiants restent dans un fichier temporaire lisible uniquement
        # par l'utilisateur, jamais directement sur la ligne de commande SQL.
        nom_cred = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix=".mysql_", suffix=".cnf",
                dir=REPERTOIRE_SAUVEGARDES, delete=False
            ) as identifiants:
                nom_cred = identifiants.name
                identifiants.write("[client]\n")
                identifiants.write(f"host={option_mysql(hote)}\n")
                identifiants.write(f"port={int(port)}\n")
                identifiants.write(f"user={option_mysql(utilisateur)}\n")
                identifiants.write(f"password={option_mysql(mot_de_passe)}\n")

            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Sauvegarde de {base}...")
            commande = [
                outil_dump,
                f"--defaults-extra-file={nom_cred}",  # doit etre premier argument
                "--single-transaction",
                "--quick",
                "--no-tablespaces",
                "--databases",
                base,
            ]
            # Ecriture en flux pour ne jamais charger toute la base en RAM.
            with tempfile.TemporaryFile(mode="w+b") as erreurs_dump:
                with gzip.open(provisoire, "wb", compresslevel=6) as sortie:
                    with subprocess.Popen(
                        commande, stdout=subprocess.PIPE, stderr=erreurs_dump
                    ) as processus:
                        assert processus.stdout is not None
                        shutil.copyfileobj(processus.stdout, sortie, length=1024 * 1024)
                        processus.stdout.close()
                        code_retour = processus.wait(timeout=1800)
                if code_retour != 0:
                    erreurs_dump.seek(0)
                    message = erreurs_dump.read().decode("utf-8", errors="replace").strip()
                    raise RuntimeError(f"Echec du dump SQL ({code_retour}) : {message}")

            verification_gzip(provisoire)
            provisoire.replace(archive)
            print(f"Sauvegarde locale creee : {archive} ({archive.stat().st_size} octets)")

        finally:
            if nom_cred:
                Path(nom_cred).unlink(missing_ok=True)
            provisoire.unlink(missing_ok=True)

        # L'API pCloud retourne un JSON : HTTP 200 ne suffit pas pour conclure.
        print("Televersement vers pCloud...")
        transfert = subprocess.run(
            [
                "curl", "--fail", "--silent", "--show-error", "--retry", "2",
                "--retry-delay", "10", "--connect-timeout", "20",
                "--max-time", "1800", "--form", f"code={code_pcloud}",
                "--form", "names=StationMeteo",
                "--form", "nopartial=1",
                "--form", f"file=@{archive};filename={archive.name}",
                PCLOUD_UPLOAD_URL,
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=1900, check=False
        )
        if transfert.returncode != 0:
            raise RuntimeError(
                f"Echec de la connexion pCloud ({transfert.returncode}) : "
                f"{transfert.stderr.strip()}. Archive locale conservee : {archive}"
            )
        try:
            reponse = json.loads(transfert.stdout)
        except json.JSONDecodeError as err:
            raise RuntimeError(
                "Reponse pCloud non JSON ; verifier le televersement. "
                f"Archive locale conservee : {archive}"
            ) from err
        if not isinstance(reponse, dict) or reponse.get("result") != 0:
            raise RuntimeError(
                f"pCloud refuse la sauvegarde : code={reponse.get('result') if isinstance(reponse, dict) else 'inconnu'}, "
                f"message={reponse.get('error', 'indeterminee') if isinstance(reponse, dict) else 'reponse inattendue'}. "
                f"Archive locale conservee : {archive}"
            )

        print("Televersement pCloud confirme (result=0).")

        # Un lien de depot ne permet pas la suppression des archives pCloud.
        # On nettoie donc UNIQUEMENT les copies locales anciennes.
        limite = datetime.now() - timedelta(days=CONSERVATION_LOCALE_JOURS)
        for ancienne in REPERTOIRE_SAUVEGARDES.glob(f"{nom_base}_*.sql.gz"):
            if datetime.fromtimestamp(ancienne.stat().st_mtime) < limite:
                ancienne.unlink()
                print(f"Ancienne sauvegarde locale supprimee : {ancienne.name}")

        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Sauvegarde terminee avec succes.")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        sys.exit(1)
