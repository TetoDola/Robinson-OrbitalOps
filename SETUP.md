# Website Cloner — prêt à l'emploi

Projet installé le 4 juillet 2026. Tout est configuré pour cloner un site avec Cursor.

## Utilisation

1. Ouvrez ce dossier dans Cursor : `C:\Users\0303511D\Desktop\BreathCalm\website-cloner`
2. Dans le chat, tapez par exemple :
   - `/clone-website https://example.com`
   - ou : « Clone ce site : https://example.com »
3. L'agent suit le skill **clone-website** (reconnaissance → specs → build parallèle → QA visuelle).

## Prérequis

- **Browser MCP** : Chrome MCP, Playwright MCP ou équivalent (obligatoire pour inspecter le site cible).
- **Node.js** : v22+ fonctionne (le template recommande v24+).

## Commandes utiles

```bash
npm run dev      # http://localhost:3000
npm run build    # vérifier la compilation
npm run check    # lint + typecheck + build
```

## Fichiers générés lors d'un clone

- `docs/research/` — specs et comportements extraits
- `docs/design-references/` — captures d'écran
- `public/images/`, `public/videos/` — assets téléchargés
- `src/components/` — composants reconstruits
