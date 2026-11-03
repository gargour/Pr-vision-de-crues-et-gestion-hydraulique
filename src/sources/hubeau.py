import argparse
import os
import sys

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.common import charger_config, get_logger

log = get_logger("hubeau")


def session_avec_reessais():
    """Session HTTP qui réessaie en cas d'erreur réseau ou serveur."""
    retry = Retry(total=5, backoff_factor=1,
                  status_forcelist=[429, 500, 502, 503, 504])
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def get_all(session, base_url, endpoint, params, timeout):
    """Télécharge toutes les pages d'un endpoint Hub'Eau."""
    url = f"{base_url}/{endpoint}"
    rows, page = [], 0
    while url:
        r = session.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        js = r.json()
        rows += js["data"]
        page += 1
        log.info("page %d : %d lignes (total %d)", page, len(js["data"]), len(rows))
        url = js.get("next")   # None à la dernière page
        params = None          # déjà inclus dans le lien "next"
    return pd.DataFrame(rows)


def telecharger_debit(cfg, debut=None):
    """Débit moyen journalier de la station, enregistré dans data/raw/."""
    h = cfg["hubeau"]
    code = cfg["station"]["code_site"]
    debut = debut or cfg["periode"]["debut"]
    log.info("Téléchargement du débit %s, station %s, depuis %s",
             h["grandeur"], code, debut)

    df = get_all(session_avec_reessais(), h["base_url"], "obs_elab", {
        "code_entite": code,
        "grandeur_hydro_elab": h["grandeur"],
        "date_debut_obs_elab": debut,
        "size": h["taille_page"],
    }, h["timeout"])

    if df.empty:
        raise ValueError("Aucune donnée reçue de Hub'Eau")

    dossier = cfg["chemins"]["raw"]
    os.makedirs(dossier, exist_ok=True)
    sortie = os.path.join(dossier, f"hubeau_{code}_{h['grandeur']}.csv")
    tmp = sortie + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, sortie)        # écriture complète ou rien
    log.info("Fichier écrit : %s (%d lignes)", sortie, len(df))
    return sortie


def main(argv=None):
    parser = argparse.ArgumentParser(description="Importation du débit Hub'Eau")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--debut", help="date de début (AAAA-MM-JJ)")
    args = parser.parse_args(argv)
    try:
        telecharger_debit(charger_config(args.config), args.debut)
        return 0
    except Exception:
        log.exception("Échec de l'importation Hub'Eau")
        return 1


if __name__ == "__main__":
    sys.exit(main())