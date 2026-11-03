import numpy as np
import pandas as pd
import rasterio

idx = pd.read_csv("data/clean/s2_index.csv")
lignes = []
for _, r in idx.iterrows():
    with rasterio.open(r["fichier"]) as src:
        a = src.read().astype("float32")
        nodata = src.nodata
    ok = a[0] != nodata
    refl = a[:, ok] / 10000                    # (4 bandes, pixels valides)
    tous = refl.ravel()
    lignes.append({
        "date": r["date"],
        "max": round(float(tous.max()), 2),
        "p99.9": round(float(np.percentile(tous, 99.9)), 2),
        "pct_>1": round(float((tous > 1).mean() * 100), 4),
        "med_B02": round(float(np.median(refl[0])), 3),
        "med_B04": round(float(np.median(refl[2])), 3),
        "med_B08": round(float(np.median(refl[3])), 3),
    })

df = pd.DataFrame(lignes)
pd.set_option("display.width", 200)
print(df.to_string(index=False))
print()
print("Max par image : min", df["max"].min(), "| médiane", df["max"].median(),
      "| max", df["max"].max())
print("p99.9 le plus haut :", df["p99.9"].max())
print("Part de pixels > 1 la plus haute :", df["pct_>1"].max(), "%")