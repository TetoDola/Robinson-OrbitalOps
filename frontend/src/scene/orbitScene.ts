import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import earthCloudsUrl from "../../assets/earth_clouds_4k.jpg";
import earthDayUrl from "../../assets/earth_day_8k.jpg";
import earthNightUrl from "../../assets/earth_night_4k.jpg";
import earthNormalUrl from "../../assets/earth_normal_4k.jpg";
import earthSpecUrl from "../../assets/earth_spec_2k.jpg";
import starmapUrl from "../../assets/starmap_2020_4k.jpg";
import { useWorldStore, type TelemetrySnapshot } from "../store/worldStore";
import type {
  ProcessedRadiationRisk,
  RadiationFluxCell,
  RadiationPoint,
  RadiationZone,
  WorldState,
} from "../types/backend";

export interface OrbitScene {
  start: () => void;
  destroy: () => void;
  resize: () => void;
  updateWorldState: (worldState: WorldState | null) => void;
  setInspection: (open: boolean) => void;
}

const ORBIT_RADIUS = 1.9;
const ORBIT_PERIOD_S = 92.9 * 60;
const EARTH_RADIUS_KM = 6371;
const NODE_ALTITUDE_KM = 420;
const ORBITAL_SPEED_KMS = (2 * Math.PI * (EARTH_RADIUS_KM + NODE_ALTITUDE_KM)) / ORBIT_PERIOD_S;
const Y_AXIS = new THREE.Vector3(0, 1, 0);
const CLOUD_DRIFT = THREE.MathUtils.degToRad(360 / (18 * 3600));
// Geomagnetic dipole axis is tilted ~11 deg from the rotation axis; the inner
// radiation belt (and SAA) follows the magnetic, not geographic, equator.
const GEOMAGNETIC_TILT_RAD = THREE.MathUtils.degToRad(11);
// Standard minimum elevation mask for LEO ground-station contact.
const MIN_ELEVATION_RAD = THREE.MathUtils.degToRad(10);

const GROUND_STATIONS = [
  { name: "Mojave-01", lat: 35.05, lon: -118.15 },
  { name: "Zurich-03", lat: 47.37, lon: 8.55 },
  { name: "Singapore-02", lat: 1.35, lon: 103.82 },
  { name: "Santiago-04", lat: -33.45, lon: -70.67 },
];

function j2000Days(ms: number) {
  return ms / 86400000 + 2440587.5 - 2451545.0;
}

function gmst(ms: number) {
  const d = j2000Days(ms);
  let deg = 280.46061837 + 360.98564736629 * d;
  deg = ((deg % 360) + 360) % 360;
  return THREE.MathUtils.degToRad(deg);
}

function computeSunDirection(ms: number, out: THREE.Vector3) {
  const d = j2000Days(ms);
  const rad = THREE.MathUtils.degToRad;
  const g = rad(357.529 + 0.98560028 * d);
  const L = rad(280.459 + 0.98564736 * d + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g));
  const e = rad(23.439 - 0.00000036 * d);
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L));
  const dec = Math.asin(Math.sin(e) * Math.sin(L));
  return out.set(Math.cos(dec) * Math.cos(ra), Math.sin(dec), -Math.cos(dec) * Math.sin(ra));
}

// Matches the lon = atan2(-z, x) convention used to derive telemetry lat/lon.
function latLonToUnitVec(latDeg: number, lonDeg: number, out: THREE.Vector3) {
  const lat = THREE.MathUtils.degToRad(latDeg);
  const lon = THREE.MathUtils.degToRad(lonDeg);
  return out.set(Math.cos(lat) * Math.cos(lon), Math.sin(lat), -Math.cos(lat) * Math.sin(lon));
}

function latLonToVector(latDeg: number, lonDeg: number, radius: number) {
  return latLonToUnitVec(latDeg, lonDeg, new THREE.Vector3()).multiplyScalar(radius);
}

function easeOutCubic(t: number) {
  return 1 - Math.pow(1 - t, 3);
}

function wrapAngle(a: number) {
  return Math.atan2(Math.sin(a), Math.cos(a));
}

function makeGlowTexture(inner: string, outer: string) {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    throw new Error("Canvas 2D context was unavailable.");
  }
  const grad = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, inner);
  grad.addColorStop(0.35, outer);
  grad.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(canvas);
}

function buildSatellite() {
  const sat = new THREE.Group();

  const bodyMat = new THREE.MeshStandardMaterial({
    color: 0xd8d8dc,
    metalness: 0.85,
    roughness: 0.35,
    emissive: 0x333338,
    emissiveIntensity: 0.35,
  });
  const goldMat = new THREE.MeshStandardMaterial({
    color: 0xc99b3f,
    metalness: 1.0,
    roughness: 0.4,
    emissive: 0x3d2a08,
    emissiveIntensity: 0.5,
  });
  const panelMat = new THREE.MeshStandardMaterial({
    color: 0x14297a,
    metalness: 0.6,
    roughness: 0.25,
    emissive: 0x0d1e55,
    emissiveIntensity: 0.6,
    side: THREE.DoubleSide,
  });
  const rackMat = new THREE.MeshStandardMaterial({
    color: 0x25302c,
    metalness: 0.55,
    roughness: 0.36,
    emissive: 0x18251f,
    emissiveIntensity: 0.65,
  });
  const heatMat = new THREE.MeshStandardMaterial({
    color: 0x6fc49d,
    metalness: 0.45,
    roughness: 0.28,
    emissive: 0x1d5a3c,
    emissiveIntensity: 0.8,
  });

  const bus = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.18, 0.28), goldMat);
  sat.add(bus);

  const rackBay = new THREE.Group();
  rackBay.position.z = -0.015;
  for (let x = -1; x <= 1; x += 1) {
    for (let y = -1; y <= 1; y += 1) {
      const tray = new THREE.Mesh(
        new THREE.BoxGeometry(0.037, 0.026, 0.16),
        x === 1 && y === 0 ? heatMat : rackMat,
      );
      tray.position.set(x * 0.048, y * 0.036, 0.002);
      rackBay.add(tray);
    }
  }
  sat.add(rackBay);
  sat.userData.rackBay = rackBay;
  sat.userData.heatMat = heatMat;

  // Solar arrays sit on pivots so they can rotate about the boom axis, the way
  // a single-axis solar array drive tracks the sun.
  const wings: THREE.Group[] = [];
  for (const dir of [-1, 1]) {
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.1, 8), bodyMat);
    arm.rotation.z = Math.PI / 2;
    arm.position.x = dir * 0.13;
    sat.add(arm);

    const pivot = new THREE.Group();
    pivot.position.x = dir * 0.18;
    sat.add(pivot);
    wings.push(pivot);

    const wing = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.005, 0.18), panelMat);
    wing.position.x = dir * 0.21;
    pivot.add(wing);

    for (let i = 1; i < 4; i += 1) {
      const rib = new THREE.Mesh(new THREE.BoxGeometry(0.004, 0.008, 0.18), bodyMat);
      rib.position.set(dir * i * 0.105, 0, 0);
      pivot.add(rib);
    }
  }
  sat.userData.wings = wings;
  sat.userData.panelMat = panelMat;

  const dish = new THREE.Mesh(
    new THREE.SphereGeometry(0.07, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2.6),
    bodyMat,
  );
  dish.rotation.x = -Math.PI / 2;
  dish.position.z = 0.17;
  sat.add(dish);

  const feed = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, 0.08, 6), bodyMat);
  feed.rotation.x = Math.PI / 2;
  feed.position.z = 0.2;
  sat.add(feed);

  const beaconMat = new THREE.MeshBasicMaterial({ color: 0xff3333 });
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.015, 8, 8), beaconMat);
  beacon.position.set(0, 0.11, -0.1);
  sat.add(beacon);
  sat.userData.beaconMat = beaconMat;

  const glow = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: makeGlowTexture("rgba(180,220,255,0.9)", "rgba(90,150,255,0.35)"),
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  glow.scale.setScalar(0.45);
  sat.add(glow);
  sat.userData.glow = glow;

  const fill = new THREE.PointLight(0xaaccff, 1.2, 3);
  fill.position.set(0.4, 0.6, 0.4);
  sat.add(fill);
  sat.userData.fill = fill;

  sat.scale.setScalar(1.0);
  return sat;
}

