import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

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

const TEX = "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r166/examples/textures/planets/";
const ORBIT_RADIUS = 1.9;
const ORBIT_PERIOD_S = 92.9 * 60;
const EARTH_RADIUS_KM = 6371;
const NODE_ALTITUDE_KM = 420;
const ORBITAL_SPEED_KMS = (2 * Math.PI * (EARTH_RADIUS_KM + NODE_ALTITUDE_KM)) / ORBIT_PERIOD_S;
const Y_AXIS = new THREE.Vector3(0, 1, 0);
const CLOUD_DRIFT = THREE.MathUtils.degToRad(360 / (18 * 3600));

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
    color: 0xf0b35a,
    metalness: 0.45,
    roughness: 0.28,
    emissive: 0x7a3a08,
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

  for (const dir of [-1, 1]) {
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, 0.1, 8), bodyMat);
    arm.rotation.z = Math.PI / 2;
    arm.position.x = dir * 0.13;
    sat.add(arm);

    const wing = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.005, 0.18), panelMat);
    wing.position.x = dir * 0.39;
    sat.add(wing);

    for (let i = 1; i < 4; i += 1) {
      const rib = new THREE.Mesh(new THREE.BoxGeometry(0.004, 0.008, 0.18), bodyMat);
      rib.position.set(dir * (0.18 + i * 0.105), 0, 0);
      sat.add(rib);
    }
  }

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

  const beacon = new THREE.Mesh(
    new THREE.SphereGeometry(0.015, 8, 8),
    new THREE.MeshBasicMaterial({ color: 0xff3333 }),
  );
  beacon.position.set(0, 0.11, -0.1);
  sat.add(beacon);
  sat.userData.beacon = beacon;

  const glow = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: makeGlowTexture("rgba(180,220,255,0.9)", "rgba(90,150,255,0.35)"),
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  );
  glow.scale.setScalar(0.45);
  sat.add(glow);

  const fill = new THREE.PointLight(0xaaccff, 1.2, 3);
  fill.position.set(0.4, 0.6, 0.4);
  sat.add(fill);

  sat.scale.setScalar(1.0);
  return sat;
}

function toDegLabel(value: number, positive: string, negative: string) {
  const dir = value >= 0 ? positive : negative;
  return `${Math.abs(value).toFixed(2)}${dir}`;
}

