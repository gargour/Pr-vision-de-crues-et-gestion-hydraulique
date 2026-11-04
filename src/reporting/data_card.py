import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

from src.common import charger_config, get_logger

log = get_logger("data_card")


def ecart_jours(dates_images, jours):
    img = np.sort(pd.to_datetime(dates_images).values.astype("datetime64[D]"))
    return np.array([np.abs(img - d).min().astype(int)
                     for d in pd.to_datetime(jours).values.astype("datetime64[D]")])


def lire(chemin, **kw):
    if not os.path.exists(chemin):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}. "
                                "Lancer d'abord les étapes précédentes.")
    return pd.read_csv(chemin, **kw)


def calculer(cfg):
    code = cfg["station"]["code_site"]
    raw, clean = cfg["chemins"]["raw"], cfg["chemins"]["clean"]
    c = cfg["crues"]

    debit = lire(os.path.join(clean, f"hubeau_{code}_daily.csv"), parse_dates=["date"])
    s2 = lire(os.path.join(raw, "sentinel2_catalogue.csv"), parse_dates=["date"])
    utiles = lire(os.path.join(raw, "sentinel2_dates_utiles.csv"), parse_dates=["date"])
    s1 = lire(os.path.join(raw, "sentinel1_catalogue.csv"), parse_dates=["date"])
    index = lire(os.path.join(clean, "s2_index.csv"))

    crues = debit[debit["debit_m3s"] > c["seuil_m3s"]]
    cov = {}
    for nom, dates in [("optique", utiles["date"]), ("radar", s1["date"])]:
        e = ecart_jours(dates, crues["date"])
        cov[nom] = {"jours_couverts": int((e <= c["fenetre_jours"]).sum()),
                    "ecart_median_jours": float(np.median(e))}

    taille_mo = sum(os.path.getsize(f) for f in index["fichier"]
                    if os.path.exists(f)) / 1e6
    return {
        "debit": {
            "jours": int(len(debit)),
            "debut": str(debit["date"].min().date()),
            "fin": str(debit["date"].max().date()),
            "moyenne_m3s": round(float(debit["debit_m3s"].mean()), 2),
            "min_m3s": round(float(debit["debit_m3s"].min()), 2),
            "max_m3s": round(float(debit["debit_m3s"].max()), 2),
            "manquants_pct": round(float(debit["debit_m3s"].isna().mean() * 100), 2),
            "douteux": int(debit["qualite_douteuse"].sum()),
        },
        "sentinel2": {
            "images_cataloguees": int(len(s2)),
            "dates_utilisables": int(len(utiles)),
            "images_nettoyees": int(len(index)),
            "taille_images_nettoyees_mo": round(taille_mo),
        },
        "sentinel1": {"scenes": int(len(s1))},
        "crues": {"seuil_m3s": c["seuil_m3s"], "fenetre_jours": c["fenetre_jours"],
                  "jours_de_crue": int(len(crues)), **{f"couverture_{k}": v
                                                      for k, v in cov.items()}},
    }


def ecrire_fiche(cfg, s):
    d, s2, s1, cr = s["debit"], s["sentinel2"], s["sentinel1"], s["crues"]
    u, n = cfg["utilisable"], cfg["nettoyage"]
    im = cfg["images_nettoyees"]
    lic = cfg["data_card"]["licences"]
    biais = "\n".join(f"- {b}" for b in cfg["data_card"]["biais"])
    nj = cr["jours_de_crue"]
    opt, rad = cr["couverture_optique"], cr["couverture_radar"]
    return f"""# Fiche de données (data card)

Générée automatiquement par `python -m src.reporting.data_card`.

## Sources et licences

| Donnée | Source | Licence |
|---|---|---|
| Débit moyen journalier, station {cfg['station']['code_station']} | Hub'Eau (API v2) | {lic['hubeau']} |
| Images optiques | Sentinel-2 L2A (Planetary Computer, STAC) | {lic['sentinel']} |
| Images radar | Sentinel-1 GRD (Planetary Computer, STAC) | {lic['sentinel']} |

Zone d'étude (ouest, sud, est, nord) : {cfg['zone']['bbox']}.

## Volumes

- **Débit** : {d['jours']} jours ({d['debut']} au {d['fin']}), moyenne {d['moyenne_m3s']} m3/s, minimum {d['min_m3s']}, maximum {d['max_m3s']}.
- **Sentinel-2** : {s2['images_cataloguees']} images cataloguées, {s2['dates_utilisables']} dates utilisables, {s2['images_nettoyees']} images nettoyées ({s2['taille_images_nettoyees_mo']} Mo).
- **Sentinel-1** : {s1['scenes']} scènes cataloguées (images non téléchargées).

## Prétraitements

- **Débit** : une ligne par date, conversion de l/s en m3/s, calendrier complet, interpolation des trous de {n['interpolation_max_jours']} jours au plus, valeurs de qualité douteuse marquées (colonne `qualite_douteuse`) et conservées. Manquants restants : {d['manquants_pct']} % ; valeurs douteuses : {d['douteux']}.
- **Images Sentinel-2 utilisables** : zone couverte à au moins {u['couverture_min_pct']} %, nuages sous {u['nuages_max_pct']} %, ombres sous {u['ombres_max_pct']} %, neige sous {u['neige_max_pct']} % (mesurés sur la zone d'étude).
- **Images nettoyées** : bandes {', '.join(im['bandes'])}, pixels de nuages, d'ombres, de neige et hors scène mis à « pas de donnée », réflectance codée en entiers (x 10 000). Années traitées : {im['annees']}.

## Disponibilité des images pendant les crues

Sur {nj} jours de crue (débit supérieur à {cr['seuil_m3s']} m3/s), nombre de jours avec une image à moins de {cr['fenetre_jours']} jours :

| Source | Jours couverts | Part | Écart médian |
|---|---|---|---|
| Sentinel-2 utilisable | {opt['jours_couverts']} / {nj} | {opt['jours_couverts'] / nj * 100:.0f} % | {opt['ecart_median_jours']:.0f} jours |
| Sentinel-1 | {rad['jours_couverts']} / {nj} | {rad['jours_couverts'] / nj * 100:.0f} % | {rad['ecart_median_jours']:.0f} jours |

## Biais et limites connus

{biais}
"""


def generer(cfg):
    stats = calculer(cfg)
    dossier = cfg["chemins"]["reports"]
    os.makedirs(dossier, exist_ok=True)
    chemin_json = os.path.join(dossier, "stats.json")
    chemin_md = os.path.join(dossier, "data_card.md")
    with open(chemin_json, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    with open(chemin_md, "w", encoding="utf-8") as f:
        f.write(ecrire_fiche(cfg, stats))
    log.info("Statistiques : %s | fiche : %s", chemin_json, chemin_md)
    log.info("Débit : %d jours | Sentinel-2 : %d images, %d utilisables | "
             "Sentinel-1 : %d scènes", stats["debit"]["jours"],
             stats["sentinel2"]["images_cataloguees"],
             stats["sentinel2"]["dates_utilisables"], stats["sentinel1"]["scenes"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Data card et statistiques")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)
    try:
        generer(charger_config(args.config))
        return 0
    except Exception:
        log.exception("Échec de la génération de la fiche de données")
        return 1


if __name__ == "__main__":
    sys.exit(main())