# Prévision de crues (Projet 3)

Projet Deep Learning : prévoir le niveau d'eau d'une rivière en combinant une série temporelle (débit) et des images satellite.

Ce dépôt contient la **tâche 2 : importation et nettoyage des données**, écrite pour être intégrée dans un pipeline DataOps dont l'objectif principal est l'automatisation :

- une seule configuration (`config.yaml`),
- un point d'entrée unique (`python -m src.pipeline`),
- un journal (`logs/pipeline.log`),
- des contrôles qualité qui font échouer l'étape en cas de problème,
- un code de sortie (0 = succès, 1 = échec) que peut lire un orchestrateur.

## Données

| Type | Source | Période | Où |
|---|---|---|---|
| Série temporelle : débit moyen journalier, station H020302002 | Hub'Eau (API v2) | 2015-01-01 à aujourd'hui | `data/raw/`, `data/clean/` |
| Images optiques | Sentinel-2 L2A (Planetary Computer, STAC) | catalogue 2016 à 2026, images nettoyées pour 2018 | `data/raw/`, `data/clean/s2/` |
| Images radar | Sentinel-1 GRD (Planetary Computer, STAC) | catalogue 2015 à 2026 | `data/raw/` |

Les images Sentinel-2 ne sont pas toutes téléchargées : on construit d'abord un **catalogue** (date, nuages, ombres, neige, calculés sur la zone d'étude), puis on ne nettoie que les dates utilisables.

## Installation

```bash
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
```

## Exécution

Toutes les commandes se lancent depuis la racine du projet, avec `-m`.

```bash
python -m src.pipeline                              # tout le pipeline (8 étapes)
python -m src.pipeline --liste                      # afficher les étapes
python -m src.pipeline --seulement hubeau           # une seule étape
python -m src.pipeline --de analyse_catalogue       # à partir d'une étape
python -m src.pipeline --config autre_config.yaml   # autre fichier de configuration
```

Chaque étape peut aussi être lancée seule, avec ses propres options :

```bash
python -m src.sources.hubeau --debut 2020-01-01
python -m src.sources.sentinel2_catalog --annee 2024
python -m src.cleaning.build_s2_dataset --annee 2019 --limite 2
```

### Les 8 étapes

| # | Étape | Module | Rôle | Fichier produit |
|---|---|---|---|---|
| 1 | `hubeau` | `src.sources.hubeau` | Télécharge le débit journalier | `data/raw/hubeau_<station>_QmnJ.csv` |
| 2 | `clean_hubeau` | `src.cleaning.clean_hubeau` | Doublons, unités (m³/s), calendrier complet, qualité | `data/clean/hubeau_<station>_daily.csv` |
| 3 | `plot_hubeau` | `src.cleaning.plot_hubeau` | Graphique de la série | `data/clean/serie_debit.png` |
| 4 | `sentinel2_catalog` | `src.sources.sentinel2_catalog` | Catalogue Sentinel-2 (nuages sur la zone) | `data/raw/sentinel2_catalogue.csv` |
| 5 | `analyse_catalogue` | `src.cleaning.analyse_catalogue` | Dates utilisables, lien avec les crues | `data/raw/sentinel2_dates_utiles.csv` |
| 6 | `sentinel1_catalog` | `src.sources.sentinel1_catalog` | Catalogue radar, comparaison avec les crues | `data/raw/sentinel1_catalogue.csv` |
| 7 | `build_s2_dataset` | `src.cleaning.build_s2_dataset` | Images nettoyées (4 bandes, nuages et ombres masqués) | `data/clean/s2/S2_<date>.tif`, `data/clean/s2_index.csv` |
| 8 | `check_s2_dataset` | `src.cleaning.check_s2_dataset` | Contrôle automatique des images | `data/clean/s2_controle.png` |

L'ordre compte : chaque étape lit les fichiers de la précédente. Le pipeline s'arrête à la première étape en échec.

### Codes de sortie

| Code | Signification |
|---|---|
| 0 | Succès |
| 1 | Au moins une étape a échoué (détail dans le journal) |
| 2 | Nom d'étape inconnu |

## Configuration

