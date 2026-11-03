import argparse
import os
import sys

import numpy as np
import pandas as pd
import planetary_computer
from pystac_client import Client

from src.common import charger_config, get_logger

log = get_logger("sentinel1_catalog")


def scenes_annee(catalog, cfg, annee):
    """Scènes radar de l'année qui contiennent la station."""
    lon, lat = cfg["station"]["longitude"], cfg["station"]["latitude"]
    search = catalog.search(collections=[cfg["sentinel1"]["collection"]],
                            bbox=cfg["zone"]["bbox"],
                            datetime=f"{annee}-01-01/{annee}-12-31")
    items = list(search.items())
    return items, [i for i in items
                   if i.bbox[0] <= lon <= i.bbox[2] and i.bbox[1] <= lat <= i.bbox[3]]


def construire_catalogue(cfg, annees):
    chemin = os.path.join(cfg["chemins"]["raw"], "sentinel1_catalogue.csv")
    os.makedirs(cfg["chemins"]["raw"], exist_ok=True)
    cat = pd.read_csv(chemin) if os.path.exists(chemin) else pd.DataFrame()
    deja = set(cat["id"]) if len(cat) else set()
    catalog = Client.open(cfg["sentinel1"]["stac_url"],
                          modifier=planetary_computer.sign_inplace)

    for annee in annees:
        trouvees, gardees = scenes_annee(catalog, cfg, annee)
        nouvelles = [i for i in gardees if i.id not in deja]
        log.info("%d : %d scènes trouvées, %d contiennent la station, %d nouvelles",
                 annee, len(trouvees), len(gardees), len(nouvelles))
        lignes = [{"date": i.datetime.date().isoformat(), "id": i.id,
                   "plateforme": i.properties.get("platform"),
                   "orbite": i.properties.get("sat:orbit_state"),
                   "mode": i.properties.get("sar:instrument_mode")}
                  for i in nouvelles]
        if lignes:
            cat = pd.concat([cat, pd.DataFrame(lignes)], ignore_index=True)
            tmp = chemin + ".tmp"
            cat.to_csv(tmp, index=False)
            os.replace(tmp, chemin)

    if cat.empty:
        raise ValueError("Catalogue Sentinel-1 vide")
    log.info("Catalogue Sentinel-1 : %d scènes -> %s", len(cat), chemin)
    return cat


def ecart_jours(dates_images, jours):
    """Pour chaque jour, nombre de jours jusqu'à l'image la plus proche."""
    img = np.sort(dates_images.values.astype("datetime64[D]"))
    return np.array([np.abs(img - d).min().astype(int)
                     for d in jours.values.astype("datetime64[D]")])


def comparer(cfg, cat):
    """Jours de crue couverts par une image : radar, optique, les deux."""
    code = cfg["station"]["code_site"]
    c = cfg["crues"]
    chemin_debit = os.path.join(cfg["chemins"]["clean"], f"hubeau_{code}_daily.csv")
    chemin_s2 = os.path.join(cfg["chemins"]["raw"], "sentinel2_dates_utiles.csv")
    for f in (chemin_debit, chemin_s2):
        if not os.path.exists(f):
            raise FileNotFoundError(f"Fichier introuvable : {f}. "
                                    "Lancer d'abord les étapes précédentes.")
    q = pd.read_csv(chemin_debit, parse_dates=["date"])
    crues = q[q["debit_m3s"] > c["seuil_m3s"]]
    if crues.empty:
        raise ValueError(f"Aucun jour de crue au-dessus de {c['seuil_m3s']} m3/s")

    s1 = pd.to_datetime(cat["date"]).drop_duplicates()
    s2 = pd.read_csv(chemin_s2, parse_dates=["date"])["date"]
    tous = pd.concat([s1, s2]).drop_duplicates()

    log.info("Jours de crue (> %s m3/s) : %d", c["seuil_m3s"], len(crues))
    for nom, dates in [("Sentinel-2 utilisable", s2), ("Sentinel-1 radar", s1),
                       ("Sentinel-1 + Sentinel-2", tous)]:
        e = ecart_jours(dates, crues["date"])
        n = int((e <= c["fenetre_jours"]).sum())
        log.info("%-24s | image à moins de %d jours : %d / %d (%.0f %%) | "
                 "écart médian : %.0f jours", nom, c["fenetre_jours"], n,
                 len(crues), n / len(crues) * 100, np.median(e))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Catalogue Sentinel-1 de la zone")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--annee", type=int, help="une seule année (sinon toutes)")
    args = parser.parse_args(argv)
    try:
        cfg = charger_config(args.config)
        if args.annee:
            annees = [args.annee]
        else:
            a0, a1 = cfg["sentinel1"]["annees"]
            annees = range(a0, a1 + 1)
        cat = construire_catalogue(cfg, annees)
        comparer(cfg, cat)
        return 0
    except Exception:
        log.exception("Échec du catalogue Sentinel-1")
        return 1


if __name__ == "__main__":
    sys.exit(main())