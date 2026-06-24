import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { WORLD, fitScale, zoomFor, camTransform, type Stage } from "../lib/camera";

function useViewport() {
  const [vp, setVp] = useState({
    w: typeof window !== "undefined" ? window.innerWidth : 1280,
    h: typeof window !== "undefined" ? window.innerHeight : 720,
  });
  useEffect(() => {
    const on = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return vp;
}

export default function Camera(
  { stage, focus, children }: { stage: Stage; focus?: { x: number; y: number }; children: React.ReactNode },
) {
  const vp = useViewport();
  const fit = fitScale(WORLD, vp.w, vp.h);
  const z = zoomFor(stage, fit);
  const t = camTransform(WORLD, vp.w, vp.h, z, stage === "single" ? focus : undefined);
  const blur = stage === "overview" ? 6 : 0;
  return (
    <div className="stage">
      <motion.div className="cam"
        initial={false}
        animate={{ x: t.x, y: t.y, scale: t.scale, filter: `blur(${blur}px)` }}
        transition={{ duration: 1.4, ease: [0.66, 0, 0.2, 1] }}
        style={{ width: WORLD.w, height: WORLD.h, transformOrigin: "0 0" }}>
        {children}
      </motion.div>
    </div>
  );
}
