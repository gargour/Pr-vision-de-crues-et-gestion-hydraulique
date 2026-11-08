# Prévision de crues (Projet 3)

Projet Deep Learning multimodal : prévoir le niveau d'eau d'une rivière en combinant une **série temporelle** (débit) et des **images satellite** (Sentinel-2 optique, Sentinel-1 radar).

Ce dépôt contient le pipeline de données (tâches 2 et 3, partie A) : importation, nettoyage, validation, versionnement des données, rapports et surveillance. Les étapes de fusion, d'entraînement et d'évaluation viendront se brancher sur ce pipeline.

## Principes DataOps appliqués

| Principe | Mise en œuvre |
|---|---|
| Automatisation | Une commande lance tout : `dvc repro` (ou `python -m src.pipeline`) |
| Modularité | Une étape = un module avec entrées et sorties explicites (`src/sources`, `src/cleaning`, `src/validation`, `src/reporting`, `src/monitoring`) |
| Configuration externalisée | `config.yaml` (station, zone, seuils, années, chemins) ; aucun chemin ni seuil codé en dur |
| Versionnement | Code avec Git, données et rapports volumineux avec DVC |
| Qualité continue | Étape `validation` et contrôles dans chaque étape : un contrôle critique qui échoue arrête le pipeline (code de sortie 1) |
| Observabilité | Journal `logs/pipeline.log`, statistiques (`reports/stats.json`), fiche de données (`reports/data_card.md`), rapport HTML |
| Intégration continue | GitHub Actions : installation, lint, tests, pipeline sur un échantillon |

## Données

| Type | Source | Où |
|---|---|---|
| Série temporelle : débit moyen journalier, station H020302002 | Hub'Eau (API v2) | `data/raw/`, `data/clean/` |
| Images optiques | Sentinel-2 L2A (Planetary Computer, STAC) | catalogue dans `data/raw/`, images nettoyées dans `data/clean/s2/` |
| Images radar | Sentinel-1 GRD (Planetary Computer, STAC) | catalogue dans `data/raw/` (images non téléchargées) |

Les chiffres (nombre de jours, d'images, couverture pendant les crues) changent à chaque mise à jour des sources. Les valeurs à jour sont dans `reports/data_card.md`, générée par le pipeline.

## Installation

```bash
git clone <url-du-depot>
cd flood-forecasting
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
```

## Récupérer les données

Les données sont versionnées avec DVC (elles ne sont pas dans Git). Le stockage est configuré dans `.dvc/config`.

```bash
dvc pull
```

**Limite actuelle** : le stockage DVC est un dossier local (`../flood-forecasting-dvc-storage`). Il n'est donc accessible que depuis la machine qui l'héberge. Pour qu'un tiers récupère les données, il faut remplacer ce stockage par un stockage partagé, par exemple :

```bash
dvc remote modify stockage url <url-du-stockage-partagé>
```

À défaut, un tiers peut reconstruire les données à partir des sources avec `dvc repro` (voir ci-dessous), à condition d'avoir accès à Internet. Les sources évoluent dans le temps, donc les chiffres obtenus peuvent différer légèrement de ceux enregistrés.

## Exécution

```bash
dvc repro                                    # tout le pipeline (seules les étapes impactées sont relancées)
dvc dag                                      # graphe des étapes
python -m src.pipeline                       # alternative sans DVC : toutes les étapes dans l'ordre
python -m src.pipeline --liste               # liste des étapes
python -m src.pipeline --seulement hubeau    # une seule étape
python -m src.pipeline --de analyse_catalogue
python -m src.pipeline --config configs/ci.yaml --seulement hubeau   # autre configuration
```

### Les 14 étapes

| # | Étape | Rôle | Sortie principale |
|---|---|---|---|
| 1 | `hubeau` | Télécharge le débit journalier | `data/raw/hubeau_*_QmnJ.csv` |
| 2 | `clean_hubeau` | Doublons, unités (m³/s), calendrier complet, qualité | `data/clean/hubeau_*_daily.csv` |
| 3 | `plot_hubeau` | Graphique de la série | `data/clean/serie_debit.png` |
| 4 | `sentinel2_catalog` | Catalogue Sentinel-2 (nuages calculés sur la zone) | `data/raw/sentinel2_catalogue.csv` |
| 5 | `analyse_catalogue` | Dates utilisables, lien avec les crues | `data/raw/sentinel2_dates_utiles.csv` |
| 6 | `validation` | Tests de qualité et de cohérence entre modalités | `reports/validation.json` |
| 7 | `sentinel1_catalog` | Catalogue radar, comparaison avec les crues | `data/raw/sentinel1_catalogue.csv` |
| 8 | `build_s2_dataset` | Images nettoyées (4 bandes, nuages et ombres masqués) | `data/clean/s2/*.tif`, `s2_index.csv` |
| 9 | `check_s2_dataset` | Contrôle automatique des images | `data/clean/s2_controle.png` |
| 10 | `alignment` | Appariement débit et dernière image disponible (masque, âge) | `data/clean/aligned.csv` |
| 11 | `decoupage` | Découpage chronologique sans fuite (train/val/test) | `data/clean/split.csv` |
| 12 | `data_card` | Statistiques et fiche de données | `reports/data_card.md`, `stats.json` |
| 13 | `rapport_html` | Rapport de qualité en une page | `reports/rapport_qualite.html` |
| 14 | `derive` | Détection de dérive par rapport à une référence | `reports/derive.json` |
Une étape qui échoue arrête le pipeline et renvoie le code de sortie 1.

## Tests

```bash
python -m pytest -v
```

33 tests : schéma et valeurs du débit, doublons, valeurs manquantes et aberrantes, dates d'images, cohérence entre modalités (les dates d'images tombent dans la période du débit, avec une valeur), découpage train / validation / test sans fuite, détection de dérive. Les tests sur les données réelles sont ignorés si les données sont absentes.

