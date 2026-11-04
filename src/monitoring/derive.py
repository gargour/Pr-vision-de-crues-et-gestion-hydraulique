import argparse
import datetime
import json
import os
import sys

import pandas as pd

from src.common import charger_config, get_logger

log = get_logger("derive")

REL = ["debit_moyenne", "debit_ecart_type", "debit_q05", "debit_q25",
       "debit_q50", "debit_q75", "debit_q95", "debit_q99"]
PTS = ["manquants_pct", "douteux_pct",
       "couverture_crues_optique_pct", "couverture_crues_radar_pct"]
QUANTILES = {"q05": 0.05, "q25": 0.25, "q50": 0.5, "q75": 0.75, "q95": 0.95, "q99": 0.99}


def profil(cfg, chemin_debit=None):
    """Profil statistique des données actuelles."""
    code = cfg["station"]["code_site"]
    chemin_debit = chemin_debit or os.path.join(
        cfg["chemins"]["clean"], f"hubeau_{code}_daily.csv")
    chemin_stats = os.path.join(cfg["chemins"]["reports"], "stats.json")
    for f in (chemin_debit, chemin_stats):
        if not os.path.exists(f):
            raise FileNotFoundError(f"Fichier introuvable : {f}. "
                                    "Lancer d'abord les étapes précédentes.")
    debit = pd.read_csv(chemin_debit, parse_dates=["date"])
    with open(chemin_stats, encoding="utf-8") as f:
        st = json.load(f)

    q = debit["debit_m3s"].dropna()
    p = {
        "jours": int(len(debit)),
        "debut": str(debit["date"].min().date()),
        "fin": str(debit["date"].max().date()),
        "colonnes": sorted(debit.columns),
        "debit_moyenne": round(float(q.mean()), 3),
        "debit_ecart_type": round(float(q.std()), 3),
    }
    for nom, niveau in QUANTILES.items():
        p[f"debit_{nom}"] = round(float(q.quantile(niveau)), 3)
    p["manquants_pct"] = round(float(debit["debit_m3s"].isna().mean() * 100), 2)
    p["douteux_pct"] = round(float(debit["qualite_douteuse"].mean() * 100), 2)
    cr = st["crues"]
    nj = cr["jours_de_crue"]
    for k in ("optique", "radar"):
        p[f"couverture_crues_{k}_pct"] = (
            round(cr[f"couverture_{k}"]["jours_couverts"] / nj * 100, 1) if nj else 0.0)
    return p


def comparer(ref, cur, seuil_rel_pct, seuil_pts):
    """Compare deux profils. Retourne (alertes, variations)."""
    alertes, var = [], {}
    if ref["colonnes"] != cur["colonnes"]:
        alertes.append(f"colonnes modifiées : {ref['colonnes']} -> {cur['colonnes']}")
    if cur["jours"] < ref["jours"]:
        alertes.append(f"perte de données : {cur['jours']} jours au lieu de {ref['jours']}")
    if cur["debut"] != ref["debut"]:
        alertes.append(f"début de la série modifié : {ref['debut']} -> {cur['debut']}")
    for k in REL:
        r, c = ref[k], cur[k]
        if r == 0:
            continue
        v = (c - r) / abs(r) * 100
        var[k] = round(v, 1)
        if abs(v) > seuil_rel_pct:
            alertes.append(f"{k} : {r} -> {c} ({v:+.0f} %)")
    for k in PTS:
        v = cur[k] - ref[k]
        var[k] = round(v, 1)
        if abs(v) > seuil_pts:
            alertes.append(f"{k} : {ref[k]} -> {cur[k]} ({v:+.1f} points)")
    return alertes, var


def executer(cfg, chemin_debit=None, figer=False, strict=False):
    d = cfg["derive"]
    cur = profil(cfg, chemin_debit)

    if figer:
        os.makedirs(os.path.dirname(d["reference"]), exist_ok=True)
        ref = {"figee_le": datetime.date.today().isoformat(), **cur}
        with open(d["reference"], "w", encoding="utf-8") as f:
            json.dump(ref, f, indent=2, ensure_ascii=False)
        log.info("Référence figée : %s (%d jours, %s -> %s)",
                 d["reference"], cur["jours"], cur["debut"], cur["fin"])
        return

    if not os.path.exists(d["reference"]):
        raise FileNotFoundError(f"Référence introuvable : {d['reference']}. "
                                "La créer avec : python -m src.monitoring.derive --figer")
    with open(d["reference"], encoding="utf-8") as f:
        ref = json.load(f)

    alertes, var = comparer(ref, cur, d["seuil_relatif_pct"], d["seuil_points"])
    rapport = {"reference_figee_le": ref.get("figee_le"), "derive": bool(alertes),
               "alertes": alertes, "variations": var,
               "profil_reference": {k: ref[k] for k in ("jours", "fin")},
               "profil_actuel": {k: cur[k] for k in ("jours", "fin")}}
    os.makedirs(cfg["chemins"]["reports"], exist_ok=True)
    nom = "derive_test.json" if chemin_debit else "derive.json"
    sortie = os.path.join(cfg["chemins"]["reports"], nom)
    with open(sortie, "w", encoding="utf-8") as f:
        json.dump(rapport, f, indent=2, ensure_ascii=False)

    log.info("Référence figée le %s (%d jours) | données actuelles : %d jours",
             ref.get("figee_le"), ref["jours"], cur["jours"])
    if alertes:
        for a in alertes:
            log.warning("DÉRIVE : %s", a)
    else:
        log.info("Aucune dérive détectée")
    log.info("Rapport écrit : %s", sortie)
    if alertes and (strict or d["echec_si_derive"]):
        raise ValueError(f"{len(alertes)} alerte(s) de dérive")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Détection de dérive des données")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--figer", action="store_true",
                        help="enregistrer les données actuelles comme référence")
    parser.add_argument("--strict", action="store_true",
                        help="une dérive fait échouer l'étape (code 1)")
    parser.add_argument("--debit", help="fichier de débit à comparer (test)")
    args = parser.parse_args(argv)
    try:
        executer(charger_config(args.config), args.debit, args.figer, args.strict)
        return 0
    except Exception:
        log.exception("Échec de la détection de dérive")
        return 1


if __name__ == "__main__":
    sys.exit(main())