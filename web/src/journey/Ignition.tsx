import { useEffect } from "react";
import "./journey.css";

export const IGNITION_MS = 2600;
const reduceMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

// 種骨點火入口:標題風化(右→左散亂吹散,保持銳利)→ 火種緩緩升起點火 → 綻放成同心軌道 + 故事星凝現。
// 純一次性視覺;播完(或 reduced-motion 立即)呼叫 onDone 交棒給 catalog。
export default function Ignition({ onDone }: { onDone: () => void }) {
  const reduce = reduceMotion();
  useEffect(() => {
    if (reduce) { onDone(); return; }
    const t = window.setTimeout(onDone, IGNITION_MS);
    return () => clearTimeout(t);
  }, [reduce, onDone]);

  if (reduce) return <div className="ignition" data-testid="ignition" />;

  return (
    <div className="ignition" data-testid="ignition">
      <div className="ign-ring ign-r4" /><div className="ign-ring ign-r3" />
      <div className="ign-ring ign-r2" /><div className="ign-ring ign-r1" />
      <span className="ign-p" style={{ left: "40%", top: "44%", width: 6, height: 6 }} />
      <span className="ign-p" style={{ left: "60%", top: "58%", width: 7, height: 7 }} />
      <span className="ign-p" style={{ left: "68%", top: "42%", width: 5, height: 5 }} />
      <span className="ign-p" style={{ left: "32%", top: "58%", width: 6, height: 6 }} />
      <div className="ign-seed" />
      <svg className="ign-weather" viewBox="0 0 900 360" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
        <defs>
          <filter id="ign-wf" x="-20%" y="-25%" width="140%" height="150%">
            <feTurbulence type="fractalNoise" baseFrequency="0.34 0.42" numOctaves="2" seed="11" result="grain" />
            <feComponentTransfer in="grain" result="gmask">
              <feFuncA type="linear" slope="1" intercept="0">
                <animate attributeName="slope" dur="1.5s" begin="0s" fill="freeze"
                  keyTimes="0;0.4;1" values="1;1;5" />
                <animate attributeName="intercept" dur="1.5s" begin="0s" fill="freeze"
                  keyTimes="0;0.4;1" values="1;1;-1.4" />
              </feFuncA>
            </feComponentTransfer>
            <feTurbulence type="turbulence" baseFrequency="0.05 0.09" numOctaves="2" seed="3" result="jn" />
            <feDisplacementMap in="SourceGraphic" in2="jn" xChannelSelector="R" yChannelSelector="G" scale="0" result="jit">
              <animate attributeName="scale" dur="1.5s" begin="0s" fill="freeze" keyTimes="0;0.4;1" values="0;0;9" />
            </feDisplacementMap>
            <feComposite in="jit" in2="gmask" operator="in" />
          </filter>
        </defs>
        <g filter="url(#ign-wf)" textAnchor="middle" fill="#f3ecd6" fontFamily="var(--serif)">
          <text x="450" y="150" fontSize="46" letterSpacing="12">鬣文</text>
          <text x="450" y="188" fontSize="13" letterSpacing="11" fill="#8c8265">HYENOVEL</text>
        </g>
      </svg>
    </div>
  );
}
