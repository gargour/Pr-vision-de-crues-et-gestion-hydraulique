import argparse
import os
import sys

import numpy as np
import pandas as pd

from src.common import charger_config, get_logger

log = get_logger("analyse_catalogue")


def ecart_jours(dates_images, jours):
    """Pour chaque jour, nombre de jours jusqu'à l'image la plus proche."""
    img = dates_images.values.astype("datetime64[D]")
    return np.array([np.abs(img - np.datetime64(d, "D")).min().astype(int)
                     for d in jours.values.astype("datetime64[D]")])


def analyser(cfg):
    raw = cfg["chemins"]["raw"]
    code = cfg["station"]["code_site"]
    u = cfg["utilisable"]
    c = cfg["crues"]
    chemin_cat = os.path.join(raw, "sentinel2_catalogue.csv")
    chemin_debit = os.path.join(cfg["chemins"]["clean"], f"hubeau_{code}_daily.csv")
    sortie = os.path.join(raw, "sentinel2_dates_utiles.csv")

    for f in (chemin_cat, chemin_debit):
        if not os.path.exists(f):
            raise FileNotFoundError(f"Fichier introuvable : {f}. "
                                    "Lancer d'abord les étapes précédentes.")

    cat = pd.read_csv(chemin_cat, parse_dates=["date"])
    log.info("Catalogue : %d images", len(cat))

    # 1. Images utilisables (critères mesurés sur notre zone)
    utile = cat[(cat["couverture_pct"] >= u["couverture_min_pct"])
                & (cat["nuages_pct"] < u["nuages_max_pct"])
                & (cat["ombres_pct"] < u["ombres_max_pct"])
                & (cat["neige_pct"] < u["neige_max_pct"])]
    # 2. Une seule image par date : la mieux couverte
    utile = (utile.sort_values(["date", "couverture_pct"], ascending=[True, False])
                  .drop_duplicates("date").sort_values("date").reset_index(drop=True))
    log.info("Dates utilisables : %d", len(utile))
    if utile.empty:
        raise ValueError("Aucune image utilisable avec ces critères")

    par_annee = utile.groupby(utile["date"].dt.year).size()
    log.info("Dates utilisables par année : %s", par_annee.to_dict())

    ecarts = utile["date"].diff().dt.days.dropna()
    log.info("Écart médian entre deux images : %.0f jours | plus long trou : %d jours",
             ecarts.median(), int(ecarts.max()))

    # 3. Lien avec les crues
    q = pd.read_csv(chemin_debit, parse_dates=["date"])
    crues = q[q["debit_m3s"] > c["seuil_m3s"]]
    if crues.empty:
        raise ValueError(f"Aucun jour de crue au-dessus de {c['seuil_m3s']} m3/s")
    e = ecart_jours(utile["date"], crues["date"])
    proches = int((e <= c["fenetre_jours"]).sum())
    log.info("Jours de crue (> %s m3/s) : %d | image à moins de %d jours : %d (%.0f %%) "
             "| écart médian : %.0f jours", c["seuil_m3s"], len(crues),
             c["fenetre_jours"], proches, proches / len(crues) * 100, np.median(e))

    # 4. Écriture (fichier complet ou rien)
    out = utile[["date", "tuile", "id", "couverture_pct", "nuages_pct"]]
    tmp = sortie + ".tmp"
    out.to_csv(tmp, index=False)
    os.replace(tmp, sortie)
    log.info("Fichier écrit : %s (%d dates)", sortie, len(out))
    return sortie


def main(argv=None):
    parser = argparse.ArgumentParser(description="Dates Sentinel-2 utilisables")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)
    try:
        analyser(charger_config(args.config))
        return 0
    except Exception:
        log.exception("Échec de l'analyse du catalogue")
        return 1


if __name__ == "__main__":
    sys.exit(main())