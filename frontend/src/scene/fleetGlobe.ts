import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { FLEET, type AssetHealth } from "../fleet/fleetData";
import { buildSatellite } from "./satelliteModel";

const TEX = "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r166/examples/textures/planets/";

const BEACON: Record<AssetHealth, number> = {
  critical: 0xff4444,
  caution: 0xf0b35a,
  nominal: 0x6fc49d,
};

/** Three LEO planes — shared by multiple datacenters in the fleet roster. */
const ORBIT_PLANES = [
  { radius: 1.52, incY: 38, incZ: 52 },
  { radius: 1.72, incY: -32, incZ: 68 },
  { radius: 1.92, incY: 105, incZ: 24 },
];

export interface FleetSceneOptions {
  onAssetClick: (id: string) => void;
}

export interface FleetGlobe {
  start: () => void;
  destroy: () => void;
  focusAsset: (id: string | null) => void;
}

interface FleetSatellite {
  root: THREE.Group;
  angle: number;
  speed: number;
  assetId: string;
}

function orbitRing(radius: number) {
  const pts: THREE.Vector3[] = [];
  for (let i = 0; i <= 128; i += 1) {
    const a = (i / 128) * Math.PI * 2;
    pts.push(new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius));
  }
  return new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(pts),
    new THREE.LineBasicMaterial({ color: 0x4d86c8, transparent: true, opacity: 0.28 }),
  );
}

