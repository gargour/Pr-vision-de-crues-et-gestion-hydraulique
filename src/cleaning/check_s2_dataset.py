import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")          # pas de fenêtre : enregistre seulement
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio

from src.common import charger_config, get_logger

log = get_logger("check_s2_dataset")


def lire(chemin):
    """Lit un fichier : réflectance 0 à 1, et masque des pixels invalides."""
    with rasterio.open(chemin) as src:
        a = src.read().astype("float32")
        nodata = src.nodata
        nb = src.count
    masque = a == nodata
    a[masque] = np.nan
    return a / 10000, masque[0], nb


def controler(cfg):
    c = cfg["controle_images"]
    n_bandes = len(cfg["images_nettoyees"]["bandes"])
    clean = cfg["chemins"]["clean"]
    chemin_index = os.path.join(clean, "s2_index.csv")
    if not os.path.exists(chemin_index):
        raise FileNotFoundError(f"Fichier introuvable : {chemin_index}. "
                                "Lancer d'abord build_s2_dataset.")
    idx = pd.read_csv(chemin_index)
    log.info("Index : %d images, du %s au %s", len(idx), idx["date"].min(), idx["date"].max())

    erreurs, lignes = [], []
    for _, r in idx.iterrows():
        f = r["fichier"]
        if not os.path.exists(f):
            erreurs.append(f"fichier manquant : {f}")
            continue
        a, masque, nb = lire(f)
        valide = round(float((~masque).mean() * 100), 1)
        v = a[~np.isnan(a)]
        mx = float(v.max()) if v.size else np.nan
        p999 = float(np.percentile(v, 99.9)) if v.size else np.nan
        sup1 = float((v > 1).mean() * 100) if v.size else np.nan
        lignes.append({"date": r["date"], "fichier": f, "valide_pct": valide,
                       "refl_max": mx, "p999": p999, "sup1_pct": sup1})
        if nb != n_bandes:
            erreurs.append(f"{r['date']} : {nb} bandes au lieu de {n_bandes}")
        if valide < c["valide_min_pct"]:
            erreurs.append(f"{r['date']} : {valide} % de pixels valides "
                           f"(minimum {c['valide_min_pct']} %)")
        if abs(valide - r["valide_pct"]) > c["ecart_index_max_pct"]:
            erreurs.append(f"{r['date']} : {valide} % dans le fichier, "
                           f"{r['valide_pct']} % dans l'index")
        if not np.isnan(p999) and p999 > c["reflectance_p999_max"]:
            erreurs.append(f"{r['date']} : réflectance p99.9 = {p999:.2f} (échelle fausse ?)")
        if not np.isnan(sup1) and sup1 > c["pixels_sup1_max_pct"]:
            erreurs.append(f"{r['date']} : {sup1:.4f} % de pixels au-dessus de 1")

    res = pd.DataFrame(lignes)
    if res.empty:
        raise ValueError("Aucune image lisible")
    log.info("Pixels valides : min %.1f %% | médiane %.1f %% | max %.1f %%",
             res["valide_pct"].min(), res["valide_pct"].median(), res["valide_pct"].max())
    log.info("Réflectance p99.9 la plus haute : %.3f | part max de pixels > 1 : %.4f %%",
             res["p999"].max(), res["sup1_pct"].max())
    taille = sum(os.path.getsize(f) for f in res["fichier"]) / 1e6
    log.info("Taille totale : %.0f Mo", taille)

    # Image de contrôle : mieux couverte, moins bien couverte, médiane
    tri = res.sort_values("valide_pct").reset_index(drop=True)
    choix = [tri.iloc[-1], tri.iloc[0], tri.iloc[len(tri) // 2]]
    fig, axes = plt.subplots(2, 3, figsize=(15, 11))
    for col, row in enumerate(choix):
        a, masque, _ = lire(row["fichier"])
        rgb = np.clip(np.stack([a[2], a[1], a[0]], axis=-1) / 0.3, 0, 1)
        rgb[masque] = [1, 0, 1]                      # pixels masqués en magenta
        axes[0, col].imshow(rgb)
        axes[0, col].set_title(f"{row['date']} | valide {row['valide_pct']} %")
        ndvi = (a[3] - a[2]) / (a[3] + a[2])
        axes[1, col].imshow(ndvi, cmap="RdYlGn", vmin=-0.2, vmax=0.9)
        axes[1, col].set_title("NDVI")
        log.info("%s | NDVI médian : %.2f", row["date"], np.nanmedian(ndvi))
    for ax in axes.ravel():
        ax.axis("off")
    fig.tight_layout()
    sortie = os.path.join(clean, "s2_controle.png")
    fig.savefig(sortie, dpi=110)
    plt.close(fig)
    log.info("Image de contrôle : %s", sortie)

    if erreurs:
        for e in erreurs:
            log.error(e)
        raise ValueError(f"{len(erreurs)} contrôle(s) échoué(s)")
    log.info("Contrôles qualité des images : OK")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Contrôle des images nettoyées")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)
    try:
        controler(charger_config(args.config))
        return 0
    except Exception:
        log.exception("Échec du contrôle des images")
        return 1


if __name__ == "__main__":
    sys.exit(main())