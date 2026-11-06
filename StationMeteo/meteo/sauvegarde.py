"""Sauvegarde la base MeteoMaison en SQL.gz puis l'envoie vers le lien pCloud.

Utilisation (Linux uniquement) :
    - par serveur.py, en tâche de fond (demarrer_en_arriere_plan), à partir
      de SAUVEGARDE_HEURE puis toutes les SAUVEGARDE_PERIODICITE_HEURES heures ;
    - seule, pour une sauvegarde immédiate : python -m meteo.sauvegarde

Parametres lus dans config_local.py : DB_*, PCLOUD_UPLOAD_CODE et SAUVEGARDE_*.
Prerequis : mysql/mariadb-dump, curl, Python 3 (bibliotheque standard).
"""

from __future__ import annotations

import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, time, timedelta

from . import config

# Le domaine eapi.pcloud.com correspond aux comptes pCloud en Europe.
PCLOUD_UPLOAD_URL = "https://eapi.pcloud.com/uploadtolink"
REPERTOIRE_SAUVEGARDES = Path.home() / "sauvegardes" / "MeteoMaison"
CONSERVATION_LOCALE_JOURS = 14

# Planification par serveur.py
FICHIER_ETAT = config.DOSSIER_DONNEES / "sauvegarde.json"
DELAI_DEMARRAGE = 120                   # laisser le réseau démarrer (s)
DELAI_NOUVEL_ESSAI = timedelta(hours=1)  # après un échec
PAS_ATTENTE = 60                        # re-vérification de l'horloge (s)


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
    """Une sauvegarde complète. Renvoie 0 si réussie, 1 si déjà en cours.

    Lève une exception en cas d'échec.
    """
    # Le masque est commun à tout le processus (serveur compris) : on le
    # rétablit à la fin.
    ancien_masque = os.umask(0o077)
    try:
        return _sauvegarder()
    finally:
        os.umask(ancien_masque)


def _sauvegarder() -> int:
    import fcntl  # Linux uniquement : importe ici pour garder le module importable

    REPERTOIRE_SAUVEGARDES.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Evite deux sauvegardes simultanees (par exemple cron + lancement manuel).
    with (REPERTOIRE_SAUVEGARDES / ".sauvegarde.lock").open("a+") as verrou:
        try:
            fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Une autre sauvegarde est deja en cours.", file=sys.stderr)
            return 1

        hote = config.DB_HOST
        port = config.DB_PORT
        utilisateur = config.DB_USER
        mot_de_passe = config.DB_PASSWORD
        base = str(config.DB_NAME)
        code_pcloud = str(config.parametre("PCLOUD_UPLOAD_CODE")).strip()
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


# =======================================
# PLANIFICATION DANS LE SERVEUR
# =======================================

def lire_heure(texte) -> time:
    """Convertit "HH:MM" en heure ; ValueError si le format est incorrect."""
    correspondance = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", str(texte).strip())
    if not correspondance:
        raise ValueError(
            f"SAUVEGARDE_HEURE invalide : {texte!r} (format HH:MM attendu)"
        )
    return time(int(correspondance.group(1)), int(correspondance.group(2)))


def derniere_sauvegarde() -> datetime | None:
    """Début de la dernière sauvegarde réussie.

    Lue dans donnees/sauvegarde.json ; à défaut, date de l'archive locale
    la plus récente (sauvegardes faites avant cette version) ; sinon None.
    """
    try:
        with open(FICHIER_ETAT, "r", encoding="utf-8") as fichier:
            return datetime.fromisoformat(json.load(fichier)["derniere_reussite"])
    except (OSError, ValueError, KeyError, TypeError):
        pass

    try:
        dates = [p.stat().st_mtime for p in REPERTOIRE_SAUVEGARDES.glob("*.sql.gz")]
    except OSError:
        dates = []
    return datetime.fromtimestamp(max(dates)) if dates else None


def noter_reussite(debut: datetime) -> None:
    FICHIER_ETAT.parent.mkdir(parents=True, exist_ok=True)
    temporaire = FICHIER_ETAT.with_suffix(".tmp")
    with open(temporaire, "w", encoding="utf-8") as fichier:
        json.dump({"derniere_reussite": debut.isoformat(timespec="seconds")}, fichier)
    temporaire.replace(FICHIER_ETAT)