### Démonstration d'un échec contrôlé

```bash
python -m scripts.demo_echec
python -m src.validation.valider --debit data/clean/debit_corrompu.csv
```

Le fichier corrompu contient un doublon et un débit négatif : la validation affiche les erreurs et renvoie le code 1.

## Détection de dérive

`configs/reference_stats.json` contient le profil des données au moment où il a été figé. L'étape `derive` compare les données actuelles à ce profil (moyenne, écart-type et quantiles du débit, pourcentage de valeurs manquantes et douteuses, couverture des crues par les images).

```bash
python -m src.monitoring.derive            # avertissements, code 0
python -m src.monitoring.derive --strict   # une dérive fait échouer l'étape (code 1)
python -m src.monitoring.derive --figer    # enregistrer les données actuelles comme nouvelle référence
python -m scripts.demo_derive              # fabrique des données qui dérivent (démonstration)
```

La référence est figée à la main : après une mise à jour volontaire des données, il faut la refiger puis la commiter. Les seuils sont dans `config.yaml` (section `derive`). Ce sont des indicateurs résumés, pas un test statistique complet.

## Docker

```bash
docker build -t flood-forecasting .
docker run --rm flood-forecasting python -m pytest -q
docker run --rm -v "${PWD}/data_ci:/app/data_ci" -v "${PWD}/reports_ci:/app/reports_ci" flood-forecasting \
  sh -c 'for e in hubeau clean_hubeau plot_hubeau sentinel2_catalog analyse_catalogue validation sentinel1_catalog; do python -m src.pipeline --config configs/ci.yaml --seulement $e || exit 1; done'
```

L'image contient le code, la configuration et les dépendances figées, mais pas les données ni DVC. Elle exécute les tests et le pipeline sur l'échantillon (`configs/ci.yaml`). Le pipeline complet avec versionnement des données se lance avec `dvc repro` depuis le dépôt.

## Intégration continue et collecte planifiée

- `.github/workflows/ci.yml` : à chaque push, installation, lint (erreurs graves), tests, graphe DVC, puis pipeline sur l'échantillon 2024 (`configs/ci.yaml`).
- `.github/workflows/collecte.yml` : chaque lundi, collecte et validation sur l'échantillon, avec conservation des rapports et du journal. Les données ne sont pas conservées.

Hub'Eau et Planetary Computer sont interrogés depuis les serveurs de GitHub : si ces services bloquent leurs adresses, les étapes d'importation peuvent échouer dans la CI sans échouer en local.

## Structure

```
config.yaml           paramètres du pipeline
configs/              configuration de la CI (échantillon), profil de référence de la dérive
dvc.yaml, dvc.lock    définition et état du pipeline DVC
Dockerfile            image du pipeline
requirements.txt      dépendances (versions figées)
src/
  common.py           lecture de la configuration, journal
  pipeline.py         point d'entrée sans DVC : enchaîne les étapes
  sources/            importation (hubeau, sentinel2, sentinel2_catalog, sentinel1_catalog)
  cleaning/           nettoyage et contrôle (clean_hubeau, plot_hubeau, analyse_catalogue,
                      build_s2_dataset, check_s2_dataset)
  validation/         contrôles de qualité testés (donnees.py) et étape de validation (valider.py)
  reporting/          fiche de données et rapport HTML
  monitoring/         détection de dérive
tests/                tests unitaires et tests sur les données
scripts/              démonstrations (échec contrôlé, dérive)
data/                 données (suivies par DVC, ignorées par Git)
reports/              rapports générés
logs/                 journal (pipeline.log)
experiments/          essais hors pipeline, non maintenus
```

## Limites connues

- Une seule station et une seule zone d'étude.
- Les images Sentinel-2 nettoyées ne couvrent qu'une partie des années (voir `images_nettoyees.annees` dans `config.yaml`) ; nettoyer les autres représente plusieurs heures de calcul.
- La zone est à cheval sur deux tuiles Sentinel-2 : on en garde une par date, donc certaines images ne couvrent qu'environ la moitié de la zone.
- Les jours de crue sont des jours, pas des événements ; le seuil de crue est propre à cette station.
- Les images radar ne sont pas téléchargées (catalogue seulement).
- Le stockage DVC est local (voir plus haut).
- L'étape `hubeau` retélécharge tout l'historique à chaque lancement, et les sources changent dans le temps : un téléchargement neuf ne redonne pas exactement les mêmes chiffres que ceux enregistrés par DVC.
- Pas encore d'étapes d'alignement, de fusion, d'entraînement ni d'évaluation.

# Étapes à venir (réservées)

Ces dossiers sont vides : ils indiquent où se branchent les étapes suivantes du pipeline.

| Dossier | Étape prévue | Entrées | Sorties |
|---|---|---|---|
| `src/alignment/` | alignement (fait) et découpage (fait) | débit, catalogues d'images | `data/clean/aligned.csv`, `split.csv` |
| `src/fusion/` | extraction des représentations et module de fusion | table alignée, images, découpage | représentations mises en cache, modèle de fusion |
| `src/training/` | entraînement (baselines unimodales, fusion) | découpage, représentations | modèles, métriques suivies avec MLflow |
| `src/evaluation/` | évaluation et ablations | modèles, ensemble de test | métriques par ensemble, tableau d'ablation |

Le suivi des expériences se fait avec MLflow (`src/tracking/`).