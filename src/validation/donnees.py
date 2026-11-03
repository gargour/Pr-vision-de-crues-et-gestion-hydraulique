import numpy as np
import pandas as pd

COLONNES_DEBIT = {"debit_m3s", "libelle_qualification", "libelle_statut",
                  "qualite_douteuse", "est_manquant", "est_interpole"}
COLONNES_DATES = {"date", "tuile", "id", "couverture_pct", "nuages_pct"}


def valider_debit(df, max_manquants_pct=5.0, debit_max_m3s=500.0):
    """Série de débit nettoyée (index = date). Retourne la liste des erreurs."""
    absentes = COLONNES_DEBIT - set(df.columns)
    if absentes:
        return [f"colonnes manquantes : {sorted(absentes)}"]
    if not isinstance(df.index, pd.DatetimeIndex):
        return ["l'index n'est pas une date"]
    if df.empty:
        return ["série vide"]

    erreurs = []
    if df.index.has_duplicates:
        erreurs.append("dates en double")
    if not df.index.is_monotonic_increasing:
        erreurs.append("dates non triées")
    attendus = len(pd.date_range(df.index.min(), df.index.max(), freq="D"))
    if attendus != df.index.nunique():
        erreurs.append(f"calendrier incomplet : {attendus - df.index.nunique()} jour(s) absent(s)")
    debit = df["debit_m3s"]
    if (debit < 0).any():
        erreurs.append("débits négatifs")
    if (debit > debit_max_m3s).any():
        erreurs.append(f"débit aberrant (> {debit_max_m3s} m3/s)")
    pct = debit.isna().mean() * 100
    if pct > max_manquants_pct:
        erreurs.append(f"{pct:.1f} % de jours sans valeur (max {max_manquants_pct} %)")
    return erreurs


def valider_dates_images(df):
    """Dates d'images utilisables : colonnes, unicité, pourcentages."""
    absentes = COLONNES_DATES - set(df.columns)
    if absentes:
        return [f"colonnes manquantes : {sorted(absentes)}"]
    if df.empty:
        return ["aucune date d'image"]

    erreurs = []
    if df["date"].isna().any():
        erreurs.append("dates manquantes")
    if df["date"].duplicated().any():
        erreurs.append("plusieurs images pour une même date")
    if df["id"].duplicated().any():
        erreurs.append("identifiants d'image en double")
    for col in ("couverture_pct", "nuages_pct"):
        if not df[col].between(0, 100).all():
            erreurs.append(f"{col} hors de 0-100")
    return erreurs


def coherence_inter_modalites(debit, dates_images):
    """Les dates d'images doivent tomber dans la période du débit, avec une valeur."""
    dates_images = pd.DatetimeIndex(dates_images)
    if len(dates_images) == 0:
        return ["aucune date d'image"]
    erreurs = []
    d0, d1 = debit.index.min(), debit.index.max()
    hors = dates_images[(dates_images < d0) | (dates_images > d1)]
    if len(hors):
        erreurs.append(f"{len(hors)} date(s) d'image hors de la période du débit "
                       f"({d0.date()} -> {d1.date()})")
    dans = dates_images.intersection(debit.index)
    sans_valeur = int(debit.loc[dans, "debit_m3s"].isna().sum())
    if sans_valeur:
        erreurs.append(f"{sans_valeur} date(s) d'image sans valeur de débit")
    return erreurs


def verifier_decoupage(train, val, test):
    """Découpage chronologique : pas de date commune, train < val < test."""
    ens = {"train": pd.DatetimeIndex(train), "val": pd.DatetimeIndex(val),
           "test": pd.DatetimeIndex(test)}
    vides = [nom for nom, e in ens.items() if len(e) == 0]
    if vides:
        return [f"ensemble(s) vide(s) : {vides}"]
    erreurs = []
    for a, b in [("train", "val"), ("train", "test"), ("val", "test")]:
        commun = ens[a].intersection(ens[b])
        if len(commun):
            erreurs.append(f"{len(commun)} date(s) communes entre {a} et {b} (fuite)")
    if ens["train"].max() >= ens["val"].min():
        erreurs.append("train doit précéder val")
    if ens["val"].max() >= ens["test"].min():
        erreurs.append("val doit précéder test")
    return erreurs