function stationForLongitude(lon: number) {
  if (lon > -35 && lon < 45) return "Zurich-03";
  if (lon >= 45 && lon < 140) return "Singapore-02";
  if (lon >= 140 || lon < -120) return "Mojave-01";
  return "Santiago-04";
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
  return value ? value.replace(/[_-]+/g, " ") : "approaching eclipse";
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

function latLonToVector(latDeg: number, lonDeg: number, radius = 1.03) {
  const lat = THREE.MathUtils.degToRad(latDeg);
  const lon = THREE.MathUtils.degToRad(lonDeg);
  const cosLat = Math.cos(lat);
  return new THREE.Vector3(
    Math.cos(lon) * cosLat * radius,
    Math.sin(lat) * radius,
    -Math.sin(lon) * cosLat * radius,
  );
}

function colorForRisk(score = 0) {
  if (score >= 75) return "#ff4f58";
  if (score >= 50) return "#ff9f45";
  if (score >= 25) return "#f0d96a";
  return "#64f0c8";
}

function setBaseOpacity(object: THREE.Object3D, opacity: number, pulseRate = 0.6) {
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
  reticle.setAttribute("aria-label", "Inspect AKJA-01 satellite");
  reticle.innerHTML = '<span class="sat-reticle-label">AKJA-01</span>';
  document.body.appendChild(reticle);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.minDistance = 1.3;
  controls.maxDistance = 40;

  let speed = useWorldStore.getState().simSpeed;
  let simBase = Date.now();
  let realBase = performance.now();
  let follow = useWorldStore.getState().followNode;
  let satelliteSelected = useWorldStore.getState().inspectionOpen;
  let satelliteHovered = false;
  let currentWorldState = useWorldStore.getState().worldState;
  let lastTelemetryAt = 0;

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
    camera.position.copy(camDir.normalize().multiplyScalar(5.6));
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
  const radiationProjection = new THREE.Group();
  radiationProjection.name = "radiation-projection";
  earth.add(radiationProjection);
  let radiationFrameGroups: THREE.Group[] = [];
  let activeRadiationFrame = -1;
  let radiationPlaybackSeconds = 90;
  const radiationGlowTexture = makeGlowTexture("rgba(255,255,255,0.95)", "rgba(100,240,210,0.35)");

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
      new THREE.LineBasicMaterial({ color: 0x4d86c8, transparent: true, opacity: 0.5 }),
    ),
  );

  const riskBandPoints: THREE.Vector3[] = [];
  for (let i = 0; i <= 220; i += 1) {
    const a = (i / 220) * Math.PI * 2;
    riskBandPoints.push(new THREE.Vector3(Math.cos(a) * 1.23, Math.sin(a) * 0.08, Math.sin(a) * 1.23));
  }
  const radiationBand = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(riskBandPoints),
    new THREE.LineBasicMaterial({ color: 0xf0b35a, transparent: true, opacity: 0.34 }),
  );
  radiationBand.rotation.z = THREE.MathUtils.degToRad(24);
  scene.add(radiationBand);

  const downlinkPositions = new Float32Array(6);
  const downlinkLine = new THREE.Line(
    new THREE.BufferGeometry().setAttribute("position", new THREE.BufferAttribute(downlinkPositions, 3)),
    new THREE.LineBasicMaterial({ color: 0x6fc49d, transparent: true, opacity: 0.62 }),
  );
  scene.add(downlinkLine);

  {
    const count = 4000;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i += 1) {
      const v = new THREE.Vector3().randomDirection().multiplyScalar(120 + Math.random() * 80);
      positions.set([v.x, v.y, v.z], i * 3);
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xbfd0e6, size: 0.4, sizeAttenuation: true })));
  }

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const clickPoint = new THREE.Vector2();
  const satWorldPos = new THREE.Vector3();
  const earthFixedPos = new THREE.Vector3();
  const groundPoint = new THREE.Vector3();
  const screenPos = new THREE.Vector3();

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

  function updateWorldState(worldState: WorldState | null) {
    currentWorldState = worldState;
    const lineMaterial = radiationBand.material as THREE.LineBasicMaterial;
    const risk = useWorldStore.getState().radiationRisk;
    const riskLevel = risk?.radiationLevel ?? worldState?.radiation?.risk ?? "";
    lineMaterial.opacity = ["MEDIUM", "HIGH", "CRITICAL"].some((level) => riskLevel.toUpperCase().includes(level))
      ? 0.48
      : 0.24;
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
      depthWrite: false,
    });
    const mesh = new THREE.Mesh(geometry, material);
    setBaseOpacity(mesh, opacity);
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
        depthWrite: false,
      }),
    );
    sprite.position.copy(latLonToVector(point.latDeg, point.lonDeg, radius));
    sprite.scale.setScalar(scale);
    setBaseOpacity(sprite, opacity, 1.1);
    return sprite;
  }

  function makeZoneMaterial(color: string, opacity: number) {
    return new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
  }

  function renderFluxCells(target: THREE.Group, cells: RadiationFluxCell[] | undefined) {
    if (!cells?.length) return;
    const vertices: number[] = [];
    const colors: number[] = [];
    const indices: number[] = [];
    const color = new THREE.Color();
    const radius = 1.052;
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
      opacity: 0.48,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = "poes-style-flux-grid";
    setBaseOpacity(mesh, 0.48, 0.5);
    target.add(mesh);
  }

  function makeBandZoneMesh(zone: RadiationZone, opacity: number, radius: number) {
    const points = zone.points;
    if (points.length < 2) return null;
    const halfWidth = (zone.widthDeg ?? 8) / 2;
    const vertices: number[] = [];
    const indices: number[] = [];
    points.forEach((point) => {
      const upper = latLonToVector(point.latDeg + halfWidth, point.lonDeg, radius);
      const lower = latLonToVector(point.latDeg - halfWidth, point.lonDeg, radius);
      vertices.push(upper.x, upper.y, upper.z, lower.x, lower.y, lower.z);
    });
    for (let index = 0; index < points.length - 1; index += 1) {
      const a = index * 2;
      indices.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(vertices, 3));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    const mesh = new THREE.Mesh(geometry, makeZoneMaterial(zone.color, opacity));
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
      const segment = makeRadiationTube([start, end], colorForRisk(score), 0.52, 1.09, 0.0045);
      if (segment) {
        setBaseOpacity(segment, 0.52, 0.95);
        target.add(segment);
      }
    }
    addRadiationSprites(target, points, "#ffffff", 0.42, 1.115, 2, 0.04);
  }

  function updateRadiationProjection(risk: ProcessedRadiationRisk | null) {
    clearRadiationProjection();
    if (!risk?.visualization) {
      return;
    }
    radiationPlaybackSeconds = Math.max(12, Number(risk.visualization.playbackSeconds ?? 90));
    const frames = risk.visualization.frames?.length ? risk.visualization.frames : [{ zones: risk.visualization.zones }];
    radiationFrameGroups = frames.map((frame, index) => {
      const group = new THREE.Group();
      group.name = `radiation-frame-${index}`;
      group.visible = index === 0;
      renderFluxCells(group, frame.fluxCells);
      frame.zones.forEach((zone) => renderRadiationZone(group, zone));
      radiationProjection.add(group);
      return group;
    });
    activeRadiationFrame = radiationFrameGroups.length ? 0 : -1;
    renderRadiationTrajectory(radiationProjection, risk.visualization.trajectory);
  }

  function setInspection(open: boolean) {
    satelliteSelected = open;
    reticle.classList.toggle("is-selected", open);
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
    const station = stationForLongitude(lon);
    const computeLoad =
      backend?.nodes?.length
        ? backend.nodes.reduce((total, node) => total + (node.gpu_util ?? 0), 0) / backend.nodes.length
        : 78 + Math.sin(nowS / 47) * 8 + Math.sin(nowS / 13) * 3;
    const latency = 38 + Math.sin(nowS / 19) * 5 + Math.cos(nowS / 29) * 2;
    const thermal = backend?.thermal?.highest_temp_c ?? 20.8 + Math.sin(nowS / 31) * 1.1;
    const battery = backend?.power?.battery_percent ?? 38 + Math.sin(nowS / 83) * 1.4;
    const solarInput = backend?.power?.solar_kw ?? 1.2 + Math.cos(nowS / 79) * 0.18;
    const eclipseMinutes = backend?.satellite?.time_to_eclipse_min ?? 11 + Math.sin(nowS / 67) * 1.3;
    const downlinkCapacity = backend?.downlink?.capacity_gb ?? 22 + Math.sin(nowS / 51) * 1.1;
    const eclipseLabel = `${Math.max(0, eclipseMinutes).toFixed(1)} min`;
    const downlinkLabel = `${downlinkCapacity.toFixed(1)} GB / 180 GB`;
    const latestCheckpoint = backend?.training?.latest_checkpoint ?? "ckpt-184900";
    const latestStatus = backend?.training?.latest_checkpoint_status ?? "suspect";
    const eccErrors = backend?.radiation?.ecc_errors_last_5min ?? 921;

    groundPoint.copy(normalized).applyAxisAngle(Y_AXIS, earth.rotation.y).multiplyScalar(1.04);

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
        : phaseLabel(backend?.radiation?.risk ?? "Elevated"),
      radiationExplanation: radiationRisk?.explanation,
      radiationRecommendedAction: radiationRisk?.recommendedAction,
      eccTrend: eccErrors > 850 ? "Rising" : "Nominal",
      trustedCheckpoint: backend?.training?.last_trusted_checkpoint ?? "ckpt-184500",
      latestCheckpoint: `${latestCheckpoint} ${latestStatus}`,
      downlink: downlinkLabel,
      rackHealth: thermal > 85 ? "heat watch" : phaseLabel(backend?.thermal?.cooling_status ?? "degraded"),
      rackHealthTone: thermal > 85 ? "orange" : "yellow",
      groundLink: station,
      orbitPhase: phaseLabel(backend?.satellite?.orbit_phase),
      patchConfidence: `${Math.round(86 + Math.sin(nowS / 90) * 2)}%`,
    };

    const positions = downlinkLine.geometry.attributes.position.array as Float32Array;
    positions[0] = satWorldPos.x;
    positions[1] = satWorldPos.y;
    positions[2] = satWorldPos.z;
    positions[3] = groundPoint.x;
    positions[4] = groundPoint.y;
    positions[5] = groundPoint.z;
    downlinkLine.geometry.attributes.position.needsUpdate = true;

    if (performance.now() - lastTelemetryAt > 250) {
      lastTelemetryAt = performance.now();
      const store = useWorldStore.getState();
      store.setTelemetry(telemetry);
      store.pushMetrics({
        battery,
        solar: solarInput,
        latency: Math.max(24, latency),
        computeLoad,
        eclipseMin: Math.max(0, eclipseMinutes),
        downlinkWindowGb: downlinkCapacity,
        eccErrors,
        thermal,
      });
    }
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
    const nowMs = simNow();
    const nowS = nowMs / 1000;

    earth.rotation.y = gmst(nowMs);
    clouds.rotation.y = earth.rotation.y + (nowS % 86400) * CLOUD_DRIFT;
    computeSunDirection(nowMs, sunDirection);
    sun.position.copy(sunDirection).multiplyScalar(50);
    sunSprite.position.copy(sunDirection).multiplyScalar(90);
    if (radiationFrameGroups.length > 1) {
      const loopPosition = (performance.now() / 1000) % radiationPlaybackSeconds;
      const nextFrame = Math.floor((loopPosition / radiationPlaybackSeconds) * radiationFrameGroups.length);
      if (nextFrame !== activeRadiationFrame) {
        radiationFrameGroups.forEach((group, index) => {
          group.visible = index === nextFrame;
        });
        activeRadiationFrame = nextFrame;
      }
    }
    radiationProjection.traverse((object) => {
      const material = (object as THREE.Mesh | THREE.Sprite).material as THREE.Material & { opacity?: number };
      if (material && typeof material.opacity === "number" && object.userData.baseOpacity) {
        const pulse = 0.78 + Math.sin(nowS * (object.userData.pulseRate ?? 0.7) + object.id * 0.17) * 0.22;
        material.opacity = THREE.MathUtils.clamp(object.userData.baseOpacity * pulse, 0.04, 0.88);
      }
    });

    const a = ((2 * Math.PI * nowS) / ORBIT_PERIOD_S) % (2 * Math.PI);
    satellite.position.set(Math.cos(a) * ORBIT_RADIUS, 0, Math.sin(a) * ORBIT_RADIUS);
    satellite.lookAt(0, 0, 0);

    const beacon = satellite.userData.beacon as THREE.Mesh<THREE.SphereGeometry, THREE.MeshBasicMaterial>;
    beacon.material.color.setHex(Math.sin((performance.now() / 1000) * 6) > 0 ? 0xff3333 : 0x441111);
    (satellite.userData.rackBay as THREE.Group).rotation.z = Math.sin((performance.now() / 1000) * 1.4) * 0.04;

    if (follow) {
      satellite.getWorldPosition(satWorldPos);
      controls.target.lerp(satWorldPos, 0.15);
    }

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

  const onPointerMove = (event: PointerEvent) => {
    setPointerFromEvent(event);
    satelliteHovered = intersectSatellite(event);
    renderer.domElement.style.cursor = satelliteHovered ? "pointer" : "grab";
  };

  const onPointerDown = () => {
    renderer.domElement.style.cursor = "grabbing";
  };

  const onPointerUp = () => {
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

  renderer.domElement.addEventListener("pointermove", onPointerMove);
  renderer.domElement.addEventListener("pointerdown", onPointerDown);
  renderer.domElement.addEventListener("pointerup", onPointerUp);
  renderer.domElement.addEventListener("pointerleave", onPointerLeave);
  renderer.domElement.addEventListener("click", onCanvasClick);
  reticle.addEventListener("click", onReticleClick);
  window.addEventListener("resize", resize);
  window.addEventListener("keydown", onKeyDown);
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container);

  const unsubscribers = [
    useWorldStore.subscribe((state) => state.worldState, updateWorldState),
    useWorldStore.subscribe((state) => state.radiationRisk, updateRadiationProjection),
    useWorldStore.subscribe((state) => state.simSpeed, setSpeed),
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
        satelliteSelected = open;
        reticle.classList.toggle("is-selected", open);
      },
    ),
  ];

  const api: OrbitScene = {
    start: () => {
      resize();
      updateWorldState(currentWorldState);
      updateRadiationProjection(useWorldStore.getState().radiationRisk);
      renderer.setAnimationLoop(animate);
    },
    destroy: () => {
      renderer.setAnimationLoop(null);
      window.removeEventListener("resize", resize);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointermove", onPointerMove);
      renderer.domElement.removeEventListener("pointerdown", onPointerDown);
      renderer.domElement.removeEventListener("pointerup", onPointerUp);
      renderer.domElement.removeEventListener("pointerleave", onPointerLeave);
      renderer.domElement.removeEventListener("click", onCanvasClick);
      reticle.removeEventListener("click", onReticleClick);
      window.removeEventListener("keydown", onKeyDown);
      unsubscribers.forEach((unsubscribe) => unsubscribe());
      controls.dispose();
      scene.traverse(disposeObject);
      dayMap.dispose();
      nightMap.dispose();
      cloudsMap.dispose();
      specMap.dispose();
      radiationGlowTexture.dispose();
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
