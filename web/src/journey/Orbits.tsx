import { WORLD, ringRadii, RING_XSCALE } from "../lib/camera";

// 淡淡的軌道線:每圈一條同心橢圓,跟 worldPos 的卡位同源,讓「繞中心的環」讀得出來。
// bloom:入場時各圈由中心往外一圈圈綻放(種骨點火後的宇宙成形)。
export default function Orbits({ count, bloom }: { count: number; bloom?: boolean }) {
  const cx = WORLD.w / 2, cy = WORLD.h / 2;
  return (
    <svg className={`orbits${bloom ? " bloom" : ""}`} width={WORLD.w} height={WORLD.h}
      viewBox={`0 0 ${WORLD.w} ${WORLD.h}`} aria-hidden>
      {ringRadii(count).map((R, i) => (
        <ellipse key={i} cx={cx} cy={cy} rx={R * RING_XSCALE} ry={R}
          fill="none" stroke="rgba(226,208,160,.3)" strokeWidth={2.5} strokeDasharray="3 16"
          style={bloom ? { animationDelay: `${i * 0.13}s` } : undefined} />
      ))}
    </svg>
  );
}
