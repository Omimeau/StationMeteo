"""Bibliothèque de la station météo.

Modules :
    config        paramètres lus dans config_local.py
    base_donnees  accès MySQL/MariaDB (table releves)
    acquisition   lecture des capteurs Tuya et enregistrement des relevés
    previsions    prévisions météo : fournisseur actif, cache, heures passées
    geocodage     nom de la ville à partir des coordonnées
    sauvegarde    export SQL.gz de la base et envoi vers pCloud
    fournisseurs  API des différents fournisseurs de prévisions
"""
