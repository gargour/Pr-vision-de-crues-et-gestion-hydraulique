import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

df = pd.read_csv("data/raw/hubeau_H0203020_QmnJ.csv")

print("Colonnes :", df.columns.tolist())
print()
print(df.dtypes)
print()
print("Exemple d'une ligne :")
print(df.iloc[0])
print()
print("Lignes par station :")
print(df["code_station"].value_counts())
print()
print("Période :", df["date_obs_elab"].min(), "->", df["date_obs_elab"].max())
print()
print("Nombre de lignes par date :")
print(df.groupby("date_obs_elab").size().value_counts())
print()
print("Valeurs manquantes par colonne :")
print(df.isna().sum())