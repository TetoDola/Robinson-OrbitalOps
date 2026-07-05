import * as THREE from "three";

const TEX = "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r166/examples/textures/planets/";

export interface FleetGlobe {
  start: () => void;
  destroy: () => void;
}

/**
 * The same photoreal Earth as the ops console (identical textures + shader),
 * but standalone: no satellite, reticle, network or telemetry — just the planet
 * rotating slowly as the centrepiece of the fleet constellation.
 */
export function createFleetGlobe(container: HTMLElement): FleetGlobe {
  const scene = new THREE.Scene();
  const rect = container.getBoundingClientRect();
  const w0 = Math.max(1, rect.width);
  const h0 = Math.max(1, rect.height);

  const camera = new THREE.PerspectiveCamera(42, w0 / h0, 0.05, 1000);
  const sunDirection = new THREE.Vector3(0.62, 0.3, 0.72).normalize();
  camera.position.copy(sunDirection.clone().multiplyScalar(5.4));
  camera.position.y += 0.5;
  camera.lookAt(0, 0, 0);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.domElement.className = "scene-canvas";
  renderer.setSize(w0, h0);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.appendChild(renderer.domElement);

  const sun = new THREE.DirectionalLight(0xffffff, 3);
  sun.position.copy(sunDirection).multiplyScalar(50);
  scene.add(sun);
  scene.add(new THREE.AmbientLight(0x223344, 0.3));

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
    }
    renderer.render(scene, camera);
    raf = requestAnimationFrame(frame);
  }

  return {
    start() {
      raf = requestAnimationFrame(frame);
    },
    destroy() {
      cancelAnimationFrame(raf);
      observer.disconnect();
      renderer.dispose();
      earthMaterial.dispose();
      [dayMap, nightMap, cloudsMap, specMap].forEach((t) => t.dispose());
      renderer.domElement.remove();
    },
  };
}
