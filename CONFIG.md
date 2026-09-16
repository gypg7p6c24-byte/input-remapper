# CONFIG — input-remapper

> Suivi de configuration factuel. État actuel, au présent.

## Stack & versions
- Langage : Python
- Gestionnaire de paquets : pip
- Conteneurisation : non

## Dépendances clés
evdev · psutil · dasbus · pycairo · PyGObject · pydantic · packaging

## Variables d'environnement
Aucune requise.

## Réseau / ports
Aucun. L'application est locale ; elle dialogue par D-Bus.

## Commandes
- Installer les dépendances : `pip install -r requirements.txt`
- Tester : `pytest`
- Construire le paquet Debian : `./scripts/build-deb.sh`
- Construire le bundle Flatpak : manifeste `install/flatpak/io.github.sezanzeb.input_remapper.yml`

## Distribution
Deux canaux, publiés par les workflows du dépôt :

| Canal | Branche | Release roulante | Contenu |
|---|---|---|---|
| dev | `dev` | `dev-latest` | prérelease |
| stable | `main` | `stable-latest` | release |

L'asset porte le nom `input-remapper-<version>.flatpak` : c'est de ce nom que le mécanisme
de mise à jour intégré déduit la version disponible. Détail : `readme/flatpak.md`.

## Version applicative
Version courante : **1.0.0**.

Elle est inscrite en **six** endroits, à tenir alignés :

| Fichier | Qui le lit |
|---|---|
| `pyproject.toml` | la chaîne Flatpak, pour nommer l'asset |
| `DEBIAN/control` | `scripts/build-deb.sh`, pour nommer le paquet |
| `inputremapper/installation_info.py` | l'application |
| `data/io.github.sezanzeb.input_remapper.metainfo.xml` | les magasins d'applications |
| `data/input-remapper.glade` | l'écran « À propos » |
| `README.md` | le lecteur, pour le nom du paquet stable |

Les deux premiers déterminent le nom des assets publiés : les désaligner casse le
mécanisme de mise à jour, qui déduit la version du nom de l'asset.

## Gestion Git
Deux remotes d'écriture, `nas` (source de vérité) et `github` (construction et
distribution), plus `upstream` en lecture seule. Voir `CLAUDE.md`.
