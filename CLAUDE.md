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

## Accès — kanban, git, Gitea

Rien de tout cela ne dépend du dossier monté : les outils MCP répondent depuis n'importe quelle
session, y compris quand seul le dossier de ce projet est ouvert.

| Besoin | Voie | Secret à fournir |
|---|---|---|
| Kanban | outils `gov_kanban_*` | aucun |
| Lire / écrire le dépôt (fetch, commit, push, tag) | outils `nas_git_*` | aucun |
| Interface web Gitea | `http://192.168.1.63:3000/claude/<projet>` | jeton personnel, hors session |
| Push depuis le MacBook | `ssh://git@192.168.1.63:2222/claude/<projet>.git`, remote `nas` | clé SSH |

**Une session n'a aucun secret à fournir.** Le conteneur MCP porte sa propre identité Gitea —
compte de service `claude-mcp`, jeton dans son `.env` sur le NAS, injecté à l'exécution et jamais
persisté dans le dépôt. C'est pour cela que commit, push et tag fonctionnent sans rien configurer.
Le compte **personnel** de Pierre est une identité distincte, qui ne sert qu'au poste.

**Un secret ne transite jamais par le canal MCP**, ne vit jamais dans un dépôt ni dans un fichier
du dossier monté, et ne s'affiche jamais dans une réponse. Méthode de référence (décision du
2026-08-13) : `nas_git_read_file(name="mcp-synology-odysseus", path="docs/secrets-et-acces.md")`.

## Fichiers à supprimer — règle commune

**Rien ne se supprime dans le dossier de travail de Pierre.** Le montage du Mac refuse `unlink`, et
une suppression est de toute façon irréversible. Tout élément à supprimer est **déplacé** dans
`Projects/archives/_to_delete/AAAA-MM-JJ/`, chemin d'origine conservé dans le nom du fichier, puis
**annoncé à Pierre**. La purge est faite par lui, ou sur une proposition qu'il valide — jamais
d'office. **Ne pas demander l'autorisation système de suppression** : le déplacement suffit.

Cas le plus fréquent : les **verrous git orphelins** des clones Mac — `index.lock` et `HEAD.lock`
sont **fatals** (tout commit de Pierre échoue `rc=128`). Cause et conduite à tenir :
`nas_git_read_file(name="mcp-synology-odysseus", path="docs/ouverture-session.md")`.

## Garde-fou
Si un sujet abordé sort de ce périmètre, le signaler et proposer le bon niveau/projet.
Déclarer le contexte en début de session (ex. « Session : input-remapper »).
