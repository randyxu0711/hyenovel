import { motion } from "framer-motion";
import { WORLD, stageZoom, camTransform, type Stage } from "../lib/camera";
import { useViewport } from "../lib/useViewport";

export default function Camera(
  { stage, count, focus, children }:
  { stage: Stage; count: number; focus?: { x: number; y: number }; children: React.ReactNode },
) {
  const vp = useViewport();
  const z = stageZoom(stage, count, vp.w, vp.h);
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
