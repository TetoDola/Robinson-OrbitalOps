# Robinson-OrbitalOps

Landing page (clone Terminal Industries) + démo OrbitOps — command center multi-agent pour datacenters orbitaux.

## Lancer le site

```bash
npm install
npm run dev
```

- Landing : http://localhost:3000
- Démo live : http://localhost:3000/demo (iframe → `public/demo.html`)
- Démo standalone : ouvrir `frontend/satellite-orbit.html` (GeoJSON relatif dans `frontend/geo/`)

## Structure

| Dossier | Contenu |
|---------|---------|
| `src/` | Next.js 16 — landing Terminal Industries + route `/demo` |
| `public/` | Assets (fonts, images, videos), `demo.html`, `geo/ne_50m_land.geojson` |
| `frontend/` | Démo HTML autonome (`satellite-orbit.html`) pour usage hors Next.js |
| `docs/` | Specs, captures, recherche clone |

## Stack

Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui, Three.js r166 (démo).

Voir `CLAUDE.md` pour le contexte produit, l'historique du globe 3D et les paramètres de réglage.
