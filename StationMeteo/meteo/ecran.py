"""Veille de l'écran : coupure du signal HDMI et réveil au toucher.

L'écran n'a pas de DDC/CI : seul l'arrêt du signal HDMI éteint son
rétroéclairage. La page demande la veille (mode nuit, si ECRAN_VEILLE =
"hdmi") par POST /api/ecran ; la sortie est coupée par wlr-randr dans la
session Wayland du kiosque (cage).

Écran éteint, cage ne transmet plus les touchers à Chromium : un thread
lit donc directement les périphériques d'entrée (/dev/input, l'utilisateur
doit être dans le groupe input) et rallume l'écran au premier appui. La
page l'apprend par GET /api/ecran (date du dernier réveil) et repasse en
mode jour.

Linux uniquement ; ailleurs (PC Windows) les demandes sont ignorées.
"""

import glob
import os
import select
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime

from meteo import config

# struct input_event : timeval (deux "long" natifs), type, code, value
_FORMAT_EVENEMENT = "llHHi"
_TAILLE_EVENEMENT = struct.calcsize(_FORMAT_EVENEMENT)

EV_KEY = 0x01
EV_ABS = 0x03
ABS_MT_TRACKING_ID = 0x39

# Après la mise en veille, les événements de l'appui qui l'a demandée
# (doigt relevé sur le bouton 🌙) ne doivent pas rallumer l'écran.
DELAI_IGNORE_S = 2.0

# Nouvelle recherche des périphériques d'entrée (branchement à chaud)
INTERVALLE_RECHERCHE_S = 60

_verrou = threading.Lock()
_en_veille = False
_debut_veille = 0.0
_dernier_reveil = None      # date ISO du dernier réveil au toucher


def disponible():
    """Veille HDMI demandée et possible (Linux)."""
    return config.ECRAN_VEILLE == "hdmi" and sys.platform.startswith("linux")


def _environnement_wayland():
    """Variables pour joindre la session cage du même utilisateur."""
    env = dict(os.environ)
    dossier = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    env["XDG_RUNTIME_DIR"] = dossier

    if not env.get("WAYLAND_DISPLAY"):
        sockets = sorted(
            os.path.basename(s)
            for s in glob.glob(os.path.join(dossier, "wayland-*"))
            if not s.endswith(".lock")
        )
        env["WAYLAND_DISPLAY"] = sockets[0] if sockets else "wayland-0"

    return env


def _sortie(allumee):
    """Allume ou coupe la sortie HDMI ; True si wlr-randr a réussi."""
    commande = [
        "wlr-randr", "--output", config.ECRAN_SORTIE,
        "--on" if allumee else "--off"
    ]
    try:
        resultat = subprocess.run(
            commande, env=_environnement_wayland(),
            capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired) as erreur:
        print(f"Écran : {' '.join(commande)} impossible : {erreur}")
        return False

    if resultat.returncode != 0:
        print(
            f"Écran : {' '.join(commande)} a échoué : "
            f"{resultat.stderr.strip() or resultat.returncode}"
        )
        return False
    return True


def etat():
    """État pour la page : veille en cours et date du dernier réveil."""
    with _verrou:
        return {
            "veille_hdmi": disponible(),
            "veille": _en_veille,
            "dernier_reveil": _dernier_reveil
        }


def mettre_en_veille():
    global _en_veille, _debut_veille
    if not disponible():
        return False

    with _verrou:
        if _sortie(False):
            _en_veille = True
            _debut_veille = time.monotonic()
            return True
        return False


def reveiller(par_toucher=False):
    global _en_veille, _dernier_reveil
    if not disponible():
        return False

    with _verrou:
        if not _en_veille:
            return True
        if not _sortie(True):
            return False
        _en_veille = False
        if par_toucher:
            _dernier_reveil = datetime.now().isoformat(timespec="seconds")
        return True


def _peripheriques():
    """Chemins des périphériques d'entrée à surveiller."""
    if config.ECRAN_TACTILE:
        return [config.ECRAN_TACTILE]
    # Défaut : tous les périphériques USB (tactile, souris, clavier).
    # L'entrée HDMI-CEC (télécommande de télé) n'y figure pas.
    return sorted(glob.glob("/dev/input/by-id/*-event-*"))


def _est_un_appui(donnees):
    """Un événement du bloc lu est-il un appui (toucher, bouton, touche) ?"""
    for debut in range(0, len(donnees) - _TAILLE_EVENEMENT + 1, _TAILLE_EVENEMENT):
        _, _, type_, code, valeur = struct.unpack_from(
            _FORMAT_EVENEMENT, donnees, debut
        )
        if type_ == EV_KEY and valeur == 1:
            return True
        if type_ == EV_ABS and code == ABS_MT_TRACKING_ID and valeur >= 0:
            return True
    return False


def _surveiller():
    ouverts = {}            # descripteur -> chemin
    derniere_recherche = 0.0

    while True:
        try:
            if time.monotonic() - derniere_recherche > INTERVALLE_RECHERCHE_S:
                derniere_recherche = time.monotonic()
                connus = set(ouverts.values())
                for chemin in _peripheriques():
                    if chemin in connus:
                        continue
                    try:
                        ouverts[os.open(chemin, os.O_RDONLY | os.O_NONBLOCK)] = chemin
                        print(f"Écran : réveil au toucher par {chemin}")
                    except OSError as erreur:
                        print(f"Écran : {chemin} illisible : {erreur}")

            if not ouverts:
                time.sleep(INTERVALLE_RECHERCHE_S)
                continue

            prets, _, _ = select.select(list(ouverts), [], [], INTERVALLE_RECHERCHE_S)

            for descripteur in prets:
                try:
                    donnees = os.read(descripteur, _TAILLE_EVENEMENT * 64)
                except BlockingIOError:
                    continue
                except OSError:
                    donnees = b""
                if not donnees:
                    # Périphérique débranché : il sera rouvert s'il revient
                    os.close(descripteur)
                    del ouverts[descripteur]
                    continue

                # Les événements sont lus (et oubliés) même écran allumé :
                # sans prise exclusive, cage les reçoit aussi.
                if (_en_veille
                        and time.monotonic() - _debut_veille > DELAI_IGNORE_S
                        and _est_un_appui(donnees)):
                    reveiller(par_toucher=True)

        except Exception as erreur:
            print(f"Erreur surveillance du toucher : {erreur}")
            time.sleep(5)


def demarrer_en_arriere_plan():
    """Lance la surveillance du toucher (si ECRAN_VEILLE = "hdmi")."""
    if not disponible():
        return
    threading.Thread(target=_surveiller, name="ecran", daemon=True).start()


if __name__ == "__main__":
    # Essai manuel : veille 1 min (ou jusqu'au toucher), puis réveil
    if not disponible():
        sys.exit('ECRAN_VEILLE = "hdmi" et Linux nécessaires.')
    demarrer_en_arriere_plan()
    print("Veille pendant 1 min (toucher l'écran pour réveiller)...")
    mettre_en_veille()
    for i in range(600):
        if not _en_veille:
            print("Réveillé par le toucher au bout de", i/10, "s")
            break
        time.sleep(0.1)
    reveiller()
