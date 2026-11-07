import argparse
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd
import planetary_computer
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
from scipy import ndimage

from src.common import charger_config, get_logger

warnings.filterwarnings("ignore")
log = get_logger("build_s1_dataset")

SEUIL_LINEAIRE = 1e-3   # en dessous : pas de donnée (bord de scène), pas de l'eau
NODATA = -32768


def vers_db_int16(lineaire):
    """Valeurs linéaires -> dB x 100 (entiers). Valeur invalide -> NODATA."""
    lin = np.asarray(lineaire, dtype="float32")
    ok = np.isfinite(lin) & (lin >= SEUIL_LINEAIRE)
    out = np.full(lin.shape, NODATA, dtype="int16")
    out[ok] = np.clip(np.round(10 * np.log10(lin[ok]) * 100), -4000, 1500).astype("int16")
    return out


def meilleure_par_date(lignes, couverture_min):
    """Une seule scène par date : la mieux couverte, si elle atteint le minimum."""
    df = pd.DataFrame(lignes)
    if df.empty:
        return df
    df = df[df["couverture_pct"] >= couverture_min]
    return (df.sort_values(["date", "couverture_pct"], ascending=[True, False])
              .drop_duplicates("date").reset_index(drop=True))


def lire_bande(href, bbox, shape, resampling=Resampling.average):
    """Lit la zone d'une bande, directement à la taille voulue."""
    with rasterio.open(href) as src:
        bounds = transform_bounds("EPSG:4326", src.crs, *bbox)
        win = from_bounds(*bounds, transform=src.transform)
        a = src.read(1, window=win, out_shape=shape, boundless=True,
                     fill_value=0, resampling=resampling).astype("float32")
        tr = src.window_transform(win) * Affine.scale(win.width / shape[1],
                                                       win.height / shape[0])
        return a, src.crs, tr


def couverture_rapide(href, bbox):
    """Part de la zone couverte par la scène (lecture très basse résolution)."""
    a, _, _ = lire_bande(href, bbox, (48, 32), Resampling.nearest)
    return round(float((a >= SEUIL_LINEAIRE).mean() * 100), 1)


def ecrire_image(item, cfg, chemin):
    r = cfg["radar_nettoye"]
    bbox = cfg["zone"]["bbox"]
    shape = tuple(r["taille_sortie"])

    bandes, crs, tr = [], None, None
    for nom in ("vv", "vh"):
        a, crs_, tr_ = lire_bande(item.assets[nom].href, bbox, shape)
        if crs is None:
            crs, tr = crs_, tr_
        bandes.append(a)

    valide = (bandes[0] >= SEUIL_LINEAIRE) & (bandes[1] >= SEUIL_LINEAIRE)
    if r["marge_bord_pixels"] > 0:
        valide = ndimage.binary_erosion(valide, iterations=r["marge_bord_pixels"],
                                        border_value=1)
    out = np.stack([vers_db_int16(np.where(valide, b, np.nan)) for b in bandes])

    tmp = chemin + ".tmp"
    profil = dict(driver="GTiff", height=shape[0], width=shape[1], count=2,
                  dtype="int16", crs=crs, transform=tr, nodata=NODATA,
                  compress="deflate", predictor=2)
    with rasterio.open(tmp, "w", **profil) as dst:
        dst.write(out)
        dst.descriptions = ("VV_dB_x100", "VH_dB_x100")
    os.replace(tmp, chemin)          # image complète ou rien
    return round(float(valide.mean() * 100), 1)


def scenes_annee(catalog, cfg, annee):
    r = cfg["radar_nettoye"]
    lon, lat = cfg["station"]["longitude"], cfg["station"]["latitude"]
    items = list(catalog.search(collections=[r["collection"]], bbox=cfg["zone"]["bbox"],
                                datetime=f"{annee}-01-01/{annee}-12-31").items())
    items = [i for i in items
             if i.bbox[0] <= lon <= i.bbox[2] and i.bbox[1] <= lat <= i.bbox[3]]
    if r["orbites"]:
        items = [i for i in items if i.properties.get("sat:relative_orbit") in r["orbites"]]
    return items


def sauver_index(index, chemin):
    tmp = chemin + ".tmp"
    index.to_csv(tmp, index=False)
    os.replace(tmp, chemin)


def construire(cfg, annees, limite=None):
    r = cfg["radar_nettoye"]
    bbox = cfg["zone"]["bbox"]
    clean = cfg["chemins"]["clean"]
    dossier = os.path.join(clean, "s1")
    chemin_index = os.path.join(clean, "s1_index.csv")
    os.makedirs(dossier, exist_ok=True)

    index = pd.read_csv(chemin_index) if os.path.exists(chemin_index) else pd.DataFrame()
    faites = set(index["date"]) if len(index) else set()
    catalog = Client.open(r["stac_url"], modifier=planetary_computer.sign_inplace)
    echecs, traitees = 0, 0

    for annee in annees:
        items = scenes_annee(catalog, cfg, annee)
        items = [i for i in items if i.datetime.date().isoformat() not in faites]
        lignes, par_id = [], {}
        for it in items:
            try:
                cov = couverture_rapide(it.assets["vv"].href, bbox)
            except Exception as e:
                echecs += 1
                log.warning("couverture %s : %s", it.id, e)
                continue
            par_id[it.id] = it
            lignes.append({"date": it.datetime.date().isoformat(), "id": it.id,
                           "orbite": it.properties.get("sat:relative_orbit"),
                           "couverture_pct": cov})
        choix = meilleure_par_date(lignes, r["couverture_min_pct"])
        log.info("%d : %d scènes à examiner, %d dates retenues (couverture >= %s %%)",
                 annee, len(items), len(choix), r["couverture_min_pct"])

        for _, ligne in choix.iterrows():
            if limite and traitees >= limite:
                break
            t0 = time.time()
            chemin = os.path.join(dossier, f"S1_{ligne['date']}.tif")
            try:
                valide = ecrire_image(par_id[ligne["id"]], cfg, chemin)
                nouvelle = {"date": ligne["date"], "id": ligne["id"],
                            "orbite": ligne["orbite"], "fichier": chemin.replace("\\", "/"),
                            "valide_pct": valide,
                            "hauteur": r["taille_sortie"][0], "largeur": r["taille_sortie"][1]}
                index = pd.concat([index, pd.DataFrame([nouvelle])], ignore_index=True)
                sauver_index(index, chemin_index)
                faites.add(ligne["date"])
                traitees += 1
                log.info("%s | orbite %s | valide %.1f %% | %d s | %.2f Mo", ligne["date"],
                         ligne["orbite"], valide, time.time() - t0,
                         os.path.getsize(chemin) / 1e6)
            except Exception as e:
                echecs += 1
                log.warning("Échec %s : %s", ligne["date"], e)

    log.info("Index radar : %d images -> %s (%d échecs)", len(index), chemin_index, echecs)
    if echecs:
        raise RuntimeError(f"{echecs} échec(s) : relancer, le script reprend")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Images radar Sentinel-1 nettoyées")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--annee", type=int, help="une seule année (sinon la config)")
    parser.add_argument("--limite", type=int, help="nombre maximum d'images (test)")
    args = parser.parse_args(argv)
    try:
        cfg = charger_config(args.config)
        annees = [args.annee] if args.annee else cfg["radar_nettoye"]["annees"]
        construire(cfg, annees, args.limite)
        return 0
    except Exception:
        log.exception("Échec de la construction des images radar")
        return 1


if __name__ == "__main__":
    sys.exit(main())