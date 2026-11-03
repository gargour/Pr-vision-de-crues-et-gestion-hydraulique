import argparse
import json
import os
import sys

import pandas as pd

from src.common import charger_config, get_logger
from src.validation.donnees import (coherence_inter_modalites,
                                    valider_dates_images, valider_debit)

log = get_logger("validation")


def valider(cfg, chemin_debit=None, chemin_dates=None):
    code = cfg["station"]["code_site"]
    chemin_debit = chemin_debit or os.path.join(
        cfg["chemins"]["clean"], f"hubeau_{code}_daily.csv")
    chemin_dates = chemin_dates or os.path.join(
        cfg["chemins"]["raw"], "sentinel2_dates_utiles.csv")
    for f in (chemin_debit, chemin_dates):
        if not os.path.exists(f):
            raise FileNotFoundError(f"Fichier introuvable : {f}. "
                                    "Lancer d'abord les étapes précédentes.")

    debit = pd.read_csv(chemin_debit, parse_dates=["date"]).set_index("date")
    dates = pd.read_csv(chemin_dates, parse_dates=["date"])
    log.info("Débit : %d jours (%s -> %s) | images : %d dates",
             len(debit), debit.index.min().date(), debit.index.max().date(), len(dates))

    controles = [
        ("débit", valider_debit(debit, cfg["nettoyage"]["max_manquants_pct"])),
        ("dates d'images", valider_dates_images(dates)),
        ("cohérence débit/images", coherence_inter_modalites(debit, dates["date"])),
    ]
    total = 0
    for nom, erreurs in controles:
        if erreurs:
            for e in erreurs:
                log.error("[%s] %s", nom, e)
            total += len(erreurs)
        else:
            log.info("[%s] OK", nom)

    # Rapport de statistiques (sans date d'exécution : même données = même fichier)
    rapport = {
        "debit_jours": int(len(debit)),
        "debit_debut": str(debit.index.min().date()),
        "debit_fin": str(debit.index.max().date()),
        "debit_manquants_pct": round(float(debit["debit_m3s"].isna().mean() * 100), 2),
        "debit_douteux": int(debit["qualite_douteuse"].sum()),
        "images_dates_utilisables": int(len(dates)),
        "erreurs_validation": int(total),
    }
    os.makedirs(cfg["chemins"]["reports"], exist_ok=True)
    sortie = os.path.join(cfg["chemins"]["reports"], "validation.json")
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, indent=2, ensure_ascii=False)
    log.info("Rapport écrit : %s", sortie)

    if total:
        raise ValueError(f"{total} erreur(s) de validation")
    log.info("Validation : OK")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validation des données préparées")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--debit", help="fichier de débit à valider (test)")
    parser.add_argument("--dates", help="fichier de dates d'images à valider (test)")
    args = parser.parse_args(argv)
    try:
        valider(charger_config(args.config), args.debit, args.dates)
        return 0
    except Exception:
        log.exception("Échec de la validation")
        return 1


if __name__ == "__main__":
    sys.exit(main())