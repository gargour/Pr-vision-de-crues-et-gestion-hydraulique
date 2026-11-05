import argparse
import os
import sys

import pandas as pd

from src.common import charger_config, get_logger

log = get_logger("alignement")


def derniere_image(jours, dates_images, nom):
    """Pour chaque jour : dernière image disponible le jour même ou avant.
    Jamais une image du futur (sinon fuite d'information vers le passé)."""
    img = pd.DataFrame({f"date_{nom}": sorted(pd.to_datetime(dates_images).unique())})
    img["_cle"] = img[f"date_{nom}"]
    j = pd.DataFrame({"date": pd.to_datetime(jours)}).sort_values("date")
    m = pd.merge_asof(j, img, left_on="date", right_on="_cle", direction="backward")
    return m.drop(columns="_cle").set_index("date")


def aligner(cfg):
    code = cfg["station"]["code_site"]
    fen = cfg["alignement"]["fenetre_jours"]
    seuil = cfg["crues"]["seuil_m3s"]
    clean, raw = cfg["chemins"]["clean"], cfg["chemins"]["raw"]
    entrees = {
        "debit": os.path.join(clean, f"hubeau_{code}_daily.csv"),
        "optique": os.path.join(raw, "sentinel2_dates_utiles.csv"),
        "radar": os.path.join(raw, "sentinel1_catalogue.csv"),
    }
    for f in entrees.values():
        if not os.path.exists(f):
            raise FileNotFoundError(f"Fichier introuvable : {f}. "
                                    "Lancer d'abord les étapes précédentes.")

    debit = pd.read_csv(entrees["debit"], parse_dates=["date"]).set_index("date")
    out = debit[["debit_m3s", "qualite_douteuse"]].copy()
    sources = {"optique": pd.read_csv(entrees["optique"], parse_dates=["date"])["date"],
               "radar": pd.read_csv(entrees["radar"], parse_dates=["date"])["date"]}

    for nom, dates in sources.items():
        al = derniere_image(out.index, dates, nom).reindex(out.index)
        col = f"date_{nom}"
        out[col] = al[col]
        out[f"age_{nom}_jours"] = (out.index.to_series() - out[col]).dt.days
        out[f"{nom}_disponible"] = out[f"age_{nom}_jours"] <= fen

    # Contrôles : jamais d'image du futur, une ligne par jour
    for nom in sources:
        if (out[f"date_{nom}"] > out.index.to_series()).any():
            raise ValueError(f"image du futur utilisée pour {nom}")
    if out.index.has_duplicates or len(out) != len(debit):
        raise ValueError("l'alignement a modifié le nombre de jours")

    sortie = os.path.join(clean, "aligned.csv")
    tmp = sortie + ".tmp"
    out.to_csv(tmp)
    os.replace(tmp, sortie)

    crue = out["debit_m3s"] > seuil
    log.info("Table alignée : %d jours -> %s", len(out), sortie)
    for nom in sources:
        dispo = out[f"{nom}_disponible"]
        log.info("%-8s disponible (image à %d jours au plus) : %.0f %% de tous les jours, "
                 "%.0f %% des %d jours de crue", nom, fen, dispo.mean() * 100,
                 dispo[crue].mean() * 100, int(crue.sum()))
    return sortie


def main(argv=None):
    parser = argparse.ArgumentParser(description="Alignement débit / images")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)
    try:
        aligner(charger_config(args.config))
        return 0
    except Exception:
        log.exception("Échec de l'alignement")
        return 1


if __name__ == "__main__":
    sys.exit(main())