Tous les paramètres sont dans `config.yaml` : station, zone d'étude (`bbox`), période, critères d'une image utilisable (nuages, ombres, neige, couverture), seuil de crue, années à nettoyer, seuils des contrôles. Pour changer de station, de zone ou d'année, il n'y a pas de code à modifier.

## Contrôles qualité

Une étape échoue (code 1) si :

- **Débit** : dates en double, débit négatif, aucune valeur, ou trop de jours sans valeur (`nettoyage.max_manquants_pct`).
- **Images** : fichier manquant, mauvais nombre de bandes, trop peu de pixels valides, réflectance incohérente (échelle fausse), écart entre l'index et le fichier.

Les valeurs de débit de qualité douteuse (« Douteuse », « Non qualifiée ») ne sont **pas supprimées** : elles sont marquées dans la colonne `qualite_douteuse`.

## Reprise et relance

Les étapes sont **idempotentes** et **incrémentales** : relancer ne crée ni doublons ni travail inutile.

- Les catalogues n'ajoutent que les nouvelles scènes.
- `build_s2_dataset` ne retraite que les images manquantes.
- Les fichiers sont écrits en entier ou pas du tout (fichier temporaire puis remplacement).

Exception : l'étape `hubeau` retélécharge tout l'historique à chaque lancement (environ 10 secondes).

## Structure

```
config.yaml           paramètres du pipeline
requirements.txt      dépendances (versions figées)
src/
  common.py           lecture de la configuration, journal
  pipeline.py         point d'entrée : enchaîne les 8 étapes
  sources/            importation (hubeau, sentinel2, sentinel2_catalog, sentinel1_catalog)
  cleaning/           nettoyage et contrôles (clean_hubeau, plot_hubeau, analyse_catalogue,
                      build_s2_dataset, check_s2_dataset)
data/
  raw/                données brutes et catalogues
  clean/              série de débit propre, images Sentinel-2 nettoyées, index
logs/                 journal (pipeline.log)
experiments/          essais hors pipeline (détection d'eau par radar), non maintenus
```

`src/cleaning/inspect_hubeau.py` et `src/cleaning/diag_reflectance.py` sont des outils d'inspection à lancer à la main. Ils ne font pas partie du pipeline.

## Résultats principaux

- **Débit** : 8 642 lignes brutes ramenées à 4 321 (l'API renvoie deux lignes par date), du 2015-01-01 au 2026-10-30, aucun jour manquant, 426 valeurs douteuses marquées.
- **Sentinel-2** : 1 900 images cataloguées, 400 dates utilisables, écart médian de 5 jours entre deux images, plus long trou de 90 jours.
- **Pendant les crues** (débit supérieur à 10 m³/s, 213 jours) : une image optique utilisable à moins de 3 jours pour 28 % des jours, contre 97 % avec le radar Sentinel-1.
- **Images nettoyées** : 42 images (40 pour 2018, 2 pour 2019), 776 Mo, pixels valides de 49,8 % à 100 % (médiane 99,2 %).
- **Exécution complète** : environ 5 minutes quand tout est déjà à jour.

## Limites connues

- Une seule station et une seule zone d'étude.
- Les images nettoyées ne couvrent que 2018 (plus 2 images de test en 2019). Les 360 autres dates utilisables représentent environ 7 à 9 heures de calcul et 7 Go, estimation faite à partir de 2 images (67 à 86 secondes chacune).
- La zone d'étude est à cheval sur deux tuiles Sentinel-2 : on garde une seule tuile par date, donc certaines images ne couvrent qu'environ la moitié de la zone. La fusion des tuiles n'est pas faite.
- Les 213 jours de crue sont des jours, pas des événements : une même crue compte plusieurs fois. Le seuil de 10 m³/s est propre à cette station.
- Le chiffre du radar repose sur les dates de passage du catalogue, pas sur des images vérifiées une par une. Les images radar ne sont pas téléchargées.
- Aucune image optique utilisable avant le 20 février 2018 : la grande crue de janvier 2018 n'a pas d'image optique.
- Pas de planification, de reprise automatique ni d'alertes : cela relève de l'orchestrateur.