import os

import numpy as np
import pandas as pd

from src.common import charger_config

cfg = charger_config()
code = cfg["station"]["code_site"]
source = os.path.join(cfg["chemins"]["clean"], f"hubeau_{code}_daily.csv")
sortie = os.path.join(cfg["chemins"]["clean"], "debit_derive.csv")

df = pd.read_csv(source)
df["debit_m3s"] = df["debit_m3s"] * 1.5
df.loc[df.index[:600], "debit_m3s"] = np.nan
df.to_csv(sortie, index=False)
print("Fichier avec dérive écrit :", sortie)