import planetary_computer
from pystac_client import Client


def ouvrir_catalogue(cfg):
    """Connexion au catalogue STAC (liens signés automatiquement)."""
    return Client.open(cfg["sentinel2"]["stac_url"],
                       modifier=planetary_computer.sign_inplace)


def search_scenes(cfg, date_debut, date_fin, max_nuages=None):
    """Scènes Sentinel-2 L2A de la zone d'étude entre deux dates."""
    s2 = cfg["sentinel2"]
    max_nuages = max_nuages if max_nuages is not None else s2["max_nuages_tuile"]
    search = ouvrir_catalogue(cfg).search(
        collections=[s2["collection"]],
        bbox=cfg["zone"]["bbox"],
        datetime=f"{date_debut}/{date_fin}",
        query={"eo:cloud_cover": {"lt": max_nuages}},
    )
    return list(search.items())