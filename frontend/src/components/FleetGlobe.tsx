import { useEffect, useRef } from "react";

import { createFleetGlobe } from "../scene/fleetGlobe";

export default function FleetGlobe() {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return undefined;
    const globe = createFleetGlobe(ref.current);
    globe.start();
    return () => globe.destroy();
  }, []);

  return <div className="const-globe3d" ref={ref} aria-hidden="true" />;
}
