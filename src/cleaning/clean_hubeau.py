import argparse
import os
import sys

import numpy as np
import pandas as pd

from src.common import charger_config, get_logger

log = get_logger("clean_hubeau")


def nettoyer(cfg):
    code = cfg["station"]["code_site"]
    grandeur = cfg["hubeau"]["grandeur"]
    n = cfg["nettoyage"]
    entree = os.path.join(cfg["chemins"]["raw"], f"hubeau_{code}_{grandeur}.csv")
    sortie = os.path.join(cfg["chemins"]["clean"], f"hubeau_{code}_daily.csv")

    if not os.path.exists(entree):
        raise FileNotFoundError(f"Fichier brut introuvable : {entree}. "
                                "Lancer d'abord l'importation Hub'Eau.")
    df = pd.read_csv(entree)
    log.info("Lignes brutes : %d", len(df))

    # 1. Une ligne par date (on garde celle qui a un code_station)
    nb_val = df.groupby("date_obs_elab")["resultat_obs_elab"].nunique()
    if (nb_val > 1).any():
        log.warning("%d dates avec 2 valeurs différentes (on garde la ligne station)",
                    int((nb_val > 1).sum()))
    df = df.sort_values(["date_obs_elab", "code_station"], na_position="last")
    df = df.drop_duplicates(subset="date_obs_elab", keep="first")
    log.info("Lignes après dédoublonnage : %d", len(df))

    # 2. Dates
    df["date"] = pd.to_datetime(df["date_obs_elab"])
    df = df.set_index("date").sort_index()

    # 3. Unités : l/s -> m3/s
    df["debit_m3s"] = df["resultat_obs_elab"] / 1000

    # 4. Valeurs impossibles -> manquant
    neg = df["debit_m3s"] < 0
    if neg.any():
        log.warning("%d débits négatifs mis à manquant", int(neg.sum()))
    df.loc[neg, "debit_m3s"] = np.nan

    # 5. Calendrier complet (un jour = une ligne)
    full = pd.date_range(df.index.min(), df.index.max(), freq="D")
    df = df.reindex(full)
    df.index.name = "date"
    df["est_manquant"] = df["debit_m3s"].isna()
    log.info("Jours manquants : %d", int(df["est_manquant"].sum()))

    # 6. Petits trous : interpolation. Les grands trous restent vides.
    df["debit_m3s"] = df["debit_m3s"].interpolate(
        limit=n["interpolation_max_jours"], limit_area="inside")
    df["est_interpole"] = df["est_manquant"] & df["debit_m3s"].notna()
    log.info("Jours interpolés : %d", int(df["est_interpole"].sum()))

    # 7. Qualité douteuse : on garde les valeurs, on les marque
    df["qualite_douteuse"] = df["libelle_qualification"].isin(
        ["Douteuse", "Non qualifiée"])
    log.info("Valeurs douteuses marquées : %d", int(df["qualite_douteuse"].sum()))

    out = df[["debit_m3s", "libelle_qualification", "libelle_statut",
              "qualite_douteuse", "est_manquant", "est_interpole"]]

    # 8. Contrôles automatiques : si un contrôle échoue, l'étape échoue
    erreurs = []
    if out.index.has_duplicates:
        erreurs.append("dates en double")
    if (out["debit_m3s"] < 0).any():
        erreurs.append("débits négatifs")
    if out["debit_m3s"].notna().sum() == 0:
        erreurs.append("aucune valeur de débit")
    restants = out["debit_m3s"].isna().mean() * 100
    if restants > n["max_manquants_pct"]:
        erreurs.append(f"{restants:.1f} % de jours sans valeur "
                       f"(max autorisé {n['max_manquants_pct']} %)")
    if erreurs:
        raise ValueError("Contrôles qualité échoués : " + " ; ".join(erreurs))
    log.info("Contrôles qualité : OK")

    os.makedirs(cfg["chemins"]["clean"], exist_ok=True)
    tmp = sortie + ".tmp"
    out.to_csv(tmp)
    os.replace(tmp, sortie)
    log.info("Fichier écrit : %s (%d lignes, %s -> %s)", sortie, len(out),
             out.index.min().date(), out.index.max().date())
    return sortie


def main(argv=None):
    parser = argparse.ArgumentParser(description="Nettoyage de la série de débit")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)
    try:
        nettoyer(charger_config(args.config))
        return 0
    except Exception:
        log.exception("Échec du nettoyage Hub'Eau")
        return 1


if __name__ == "__main__":
    sys.exit(main())