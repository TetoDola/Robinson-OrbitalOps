import { useEffect, useRef } from "react";

import { createOrbitScene } from "../scene/orbitScene";

export default function SceneViewport() {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }

    const scene = createOrbitScene(containerRef.current);
    scene.start();

    return () => {
      scene.destroy();
    };
  }, []);

  return <div className="scene-viewport" ref={containerRef} />;
}
