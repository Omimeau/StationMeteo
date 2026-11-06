"""Destination de sauvegarde : lien de dépôt pCloud (« upload link »).

Tout ce qui est propre à pCloud se trouve ici : adresse de l'API,
code du lien de dépôt et interprétation de la réponse.

Paramètre lu dans config_local.py : PCLOUD_UPLOAD_CODE (code du lien de
dépôt créé dans pCloud ; c'est une donnée personnelle, ne jamais la publier).
Prérequis : curl.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .. import config

NOM = "pCloud"

# Le domaine eapi.pcloud.com correspond aux comptes pCloud en Europe.
PCLOUD_UPLOAD_URL = "https://eapi.pcloud.com/uploadtolink"

# Nom de l'expéditeur affiché dans pCloud pour chaque dépôt.
NOM_EXPEDITEUR = "StationMeteo"


def _code_depot() -> str:
    code = str(config.parametre("PCLOUD_UPLOAD_CODE")).strip()
    if not re.fullmatch(r"[a-zA-Z0-9]+", code):
        raise ValueError("PCLOUD_UPLOAD_CODE contient des caracteres inattendus")
    return code


def verifier() -> None:
    """Vérifie la configuration avant le dump (échec rapide)."""
    _code_depot()
    if not shutil.which("curl"):
        raise RuntimeError("Installer curl : sudo apt install curl")


def envoyer(archive: Path) -> None:
    """Téléverse l'archive ; lève RuntimeError si pCloud ne la confirme pas."""
    code = _code_depot()

    print("Televersement vers pCloud...")
    transfert = subprocess.run(
        [
            "curl", "--fail", "--silent", "--show-error", "--retry", "2",
            "--retry-delay", "10", "--connect-timeout", "20",
            "--max-time", "1800", "--form", f"code={code}",
            "--form", f"names={NOM_EXPEDITEUR}",
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
            f"{transfert.stderr.strip()}"
        )

    # L'API pCloud retourne un JSON : HTTP 200 ne suffit pas pour conclure.
    try:
        reponse = json.loads(transfert.stdout)
    except json.JSONDecodeError as err:
        raise RuntimeError(
            "Reponse pCloud non JSON ; verifier le televersement"
        ) from err
    if not isinstance(reponse, dict) or reponse.get("result") != 0:
        raise RuntimeError(
            f"pCloud refuse la sauvegarde : code={reponse.get('result') if isinstance(reponse, dict) else 'inconnu'}, "
            f"message={reponse.get('error', 'indeterminee') if isinstance(reponse, dict) else 'reponse inattendue'}"
        )

    # Un lien de dépôt ne permet pas de supprimer les anciennes archives
    # dans pCloud : seules les copies locales sont nettoyées (sauvegarde.py).
    print("Televersement pCloud confirme (result=0).")
