# Prompt — Clone pixel-perfect Terminal Industries

Copiez-collez le bloc ci-dessous dans une **nouvelle conversation Cursor**, après avoir :
1. Redémarré Cursor
2. Vérifié que **Playwright MCP** est actif (Settings → MCP → vert)
3. Ouvert le dossier **`C:\Users\0303511D\Desktop\Robinson`** comme workspace

---

```
/clone-website https://terminal-industries.com/

## Workspace (obligatoire)
- Travaille UNIQUEMENT dans : C:\Users\0303511D\Desktop\Robinson
- Ne touche pas à breathe-calm ni aux autres projets du bureau
- Tous les fichiers source, assets, specs et builds vont dans ce dossier

## Prérequis avant de commencer
1. Vérifie que Playwright MCP est disponible (navigate, screenshot, evaluate JS)
2. Si aucun browser MCP n'est détecté, STOP et dis-moi quoi activer
3. Confirme que `npm run build` passe dans Robinson ; sinon corrige d'abord

## Objectif
Clone pixel-perfect de https://terminal-industries.com/
Recommence from scratch — remplace les composants approximatifs actuels.
Fidélité : couleurs, typo, espacements, animations, scroll, hover, responsive.

## Pipeline à suivre (skill clone-website)
1. Reconnaissance Playwright : screenshots full-page desktop 1440px + mobile 390px → docs/design-references/
2. Extraction globale : fonts SuisseIntl, tokens CSS (--c-dark-green #052424, --c-lime #abff02), favicons → public/seo/
3. Interaction sweep : scroll header, tabs, vidéos, odomètre, Lenis/smooth scroll → docs/research/BEHAVIORS.md
4. Topologie page → docs/research/PAGE_TOPOLOGY.md
5. Pour CHAQUE section : spec file docs/research/components/<nom>.spec.md avec getComputedStyle() exact, PUIS rebuild du composant
6. Assemblage src/app/page.tsx
7. QA visuelle : screenshots clone vs original, corriger jusqu'à match

## Structure de sortie
- Composants : src/components/
- Assets : public/images/, public/videos/, public/fonts/
- Specs : docs/research/components/
- Captures : docs/design-references/

## Commandes utiles
cd C:\Users\0303511D\Desktop\Robinson
npm run dev      → preview http://localhost:3000
npm run build    → vérifier compilation
npm run check    → lint + typecheck + build

## Ce que je veux à la fin
- Rapport : sections built, specs écrites, assets téléchargés, build OK, écarts QA restants
- Site visible sur http://localhost:3000
```
