import { useEffect, useRef } from "react";

import { FLEET, ORBITS, HEALTH_LABEL } from "../fleet/fleetData";
import FleetGlobe from "./FleetGlobe";

interface ConstellationProps {
  selected: string;
  onSelect: (id: string) => void;
}

function ellipsePoint(orbit: number, angle: number): { x: number; y: number } {
  const o = ORBITS[orbit];
  const t = (o.tilt * Math.PI) / 180;
  const px = o.rx * Math.cos(angle);
  const py = o.ry * Math.sin(angle);
  const x = px * Math.cos(t) - py * Math.sin(t) + 400;
  const y = px * Math.sin(t) + py * Math.cos(t) + 230;
  return { x: (x / 800) * 100, y: (y / 460) * 100 };
}

export default function Constellation({ selected, onSelect }: ConstellationProps) {
  const nodeRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const anglesRef = useRef<number[]>(FLEET.map((a) => (a.angle * Math.PI) / 180));

  useEffect(() => {
    let raf = 0;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const tick = () => {
      FLEET.forEach((asset, i) => {
        if (!reduce) anglesRef.current[i] += asset.speed * 0.012;
        const p = ellipsePoint(asset.orbit, anglesRef.current[i]);
        const el = nodeRefs.current[i];
        if (el) {
          el.style.left = `${p.x}%`;
          el.style.top = `${p.y}%`;
        }
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="const-field" aria-hidden="false">
      <FleetGlobe />
      <svg className="const-orbits" viewBox="0 0 800 460" preserveAspectRatio="none" aria-hidden="true">
        {ORBITS.map((o, i) => (
          <ellipse key={i} cx="400" cy="230" rx={o.rx} ry={o.ry} transform={`rotate(${o.tilt} 400 230)`} />
        ))}
      </svg>
      <div className="const-nodes">
        {FLEET.map((asset, i) => (
          <button
            key={asset.id}
            ref={(el) => {
              nodeRefs.current[i] = el;
            }}
            className={`const-node ${asset.health}${asset.id === selected ? " is-sel" : ""}`}
            title={`${asset.id} · ${HEALTH_LABEL[asset.health]}`}
            aria-label={`${asset.id}, ${HEALTH_LABEL[asset.health]}`}
            onClick={() => onSelect(asset.id)}
            type="button"
          >
            <i />
          </button>
        ))}
      </div>
    </div>
  );
}
