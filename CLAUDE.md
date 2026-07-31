# input-remapper — cadrage (dépôt)

> **Pointeur stable.** Le cadrage évolutif et les règles de gouvernance vivent dans `Direction/`
> (non versionné) : `Direction/CONVENTIONS.md` · `Direction/KANBAN.md` · `Direction/portfolio.yaml`.
> Ce fichier ne les duplique pas : il ne change qu'en cas d'évolution du périmètre du dépôt.

## Périmètre (technique)
Remappage d'entrées clavier/souris — fork de `sezanzeb/input-remapper`.
Correctifs locaux, packaging (flatpak/deb), synchronisation avec `upstream`.
Hors-périmètre : autres apps ; ne pas diverger inutilement de l'amont.
Remotes : `nas` (référence) · `upstream` (amont).

## Kanban
Le backlog vit en base (`gouvernance.items`, conteneur `shared-db`). Canal officiel depuis une
session : outils MCP `gov_kanban_*`. Détail, pièges et cycle de vie : `Direction/KANBAN.md`.

## Garde-fou
Si un sujet abordé sort de ce périmètre, le signaler et proposer le bon niveau/projet.
Déclarer le contexte en début de session (ex. « Session : input-remapper »).
