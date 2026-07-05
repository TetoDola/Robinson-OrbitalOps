import * as THREE from "three";

export function makeGlowTexture(inner: string, outer: string) {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D context was unavailable.");
  const grad = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, inner);
  grad.addColorStop(0.35, outer);
  grad.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(canvas);
}

/** Detailed datacenter satellite (bus, rack bay, solar wings, dish, beacon). */
export function buildSatellite(scale = 1.0) {
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
  glow.scale.setScalar(0.45 * scale);
  sat.add(glow);

  const fill = new THREE.PointLight(0xaaccff, 1.2, 3);
  fill.position.set(0.4, 0.6, 0.4);
  sat.add(fill);

  if (scale !== 1) sat.scale.setScalar(scale);
  return sat;
}
