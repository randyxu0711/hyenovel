import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { WORLD, cameraPose, type Stage } from "../lib/camera";
import { useViewport } from "../lib/useViewport";
import { EASE_HOUSE, camDuration } from "../lib/motion";

export default function Camera(
  { stage, count, focus, children }:
  { stage: Stage; count: number; focus?: { x: number; y: number }; children: React.ReactNode },
) {
  const vp = useViewport();
  const t = cameraPose(stage, count, vp.w, vp.h, focus);
  const blur = stage === "overview" ? 6 : 0;
  // 相機時長屬於相機自己的知識:退場(離開單篇)比進場快 —— 見 lib/motion.ts camDuration。
  // 這一輪 render 時 prev 還是上一個 stage,正好是轉場的來向;effect 之後才推進。
  const prev = useRef<Stage | null>(null);
  const duration = camDuration(prev.current, stage);
  useEffect(() => { prev.current = stage; }, [stage]);
  return (
    <div className="stage">
      <motion.div className="cam"
        initial={false}
        animate={{ x: t.x, y: t.y, scale: t.scale, filter: `blur(${blur}px)` }}
        transition={{ duration, ease: EASE_HOUSE }}
        style={{ width: WORLD.w, height: WORLD.h, transformOrigin: "0 0" }}>
        {children}
      </motion.div>
    </div>
  );
}
