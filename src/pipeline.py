import argparse
import importlib
import sys
import time

from src.common import get_logger

log = get_logger("pipeline")

# Ordre d'exécution : chaque étape utilise les fichiers de la précédente
ETAPES = [
    ("hubeau",            "src.sources.hubeau"),
    ("clean_hubeau",      "src.cleaning.clean_hubeau"),
    ("plot_hubeau",       "src.cleaning.plot_hubeau"),
    ("sentinel2_catalog", "src.sources.sentinel2_catalog"),
    ("analyse_catalogue", "src.cleaning.analyse_catalogue"),
    ("validation",        "src.validation.valider"),
    ("sentinel1_catalog", "src.sources.sentinel1_catalog"),
    ("build_s2_dataset",  "src.cleaning.build_s2_dataset"),
    ("check_s2_dataset",  "src.cleaning.check_s2_dataset"),
    ("check_s2_dataset",  "src.cleaning.check_s2_dataset"),
    ("data_card",         "src.reporting.data_card"),
    ("data_card",         "src.reporting.data_card"),
    ("rapport_html",      "src.reporting.rapport_html"),
    ("rapport_html",      "src.reporting.rapport_html"),
    ("derive",            "src.monitoring.derive"),

]




def choisir(de=None, seulement=None):
    noms = [n for n, _ in ETAPES]
    for n in (de, seulement):
        if n and n not in noms:
            raise ValueError(f"Étape inconnue : {n}. Étapes : {', '.join(noms)}")
    if seulement:
        return [e for e in ETAPES if e[0] == seulement]
    if de:
        return ETAPES[noms.index(de):]
    return ETAPES


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pipeline d'importation et de nettoyage")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--de", help="commencer à cette étape")
    parser.add_argument("--seulement", help="lancer une seule étape")
    parser.add_argument("--liste", action="store_true", help="afficher les étapes")
    args = parser.parse_args(argv)

    if args.liste:
        for i, (nom, module) in enumerate(ETAPES, 1):
            print(f"{i}. {nom}  ({module})")
        return 0

    try:
        etapes = choisir(args.de, args.seulement)
    except ValueError as e:
        log.error(str(e))
        return 2

    log.info("=== Début du pipeline : %d étape(s) ===", len(etapes))
    debut = time.time()
    resultats = []
    for nom, module in etapes:
        log.info("--- Étape : %s ---", nom)
        t0 = time.time()
        code = importlib.import_module(module).main(["--config", args.config])
        duree = time.time() - t0
        resultats.append((nom, code, duree))
        if code != 0:
            log.error("Étape %s en échec (code %d) : pipeline arrêté", nom, code)
            break

    log.info("=== Résumé ===")
    for nom, code, duree in resultats:
        log.info("%-20s %-8s %6.0f s", nom, "OK" if code == 0 else "ÉCHEC", duree)
    ok = all(c == 0 for _, c, _ in resultats) and len(resultats) == len(etapes)
    log.info("Pipeline %s en %.0f s", "terminé avec succès" if ok else "ARRÊTÉ",
             time.time() - debut)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())


