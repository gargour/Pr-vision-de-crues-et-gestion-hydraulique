import pandas as pd

from src.alignment.aligner import derniere_image
from src.alignment.decoupage import affecter_ensembles
from src.validation.donnees import verifier_decoupage


def test_derniere_image_jamais_dans_le_futur():
    jours = pd.date_range("2018-01-01", "2018-01-10")
    images = pd.to_datetime(["2018-01-03", "2018-01-08"])
    al = derniere_image(jours, images, "optique")
    col = al["date_optique"]
    assert col.isna().sum() == 2                       # 1er et 2 janvier : pas d'image avant
    assert (col.dropna() <= al.index.to_series()[col.notna()]).all()
    assert al.loc["2018-01-07", "date_optique"] == pd.Timestamp("2018-01-03")
    assert al.loc["2018-01-08", "date_optique"] == pd.Timestamp("2018-01-08")


def test_derniere_image_une_ligne_par_jour():
    jours = pd.date_range("2018-01-01", "2018-01-10")
    al = derniere_image(jours, pd.to_datetime(["2018-01-05"]), "radar")
    assert len(al) == len(jours)


def test_decoupage_chronologique_sans_fuite():
    idx = pd.date_range("2018-01-01", "2018-12-31")
    ens = affecter_ensembles(idx, "2018-06-30", "2018-09-30")
    assert set(ens) == {"train", "val", "test"}
    erreurs = verifier_decoupage(ens[ens == "train"].index, ens[ens == "val"].index,
                                 ens[ens == "test"].index)
    assert erreurs == []
    assert ens["2018-06-30"] == "train" and ens["2018-07-01"] == "val"
    assert ens["2018-10-01"] == "test"