import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")          # pas de fenêtre : enregistre seulement
import matplotlib.pyplot as plt
import pandas as pd

from src.common import charger_config, get_logger

log = get_logger("plot_hubeau")


def tracer(cfg):
    code = cfg["station"]["code_site"]
    entree = os.path.join(cfg["chemins"]["clean"], f"hubeau_{code}_daily.csv")
    sortie = os.path.join(cfg["chemins"]["clean"], "serie_debit.png")

    if not os.path.exists(entree):
        raise FileNotFoundError(f"Fichier introuvable : {entree}. "
                                "Lancer d'abord le nettoyage Hub'Eau.")
    df = pd.read_csv(entree, parse_dates=["date"]).set_index("date")
    douteux = df[df["qualite_douteuse"]]

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(df.index, df["debit_m3s"], lw=0.8, label="Débit journalier")
    ax.scatter(douteux.index, douteux["debit_m3s"], s=8, color="red",
               label="Qualité douteuse / non qualifiée")
    ax.set_ylabel("Débit (m3/s)")
    ax.set_title(f"Station {cfg['station']['code_station']} : débit moyen journalier")
    ax.legend()
    fig.tight_layout()
    fig.savefig(sortie, dpi=150)
    plt.close(fig)
    log.info("Graphique écrit : %s (%d jours, %d douteux)", sortie, len(df), len(douteux))
    return sortie


def main(argv=None):
    parser = argparse.ArgumentParser(description="Graphique de la série de débit")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)
    try:
        tracer(charger_config(args.config))
        return 0
    except Exception:
        log.exception("Échec du graphique")
        return 1


if __name__ == "__main__":
    sys.exit(main())