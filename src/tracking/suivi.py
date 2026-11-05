import argparse
import json
import os
import subprocess
import sys

import mlflow

from src.common import charger_config, get_logger

log = get_logger("suivi")


def lire_json(chemin):
    if not os.path.exists(chemin):
        log.warning("Rapport absent : %s", chemin)
        return {}
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def aplatir(d, prefixe=""):
    """Dictionnaire imbriqué -> métriques numériques à plat."""
    res = {}
    for k, v in d.items():
        nom = f"{prefixe}_{k}" if prefixe else str(k)
        if isinstance(v, dict):
            res.update(aplatir(v, nom))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            res[nom] = float(v)
    return res


def commit_git():
    try:
        sortie = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True, check=True)
        return sortie.stdout.strip()
    except Exception:
        return "inconnu"


def suivre(cfg):
    s = cfg["suivi"]
    rep = cfg["chemins"]["reports"]
    mlflow.set_tracking_uri(s["tracking_uri"])
    mlflow.set_experiment(s["experience"])

    stats = lire_json(os.path.join(rep, "stats.json"))
    split = lire_json(os.path.join(rep, "split.json"))
    valid = lire_json(os.path.join(rep, "validation.json"))
    derive = lire_json(os.path.join(rep, "derive.json"))

    metriques = {}
    metriques.update(aplatir(stats, "stats"))
    metriques.update(aplatir(split, "split"))
    metriques.update(aplatir(valid, "validation"))
    if derive:
        metriques["derive_detectee"] = 1.0 if derive.get("derive") else 0.0
        metriques["derive_nb_alertes"] = float(len(derive.get("alertes", [])))

    params = {
        "seuil_crue_m3s": cfg["crues"]["seuil_m3s"],
        "fenetre_crue_jours": cfg["crues"]["fenetre_jours"],
        "fenetre_alignement_jours": cfg["alignement"]["fenetre_jours"],
        "train_fin": cfg["decoupage"]["train_fin"],
        "val_fin": cfg["decoupage"]["val_fin"],
        "annees_images_nettoyees": str(cfg["images_nettoyees"]["annees"]),
        "station": cfg["station"]["code_station"],
    }

    with mlflow.start_run(run_name="donnees"):
        mlflow.set_tag("git_commit", commit_git())
        mlflow.log_params(params)
        mlflow.log_metrics(metriques)
        for f in [os.path.join(rep, "data_card.md"),
                  os.path.join(rep, "rapport_qualite.html"),
                  "config.yaml", "dvc.lock"]:
            if os.path.exists(f):
                mlflow.log_artifact(f)
        run_id = mlflow.active_run().info.run_id
    log.info("Exécution enregistrée : %s (%d paramètres, %d métriques) dans %s",
             run_id[:8], len(params), len(metriques), s["tracking_uri"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Suivi MLflow de la version des données")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)
    try:
        suivre(charger_config(args.config))
        return 0
    except Exception:
        log.exception("Échec du suivi MLflow")
        return 1


if __name__ == "__main__":
    sys.exit(main())