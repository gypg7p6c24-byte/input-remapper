# input-remapper — cadrage (dépôt)

> **Pointeur stable.** Le cadrage évolutif et les règles de gouvernance vivent hors de ce
> dépôt, dans le dossier de gouvernance non versionné. Ce fichier ne les duplique pas :
> il ne change qu'en cas d'évolution du périmètre du dépôt.

## Périmètre (technique)
Remappage d'entrées clavier/souris — fork de `sezanzeb/input-remapper`.
Correctifs locaux, packaging (flatpak/deb), synchronisation avec l'amont.
Hors-périmètre : autres apps ; ne pas diverger inutilement de l'amont.

Amont : https://github.com/sezanzeb/input-remapper

## Remotes

| Nom | Rôle | Qui écrit |
|---|---|---|
| `nas` | source de vérité, historique, revue | les sessions et le poste |
| `github` | construction, release, distribution | le poste uniquement |
| `upstream` | amont, lecture seule | personne |

**Toute modification part sur `nas` et sur `github` dans la même séance.** Poussée normale
uniquement, jamais de miroir ni de poussée forcée : un miroir détruirait les tags roulants
qui portent les releases, et leurs assets avec eux.

## Kanban
Le backlog vit en base. Canal officiel depuis une session : outils MCP `gov_kanban_*`.
Détail, pièges et cycle de vie : documentation de gouvernance.

## Garde-fou
Si un sujet abordé sort de ce périmètre, le signaler et proposer le bon niveau/projet.
Déclarer le contexte en début de session (ex. « Session : input-remapper »).
