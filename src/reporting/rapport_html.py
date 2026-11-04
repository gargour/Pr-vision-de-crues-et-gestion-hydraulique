import argparse
import base64
import html
import json
import os
import sys

from src.common import charger_config, get_logger

log = get_logger("rapport_html")

CSS = """
body{font-family:Arial,Helvetica,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}
h1{color:#1f3864}h2{color:#2f5496;border-bottom:2px solid #d9e2f3;padding-bottom:.2rem;margin-top:2rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0}
th,td{border:1px solid #bbb;padding:.4rem .6rem;text-align:left}th{background:#d9e2f3}
.ok{background:#e2efda;color:#375623;padding:.2rem .6rem;border-radius:4px;font-weight:bold}
.ko{background:#f8d7da;color:#842029;padding:.2rem .6rem;border-radius:4px;font-weight:bold}
.barre{background:#eee;border-radius:4px;height:1.1rem;width:100%}
.barre div{background:#2f5496;height:100%;border-radius:4px}
img{max-width:100%;border:1px solid #ccc}
small{color:#555}
"""


def lire_json(chemin):
    if not os.path.exists(chemin):
        raise FileNotFoundError(f"Fichier introuvable : {chemin}. "
                                "Lancer d'abord les étapes précédentes.")
    with open(chemin, encoding="utf-8") as f:
        return json.load(f)


def image_html(chemin, legende):
    if not os.path.exists(chemin):
        return f"<p><small>Image absente : {html.escape(chemin)}</small></p>"
    with open(chemin, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return (f'<figure><img src="data:image/png;base64,{b64}" alt="{html.escape(legende)}">'
            f"<figcaption><small>{html.escape(legende)}</small></figcaption></figure>")


def tableau(entetes, lignes):
    th = "".join(f"<th>{html.escape(str(e))}</th>" for e in entetes)
    tr = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in l) + "</tr>"
                 for l in lignes)
    return f"<table><tr>{th}</tr>{tr}</table>"


def barre(pct):
    return f'<div class="barre"><div style="width:{pct:.0f}%"></div></div>'


def generer(cfg):
    rep, clean = cfg["chemins"]["reports"], cfg["chemins"]["clean"]
    val = lire_json(os.path.join(rep, "validation.json"))
    st = lire_json(os.path.join(rep, "stats.json"))
    d, s2, s1, cr = st["debit"], st["sentinel2"], st["sentinel1"], st["crues"]
    nj = cr["jours_de_crue"]
    opt, rad = cr["couverture_optique"], cr["couverture_radar"]
    po, pr = opt["jours_couverts"] / nj * 100, rad["jours_couverts"] / nj * 100
    ok = val["erreurs_validation"] == 0
    statut = ('<span class="ok">Validation : OK</span>' if ok else
              f'<span class="ko">Validation : {val["erreurs_validation"]} erreur(s)</span>')
    biais = "".join(f"<li>{html.escape(b)}</li>" for b in cfg["data_card"]["biais"])

    page = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Rapport de qualité des données</title><style>{CSS}</style></head><body>
<h1>Rapport de qualité des données</h1>
<p>Station {html.escape(cfg['station']['code_station'])} · généré automatiquement par
<code>python -m src.reporting.rapport_html</code> · {statut}</p>

<h2>Série de débit (Hub'Eau)</h2>
{tableau(["Mesure", "Valeur"], [
    ["Période", f"{d['debut']} au {d['fin']}"],
    ["Jours", d["jours"]],
    ["Débit moyen / min / max (m³/s)", f"{d['moyenne_m3s']} / {d['min_m3s']} / {d['max_m3s']}"],
    ["Jours sans valeur", f"{d['manquants_pct']} %"],
    ["Valeurs de qualité douteuse (marquées)", d["douteux"]]])}
{image_html(os.path.join(clean, "serie_debit.png"), "Débit moyen journalier ; points rouges = qualité douteuse")}

<h2>Images satellite</h2>
{tableau(["Mesure", "Valeur"], [
    ["Sentinel-2 : images cataloguées", s2["images_cataloguees"]],
    ["Sentinel-2 : dates utilisables", s2["dates_utilisables"]],
    ["Sentinel-2 : images nettoyées", f"{s2['images_nettoyees']} ({s2['taille_images_nettoyees_mo']} Mo)"],
    ["Sentinel-1 : scènes cataloguées", s1["scenes"]]])}
{image_html(os.path.join(clean, "s2_controle.png"), "Contrôle des images : pixels masqués en magenta, NDVI en dessous")}

<h2>Disponibilité des images pendant les crues</h2>
<p>{nj} jours de crue (débit supérieur à {cr['seuil_m3s']} m³/s). Une image est « proche » si elle est à
moins de {cr['fenetre_jours']} jours.</p>
<p>Optique (Sentinel-2) : {opt['jours_couverts']} / {nj} ({po:.0f} %), écart médian {opt['ecart_median_jours']:.0f} jours{barre(po)}</p>
<p>Radar (Sentinel-1) : {rad['jours_couverts']} / {nj} ({pr:.0f} %), écart médian {rad['ecart_median_jours']:.0f} jours{barre(pr)}</p>

<h2>Biais et limites connus</h2>
<ul>{biais}</ul>
</body></html>"""

    sortie = os.path.join(rep, "rapport_qualite.html")
    tmp = sortie + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(page)
    os.replace(tmp, sortie)
    log.info("Rapport écrit : %s (%.0f Ko)", sortie, os.path.getsize(sortie) / 1e3)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rapport de qualité HTML")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args(argv)
    try:
        generer(charger_config(args.config))
        return 0
    except Exception:
        log.exception("Échec de la génération du rapport HTML")
        return 1


if __name__ == "__main__":
    sys.exit(main())