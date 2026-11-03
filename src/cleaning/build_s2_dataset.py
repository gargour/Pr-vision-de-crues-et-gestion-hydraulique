import argparse
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

from src.common import charger_config, get_logger
from src.sources.sentinel2 import ouvrir_catalogue

warnings.filterwarnings("ignore")
log = get_logger("build_s2_dataset")


def lire(href, bbox, shape=None, resampling=Resampling.bilinear):
    """Lit la zone d'une bande. Pixels hors scène = 0."""
    with rasterio.open(href) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, *bbox)
        win = from_bounds(*bounds, transform=src.transform)
        if shape is None:
            shape = (int(round(win.height)), int(round(win.width)))
        a = src.read(1, window=win, out_shape=shape, boundless=True,
                     fill_value=0, resampling=resampling)
        return a, shape, src.crs, src.window_transform(win)


def echelle_offset(item, nom_bande):
    """Facteur et décalage pour passer des valeurs brutes à la réflectance."""
    extra = item.assets[nom_bande].extra_fields.get("raster:bands", [{}])[0]
    scale = extra.get("scale", 0.0001)
    if "offset" in extra:
        return scale, extra["offset"]
    base = str(item.properties.get("s2:processing_baseline", "0"))
    return scale, (-0.1 if float(base) >= 4.0 else 0.0)


def ecrire_image(item, cfg, chemin):
    """Lit les bandes, masque les pixels invalides, écrit un GeoTIFF."""
    bbox = cfg["zone"]["bbox"]
    bandes = cfg["images_nettoyees"]["bandes"]
    mauvais = cfg["images_nettoyees"]["scl_mauvais"]

    dn, shape, crs, tr = {}, None, None, None
    for nom in bandes:
        a, shape, crs_, tr_ = lire(item.assets[nom].href, bbox, shape)
        if crs is None:
            crs, tr = crs_, tr_
        dn[nom] = a
    scl, _, _, _ = lire(item.assets["SCL"].href, bbox, shape, Resampling.nearest)

    ok = ~np.isin(scl, mauvais)
    for nom in bandes:
        ok &= dn[nom] > 0

    out = np.full((len(bandes),) + shape, -1, dtype="int16")
    for k, nom in enumerate(bandes):
        scale, offset = echelle_offset(item, nom)
        refl = dn[nom].astype("float32") * scale + offset
        val = np.clip(refl * 10000, 0, 30000).astype("int16")
        out[k][ok] = val[ok]

    tmp = chemin + ".tmp"
    profil = dict(driver="GTiff", height=shape[0], width=shape[1],
                  count=len(bandes), dtype="int16", crs=crs, transform=tr,
                  nodata=-1, compress="deflate", predictor=2)
    with rasterio.open(tmp, "w", **profil) as dst:
        dst.write(out)
        dst.descriptions = tuple(bandes)
    os.replace(tmp, chemin)          # image complète ou rien
    return round(ok.mean() * 100, 1), shape


def sauver_index(index, chemin):
    tmp = chemin + ".tmp"
    index.to_csv(tmp, index=False)
    os.replace(tmp, chemin)


def construire(cfg, annees, limite=None):
    clean = cfg["chemins"]["clean"]
    dossier = os.path.join(clean, "s2")
    chemin_index = os.path.join(clean, "s2_index.csv")
    chemin_dates = os.path.join(cfg["chemins"]["raw"], "sentinel2_dates_utiles.csv")
    if not os.path.exists(chemin_dates):
        raise FileNotFoundError(f"Fichier introuvable : {chemin_dates}. "
                                "Lancer d'abord analyse_catalogue.")
    os.makedirs(dossier, exist_ok=True)

    dates = pd.read_csv(chemin_dates, parse_dates=["date"])
    dates = dates[dates["date"].dt.year.isin(annees)]
    if limite:
        dates = dates.head(limite)
    index = pd.read_csv(chemin_index) if os.path.exists(chemin_index) else pd.DataFrame()
    deja = set(index["id"]) if len(index) else set()

    a_faire = [r for _, r in dates.iterrows()
               if not (r["id"] in deja and os.path.exists(
                   os.path.join(dossier, f"S2_{r['date'].date().isoformat()}.tif")))]
    log.info("Années %s : %d dates utilisables, %d à traiter",
             list(annees), len(dates), len(a_faire))

    catalog = ouvrir_catalogue(cfg)
    echecs = 0
    for r in a_faire:
        t0 = time.time()
        date = r["date"].date().isoformat()
        chemin = os.path.join(dossier, f"S2_{date}.tif")
        try:
            item = next(catalog.search(collections=[cfg["sentinel2"]["collection"]],
                                       ids=[r["id"]]).items())
            valide, shape = ecrire_image(item, cfg, chemin)
            ligne = {"date": date, "tuile": r["tuile"], "id": r["id"],
                     "fichier": chemin.replace("\\", "/"), "valide_pct": valide,
                     "hauteur": shape[0], "largeur": shape[1]}
            index = index[index["id"] != r["id"]] if len(index) else index
            index = pd.concat([index, pd.DataFrame([ligne])], ignore_index=True)
            sauver_index(index, chemin_index)
            log.info("%s | %s | valide %.1f %% | %d s | %.1f Mo", date, r["tuile"],
                     valide, time.time() - t0, os.path.getsize(chemin) / 1e6)
        except Exception as e:
            echecs += 1
            log.warning("Échec %s : %s", date, e)

    log.info("Index : %d images -> %s (%d échecs)", len(index), chemin_index, echecs)
    if echecs:
        raise RuntimeError(f"{echecs} images en échec : relancer, le script reprend")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Images Sentinel-2 nettoyées")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--annee", type=int, help="une seule année (sinon la config)")
    parser.add_argument("--limite", type=int, help="nombre maximum d'images (test)")
    args = parser.parse_args(argv)
    try:
        cfg = charger_config(args.config)
        annees = [args.annee] if args.annee else cfg["images_nettoyees"]["annees"]
        construire(cfg, annees, args.limite)
        return 0
    except Exception:
        log.exception("Échec de la construction des images nettoyées")
        return 1


if __name__ == "__main__":
    sys.exit(main())