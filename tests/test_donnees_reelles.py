import os

import pandas as pd
import pytest

from src.common import charger_config
from src.validation.donnees import (coherence_inter_modalites,
                                    valider_dates_images, valider_debit)

CFG = charger_config()
CODE = CFG["station"]["code_site"]
DEBIT = os.path.join(CFG["chemins"]["clean"], f"hubeau_{CODE}_daily.csv")
DATES = os.path.join(CFG["chemins"]["raw"], "sentinel2_dates_utiles.csv")

absent = pytest.mark.skipif(not (os.path.exists(DEBIT) and os.path.exists(DATES)),
                            reason="données absentes : lancer le pipeline")


def lire_debit():
    return pd.read_csv(DEBIT, parse_dates=["date"]).set_index("date")


@absent
def test_debit_reel():
    n = CFG["nettoyage"]
    assert valider_debit(lire_debit(), n["max_manquants_pct"]) == []


@absent
def test_dates_images_reelles():
    df = pd.read_csv(DATES, parse_dates=["date"])
    assert valider_dates_images(df) == []


@absent
def test_coherence_reelle():
    dates = pd.read_csv(DATES, parse_dates=["date"])["date"]
    assert coherence_inter_modalites(lire_debit(), dates) == []