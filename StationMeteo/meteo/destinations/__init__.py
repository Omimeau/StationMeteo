"""Destinations des archives de sauvegarde (plugins).

Chaque destination est un module qui fournit :
    NOM                    nom affiché dans les messages ;
    verifier()             contrôle la configuration (appelée avant le dump) ;
    envoyer(archive)       envoie le fichier ; lève une exception en cas d'échec.

Pour ajouter une destination : créer son module dans ce dossier puis
l'inscrire dans DESTINATIONS. Elle se choisit dans config_local.py avec
SAUVEGARDE_DESTINATION.
"""

from __future__ import annotations

from pathlib import Path

from .. import config

from . import pcloud

DESTINATIONS = {
    "pcloud": pcloud,
}


def destination_choisie():
    nom = str(config.SAUVEGARDE_DESTINATION).strip().lower()
    try:
        return DESTINATIONS[nom]
    except KeyError:
        raise ValueError(
            f"SAUVEGARDE_DESTINATION inconnue : {nom!r} "
            f"(valeurs possibles : {', '.join(DESTINATIONS)})"
        ) from None


def verifier_destination() -> None:
    destination_choisie().verifier()


def sauve_l_archive(archive: Path) -> None:
    """Envoie l'archive vers la destination configurée."""
    destination_choisie().envoyer(archive)
