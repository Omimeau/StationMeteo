"""Compare config_local.py au modèle config_local.exemple.py.

Affiche les paramètres du modèle absents de config_local.py, avec leur
valeur par défaut (meteo/config.py) et les lignes du modèle à recopier,
puis les paramètres de config_local.py inconnus du modèle.

Les fichiers sont analysés sans être exécutés, et les valeurs de
config_local.py (mots de passe, clés) ne sont jamais affichées.

    python verifier_config.py

Code de sortie : 0 si rien ne manque, 1 s'il manque des paramètres,
2 si un fichier est absent ou illisible.
"""

import ast
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
LOCAL = RACINE / "config_local.py"
MODELE = RACINE / "config_local.exemple.py"
DOSSIER_CODE = RACINE / "meteo"

# Anciens noms acceptés en secours par meteo/config.py.
ANCIENS_NOMS = {
    "DB_HOST": ("MYSQL_HOST",),
    "DB_USER": ("MYSQL_USER",),
    "DB_PASSWORD": ("MYSQL_PASSWORD",),
    "DB_NAME": ("MYSQL_DATABASE",),
}


def lire(fichier):
    """Lignes et arbre syntaxique d'un fichier Python."""
    source = fichier.read_text(encoding="utf-8")
    return source.splitlines(), ast.parse(source, filename=str(fichier))


def parametres(arbre):
    """{nom: noeud} des affectations de premier niveau en majuscules."""
    trouves = {}
    for noeud in arbre.body:
        if isinstance(noeud, ast.Assign):
            cibles = noeud.targets
        elif isinstance(noeud, ast.AnnAssign):
            cibles = [noeud.target]
        else:
            continue
        for cible in cibles:
            if isinstance(cible, ast.Name) and cible.id.isupper():
                trouves.setdefault(cible.id, noeud)
    return trouves


def valeurs_par_defaut():
    """{nom: texte} des défauts lus dans les appels parametre() de meteo/.
    Texte "obligatoire" quand l'appel n'a pas de defaut."""
    defauts = {}
    for fichier in sorted(DOSSIER_CODE.rglob("*.py")):
        try:
            _, arbre = lire(fichier)
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            fonction = noeud.func
            nom_fonction = getattr(fonction, "id", None) or getattr(fonction, "attr", None)
            if nom_fonction != "parametre":
                continue
            texte = "obligatoire"
            for mot_cle in noeud.keywords:
                if mot_cle.arg == "defaut":
                    texte = "défaut " + ast.unparse(mot_cle.value)
            for argument in noeud.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    defauts.setdefault(argument.value, texte)
    return defauts


def lignes_du_modele(lignes, noeud):
    """Commentaires placés juste au-dessus du paramètre (sans les titres
    de section « # --- ... »), puis sa ligne."""
    debut = noeud.lineno - 1
    while debut > 0:
        precedente = lignes[debut - 1].lstrip()
        if not precedente.startswith("#") or precedente.startswith("# ---"):
            break
        debut -= 1
    return lignes[debut:noeud.end_lineno]


def main():
    for fichier in (MODELE, LOCAL):
        if not fichier.is_file():
            print(f"Fichier absent : {fichier}")
            return 2

    try:
        lignes_modele, arbre_modele = lire(MODELE)
        _, arbre_local = lire(LOCAL)
    except SyntaxError as erreur:
        # Pas de erreur.text : la ligne pourrait contenir un mot de passe.
        print(f"Erreur de syntaxe dans {Path(erreur.filename).name}, ligne {erreur.lineno}")
        return 2
    except (OSError, UnicodeDecodeError) as erreur:
        print(f"Lecture impossible : {erreur}")
        return 2

    modele = parametres(arbre_modele)
    local = parametres(arbre_local)
    defauts = valeurs_par_defaut()

    def present(nom):
        return nom in local or any(ancien in local for ancien in ANCIENS_NOMS.get(nom, ()))

    absents = [nom for nom in modele if not present(nom)]
    anciens = {ancien for noms in ANCIENS_NOMS.values() for ancien in noms}
    inconnus = [nom for nom in local if nom not in modele and nom not in anciens]

    print(f"Modèle : {MODELE}")
    print(f"Comparé à : {LOCAL}")
    print()

    if absents:
        print(f"Paramètres absents de config_local.py : {len(absents)}")
        print("(sans eux, la valeur par défaut de meteo/config.py s'applique ;")
        print(" recopier les lignes voulues du modèle puis adapter la valeur)")
        for nom in absents:
            print()
            print(f"  {nom}  ({defauts.get(nom, 'défaut : voir meteo/config.py')})")
            for ligne in lignes_du_modele(lignes_modele, modele[nom]):
                print("    " + ligne)
    else:
        print("Aucun paramètre du modèle ne manque dans config_local.py.")

    if inconnus:
        print()
        print(f"Paramètres de config_local.py absents du modèle : {len(inconnus)}")
        print("(anciens ou propres à cette installation ; ignorés s'ils ne sont plus lus)")
        for nom in inconnus:
            print(f"  {nom}")

    return 1 if absents else 0


if __name__ == "__main__":
    sys.exit(main())
