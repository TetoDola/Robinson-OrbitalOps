# Robinson — Contexte projet (claude.md)

Document de référence pour reprendre le travail sur le clone Terminal Industries + la démo OrbitOps / AKJA.

---

## Vue d'ensemble

**Robinson** est un projet hybride en deux parties :

1. **Site marketing** — clone pixel-perfect de [terminal-industries.com](https://terminal-industries.com/) (Next.js 16, React 19, Tailwind v4, shadcn/ui).
2. **Démo produit** — command center orbital « OrbitOps / AKJA Orbital Datacenter Command » : scène Three.js + UI ops (télémétrie, boucle produit, console d’approbation Mission Patch).

---

## Workspaces & dépôts

| Chemin | Rôle | Git |
|--------|------|-----|
| `C:\Users\0303511D\Desktop\Robinson` | Site Next.js + démo intégrée (`/demo`) | **Pas un repo git** |
| `C:\Users\0303511D\Desktop\Robinson-OrbitalOps` | Démo standalone | GitHub : [TetoDola/Robinson-OrbitalOps](https://github.com/TetoDola/Robinson-OrbitalOps) |
| `C:\Users\0303511D\Desktop\BreathCalm\website-cloner` | Template générique clone (ne pas mélanger) | — |

**Règle importante :** travailler sur Robinson / Robinson-OrbitalOps. Ne pas toucher `breathe-calm` ni les autres projets du bureau.

---

## Value proposition (produit Robinson)

**One-liner :** Robinson is a supervised multi-agent command center that keeps datacenters in space alive.

**Problème :** En orbite, pas d’intervention physique possible. Radiation, thermique, alimentation, connectivité → risque de corruption du training, dommages matériels, fenêtres downlink perdues.

**USP :** Agent multimodal de command center pour datacenters orbitaux. Adapte les workloads en temps réel aux risques (radiation, thermique, power, connectivité). **Boucle d’approbation humaine** sur chaque action critique.

**Boucle produit (UI démo) :**  
`MONITOR → DETECT → EXPLAIN → PROPOSE → APPROVE → EXECUTE → VERIFY`

**Mission Patch (exemple démo) :** `patch-042` — 5 agents (Power, Integrity, Workload, Thermal, Downlink) fusionnés par Commander ; l’humain approuve avant exécution.

---

## Site clone Terminal Industries

### Stack
- Next.js 16, React 19, TypeScript, Tailwind CSS v4, shadcn/ui
- Lenis smooth scroll, scroll-driven animations

### Tokens design clés
- `--c-dark-green`: `#052424`
- `--c-lime`: `#abff02`
- Font : SuisseIntl (dans `public/fonts/`)

### Sections principales (`src/components/`)
| Composant | Notes |
|-----------|-------|
| `HeroSection.tsx` | **Vidéo scrubbée au scroll** (pas carousel autoplay). 3 segments vidéo, `currentTime` lié au scroll, pause à l’arrêt. |
| `FeaturesSteps.tsx` | Section « capability » sticky. **Notch animé** sur l’image (SVG `clip-path` / `mask-image` généré dynamiquement). Texte repositionné (éviter le header). Hauteur section augmentée pour éviter le clipping. |
| `Header.tsx` | Boutons **DEMO** → `/demo` (desktop + mobile) |
| Autres | `HowItWorks`, `BenefitsSection`, `ContactSection`, `Footer`, etc. |

### Assets
- `public/images/`, `public/videos/`, `public/fonts/`
- Specs / captures : `docs/research/`, `docs/design-references/` (si présents)

### Commandes
```bash
cd C:\Users\0303511D\Desktop\Robinson
npm run dev      # http://localhost:3000
npm run build    # vérifier compilation
npm run check    # lint + typecheck + build
```

---

## Démo OrbitOps — intégration

### Architecture
- **`public/demo.html`** — HTML/CSS/JS autonome (Three.js r166 via importmap CDN). Toute la logique 3D + UI ops.
- **`src/app/demo/page.tsx`** — route Next.js `/demo` : iframe plein écran vers `/demo.html` (isolation du layout site, pas de conflit CSS).
- **`public/geo/ne_50m_land.geojson`** — côtes Natural Earth 1:50m (~1,6 Mo), fetch `/geo/ne_50m_land.geojson`.

### Accès
- Header → bouton **DEMO** → `http://localhost:3000/demo`
- Fichier direct : `http://localhost:3000/demo.html`

### UI démo (inchangée depuis l’intégration initiale)
- **Command bar** : titre OrbitOps, statuts (supervised ops, ground link, approval required, eclipse…)
- **Mission risk monitor** (gauche) : vitesse, altitude, coords, training load, latence, batterie, solaire, radiation, ECC…
- **Ops loop** (haut centre) : étapes produit, APPROVE surligné
- **Console patch-042** : rack cutaway, états nodes, sévérités agents
- **Active incidents** (bas) : feed agents coloré (ORANGE / RED / YELLOW)
- **Contrôles temps** : 1x / 60x / 600x, follow node
- **Interaction** : clic réticule AKJA-01 → ouvre console d’approbation ; OrbitControls (drag + inertie)

### Astronomie / simulation
- GMST réel (`j2000Days`, `gmst`) pour rotation Terre
- Orbite principale : ~51.6° inclinaison, 420 km, période ~92.9 min
- `simNow()` + `setSpeed()` pour accélération temporelle
- Key light suit la caméra (éclairage frontal constant)

---

## Globe 3D — historique des itérations

### v0 — Photoréaliste (originale)
Textures CDN three.js (earth day/night, specular, clouds), atmosphère shader, satellite modélisé (bus, panneaux, antenne).

### v1 — Minimaliste low-poly (brief utilisateur)
- Icosphère facettes larges, flat-shading, tons océan/terre subtils
- Réseau sparse ~46 nœuds (Fibonacci), liens intentionnels (degré ≤ 2)
- Satellites = dots lumineux sur orbites fines
- Lumière douce, pas de photoréalisme

### v2 — Éclaircissement (combo key-light + fill + tons + exposure)
- Key light fixe (suit caméra)
- Emissive sur matériau, HemisphereLight + AmbientLight renforcés
- `toneMappingExposure` ajusté

### v3 — Fond clair
- `scene.background = #e7e5db`
- Palette inversée (sphère claire, éléments sombres)
- Atmosphère rim désactivée (trop visible sur fond clair)

### v4 — Continents précis (Piste B)
- Natural Earth GeoJSON local → texture 2 tons pleine
- Côtes au pixel près, mais trop lisse / « parfait »

### v5 — Mode points (hybride B + stipple)
- Masque vectoriel → placement de points sur grille lat/long
- Océan visible (sphère `#cdd5d5`) puis **océan transparent**

### v6 — État actuel (validé utilisateur)
| Paramètre | Valeur |
|-----------|--------|
| Fond scène | `#e7e5db` |
| Couleur terre (points) | `#33454a` |
| Océan | **Transparent** (`MeshBasicMaterial({ colorWrite: false })` — masque profondeur uniquement) |
| `LAT_STEPS` | **25** (grille clairsemée, ~25 rangées pole→pole) |
| Taille points | **0.1** |
| Masque | 2048×1024, rasterisé depuis GeoJSON |
| Texture point | `makeLandDot()` — cœur quasi plein + léger anti-alias |
| `CONT_R` | `GLOBE_RADIUS * 1.004` |

### Esthétique cible (brief original — toujours valide)
- Entre low-poly et visualisation computationnelle
- Pas photoréaliste, pas néon cyberpunk, pas HUD dense
- Langage : Apple / OpenAI / Linear, editorial motion, scientific viz
- Animations calmes : rotation lente, orbites satellites, pulse subtil nœuds
- **À éviter :** textures photo, wireframe dense, lat/long visibles, particules flashy

### Réseau & satellites (conservés)
- **Nœuds overlay :** 46 points, shader pulse (`uTime`, `uPhase`), couleur `#b3781f`, liens `#6d6448` opacity 0.32
- **Satellite principal AKJA-01 :** dot orange `#d98d43`, orbite `ORBIT_RADIUS = 1.9`
- **3 satellites ambient** sur orbites inclinées différentes
- **Anneaux d’orbite** fins, opacité ~0.3–0.4
- **Étoiles** : 4000 points, `#8a92a0`, opacity 0.28

### Réglages faciles (dans `public/demo.html`, section globe)
```javascript
const LAT_STEPS = 25;   // ↑ = plus dense, ↓ = plus aéré
size: 0.1,              // taille des pastilles terre
const LAND_COL = '#33454a';
scene.background = new THREE.Color('#e7e5db');
```

Pour remettre un océan visible : remplacer le matériau invisible par `MeshLambertMaterial({ color: '#cdd5d5' })`.

---

## Robinson-OrbitalOps (repo git)

### Fichiers
- Source unique de la démo : `public/demo.html` (+ `public/geo/ne_50m_land.geojson`).
- L'ancien dossier `frontend/` (copie `satellite-orbit.html` + geo dupliqué) a été supprimé au nettoyage — plus de synchronisation à maintenir.

### Chemin GeoJSON
- `fetch('geo/ne_50m_land.geojson')` — **relatif**, fonctionne à la fois servi par Next.js (`/demo.html`) et ouvert en `file://`.

### Commit récent
```
f67003a — Replace photorealistic globe with dotted Natural Earth continents.
```
- Branche `main` **1 commit en avance** sur `origin/main` (push non fait sauf demande explicite)

### Commandes
```bash
cd C:\Users\0303511D\Desktop\Robinson-OrbitalOps
git status
git push -u origin main   # si push demandé
```

---

## Fichiers clés — Robinson

```
Robinson/
├── claude.md                    ← ce fichier
├── public/
│   ├── demo.html                ← démo Three.js complète (SOURCE OF TRUTH scène 3D)
│   └── geo/ne_50m_land.geojson  ← côtes Natural Earth
├── src/
│   ├── app/
│   │   ├── page.tsx             ← homepage clone Terminal
│   │   └── demo/page.tsx        ← iframe /demo
│   └── components/
│       ├── Header.tsx           ← lien DEMO
│       ├── HeroSection.tsx      ← scroll-scrub video
│       └── FeaturesSteps.tsx    ← capability + notch animé
└── package.json
```

---

## QA / outils

- **Playwright MCP** utilisé pour captures et vérif visuelle (`/demo`, `/demo.html`)
- Build Next.js validé après intégration démo
- Screenshots de référence globe (dans breathe-calm temporairement) : `globe-b1.jpeg`, `globe-dots2.jpeg`, `globe-sparse-transparent.jpeg`, `globe-01-large.jpeg`

---

## Pistes ouvertes (non faites)

- Push du commit OrbitalOps vers GitHub
- Initialiser git sur `Robinson` si souhaité
- Hybride trame de points + terre pleine (refusé au profit du mode points pur)
- Natural Earth 1:10m pour plus de petites îles (fichier plus lourd)
- Liseré/contour continents pour plus de séparation du fond
- Ajuster grain globe : entre-deux suggéré `size: 0.06` / `LAT_STEPS: 40`

---

## Rappels pour l’agent

1. Modifier la scène 3D dans `public/demo.html` — source unique, plus de copie `frontend/` à synchroniser.
2. Ne pas casser l’UI ops (patch console, télémétrie, incidents) — seules les sections Three.js globe/lighting/satellites ont été refactorées.
3. Garder l’esthétique **computational / premium / non photoréaliste**.
4. Couleurs terre validées : `#33454a` sur fond `#e7e5db`, océan transparent.
5. Le dossier Robinson n’est pas versionné ; les commits vont dans Robinson-OrbitalOps.
