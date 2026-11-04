from src.monitoring.derive import PTS, REL, comparer


def profil_ref():
    p = {"jours": 4000, "debut": "2015-01-01", "colonnes": ["a", "b"]}
    for k in REL + PTS:
        p[k] = 10.0
    return p


def contient(alertes, mot):
    return any(mot in a for a in alertes)


def test_pas_de_derive():
    ref = profil_ref()
    alertes, _ = comparer(ref, dict(ref), 25, 5)
    assert alertes == []


def test_derive_moyenne():
    ref, cur = profil_ref(), profil_ref()
    cur["debit_moyenne"] = 20.0
    alertes, _ = comparer(ref, cur, 25, 5)
    assert contient(alertes, "debit_moyenne")


def test_petite_variation_toleree():
    ref, cur = profil_ref(), profil_ref()
    cur["debit_moyenne"] = 11.0          # +10 %, sous le seuil de 25 %
    alertes, _ = comparer(ref, cur, 25, 5)
    assert alertes == []


def test_perte_de_donnees():
    ref, cur = profil_ref(), profil_ref()
    cur["jours"] = 3000
    alertes, _ = comparer(ref, cur, 25, 5)
    assert contient(alertes, "perte de données")


def test_derive_manquants():
    ref, cur = profil_ref(), profil_ref()
    cur["manquants_pct"] = 30.0
    alertes, _ = comparer(ref, cur, 25, 5)
    assert contient(alertes, "manquants_pct")


def test_colonnes_modifiees():
    ref, cur = profil_ref(), profil_ref()
    cur["colonnes"] = ["a"]
    alertes, _ = comparer(ref, cur, 25, 5)
    assert contient(alertes, "colonnes")