import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import "./journey.css";

export default function Overview({ onEnter }: { onEnter: () => void }) {
  const [lit, setLit] = useState(false);
  useEffect(() => { const t = requestAnimationFrame(() => setLit(true)); return () => cancelAnimationFrame(t); }, []);
  return (
    <motion.div className="overview" initial={{ opacity: 0 }} animate={{ opacity: lit ? 1 : 0 }}
      transition={{ duration: 2, ease: "easeOut" }} data-testid="overview">
      <div className="ov-title">
        <div className="ov-nm">鬣文</div>
        <div className="ov-en">hyenovel</div>
        <button className="ov-go" onClick={onEnter}>進入 ⟶</button>
      </div>
    </motion.div>
  );
}
