import logging
import os
import sys

import yaml


def charger_config(chemin="config.yaml"):
    """Lit le fichier de configuration."""
    with open(chemin, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_logger(nom, dossier_logs="logs"):
    """Journal affiché dans le terminal ET écrit dans logs/pipeline.log."""
    os.makedirs(dossier_logs, exist_ok=True)
    logger = logging.getLogger(nom)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    fichier = logging.FileHandler(os.path.join(dossier_logs, "pipeline.log"),
                                  encoding="utf-8")
    fichier.setFormatter(fmt)
    logger.addHandler(console)
    logger.addHandler(fichier)
    return logger