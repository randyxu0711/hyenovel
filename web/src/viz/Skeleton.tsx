import { spline, beatsToPoints } from "../lib/spline";

export default function Skeleton({ beats, width }: { beats: number[]; width: number }) {
  const x0 = 20, x1 = 280, yb = 120, amp = 92;
  const pts = beatsToPoints(beats, x0, x1, yb, amp);
  const d = spline(pts);
  const max = Math.max(...beats);
  return (
    <svg viewBox="0 0 300 150" width={width} height={(width * 150) / 300}
      style={{ filter: "drop-shadow(0 0 5px rgba(240,228,200,.3)) drop-shadow(0 0 18px rgba(214,196,150,.15))" }}>
      <path d={`${d} L${x1},${yb} L${x0},${yb} Z`} fill="rgba(230,201,138,.10)" />
      <path d={d} fill="none" stroke="var(--bone)" strokeWidth={2.2} strokeLinecap="round" />
      {pts.map((p, i) => i % 2 === 0 && (
        <line key={`r${i}`} className="rib" x1={p[0]} y1={p[1]} x2={p[0]} y2={yb}
          stroke="#dccfae" strokeWidth={1} opacity={0.55} />
      ))}
      {pts.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={beats[i] >= max - 1e-6 ? 4 : 2.2}
          fill={beats[i] >= max - 1e-6 ? "var(--c-theme)" : "#f3ead2"} />
      ))}
    </svg>
  );
}