function toDegLabel(value: number, positive: string, negative: string) {
  const dir = value >= 0 ? positive : negative;
  return `${Math.abs(value).toFixed(2)}${dir}`;
}

function regionForLatLon(lat: number, lon: number) {
  const absLat = Math.abs(lat);
  if (absLat > 58) return lat > 0 ? "northern auroral corridor" : "southern auroral corridor";
  if (lon > -20 && lon < 55 && lat > -35 && lat < 40) return "EMEA ground corridor";
  if (lon > 55 && lon < 150 && lat > -35 && lat < 45) return "Asia-Pacific ground corridor";
  if (lon < -35 && lon > -125 && lat > -45 && lat < 55) return "Americas ground corridor";
  return "open-ocean relay window";
}

function percent(value: number) {
  return `${Math.round(value)}%`;
}

function phaseLabel(value: string | undefined) {
  return value ? value.replace(/[_-]+/g, " ") : "sunlight";
}

function disposeObject(object: THREE.Object3D) {
  const mesh = object as THREE.Mesh;
  if (mesh.geometry) {
    mesh.geometry.dispose();
  }

  const material = mesh.material;
  if (Array.isArray(material)) {
    material.forEach((item) => item.dispose());
  } else if (material) {
    material.dispose();
  }
}

function colorForRisk(score: number) {
  if (score >= 82) return "#ff6f4f";
  if (score >= 62) return "#f0b35a";
  if (score >= 34) return "#ffda7a";
  return "#65f5c8";
}

function setBaseOpacity(object: THREE.Object3D, opacity: number, pulseRate = 0) {
  object.userData.baseOpacity = opacity;
  object.userData.pulseRate = pulseRate;
}

