import numpy as np
import pandas as pd

from src.validation.donnees import (coherence_inter_modalites,
                                    valider_dates_images, valider_debit,
                                    verifier_decoupage)


def debit_valide(n=30):
    idx = pd.date_range("2018-01-01", periods=n, freq="D", name="date")
    return pd.DataFrame({
        "debit_m3s": np.linspace(1, 5, n),
        "libelle_qualification": "Bonne",
        "libelle_statut": "Donnée pré-validée",
        "qualite_douteuse": False,
        "est_manquant": False,
        "est_interpole": False,
    }, index=idx)


def images_valides():
    return pd.DataFrame({
        "date": pd.to_datetime(["2018-01-05", "2018-01-12", "2018-01-20"]),
        "tuile": "T31UEP",
        "id": ["a", "b", "c"],
        "couverture_pct": [100.0, 90.0, 80.0],
        "nuages_pct": [0.0, 5.0, 10.0],
    })


def contient(erreurs, mot):
    return any(mot in e for e in erreurs)


# ---- Débit ----
def test_debit_valide():
    assert valider_debit(debit_valide()) == []


def test_debit_doublons():
    df = debit_valide()
    df = pd.concat([df, df.iloc[[0]]]).sort_index()
    assert contient(valider_debit(df), "double")


def test_debit_negatif():
    df = debit_valide()
    df.iloc[3, df.columns.get_loc("debit_m3s")] = -1.0
    assert contient(valider_debit(df), "négatifs")


def test_debit_aberrant():
    df = debit_valide()
    df.iloc[3, df.columns.get_loc("debit_m3s")] = 9999.0
    assert contient(valider_debit(df), "aberrant")


def test_debit_trop_de_manquants():
    df = debit_valide()
    df.iloc[:10, df.columns.get_loc("debit_m3s")] = np.nan
    assert contient(valider_debit(df), "sans valeur")


def test_debit_calendrier_incomplet():
    df = debit_valide().drop(debit_valide().index[10])
    assert contient(valider_debit(df), "calendrier")


def test_debit_colonne_manquante():
    df = debit_valide().drop(columns=["qualite_douteuse"])
    assert contient(valider_debit(df), "colonnes manquantes")


# ---- Images ----
def test_images_valides():
    assert valider_dates_images(images_valides()) == []


def test_images_date_en_double():
    df = images_valides()
    df.loc[1, "date"] = df.loc[0, "date"]
    assert contient(valider_dates_images(df), "même date")


def test_images_pourcentage_invalide():
    df = images_valides()
    df.loc[0, "nuages_pct"] = 140.0
    assert contient(valider_dates_images(df), "hors de 0-100")


# ---- Cohérence inter-modalités ----
def test_coherence_ok():
    assert coherence_inter_modalites(debit_valide(), images_valides()["date"]) == []


def test_coherence_image_hors_periode():
    dates = pd.to_datetime(["2018-01-05", "2019-06-01"])
    assert contient(coherence_inter_modalites(debit_valide(), dates), "hors de la période")


def test_coherence_image_sans_valeur_de_debit():
    df = debit_valide()
    df.loc["2018-01-05", "debit_m3s"] = np.nan
    dates = pd.to_datetime(["2018-01-05"])
    assert contient(coherence_inter_modalites(df, dates), "sans valeur")


# ---- Découpage train / validation / test ----
def test_decoupage_ok():
    train = pd.date_range("2018-01-01", "2018-01-20")
    val = pd.date_range("2018-01-21", "2018-01-25")
    test = pd.date_range("2018-01-26", "2018-01-30")
    assert verifier_decoupage(train, val, test) == []


def test_decoupage_fuite():
    train = pd.date_range("2018-01-01", "2018-01-22")
    val = pd.date_range("2018-01-21", "2018-01-25")
    test = pd.date_range("2018-01-26", "2018-01-30")
    assert contient(verifier_decoupage(train, val, test), "fuite")


def test_decoupage_ordre_inverse():
    train = pd.date_range("2018-01-10", "2018-01-20")
    val = pd.date_range("2018-01-01", "2018-01-05")
    test = pd.date_range("2018-01-26", "2018-01-30")
    assert contient(verifier_decoupage(train, val, test), "précéder")


def test_decoupage_ensemble_vide():
    test = pd.date_range("2018-01-26", "2018-01-30")
    assert contient(verifier_decoupage([], [], test), "vide")