export function createFleetGlobe(container: HTMLElement, options: FleetSceneOptions): FleetGlobe {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0e18);

  const rect = container.getBoundingClientRect();
  const w0 = Math.max(1, rect.width);
  const h0 = Math.max(1, rect.height);

  const camera = new THREE.PerspectiveCamera(42, w0 / h0, 0.05, 1000);
  const defaultCamPos = new THREE.Vector3(0, 1.4, 5.8);
  camera.position.copy(defaultCamPos);
  const defaultTarget = new THREE.Vector3(0, 0, 0);
  const satWorldPos = new THREE.Vector3();
  const focusCamGoal = new THREE.Vector3();
  let focusAssetId: string | null = null;

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.domElement.className = "scene-canvas";
  renderer.setSize(w0, h0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 2.2;
  controls.maxDistance = 14;
  controls.target.copy(defaultTarget);

  const sunDirection = new THREE.Vector3(0.62, 0.3, 0.72).normalize();
  const sun = new THREE.DirectionalLight(0xffffff, 3);
  sun.position.copy(sunDirection).multiplyScalar(50);
  scene.add(sun);
  scene.add(new THREE.AmbientLight(0x223344, 0.35));
  scene.add(new THREE.HemisphereLight(0x8899bb, 0x0a0e18, 0.4));

  const loader = new THREE.TextureLoader();
  loader.setCrossOrigin("anonymous");
  const dayMap = loader.load(`${TEX}earth_atmos_4096.jpg`);
  const nightMap = loader.load(`${TEX}earth_lights_2048.png`);
  const cloudsMap = loader.load(`${TEX}earth_clouds_2048.png`);
  const specMap = loader.load(`${TEX}earth_specular_2048.jpg`);
  dayMap.colorSpace = THREE.SRGBColorSpace;
  nightMap.colorSpace = THREE.SRGBColorSpace;
  dayMap.anisotropy = renderer.capabilities.getMaxAnisotropy();

  const earthMaterial = new THREE.ShaderMaterial({
    uniforms: {
      dayMap: { value: dayMap },
      nightMap: { value: nightMap },
      specMap: { value: specMap },
      sunDirection: { value: sunDirection },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      varying vec3 vNormalW;
      varying vec3 vPosW;
      void main() {
        vUv = uv;
        vNormalW = normalize(mat3(modelMatrix) * normal);
        vPosW = (modelMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform sampler2D dayMap;
      uniform sampler2D nightMap;
      uniform sampler2D specMap;
      uniform vec3 sunDirection;
      varying vec2 vUv;
      varying vec3 vNormalW;
      varying vec3 vPosW;
      void main() {
        vec3 n = normalize(vNormalW);
        vec3 viewDir = normalize(cameraPosition - vPosW);
        float sunDot = dot(n, sunDirection);
        float dayAmount = smoothstep(-0.15, 0.25, sunDot);
        vec3 day = texture2D(dayMap, vUv).rgb;
        vec3 lights = texture2D(nightMap, vUv).rgb * vec3(1.0, 0.85, 0.6) * 1.8;
        vec3 nightSide = lights + day * vec3(0.07, 0.10, 0.17);
        vec3 color = mix(nightSide, day * (0.35 + 0.85 * dayAmount), dayAmount);
        float specMask = texture2D(specMap, vUv).r;
        float glint = pow(clamp(dot(reflect(-sunDirection, n), viewDir), 0.0, 1.0), 120.0);
        color += vec3(1.0, 0.98, 0.9) * glint * specMask * dayAmount * 0.45;
        float twilight = smoothstep(0.12, 0.0, abs(sunDot)) * dayAmount;
        color = mix(color, color * vec3(1.3, 0.85, 0.6), twilight);
        float fresnel = pow(1.0 - clamp(dot(viewDir, n), 0.0, 1.0), 3.0);
        color += vec3(0.15, 0.35, 0.7) * fresnel * (0.25 + 0.75 * dayAmount);
        gl_FragColor = vec4(color, 1.0);
        #include <colorspace_fragment>
      }
    `,
  });

  const earth = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 96), earthMaterial);
  scene.add(earth);

  const clouds = new THREE.Mesh(
    new THREE.SphereGeometry(1.008, 64, 64),
    new THREE.MeshLambertMaterial({ map: cloudsMap, transparent: true, opacity: 0.5, depthWrite: false }),
  );
  scene.add(clouds);

  const atmosphere = new THREE.Mesh(
    new THREE.SphereGeometry(1.07, 64, 64),
    new THREE.ShaderMaterial({
      side: THREE.BackSide,
      transparent: true,
      blending: THREE.AdditiveBlending,
      uniforms: { sunDirection: { value: sunDirection } },
      vertexShader: /* glsl */ `
        varying vec3 vNormalW;
        varying vec3 vPosW;
        void main() {
          vNormalW = normalize(mat3(modelMatrix) * normal);
          vPosW = (modelMatrix * vec4(position, 1.0)).xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        uniform vec3 sunDirection;
        varying vec3 vNormalW;
        varying vec3 vPosW;
        void main() {
          vec3 n = normalize(vNormalW);
          vec3 viewDir = normalize(cameraPosition - vPosW);
          float rim = pow(clamp(dot(viewDir, n), 0.0, 1.0), 2.5);
          float lit = 0.3 + 0.7 * smoothstep(-0.2, 0.4, dot(n, sunDirection));
          gl_FragColor = vec4(vec3(0.3, 0.55, 1.0), rim * 0.6 * lit);
        }
      `,
    }),
  );
  scene.add(atmosphere);

  {
    const count = 2600;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i += 1) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(120 + Math.random() * 80);
      positions.set([v.x, v.y, v.z], i * 3);
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xbfd0e6, size: 0.4, sizeAttenuation: true })));
  }

  const planeGroups = ORBIT_PLANES.map((cfg) => {
    const g = new THREE.Group();
    g.rotation.y = THREE.MathUtils.degToRad(cfg.incY);
    g.rotateZ(THREE.MathUtils.degToRad(cfg.incZ));
    g.add(orbitRing(cfg.radius));
    scene.add(g);
    return g;
  });

  /** Fleet constellation satellite scale. */
  const FLEET_SAT_SCALE = 0.36;

  const pickables: THREE.Object3D[] = [];
  const fleetSats: FleetSatellite[] = [];

  FLEET.forEach((asset) => {
    const sat = buildSatellite(FLEET_SAT_SCALE);
    sat.userData.baseScale = FLEET_SAT_SCALE;
    sat.userData.assetId = asset.id;

    const beacon = sat.userData.beacon as THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>;
    beacon.material.color.setHex(BEACON[asset.health]);

    sat.traverse((obj) => {
      if (obj instanceof THREE.Mesh || obj instanceof THREE.Sprite) pickables.push(obj);
    });

    planeGroups[asset.orbit]?.add(sat);
    fleetSats.push({
      root: sat,
      angle: THREE.MathUtils.degToRad(asset.angle),
      speed: asset.speed * 0.018,
      assetId: asset.id,
    });
  });

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let hovered: THREE.Object3D | null = null;

  function findAssetId(object: THREE.Object3D | null): string | null {
    let cur: THREE.Object3D | null = object;
    while (cur) {
      if (typeof cur.userData.assetId === "string") return cur.userData.assetId;
      cur = cur.parent;
    }
    return null;
  }

  function setPointer(event: PointerEvent) {
    const r = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - r.left) / r.width) * 2 - 1;
    pointer.y = -((event.clientY - r.top) / r.height) * 2 + 1;
  }

  function onPointerMove(event: PointerEvent) {
    setPointer(event);
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(pickables, false);
    hovered = hits[0]?.object ?? null;
    renderer.domElement.style.cursor = hovered ? "pointer" : "grab";
  }

  function onPointerDown(event: PointerEvent) {
    setPointer(event);
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(pickables, false);
    const id = findAssetId(hits[0]?.object ?? null);
    if (id) options.onAssetClick(id);
  }

  renderer.domElement.addEventListener("pointermove", onPointerMove);
  renderer.domElement.addEventListener("pointerdown", onPointerDown);

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let raf = 0;
  let last = performance.now();

  function resize() {
    const r = container.getBoundingClientRect();
    const w = Math.max(1, r.width);
    const h = Math.max(1, r.height);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  const observer = new ResizeObserver(resize);
  observer.observe(container);

  function frame() {
    const now = performance.now();
    const dt = (now - last) / 1000;
    last = now;

    if (!reduceMotion) {
      earth.rotation.y += dt * 0.03;
      clouds.rotation.y += dt * 0.04;

      fleetSats.forEach((entry) => {
        entry.angle += entry.speed * dt * 60;
        const cfg = ORBIT_PLANES[FLEET.find((a) => a.id === entry.assetId)?.orbit ?? 0] ?? ORBIT_PLANES[0];
        entry.root.position.set(
          Math.cos(entry.angle) * cfg.radius,
          0,
          Math.sin(entry.angle) * cfg.radius,
        );
        entry.root.lookAt(0, 0, 0);
        const rackBay = entry.root.userData.rackBay as THREE.Group | undefined;
        if (rackBay) rackBay.rotation.z = Math.sin(now / 900 + entry.angle) * 0.03;

        const base = (entry.root.userData.baseScale as number) ?? FLEET_SAT_SCALE;
        const selected = entry.assetId === focusAssetId;
        const scaleGoal = selected ? base * 1.2 : base;
        entry.root.scale.lerp(new THREE.Vector3(scaleGoal, scaleGoal, scaleGoal), 0.1);
      });
    }

    if (focusAssetId) {
      const entry = fleetSats.find((s) => s.assetId === focusAssetId);
      if (entry) {
        entry.root.getWorldPosition(satWorldPos);
        focusCamGoal.copy(satWorldPos).normalize().multiplyScalar(0.92);
        focusCamGoal.add(satWorldPos);
        focusCamGoal.y += 0.08;
        camera.position.lerp(focusCamGoal, 0.08);
        controls.target.lerp(satWorldPos, 0.1);
      }
      controls.enabled = false;
    } else {
      controls.enabled = true;
      camera.position.lerp(defaultCamPos, 0.06);
      controls.target.lerp(defaultTarget, 0.06);
    }

    controls.update();
    renderer.render(scene, camera);
    raf = requestAnimationFrame(frame);
  }

  return {
    start() {
      fleetSats.forEach((entry) => {
        const cfg = ORBIT_PLANES[FLEET.find((a) => a.id === entry.assetId)?.orbit ?? 0] ?? ORBIT_PLANES[0];
        entry.root.position.set(
          Math.cos(entry.angle) * cfg.radius,
          0,
          Math.sin(entry.angle) * cfg.radius,
        );
        entry.root.lookAt(0, 0, 0);
      });
      raf = requestAnimationFrame(frame);
    },
    focusAsset(id: string | null) {
      focusAssetId = id;
    },
    destroy() {
      cancelAnimationFrame(raf);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      controls.dispose();
      renderer.dispose();
      earthMaterial.dispose();
      [dayMap, nightMap, cloudsMap, specMap].forEach((t) => t.dispose());
      renderer.domElement.remove();
    },
  };
}