export function createOrbitScene(container: HTMLElement): OrbitScene {
  const scene = new THREE.Scene();
  const initialRect = container.getBoundingClientRect();
  const initialWidth = Math.max(1, initialRect.width);
  const initialHeight = Math.max(1, initialRect.height);
  const camera = new THREE.PerspectiveCamera(45, initialWidth / initialHeight, 0.05, 1000);
  camera.position.set(0, 1.8, 5.6);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.domElement.className = "scene-canvas";
  renderer.setSize(initialWidth, initialHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const reticle = document.createElement("button");
  reticle.className = "sat-reticle";
  reticle.type = "button";
  reticle.setAttribute("aria-label", "Inspect Neon Noir datacenter");
  reticle.innerHTML = '<span class="sat-reticle-label">Neon Noir</span>';
  document.body.appendChild(reticle);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 1.3;
  controls.maxDistance = 40;
  controls.autoRotateSpeed = 0.35;

  let speed = useWorldStore.getState().simSpeed;
  let simBase = Date.now();
  let realBase = performance.now();
  let follow = useWorldStore.getState().followNode;
  let satelliteSelected = useWorldStore.getState().inspectionOpen;
  let satelliteHovered = false;
  let currentWorldState = useWorldStore.getState().worldState;
  let patchMode = useWorldStore.getState().patchMode;
  let lastTelemetryAt = 0;
  let radiationElevated = false;
  let rackHeatLevel = 0;
  let started = false;

  // Camera choreography state. All of this moves the observer, never the physics.
  const introStartedAt = performance.now();
  let introActive = true;
  let lastInteractionAt = performance.now();
  let focusBlend = 0;
  let distDriveUntil = 0;
  let distGoal = 5.6;
  let eclipseBlend = 0;
  let verifiedPulseAt = -Infinity;

  function simNow() {
    return simBase + (performance.now() - realBase) * speed;
  }

  function setSpeed(nextSpeed: number) {
    simBase = simNow();
    realBase = performance.now();
    speed = nextSpeed;
  }

  const sunDirection = computeSunDirection(Date.now(), new THREE.Vector3());

  {
    const camDir = sunDirection
      .clone()
      .applyAxisAngle(new THREE.Vector3(0, 1, 0), THREE.MathUtils.degToRad(28));
    camDir.y = Math.max(camDir.y + 0.25, 0.2);
    camera.position.copy(camDir.normalize().multiplyScalar(12));
    camera.lookAt(0, 0, 0);
  }

  const sun = new THREE.DirectionalLight(0xffffff, 3);
  sun.position.copy(sunDirection).multiplyScalar(50);
  scene.add(sun);
  scene.add(new THREE.AmbientLight(0x223344, 0.3));

  const sunSprite = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: makeGlowTexture("rgba(255,255,240,1)", "rgba(255,200,120,0.5)"),
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  sunSprite.scale.setScalar(14);
  sunSprite.position.copy(sunDirection).multiplyScalar(90);
  scene.add(sunSprite);

  // NASA-derived Earth textures (Blue Marble / Earth-at-Night / MODIS clouds,
  // via Solar System Scope, CC BY 4.0), vendored locally so the demo works offline.
  const loader = new THREE.TextureLoader();

  const dayMap = loader.load(earthDayUrl);
  const nightMap = loader.load(earthNightUrl);
  const cloudsMap = loader.load(earthCloudsUrl);
  const specMap = loader.load(earthSpecUrl);
  const normalMap = loader.load(earthNormalUrl);
  dayMap.colorSpace = THREE.SRGBColorSpace;
  nightMap.colorSpace = THREE.SRGBColorSpace;
  dayMap.anisotropy = renderer.capabilities.getMaxAnisotropy();
  normalMap.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());

  const earthMaterial = new THREE.ShaderMaterial({
    uniforms: {
      dayMap: { value: dayMap },
      nightMap: { value: nightMap },
      specMap: { value: specMap },
      normalMap: { value: normalMap },
      cloudMap: { value: cloudsMap },
      cloudShift: { value: 0 },
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
      uniform sampler2D normalMap;
      uniform sampler2D cloudMap;
      uniform float cloudShift;
      uniform vec3 sunDirection;
      varying vec2 vUv;
      varying vec3 vNormalW;
      varying vec3 vPosW;
      void main() {
        vec3 nGeo = normalize(vNormalW);
        vec3 viewDir = normalize(cameraPosition - vPosW);

        // Analytic tangent frame for a Y-up sphere (tangent along +u, bitangent
        // along +v); perturb with the terrain normal map for relief shading.
        vec3 tangent = normalize(cross(vec3(0.0, 1.0, 0.0), nGeo));
        vec3 bitangent = cross(nGeo, tangent);
        vec3 nm = texture2D(normalMap, vUv).xyz * 2.0 - 1.0;
        vec3 n = normalize(tangent * nm.x * 0.8 + bitangent * nm.y * 0.8 + nGeo * nm.z);

        // Terminator position uses the geometric normal; terrain detail uses
        // the perturbed one so mountains catch low sun near the terminator.
        float sunDot = dot(nGeo, sunDirection);
        float dayAmount = smoothstep(-0.15, 0.25, sunDot);
        float detail = clamp(dot(n, sunDirection), 0.0, 1.0);

        vec3 day = texture2D(dayMap, vUv).rgb;
        vec3 lights = texture2D(nightMap, vUv).rgb * vec3(1.0, 0.85, 0.6) * 1.5;

        vec3 nightSide = lights + day * vec3(0.07, 0.10, 0.17);
        vec3 dayLit = day * (0.28 + 0.95 * detail);
        vec3 color = mix(nightSide, dayLit, dayAmount);

        // Cloud shadows: the cloud layer leads the surface by cloudShift in
        // longitude, so sample the cloud map shifted back by that amount.
        float cloudCover = texture2D(cloudMap, vec2(vUv.x - cloudShift, vUv.y)).g;
        color *= 1.0 - 0.38 * cloudCover * dayAmount;

        float specMask = texture2D(specMap, vUv).r;
        float glint = pow(clamp(dot(reflect(-sunDirection, n), viewDir), 0.0, 1.0), 90.0);
        color += vec3(1.0, 0.98, 0.9) * glint * specMask * dayAmount * (1.0 - 0.8 * cloudCover) * 0.5;

        float twilight = smoothstep(0.12, 0.0, abs(sunDot)) * dayAmount;
        color = mix(color, color * vec3(1.3, 0.85, 0.6), twilight);

        float fresnel = pow(1.0 - clamp(dot(viewDir, nGeo), 0.0, 1.0), 3.0);
        color += vec3(0.15, 0.35, 0.7) * fresnel * (0.25 + 0.75 * dayAmount);

        gl_FragColor = vec4(color, 1.0);
        #include <colorspace_fragment>
      }
    `,
  });

  const earth = new THREE.Mesh(new THREE.SphereGeometry(1, 96, 96), earthMaterial);
  scene.add(earth);

  const radiationProjection = new THREE.Group();
  radiationProjection.name = "radiation-projection";
  earth.add(radiationProjection);
  let radiationFrameGroups: THREE.Group[] = [];
  let activeRadiationFrame = -1;
  let radiationPlaybackSeconds = 90;
  const radiationGlowTexture = makeGlowTexture("rgba(255,255,255,0.95)", "rgba(100,240,210,0.35)");

  const clouds = new THREE.Mesh(
    new THREE.SphereGeometry(1.008, 64, 64),
    new THREE.MeshLambertMaterial({
      color: 0xffffff,
      alphaMap: cloudsMap,
      transparent: true,
      opacity: 0.85,
      depthWrite: false,
    }),
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

  // Debug layer toggles, e.g. #off=clouds,atmo,rad
  {
    const off = new Set((location.hash.match(/off=([\w,]+)/)?.[1] ?? "").split(","));
    clouds.visible = !off.has("clouds");
    atmosphere.visible = !off.has("atmo");
    radiationProjection.visible = !off.has("rad");
  }

  const orbitPlane = new THREE.Group();
  orbitPlane.rotation.y = THREE.MathUtils.degToRad(40);
  orbitPlane.rotateZ(THREE.MathUtils.degToRad(51.6));
  scene.add(orbitPlane);

  const satellite = buildSatellite();
  orbitPlane.add(satellite);

  const interactiveObjects: THREE.Object3D[] = [];
  satellite.traverse((obj) => {
    const maybeMesh = obj as THREE.Mesh;
    const maybeSprite = obj as THREE.Sprite;
    if (maybeMesh.isMesh || maybeSprite.isSprite) {
      interactiveObjects.push(obj);
    }
  });

  const ringPoints: THREE.Vector3[] = [];
  for (let i = 0; i <= 160; i += 1) {
    const a = (i / 160) * Math.PI * 2;
    ringPoints.push(new THREE.Vector3(Math.cos(a) * ORBIT_RADIUS, 0, Math.sin(a) * ORBIT_RADIUS));
  }
  orbitPlane.add(
    new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(ringPoints),
      new THREE.LineBasicMaterial({ color: 0x4d86c8, transparent: true, opacity: 0.32 }),
    ),
  );

  // Bright arc tracing the path just travelled, fading over ~55 deg of anomaly.
  const TRAIL_SEG = 90;
  const TRAIL_SPAN = THREE.MathUtils.degToRad(55);
  const trailPositions = new Float32Array((TRAIL_SEG + 1) * 3);
  const trailColors = new Float32Array((TRAIL_SEG + 1) * 3);
  for (let i = 0; i <= TRAIL_SEG; i += 1) {
    const fade = Math.pow(1 - i / TRAIL_SEG, 1.7);
    trailColors[i * 3] = 0.48 * fade;
    trailColors[i * 3 + 1] = 0.66 * fade;
    trailColors[i * 3 + 2] = 1.0 * fade;
  }
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute("position", new THREE.BufferAttribute(trailPositions, 3));
  trailGeo.setAttribute("color", new THREE.BufferAttribute(trailColors, 3));
  const trail = new THREE.Line(
    trailGeo,
    new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  orbitPlane.add(trail);

  // Sub-satellite ground track, stored in the Earth-fixed frame so it draws the
  // classic sinusoid as Earth rotates beneath the inclined orbit.
  const GT_MAX = 480;
  const gtPositions = new Float32Array(GT_MAX * 3);
  let gtCount = 0;
  let gtLastAngle = Infinity;
  const gtGeo = new THREE.BufferGeometry();
  gtGeo.setAttribute("position", new THREE.BufferAttribute(gtPositions, 3));
  gtGeo.setDrawRange(0, 0);
  const groundTrack = new THREE.Line(
    gtGeo,
    new THREE.LineBasicMaterial({ color: 0x6fc49d, transparent: true, opacity: 0.35, depthWrite: false }),
  );
  earth.add(groundTrack);

  const riskBandPoints: THREE.Vector3[] = [];
  for (let i = 0; i <= 220; i += 1) {
    const a = (i / 220) * Math.PI * 2;
    riskBandPoints.push(new THREE.Vector3(Math.cos(a) * 1.23, Math.sin(a) * 0.08, Math.sin(a) * 1.23));
  }
  const radiationBand = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(riskBandPoints),
    new THREE.LineBasicMaterial({ color: 0xf0b35a, transparent: true, opacity: 0.34 }),
  );
  radiationBand.rotation.z = GEOMAGNETIC_TILT_RAD;
  scene.add(radiationBand);

  // Ground stations pinned to the rotating Earth at their true coordinates.
  const stations = GROUND_STATIONS.map((station) => {
    const local = latLonToUnitVec(station.lat, station.lon, new THREE.Vector3());
    const orient = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), local);

    const dot = new THREE.Mesh(
      new THREE.CircleGeometry(0.011, 12),
      new THREE.MeshBasicMaterial({ color: 0x6fc49d, transparent: true, opacity: 0.85 }),
    );
    dot.position.copy(local).multiplyScalar(1.004);
    dot.quaternion.copy(orient);
    earth.add(dot);

    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.02, 0.027, 24),
      new THREE.MeshBasicMaterial({
        color: 0x6fc49d,
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    ring.position.copy(local).multiplyScalar(1.005);
    ring.quaternion.copy(orient);
    earth.add(ring);

    return { ...station, local, ring, dotMat: dot.material as THREE.MeshBasicMaterial };
  });

  const beamMat = new THREE.LineBasicMaterial({ color: 0x6fc49d, transparent: true, opacity: 0.4 });
  const beamPositions = new Float32Array(6);
  const downlinkBeam = new THREE.Line(
    new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(beamPositions, 3)),
    beamMat,
  );
  downlinkBeam.visible = false;
  scene.add(downlinkBeam);

  const packetTexture = makeGlowTexture("rgba(220,255,235,1)", "rgba(111,196,157,0.6)");
  const packets = [0, 1, 2].map(() => {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: packetTexture,
        color: 0x9fe8c4,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    sprite.scale.setScalar(0.055);
    sprite.visible = false;
    scene.add(sprite);
    return sprite;
  });

  // Real night sky: NASA/GSFC Deep Star Map 2020 (Hipparcos-2 + Tycho-2 + Gaia
  // DR2, 1.7 billion stars, includes the Milky Way and Magellanic Clouds) in
  // ICRF/J2000 equatorial equirectangular projection. The scene's world frame
  // is already equatorial-inertial (Earth spins by GMST, sun placed by RA/dec),
  // so the map just needs the right wrap: mirror the sphere for inside viewing,
  // then yaw 180 deg because the map is centered on RA 0h with RA increasing
  // leftward. Verified against the galactic center (RA 266.4, dec -28.9) and
  // the LMC (RA 80.9, dec -69.8).
  const starmapTex = loader.load(starmapUrl);
  starmapTex.colorSpace = THREE.SRGBColorSpace;
  starmapTex.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
  const skyGeo = new THREE.SphereGeometry(160, 64, 32);
  skyGeo.scale(-1, 1, 1);
  const skyMat = new THREE.MeshBasicMaterial({ map: starmapTex, depthWrite: false });
  skyMat.color.setScalar(0.6);
  const sky = new THREE.Mesh(skyGeo, skyMat);
  sky.rotation.y = Math.PI;
  sky.renderOrder = -1;
  scene.add(sky);

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const clickPoint = new THREE.Vector2();
  const satWorldPos = new THREE.Vector3();
  const earthFixedPos = new THREE.Vector3();
  const screenPos = new THREE.Vector3();
  const stationWorld = new THREE.Vector3();
  const toSat = new THREE.Vector3();
  const scratchA = new THREE.Vector3();
  const scratchB = new THREE.Vector3();
  let activeStationName: string | null = null;

  function setPointerFromEvent(event: PointerEvent | MouseEvent, target = pointer) {
    const rect = renderer.domElement.getBoundingClientRect();
    target.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    target.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  }

  function intersectSatellite(event: PointerEvent | MouseEvent) {
    setPointerFromEvent(event, clickPoint);
    raycaster.setFromCamera(clickPoint, camera);
    return raycaster.intersectObjects(interactiveObjects, true).length > 0;
  }

  function applyRackHeat() {
    const heatMat = satellite.userData.heatMat as THREE.MeshStandardMaterial;
    if (rackHeatLevel >= 2) {
      heatMat.color.setHex(0xf07464);
      heatMat.emissive.setHex(0x7a1408);
    } else if (rackHeatLevel === 1) {
      heatMat.color.setHex(0xf0b35a);
      heatMat.emissive.setHex(0x7a3a08);
    } else {
      heatMat.color.setHex(0x6fc49d);
      heatMat.emissive.setHex(0x1d5a3c);
    }
  }

  function clearRadiationProjection() {
    const children = [...radiationProjection.children];
    children.forEach((child) => {
      radiationProjection.remove(child);
      child.traverse(disposeObject);
    });
    radiationFrameGroups = [];
    activeRadiationFrame = -1;
  }

  function makeRadiationTube(points: RadiationPoint[], color: string, opacity: number, radius: number, tubeRadius: number) {
    if (points.length < 2) {
      return null;
    }
    const vectors = points.map((point) => latLonToVector(point.latDeg, point.lonDeg, radius));
    const curve = new THREE.CatmullRomCurve3(vectors, false, "catmullrom", 0.2);
    const geometry = new THREE.TubeGeometry(curve, Math.max(8, vectors.length * 3), tubeRadius, 8, false);
    const material = new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.renderOrder = 8;
    setBaseOpacity(mesh, opacity, 0.9);
    return mesh;
  }

  function makeRadiationSprite(point: RadiationPoint, color: string, opacity: number, radius: number, scale: number) {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: radiationGlowTexture,
        color,
        transparent: true,
        opacity,
        blending: THREE.AdditiveBlending,
        depthTest: false,
        depthWrite: false,
      }),
    );
    sprite.position.copy(latLonToVector(point.latDeg, point.lonDeg, radius));
    sprite.scale.setScalar(scale);
    sprite.renderOrder = 9;
    setBaseOpacity(sprite, opacity, 1.1);
    return sprite;
  }

  function makeZoneMaterial(color: string, opacity: number) {
    return new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
  }

  function renderFluxCells(target: THREE.Group, cells: RadiationFluxCell[] | undefined) {
    if (!cells?.length) return;
    const vertices: number[] = [];
    const edgeVertices: number[] = [];
    const colors: number[] = [];
    const indices: number[] = [];
    const color = new THREE.Color();
    const radius = 1.083;
    const edgeRadius = 1.091;
    cells.forEach((cell) => {
      const vertexOffset = vertices.length / 3;
      const corners = [
        latLonToVector(cell.latMinDeg, cell.lonMinDeg, radius),
        latLonToVector(cell.latMaxDeg, cell.lonMinDeg, radius),
        latLonToVector(cell.latMinDeg, cell.lonMaxDeg, radius),
        latLonToVector(cell.latMaxDeg, cell.lonMaxDeg, radius),
      ];
      corners.forEach((corner) => {
        vertices.push(corner.x, corner.y, corner.z);
      });
      const edgeCorners = [
        latLonToVector(cell.latMinDeg, cell.lonMinDeg, edgeRadius),
        latLonToVector(cell.latMaxDeg, cell.lonMinDeg, edgeRadius),
        latLonToVector(cell.latMaxDeg, cell.lonMaxDeg, edgeRadius),
        latLonToVector(cell.latMinDeg, cell.lonMaxDeg, edgeRadius),
      ];
      for (let index = 0; index < edgeCorners.length; index += 1) {
        const start = edgeCorners[index];
        const end = edgeCorners[(index + 1) % edgeCorners.length];
        edgeVertices.push(start.x, start.y, start.z, end.x, end.y, end.z);
      }
      color.set(cell.color);
      for (let index = 0; index < 4; index += 1) {
        colors.push(color.r, color.g, color.b);
      }
      indices.push(vertexOffset, vertexOffset + 1, vertexOffset + 2, vertexOffset + 1, vertexOffset + 3, vertexOffset + 2);
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const material = new THREE.MeshBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.46,
      blending: THREE.NormalBlending,
      depthTest: false,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = "poes-style-flux-grid";
    mesh.renderOrder = 6;
    setBaseOpacity(mesh, 0.46, 0.45);
    target.add(mesh);

    const edgeGeometry = new THREE.BufferGeometry();
    edgeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(edgeVertices, 3));
    const edgeMaterial = new THREE.LineBasicMaterial({
      color: 0xa8ffe4,
      transparent: true,
      opacity: 0.24,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
    });
    const edgeMesh = new THREE.LineSegments(edgeGeometry, edgeMaterial);
    edgeMesh.name = "poes-style-flux-grid-lines";
    edgeMesh.renderOrder = 7;
    setBaseOpacity(edgeMesh, 0.24, 0.35);
    target.add(edgeMesh);
  }

  function makeBandZoneMesh(zone: RadiationZone, opacity: number, radius: number) {
    if (zone.points.length < 2) return null;
    const halfWidth = (zone.widthDeg ?? 8) / 2;
    const vertices: number[] = [];
    const indices: number[] = [];
    zone.points.forEach((point) => {
      const upper = latLonToVector(point.latDeg + halfWidth, point.lonDeg, radius);
      const lower = latLonToVector(point.latDeg - halfWidth, point.lonDeg, radius);
      vertices.push(upper.x, upper.y, upper.z, lower.x, lower.y, lower.z);
    });
    for (let index = 0; index < zone.points.length - 1; index += 1) {
      const a = index * 2;
      indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, makeZoneMaterial(zone.color, opacity));
    mesh.renderOrder = 7;
    setBaseOpacity(mesh, opacity, zone.pulseRate);
    return mesh;
  }

  function makeHotspotZoneMesh(zone: RadiationZone, opacity: number, radius: number) {
    if (zone.points.length < 3) return null;
    const centerLat = zone.points.reduce((total, point) => total + point.latDeg, 0) / zone.points.length;
    const centerLon = zone.points.reduce((total, point) => total + point.lonDeg, 0) / zone.points.length;
    const center = latLonToVector(centerLat, centerLon, radius + 0.002);
    const vertices = [center.x, center.y, center.z];
    zone.points.forEach((point) => {
      const edge = latLonToVector(point.latDeg, point.lonDeg, radius);
      vertices.push(edge.x, edge.y, edge.z);
    });
    const indices: number[] = [];
    for (let index = 1; index < zone.points.length; index += 1) {
      indices.push(0, index, index + 1);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, makeZoneMaterial(zone.color, opacity));
    mesh.renderOrder = 7;
    setBaseOpacity(mesh, opacity, zone.pulseRate);
    return mesh;
  }

  function addRadiationSprites(
    target: THREE.Group,
    points: RadiationPoint[],
    color: string,
    opacity: number,
    radius: number,
    every: number,
    scale: number,
  ) {
    points.forEach((point, index) => {
      if (index % every === 0) {
        target.add(makeRadiationSprite(point, color, opacity, radius, scale));
      }
    });
  }

  function renderRadiationZone(target: THREE.Group, zone: RadiationZone) {
    const opacity = THREE.MathUtils.clamp(zone.opacity, 0.08, 0.82);
    const radius = zone.altitudeScale ?? 1.045;
    const primary =
      zone.type === "particle_hotspot"
        ? makeHotspotZoneMesh(zone, opacity, radius)
        : makeBandZoneMesh(zone, opacity, radius);
    if (primary) {
      target.add(primary);
    }

    if (zone.type === "auroral_curtain") {
      for (let layer = 1; layer <= 3; layer += 1) {
        const upper = makeBandZoneMesh(
          {
            ...zone,
            opacity: opacity * (0.36 / layer),
            widthDeg: (zone.widthDeg ?? 8) * (1 - layer * 0.12),
          },
          opacity * (0.36 / layer),
          radius + layer * 0.024,
        );
        if (upper) {
          setBaseOpacity(upper, opacity * (0.46 / layer), (zone.pulseRate ?? 0.8) + layer * 0.15);
          target.add(upper);
        }
      }
      addRadiationSprites(target, zone.points, zone.color, opacity * 0.55, radius + 0.055, 4, 0.055);
      return;
    }

    if (zone.type === "particle_hotspot") {
      const inner = zone.points.map((point) => ({
        ...point,
        latDeg: point.latDeg * 0.92 + -25 * 0.08,
        lonDeg: point.lonDeg * 0.92 + -45 * 0.08,
      }));
      const hotCore = makeHotspotZoneMesh({ ...zone, points: inner, color: "#ff6f4f" }, opacity * 0.62, radius + 0.018);
      if (hotCore) {
        setBaseOpacity(hotCore, opacity * 0.7, zone.pulseRate ?? 0.45);
        target.add(hotCore);
      }
      addRadiationSprites(target, zone.points, "#ffd082", opacity * 0.5, radius + 0.035, 3, 0.045);
      return;
    }

    if (zone.type === "solar_particle_wash") {
      const wide = makeBandZoneMesh(
        { ...zone, color: "#fff0a6", widthDeg: (zone.widthDeg ?? 18) * 1.45 },
        opacity * 0.28,
        radius + 0.034,
      );
      if (wide) {
        setBaseOpacity(wide, opacity * 0.36, zone.pulseRate ?? 1.2);
        target.add(wide);
      }
      addRadiationSprites(target, zone.points, "#ffe5a0", opacity * 0.42, radius + 0.06, 5, 0.06);
    }
  }

  function renderRadiationTrajectory(target: THREE.Group, points: RadiationPoint[]) {
    for (let index = 0; index < points.length - 1; index += 1) {
      const start = points[index];
      const end = points[index + 1];
      const score = Math.max(start.riskScore ?? 0, end.riskScore ?? 0);
      const segment = makeRadiationTube([start, end], colorForRisk(score), 0.76, 1.16, 0.008);
      if (segment) {
        setBaseOpacity(segment, 0.76, 0.95);
        target.add(segment);
      }
    }
    addRadiationSprites(target, points, "#ffffff", 0.72, 1.185, 2, 0.07);
  }

  function updateRadiationProjection(risk: ProcessedRadiationRisk | null) {
    clearRadiationProjection();
    const riskLevel = risk?.radiationLevel ?? currentWorldState?.radiation?.risk ?? "";
    radiationElevated = ["MEDIUM", "HIGH", "CRITICAL", "ELEVATED"].some((level) =>
      riskLevel.toUpperCase().includes(level),
    );
    (radiationBand.material as THREE.LineBasicMaterial).opacity = radiationElevated ? 0.48 : 0.24;

    // Only project the flux visualization while radiation risk is actually
    // elevated; at LOW the clean Earth is the default view.
    if (!risk?.visualization || !radiationElevated) {
      return;
    }
    radiationPlaybackSeconds = Math.max(12, Number(risk.visualization.playbackSeconds ?? 90));
    const frames = risk.visualization.frames?.length
      ? risk.visualization.frames
      : [{ index: 0, timestamp: risk.visualization.generatedAt, zones: risk.visualization.zones }];
    radiationFrameGroups = frames.map((frame, index) => {
      const group = new THREE.Group();
      group.name = `radiation-frame-${index}`;
      group.visible = index === 0;
      renderFluxCells(group, frame.fluxCells);
      (frame.zones ?? []).forEach((zone) => renderRadiationZone(group, zone));
      radiationProjection.add(group);
      return group;
    });
    activeRadiationFrame = radiationFrameGroups.length ? 0 : -1;
    renderRadiationTrajectory(radiationProjection, risk.visualization.trajectory ?? []);
  }

  function updateRadiationAnimation(realS: number) {
    if (radiationFrameGroups.length > 1) {
      const loopPosition = realS % radiationPlaybackSeconds;
      const nextFrame = Math.floor((loopPosition / radiationPlaybackSeconds) * radiationFrameGroups.length);
      if (nextFrame !== activeRadiationFrame) {
        radiationFrameGroups.forEach((group, index) => {
          group.visible = index === nextFrame;
        });
        activeRadiationFrame = nextFrame;
      }
    }

    radiationProjection.traverse((object) => {
      const baseOpacity = object.userData.baseOpacity;
      if (typeof baseOpacity !== "number") {
        return;
      }
      const pulseRate = Number(object.userData.pulseRate ?? 0);
      const material = (object as THREE.Mesh | THREE.Sprite).material as
        | THREE.Material
        | THREE.Material[]
        | undefined;
      const opacity = pulseRate > 0 ? baseOpacity * (0.82 + 0.18 * Math.sin(realS * pulseRate)) : baseOpacity;
      const materials = Array.isArray(material) ? material : material ? [material] : [];
      materials.forEach((item) => {
        item.opacity = opacity;
      });
    });
  }

  function updateWorldState(worldState: WorldState | null) {
    currentWorldState = worldState;
    const processedRisk = useWorldStore.getState().radiationRisk;
    const riskLevel = processedRisk?.radiationLevel ?? worldState?.radiation?.risk ?? "";
    radiationElevated = ["MEDIUM", "HIGH", "CRITICAL", "ELEVATED"].some((level) =>
      riskLevel.toUpperCase().includes(level),
    );
    const lineMaterial = radiationBand.material as THREE.LineBasicMaterial;
    lineMaterial.opacity = radiationElevated ? 0.48 : 0.24;

    const maxTemp = (worldState?.nodes ?? []).reduce(
      (max, node) => (typeof node.temp_c === "number" && node.temp_c > max ? node.temp_c : max),
      0,
    );
    rackHeatLevel = maxTemp > 90 ? 2 : maxTemp > 70 ? 1 : 0;
    applyRackHeat();
  }

  function onSelectionChanged(open: boolean) {
    satelliteSelected = open;
    reticle.classList.toggle("is-selected", open);
    distDriveUntil = performance.now() + 1700;
    if (open) {
      distGoal = 2.2;
    } else {
      const current = camera.position.distanceTo(controls.target);
      distGoal = current < 3.4 ? 5.6 : current;
    }
  }

  function setInspection(open: boolean) {
    onSelectionChanged(open);
    useWorldStore.getState().setInspectionOpen(open);
  }

  function updateTelemetry(nowMs: number, nowS: number) {
    satellite.getWorldPosition(satWorldPos);
    earthFixedPos.copy(satWorldPos).applyAxisAngle(Y_AXIS, -earth.rotation.y);
    const normalized = earthFixedPos.normalize();
    const sceneLat = THREE.MathUtils.radToDeg(Math.asin(THREE.MathUtils.clamp(normalized.y, -1, 1)));
    const sceneLon = THREE.MathUtils.radToDeg(Math.atan2(-normalized.z, normalized.x));

    const backend = currentWorldState;
    const radiationRisk = useWorldStore.getState().radiationRisk;
    const lat = backend?.satellite?.lat ?? sceneLat;
    const lon = backend?.satellite?.lon ?? sceneLon;
    const station = activeStationName ?? "store & forward";
    const computeLoad =
      backend?.nodes?.length
        ? backend.nodes.reduce((total, node) => total + (node.gpu_util ?? 0), 0) / backend.nodes.length
        : 78 + Math.sin(nowS / 47) * 8 + Math.sin(nowS / 13) * 3;
    const latency = 38 + Math.sin(nowS / 19) * 5 + Math.cos(nowS / 29) * 2;
    const thermal = backend?.thermal?.highest_temp_c ?? 20.8 + Math.sin(nowS / 31) * 1.1;
    const battery = backend?.power?.battery_percent ?? 62 + Math.sin(nowS / 83) * 1.4;
    const solarInput = backend?.power?.solar_kw ?? 11.4 + Math.cos(nowS / 79) * 0.18;
    const eclipseMinutes = backend?.satellite?.time_to_eclipse_min ?? 31 + Math.sin(nowS / 67) * 1.3;
    const downlinkCapacity = backend?.downlink?.capacity_gb ?? 180;
    const eclipseLabel = `${Math.max(0, eclipseMinutes).toFixed(1)} min`;
    const downlinkLabel = `${downlinkCapacity.toFixed(1)} GB / 180 GB`;
    const latestCheckpoint = backend?.training?.latest_checkpoint ?? "ckpt-184500";
    const latestStatus = backend?.training?.latest_checkpoint_status ?? "trusted";
    const eccErrors = backend?.radiation?.ecc_errors_last_5min ?? 12;

    const telemetry: TelemetrySnapshot = {
      clock: `${new Date(nowMs).toISOString().replace("T", " ").slice(11, 19)} UTC`,
      speed: `${(backend?.satellite?.velocity_km_s ?? ORBITAL_SPEED_KMS).toFixed(2)} km/s`,
      altitude: `${Math.round(backend?.satellite?.alt_km ?? NODE_ALTITUDE_KM).toLocaleString()} km`,
      location: `${toDegLabel(lat, "N", "S")}  ${toDegLabel(lon, "E", "W")}`,
      groundTrack: regionForLatLon(lat, lon),
      computeLoad: percent(computeLoad),
      latency: `${Math.max(24, latency).toFixed(0)} ms`,
      battery: percent(battery),
      solar: `${solarInput.toFixed(1)} kW`,
      eclipse: eclipseLabel,
      radiation: radiationRisk
        ? `${radiationRisk.radiationLevel} ${Math.round(radiationRisk.radiationRiskScore)}`
        : phaseLabel(backend?.radiation?.risk ?? "Nominal"),
      radiationExplanation: radiationRisk?.explanation,
      radiationRecommendedAction: radiationRisk?.recommendedAction,
      eccTrend: eccErrors > 850 ? "Rising" : "Nominal",
      trustedCheckpoint: backend?.training?.last_trusted_checkpoint ?? "ckpt-184500",
      latestCheckpoint: `${latestCheckpoint} ${latestStatus}`,
      downlink: downlinkLabel,
      rackHealth: thermal > 85 ? "heat watch" : phaseLabel(backend?.thermal?.cooling_status ?? "nominal"),
      rackHealthTone: thermal > 85 ? "orange" : "yellow",
      groundLink: station,
      orbitPhase: phaseLabel(backend?.satellite?.orbit_phase),
      patchConfidence: `${Math.round(86 + Math.sin(nowS / 90) * 2)}%`,
    };

    if (performance.now() - lastTelemetryAt > 250) {
      lastTelemetryAt = performance.now();
      useWorldStore.getState().setTelemetry(telemetry);
    }
  }

  function updateGroundTrack(anomaly: number) {
    // Push a point whenever the satellite has moved enough in the Earth-fixed
    // frame (orbit anomaly plus Earth rotation) to matter visually.
    const combined = anomaly + earth.rotation.y;
    if (Math.abs(wrapAngle(combined - gtLastAngle)) < 0.008) {
      return;
    }
    gtLastAngle = combined;

    satellite.getWorldPosition(scratchA);
    scratchA.applyAxisAngle(Y_AXIS, -earth.rotation.y).normalize().multiplyScalar(1.006);

    if (gtCount === GT_MAX) {
      gtPositions.copyWithin(0, 3);
      gtCount -= 1;
    }
    gtPositions[gtCount * 3] = scratchA.x;
    gtPositions[gtCount * 3 + 1] = scratchA.y;
    gtPositions[gtCount * 3 + 2] = scratchA.z;
    gtCount += 1;
    gtGeo.setDrawRange(0, gtCount);
    gtGeo.attributes.position.needsUpdate = true;
  }

  function updateDownlink(realS: number) {
    satellite.getWorldPosition(satWorldPos);

    let best: (typeof stations)[number] | null = null;
    let bestElevation = MIN_ELEVATION_RAD;
    for (const station of stations) {
      stationWorld.copy(station.local).applyAxisAngle(Y_AXIS, earth.rotation.y);
      toSat.copy(satWorldPos).sub(stationWorld).normalize();
      // Elevation of the satellite above the station's local horizon.
      const elevation = Math.asin(THREE.MathUtils.clamp(stationWorld.dot(toSat), -1, 1));
      if (elevation > bestElevation) {
        bestElevation = elevation;
        best = station;
      }
    }

    activeStationName = best?.name ?? null;
    const executing = patchMode === "execute";
    const beamColor = executing ? 0xf0b35a : 0x6fc49d;

    for (const station of stations) {
      const isActive = station === best;
      const ringMat = station.ring.material as THREE.MeshBasicMaterial;
      if (isActive) {
        const p = (realS * 0.8) % 1;
        ringMat.opacity = 0.75 * (1 - p);
        station.ring.scale.setScalar(1 + p * 1.3);
        ringMat.color.setHex(beamColor);
        station.dotMat.color.setHex(beamColor);
      } else {
        ringMat.opacity = 0;
        station.dotMat.color.setHex(0x6fc49d);
      }
    }

    if (!best) {
      downlinkBeam.visible = false;
      packets.forEach((packet) => {
        packet.visible = false;
      });
      return;
    }

    stationWorld.copy(best.local).applyAxisAngle(Y_AXIS, earth.rotation.y);
    scratchB.copy(stationWorld).multiplyScalar(1.002);
    beamPositions[0] = satWorldPos.x;
    beamPositions[1] = satWorldPos.y;
    beamPositions[2] = satWorldPos.z;
    beamPositions[3] = scratchB.x;
    beamPositions[4] = scratchB.y;
    beamPositions[5] = scratchB.z;
    downlinkBeam.geometry.attributes.position.needsUpdate = true;
    downlinkBeam.visible = true;
    beamMat.color.setHex(beamColor);

    const rate = executing ? 1.1 : 0.45;
    packets.forEach((packet, index) => {
      const t = (realS * rate + index / packets.length) % 1;
      packet.position.copy(satWorldPos).lerp(scratchB, t);
      packet.visible = true;
      (packet.material as THREE.SpriteMaterial).color.setHex(executing ? 0xf5cf8e : 0x9fe8c4);
      (packet.material as THREE.SpriteMaterial).opacity = Math.sin(t * Math.PI);
    });
  }

  function updateSatelliteSystems(realS: number) {
    // Cylindrical umbra: in shadow when behind the terminator plane and within
    // one Earth radius of the anti-sun axis.
    satellite.getWorldPosition(satWorldPos);
    const along = satWorldPos.dot(sunDirection);
    const inUmbra = along < 0 && scratchA.copy(satWorldPos).addScaledVector(sunDirection, -along).lengthSq() < 1;
    eclipseBlend += ((inUmbra ? 1 : 0) - eclipseBlend) * 0.06;

    const fill = satellite.userData.fill as THREE.PointLight;
    const panelMat = satellite.userData.panelMat as THREE.MeshStandardMaterial;
    fill.intensity = 1.2 * (1 - 0.85 * eclipseBlend);
    panelMat.emissiveIntensity = 0.6 * (1 - 0.7 * eclipseBlend);

    // Single-axis solar array drive: rotate the wings about the boom (local x)
    // so the panel normal tracks the projection of the sun direction.
    scratchB.copy(satWorldPos).addScaledVector(sunDirection, 10);
    satellite.worldToLocal(scratchB);
    const sunAngle = Math.atan2(scratchB.z, scratchB.y);
    for (const wing of satellite.userData.wings as THREE.Group[]) {
      wing.rotation.x += wrapAngle(sunAngle - wing.rotation.x) * 0.05;
    }

    const beaconMat = satellite.userData.beaconMat as THREE.MeshBasicMaterial;
    const pulse = 0.5 + 0.5 * Math.sin(realS * 4.2);
    beaconMat.color.setRGB(0.3 + 0.7 * pulse, 0.09 + 0.1 * pulse, 0.09);

    const heatMat = satellite.userData.heatMat as THREE.MeshStandardMaterial;
    heatMat.emissiveIntensity = rackHeatLevel >= 2 ? 0.8 + 0.35 * Math.sin(realS * 5) : 0.8;

    const glow = satellite.userData.glow as THREE.Sprite;
    const glowMat = glow.material as THREE.SpriteMaterial;
    let glowScale = satelliteHovered ? 0.6 : 0.45;
    if (satelliteSelected) {
      glowScale = 0.58 + 0.05 * Math.sin(realS * 3);
    }
    const sinceVerified = performance.now() - verifiedPulseAt;
    if (sinceVerified < 1600) {
      const k = 1 - sinceVerified / 1600;
      glowMat.color.setRGB(1 - 0.55 * k, 1, 1 - 0.35 * k);
      glowScale += 0.25 * k;
    } else {
      glowMat.color.setRGB(1, 1, 1);
    }
    glowScale *= 1 - 0.35 * eclipseBlend;
    glow.scale.setScalar(glow.scale.x + (glowScale - glow.scale.x) * 0.15);

    (satellite.userData.rackBay as THREE.Group).rotation.z = Math.sin(realS * 1.4) * 0.04;
  }

  function updateCamera(realNow: number) {
    if (introActive) {
      const t = Math.min(1, (realNow - introStartedAt) / 2800);
      const dist = 12 - (12 - 5.6) * easeOutCubic(t);
      scratchA.copy(camera.position).sub(controls.target).normalize().multiplyScalar(dist);
      camera.position.copy(controls.target).add(scratchA);
      if (t >= 1) {
        introActive = false;
      }
    }

    const focusGoal = satelliteSelected ? 1 : 0;
    focusBlend += (focusGoal - focusBlend) * 0.06;
    if (focusBlend > 0.001) {
      satellite.getWorldPosition(satWorldPos);
      scratchA.set(0, 0, 0).lerp(satWorldPos, focusBlend);
      controls.target.lerp(scratchA, 0.3);
    } else if (follow) {
      satellite.getWorldPosition(satWorldPos);
      controls.target.lerp(satWorldPos, 0.15);
    }

    if (realNow < distDriveUntil) {
      const current = camera.position.distanceTo(controls.target);
      const next = current + (distGoal - current) * 0.07;
      scratchA.copy(camera.position).sub(controls.target).normalize().multiplyScalar(next);
      camera.position.copy(controls.target).add(scratchA);
    }

    controls.autoRotate =
      !introActive && !satelliteSelected && focusBlend < 0.01 && realNow - lastInteractionAt > 8000;
  }

  function updateReticle() {
    satellite.getWorldPosition(satWorldPos);
    screenPos.copy(satWorldPos).project(camera);
    const rect = container.getBoundingClientRect();
    const visible =
      screenPos.z > -1 &&
      screenPos.z < 1 &&
      screenPos.x > -1.05 &&
      screenPos.x < 1.05 &&
      screenPos.y > -1.05 &&
      screenPos.y < 1.05;

    reticle.classList.toggle("is-visible", visible);
    reticle.classList.toggle("is-selected", satelliteSelected);
    if (!visible) {
      return;
    }

    const x = rect.left + (screenPos.x * 0.5 + 0.5) * rect.width;
    const y = rect.top + (-screenPos.y * 0.5 + 0.5) * rect.height;
    reticle.style.setProperty("--x", `${x}px`);
    reticle.style.setProperty("--y", `${y}px`);
  }

  function animate() {
    const realNow = performance.now();
    const realS = realNow / 1000;
    const nowMs = simNow();
    const nowS = nowMs / 1000;

    earth.rotation.y = gmst(nowMs);
    const cloudDriftRad = (nowS % 86400) * CLOUD_DRIFT;
    clouds.rotation.y = earth.rotation.y + cloudDriftRad;
    earthMaterial.uniforms.cloudShift.value = cloudDriftRad / (2 * Math.PI);
    computeSunDirection(nowMs, sunDirection);
    sun.position.copy(sunDirection).multiplyScalar(50);
    sunSprite.position.copy(sunDirection).multiplyScalar(90);

    const a = ((2 * Math.PI * nowS) / ORBIT_PERIOD_S) % (2 * Math.PI);
    satellite.position.set(Math.cos(a) * ORBIT_RADIUS, 0, Math.sin(a) * ORBIT_RADIUS);
    satellite.lookAt(0, 0, 0);

    for (let i = 0; i <= TRAIL_SEG; i += 1) {
      const angle = a - (i / TRAIL_SEG) * TRAIL_SPAN;
      trailPositions[i * 3] = Math.cos(angle) * ORBIT_RADIUS;
      trailPositions[i * 3 + 1] = 0;
      trailPositions[i * 3 + 2] = Math.sin(angle) * ORBIT_RADIUS;
    }
    trailGeo.attributes.position.needsUpdate = true;

    if (radiationElevated) {
      (radiationBand.material as THREE.LineBasicMaterial).opacity = 0.4 + 0.1 * Math.sin(realS * 1.8);
    }
    updateRadiationAnimation(realS);

    updateSatelliteSystems(realS);
    updateGroundTrack(a);
    updateDownlink(realS);
    updateCamera(realNow);
    updateTelemetry(nowMs, nowS);
    updateReticle();

    controls.update();
    renderer.render(scene, camera);
  }

  function resize() {
    const rect = container.getBoundingClientRect();
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  }

  function noteInteraction() {
    lastInteractionAt = performance.now();
    introActive = false;
    distDriveUntil = 0;
    controls.autoRotate = false;
  }

  const onPointerMove = (event: PointerEvent) => {
    setPointerFromEvent(event);
    satelliteHovered = intersectSatellite(event);
    renderer.domElement.style.cursor = satelliteHovered ? "pointer" : "grab";
  };

  const onPointerDown = () => {
    noteInteraction();
    renderer.domElement.style.cursor = "grabbing";
  };

  const onWheel = () => {
    noteInteraction();
  };

  const onPointerUp = () => {
    lastInteractionAt = performance.now();
    renderer.domElement.style.cursor = satelliteHovered ? "pointer" : "grab";
  };

  const onPointerLeave = () => {
    satelliteHovered = false;
    renderer.domElement.style.cursor = "default";
  };

  const onCanvasClick = (event: MouseEvent) => {
    const hitSatellite = intersectSatellite(event);
    if (hitSatellite) {
      setInspection(!satelliteSelected);
      return;
    }
    if (satelliteSelected) {
      setInspection(false);
    }
  };

  const onReticleClick = () => setInspection(!satelliteSelected);

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape" && satelliteSelected) {
      setInspection(false);
    }
  };

  const onVisibilityChange = () => {
    if (!started) {
      return;
    }
    renderer.setAnimationLoop(document.hidden ? null : animate);
  };

  renderer.domElement.addEventListener("pointermove", onPointerMove);
  renderer.domElement.addEventListener("pointerdown", onPointerDown);
  renderer.domElement.addEventListener("pointerup", onPointerUp);
  renderer.domElement.addEventListener("pointerleave", onPointerLeave);
  renderer.domElement.addEventListener("wheel", onWheel, { passive: true });
  renderer.domElement.addEventListener("click", onCanvasClick);
  reticle.addEventListener("click", onReticleClick);
  window.addEventListener("resize", resize);
  window.addEventListener("keydown", onKeyDown);
  document.addEventListener("visibilitychange", onVisibilityChange);
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container);

  const unsubscribers = [
    useWorldStore.subscribe((state) => state.worldState, updateWorldState),
    useWorldStore.subscribe((state) => state.radiationRisk, updateRadiationProjection),
    useWorldStore.subscribe((state) => state.simSpeed, setSpeed),
    useWorldStore.subscribe(
      (state) => state.patchMode,
      (mode) => {
        if (mode === "verified" && patchMode !== "verified") {
          verifiedPulseAt = performance.now();
        }
        patchMode = mode;
      },
    ),
    useWorldStore.subscribe(
      (state) => state.followNode,
      (value) => {
        follow = value;
        if (!follow) {
          controls.target.set(0, 0, 0);
        }
      },
    ),
    useWorldStore.subscribe(
      (state) => state.inspectionOpen,
      (open) => {
        if (open !== satelliteSelected) {
          onSelectionChanged(open);
        }
      },
    ),
  ];

  const api: OrbitScene = {
    start: () => {
      resize();
      updateWorldState(currentWorldState);
      updateRadiationProjection(useWorldStore.getState().radiationRisk);
      started = true;
      renderer.setAnimationLoop(animate);
    },
    destroy: () => {
      started = false;
      renderer.setAnimationLoop(null);
      window.removeEventListener("resize", resize);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("pointerleave", onPointerLeave);
      renderer.domElement.removeEventListener("wheel", onWheel);
      renderer.domElement.removeEventListener("click", onCanvasClick);
      reticle.removeEventListener("click", onReticleClick);
      window.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      unsubscribers.forEach((unsubscribe) => unsubscribe());
      controls.dispose();
      scene.traverse(disposeObject);
      dayMap.dispose();
      nightMap.dispose();
      cloudsMap.dispose();
      specMap.dispose();
      normalMap.dispose();
      starmapTex.dispose();
      radiationGlowTexture.dispose();
      packetTexture.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      reticle.remove();
    },
    resize,
    updateWorldState,
    setInspection,
  };

  return api;
}
