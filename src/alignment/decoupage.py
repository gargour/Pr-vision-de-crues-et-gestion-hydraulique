import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

from src.common import charger_config, get_logger
from src.validation.donnees import verifier_decoupage

log = get_logger("decoupage")


def affecter_ensembles(index, train_fin, val_fin):
    """Découpage chronologique : train jusqu'à train_fin, val jusqu'à val_fin, test après."""
    idx = pd.DatetimeIndex(index)
    return pd.Series(np.where(idx <= pd.Timestamp(train_fin), "train",
                              np.where(idx <= pd.Timestamp(val_fin), "val", "test")),
                     index=idx)


def decouper(cfg):
    clean = cfg["chemins"]["clean"]
    chemin = os.path.join(clean, "aligned.csv")
    if not os.path.exists(chemin):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}. "
                                "Lancer d'abord l'étape alignement.")
    d = cfg["decoupage"]
    df = pd.read_csv(chemin, parse_dates=["date"]).set_index("date")
    ens = affecter_ensembles(df.index, d["train_fin"], d["val_fin"])

    erreurs = verifier_decoupage(ens[ens == "train"].index, ens[ens == "val"].index,
                                 ens[ens == "test"].index)
    crue = df["debit_m3s"] > cfg["crues"]["seuil_m3s"]
    stats = {}
    for nom in ("train", "val", "test"):
        m = ens == nom
        n_crue = int((m & crue).sum())
        if n_crue < d["min_jours_crue"]:
            erreurs.append(f"{nom} : {n_crue} jour(s) de crue (minimum {d['min_jours_crue']})")
        s = {"debut": str(df.index[m].min().date()), "fin": str(df.index[m].max().date()),
             "jours": int(m.sum()), "jours_crue": n_crue}
        for src in ("optique", "radar"):
            s[f"{src}_dispo_crue_pct"] = (
                round(float(df.loc[m & crue, f"{src}_disponible"].mean() * 100), 1)
                if n_crue else 0.0)
        stats[nom] = s
        log.info("%-5s : %s -> %s | %d jours | %d jours de crue | image à portée pendant "
                 "les crues : optique %.0f %%, radar %.0f %%", nom, s["debut"], s["fin"],
                 s["jours"], n_crue, s["optique_dispo_crue_pct"], s["radar_dispo_crue_pct"])

    os.makedirs(cfg["chemins"]["reports"], exist_ok=True)
    with open(os.path.join(cfg["chemins"]["reports"], "split.json"), "w",
              encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    if erreurs:
        for e in erreurs:
            log.error(e)
        raise ValueError(f"{len(erreurs)} erreur(s) de découpage")

    sortie = os.path.join(clean, "split.csv")
    tmp = sortie + ".tmp"
    ens.rename("ensemble").rename_axis("date").to_csv(tmp)
    os.replace(tmp, sortie)
    log.info("Découpage : OK, aucune fuite -> %s", sortie)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Découpage train / validation / test")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)
    try:
        decouper(charger_config(args.config))
        return 0
    except Exception:
        log.exception("Échec du découpage")
        return 1


if __name__ == "__main__":
    sys.exit(main())