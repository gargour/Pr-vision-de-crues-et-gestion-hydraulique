import argparse
import os
import sys
import time

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from src.common import charger_config, get_logger
from src.sources.sentinel2 import search_scenes

log = get_logger("sentinel2_catalog")


def stats_zone(href, bbox):
    """Statistiques de la carte SCL sur notre zone."""
    with rasterio.open(href) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, *bbox)
        win = from_bounds(*bounds, transform=src.transform)
        scl = src.read(1, window=win, boundless=True, fill_value=0)
    valide = scl != 0                      # 0 = pas de données (hors tuile)
    n = max(valide.sum(), 1)
    return {
        "couverture_pct": round(valide.mean() * 100, 1),
        "nuages_pct": round(np.isin(scl, [8, 9, 10]).sum() / n * 100, 1),
        "ombres_pct": round((scl == 3).sum() / n * 100, 1),
        "neige_pct": round((scl == 11).sum() / n * 100, 1),
        "eau_pct": round((scl == 6).sum() / n * 100, 1),
    }


def traiter_scene(it, bbox, essais=2):
    """Une scène -> une ligne du catalogue (avec un nouvel essai si erreur)."""
    for essai in range(1, essais + 1):
        try:
            ligne = {
                "date": it.datetime.date().isoformat(),
                "tuile": it.id.split("_")[4],
                "id": it.id,
                "nuages_tuile_pct": round(it.properties["eo:cloud_cover"], 1),
            }
            ligne.update(stats_zone(it.assets["SCL"].href, bbox))
            return ligne
        except Exception as e:
            log.warning("scène %s, essai %d/%d : %s", it.id, essai, essais, e)
            time.sleep(2)
    return None


def sauver(df, chemin):
    tmp = chemin + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, chemin)


def construire_catalogue(cfg, annees):
    chemin = os.path.join(cfg["chemins"]["raw"], "sentinel2_catalogue.csv")
    os.makedirs(cfg["chemins"]["raw"], exist_ok=True)
    cat = pd.read_csv(chemin) if os.path.exists(chemin) else pd.DataFrame()
    deja = set(cat["id"]) if len(cat) else set()
    bbox = cfg["zone"]["bbox"]
    echecs = 0

    for annee in annees:
        items = search_scenes(cfg, f"{annee}-01-01", f"{annee}-12-31")
        nouveaux = [i for i in sorted(items, key=lambda i: i.datetime)
                    if i.id not in deja]
        log.info("%d : %d scènes trouvées, %d nouvelles", annee, len(items), len(nouveaux))
        lignes = []
        for it in nouveaux:
            ligne = traiter_scene(it, bbox)
            if ligne is None:
                echecs += 1
                continue
            lignes.append(ligne)
        if lignes:
            cat = pd.concat([cat, pd.DataFrame(lignes)], ignore_index=True)
            sauver(cat, chemin)     # sauvegarde après chaque année
            log.info("%d : %d scènes ajoutées au catalogue", annee, len(lignes))

    log.info("Catalogue : %d images -> %s (%d échecs)", len(cat), chemin, echecs)
    if echecs:
        raise RuntimeError(f"{echecs} scènes en échec : relancer, le script reprend")
    return chemin


def main(argv=None):
    parser = argparse.ArgumentParser(description="Catalogue Sentinel-2 de la zone")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--annee", type=int, help="une seule année (sinon toutes)")
    args = parser.parse_args(argv)
    try:
        cfg = charger_config(args.config)
        if args.annee:
            annees = [args.annee]
        else:
            a0, a1 = cfg["sentinel2"]["annees"]
            annees = range(a0, a1 + 1)
        construire_catalogue(cfg, annees)
        return 0
    except Exception:
        log.exception("Échec du catalogue Sentinel-2")
        return 1


if __name__ == "__main__":
    sys.exit(main())