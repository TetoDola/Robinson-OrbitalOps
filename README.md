# Robinson-OrbitalOps

Landing page (clone Terminal Industries) + démo OrbitOps — command center multi-agent pour datacenters orbitaux.

## Lancer le site

```bash
npm install
npm run dev
```

- Landing : http://localhost:3000
- Démo live : http://localhost:3000/demo (iframe → `public/demo.html`)
- Démo standalone : ouvrir directement `public/demo.html` (le GeoJSON est chargé en relatif depuis `public/geo/`, donc ça marche aussi en `file://`)

## Structure

| Dossier | Contenu |
|---------|---------|
| `src/` | Next.js 16 — landing Terminal Industries + route `/demo` |
| `public/` | Assets (fonts, images, videos), `demo.html` (démo Three.js autonome), `geo/ne_50m_land.geojson` |
| `docs/` | Specs, captures, recherche clone |

## Stack

Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, Three.js r166 (démo).

Voir `CLAUDE.md` pour le contexte produit, l'historique du globe 3D et les paramètres de réglage.
