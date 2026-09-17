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
Stable publiée : **1.0.0**. Version portée par la branche `dev` : **1.0.1**.

La branche `dev` porte toujours la **version suivante**, et la chaîne de
construction estampille chaque build dev en `1.0.1.dev<numéro de build>`. C'est ce
qui rend deux builds dev distinguables : le mécanisme de mise à jour compare des
numéros de version, et un canal qui republie le même numéro ne peut rien proposer.

Cinq fichiers portent la version, à tenir alignés :

| Fichier | Qui le lit | Estampillé par la CI sur un build dev |
|---|---|---|
| `pyproject.toml` | la chaîne Flatpak, pour nommer l'asset | oui |
| `inputremapper/installation_info.py` | l'application, pour se comparer au canal | oui |
| `data/io.github.sezanzeb.input_remapper.metainfo.xml` | les magasins d'applications | oui (première entrée) |
| `DEBIAN/control` | `scripts/build-deb.sh`, pour nommer le paquet | non — le `.deb` ne sort que de `main` |
| `data/input-remapper.glade` | valeur affichée avant lecture de l'application | non — écrasée à l'exécution |

`README.md` cite le nom du paquet **stable** : il suit `main`, pas `dev`.

L'estampille vit dans `.github/workflows/flatpak.yml`, et une étape de contrôle y
échoue si un des trois fichiers estampillés ne porte pas la version du build. Un
build de tag (`v*`) publie la version de `pyproject.toml` telle quelle.

## Gestion Git
Deux remotes d'écriture, `nas` (source de vérité) et `github` (construction et
distribution), plus `upstream` en lecture seule. Voir `CLAUDE.md`.
