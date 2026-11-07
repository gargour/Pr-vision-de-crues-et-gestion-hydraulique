import numpy as np

from src.cleaning.build_s1_dataset import NODATA, meilleure_par_date, vers_db_int16


def test_conversion_db():
    lin = np.array([[1.0, 0.1, 0.01]])
    assert vers_db_int16(lin).tolist() == [[0, -1000, -2000]]


def test_valeurs_invalides_en_nodata():
    lin = np.array([[np.nan, 0.0, 1e-5, -5.0]])
    assert (vers_db_int16(lin) == NODATA).all()


def test_une_scene_par_date():
    lignes = [{"date": "2018-01-01", "id": "a", "couverture_pct": 60.0},
              {"date": "2018-01-01", "id": "b", "couverture_pct": 90.0},
              {"date": "2018-01-02", "id": "c", "couverture_pct": 30.0}]
    res = meilleure_par_date(lignes, 50)
    assert res["id"].tolist() == ["b"]


def test_aucune_scene():
    assert meilleure_par_date([], 50).empty