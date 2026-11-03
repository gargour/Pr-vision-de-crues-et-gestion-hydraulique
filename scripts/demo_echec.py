import os

import pandas as pd

from src.common import charger_config

cfg = charger_config()
code = cfg["station"]["code_site"]
source = os.path.join(cfg["chemins"]["clean"], f"hubeau_{code}_daily.csv")
sortie = os.path.join(cfg["chemins"]["clean"], "debit_corrompu.csv")

df = pd.read_csv(source)
df = pd.concat([df, df.iloc[[100]]])          # une date en double
df.loc[200, "debit_m3s"] = -5.0               # un débit négatif
df.to_csv(sortie, index=False)
print("Fichier corrompu écrit :", sortie)