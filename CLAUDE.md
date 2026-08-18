# input-remapper — cadrage (dépôt)

> **Pointeur stable.** Les règles de gouvernance vivent dans `Direction/` (non versionné) :
> `Direction/CONVENTIONS.md` · `Direction/KANBAN.md` · `Direction/portfolio.yaml`.
> Ce fichier ne les duplique pas.

## Périmètre (technique)
Remappage d'entrées clavier/souris — fork de `sezanzeb/input-remapper`.
Correctifs locaux, packaging (flatpak/deb), synchronisation avec `upstream`.
Hors-périmètre : autres apps ; ne pas diverger inutilement de l'amont.
Remotes : `nas` (référence) · `upstream` (amont).

## Expertise du périmètre

Projet en **fork**. La question permanente n'est pas « est-ce que ça marche » mais
« de combien ai-je divergé, et est-ce que je le paie encore ».

1. **État réel** — `nas_git_log` et `nas_git_branch` ; les remotes déclarés ; et surtout la
   version **installée sur la machine cible**, pas le dernier build produit. Les deux
   divergent silencieusement.
2. **Doc interne** — la liste des correctifs locaux : c'est elle qui dit ce qu'une fusion
   amont va écraser. Notes de packaging flatpak/deb.
3. **Amont** — https://github.com/sezanzeb/input-remapper
4. **Veille** — https://github.com/sezanzeb/input-remapper/releases avant toute fusion, et
   les issues ouvertes de l'amont : vérifier si un correctif local a été intégré ou rendu
   obsolète. Le supprimer est alors un gain, pas une perte.

**Règle `apps`** : un correctif local est un engagement de maintenance à vie tant qu'il n'est
pas proposé en amont.

> Ce fichier dit **où regarder**, jamais **quel est** l'état. Aucun numéro de version n'y est figé.

## Aller plus loin

Une réponse sur ce projet est incomplète tant qu'elle ne dit pas :

- l'écart avec l'amont : combien de commits, sur quels fichiers, depuis quand ;
- pour chaque correctif local — **est-il encore nécessaire ?** ;
- si le sujet mérite une contribution en amont plutôt qu'un patch local de plus ;
- le **coût de retour arrière** : le paquet précédent est-il conservé et réinstallable ?
- ce qui est prouvé vs ce qui est supposé — dit explicitement.

Un écart qui demande un arbitrage → `gov_kanban_create`, pas une ligne dans le fil.

## Kanban
Canal unique : outils MCP `gov_kanban_*`.
Modèle de flux, definition of ready et pièges — lisibles depuis n'importe quelle session :
dépôt `mcp-synology-odysseus`, `docs/kanban-modele-flux.md` (`nas_git_read_file`).
`Direction/KANBAN.md` porte le design côté COMEX mais vit hors git sur le Mac : une session
sans le dossier monté ne peut pas le lire (carte #49).

## Garde-fou
Si un sujet abordé sort de ce périmètre, le signaler et proposer le bon niveau/projet.
Déclarer le contexte en début de session (ex. « Session : input-remapper »).
