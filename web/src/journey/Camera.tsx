import { motion } from "framer-motion";
import { WORLD, cameraPose, type Stage } from "../lib/camera";
import { useViewport } from "../lib/useViewport";
import { EASE_HOUSE, D_CAM } from "../lib/motion";

export default function Camera(
  { stage, count, focus, children }:
  { stage: Stage; count: number; focus?: { x: number; y: number }; children: React.ReactNode },
) {
  const vp = useViewport();
  const t = cameraPose(stage, count, vp.w, vp.h, focus);
  const blur = stage === "overview" ? 6 : 0;
  return (
    <div className="stage">
      <motion.div className="cam"
        initial={false}
        animate={{ x: t.x, y: t.y, scale: t.scale, filter: `blur(${blur}px)` }}
        transition={{ duration: D_CAM, ease: EASE_HOUSE }}
        style={{ width: WORLD.w, height: WORLD.h, transformOrigin: "0 0" }}>
        {children}
      </motion.div>
    </div>
  );
}
