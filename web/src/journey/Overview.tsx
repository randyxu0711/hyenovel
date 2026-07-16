import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import TitleBurst from "./TitleBurst";
import "./journey.css";

export const WEATHER_MS = 1500;
const reduceMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

// 入口:標題本體(canvas)被風吹散成粒子往左飛,飛淨後才 onEnter 交棒給 catalog。
// catalog 中心的種骨(NascentStar)與軌道(Orbits)是「真正的物體」,由它們綻放入場,不畫替身。
export default function Overview({ onEnter }: { onEnter: () => void }) {
  const [lit, setLit] = useState(false);
  const [igniting, setIgniting] = useState(false);
  useEffect(() => { const t = requestAnimationFrame(() => setLit(true)); return () => cancelAnimationFrame(t); }, []);

  const enter = () => {
    if (igniting) return;
    if (reduceMotion()) { onEnter(); return; }
    setIgniting(true);
    window.setTimeout(onEnter, WEATHER_MS);
  };
  useEffect(() => {
    if (igniting) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Enter") enter(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [igniting]);

  return (
    <motion.div className="overview" initial={{ opacity: 0 }} animate={{ opacity: lit ? 1 : 0 }}
      transition={{ duration: 2, ease: "easeOut" }} data-testid="overview">
      <TitleBurst igniting={igniting} onEnter={enter} />
    </motion.div>
  );
}