def creneau_suivant(apres: datetime, heure: time,
                    periodicite_heures: int) -> datetime:
    """Premier créneau strictement postérieur à « apres ».

    Les créneaux partent de l'heure de départ et se répètent toutes les
    periodicite_heures heures : 03:01 et 6 h donnent 03:01, 09:01, 15:01,
    21:01. La référence est une date fixe, pour que la grille reste la
    même après un redémarrage, même si la périodicité ne divise pas 24.
    """
    reference = datetime.combine(datetime(2000, 1, 1).date(), heure)
    pas = timedelta(hours=periodicite_heures)
    return reference + ((apres - reference) // pas + 1) * pas


def prochaine_sauvegarde(derniere, heure: time, periodicite_heures: int,
                         maintenant: datetime) -> datetime:
    """Date de la prochaine sauvegarde.

    Sans sauvegarde connue : le prochain créneau à venir.
    Sinon : le premier créneau après la dernière sauvegarde. Une date
    passée (Raspberry éteint au moment prévu) signifie « à faire tout de
    suite » ; la suivante reprend ensuite sur la grille des créneaux.
    """
    return creneau_suivant(
        maintenant if derniere is None else derniere, heure, periodicite_heures
    )


def _boucle(heure, periodicite_heures, arret):
    if arret.wait(DELAI_DEMARRAGE):
        return

    nouvel_essai = None
    annoncee = None

    while not arret.is_set():
        maintenant = datetime.now()
        echeance = prochaine_sauvegarde(
            derniere_sauvegarde(), heure, periodicite_heures, maintenant
        )
        if nouvel_essai and nouvel_essai > echeance:
            echeance = nouvel_essai

        if maintenant < echeance:
            if echeance != annoncee:
                print(f"Prochaine sauvegarde : {echeance:%d/%m/%Y %H:%M}")
                annoncee = echeance
            # Attente par petits pas : l'horloge du Raspberry (sans pile)
            # peut être corrigée par NTP après le démarrage.
            arret.wait(min(PAS_ATTENTE, (echeance - maintenant).total_seconds()))
            continue

        debut = datetime.now()
        try:
            if main() == 0:
                noter_reussite(debut)
                nouvel_essai = None
                continue
        except Exception as erreur:
            # Une erreur ne doit pas arrêter le serveur ni les sauvegardes suivantes
            print(f"ERREUR de sauvegarde : {erreur}", file=sys.stderr)
        nouvel_essai = debut + DELAI_NOUVEL_ESSAI
        print(f"Nouvel essai de sauvegarde à {nouvel_essai:%H:%M}.")


def demarrer_en_arriere_plan(heure=None, periodicite_heures=None):
    """Lance les sauvegardes planifiées dans un thread.

    Renvoie un threading.Event (appeler .set() pour arrêter), ou None
    si la sauvegarde n'est pas possible sur ce système (Windows).
    """
    heure = lire_heure(heure or config.SAUVEGARDE_HEURE)
    periodicite_heures = int(periodicite_heures or config.SAUVEGARDE_PERIODICITE_HEURES)
    if periodicite_heures < 1:
        raise ValueError("SAUVEGARDE_PERIODICITE_HEURES doit valoir au moins 1")

    if os.name != "posix":
        print("Sauvegarde automatique : ignorée (Linux uniquement).")
        return None

    arret = threading.Event()
    threading.Thread(
        target=_boucle,
        args=(heure, periodicite_heures, arret),
        name="sauvegarde",
        daemon=True,
    ).start()

    print(
        f"Sauvegarde automatique : toutes les {periodicite_heures} h "
        f"à partir de {heure:%H:%M}"
    )
    return arret


if __name__ == "__main__":
    try:
        debut = datetime.now()
        code = main()
        if code == 0:
            noter_reussite(debut)
        sys.exit(code)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as erreur:
        print(f"ERREUR : {erreur}", file=sys.stderr)
        sys.exit(1)
