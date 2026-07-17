import { useEffect, useRef } from "react";

// 分子雲塌縮 —— 孕育第一段(analyst 跑中,分鐘級)。
// 這時**真的還沒有任何資料**,所以不畫骨:塵埃朝這個槽位聚攏、旋轉收緊,落進核心就從外圈補進來。
//
// 它是**穩態,不是進度條**。我們沒有辦法知道 analyst 還要跑多久(SDK 不報),假骨逐段畫線是在
// 假裝有完成度;塌縮只承諾「還在聚」——那是真的。動勢來自密度與轉速,不來自一個編出來的百分比。
//
// 角動量守恆:角速度 ∝ 1/r,半徑越小轉越快;重力:越近落越快。兩條都是真物理,不是隨手挑的曲線。
// 橢圓比例對齊 camera.ts 的 RING_XSCALE,讓塌縮盤躺在這片星空的同一個平面上。
//
// canvas 不吃 theme.css 的全域減動 reset → 自守 matchMedia(同 TitleBurst 前例)。

const W = 310, H = 190;
const N = 140;
const R0 = 128;      // 外圈:補進來的半徑
const CORE = 6;      // 核心:落到這裡就重生
const XS = 1.5;      // = camera.ts 的 RING_XSCALE
// 粒子尺寸得撐得住相機縮放:Camera 在 catalog 把 WORLD(2600×1500)縮進視窗,約 0.75×,
// 而塌縮在 .cam 裡面 → 吃這個縮放(Dust 是 position:fixed,不吃,所以它小也看得見)。
// 這裡的 px 是 canvas 座標,上螢幕還要再 ×0.75:設 1.6–4.4 → 實得 1.2–3.3,才不會掉進次像素。
const R_MIN = 1.6, R_MAX = 4.4;

type P = { r: number; a: number; vr: number; z: number };

const spawn = (r = CORE + Math.random() * R0): P => ({
  r,
  a: Math.random() * Math.PI * 2,
  vr: 0.22 + Math.random() * 0.5,     // 徑向落速
  z: 0.35 + Math.random() * 0.65,     // 每顆的亮度/大小權重
});

export default function CloudCollapse({ width = 300 }: { width?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current;
    const ctx = cv?.getContext("2d");
    if (!cv || !ctx) return;                 // jsdom 無 canvas → 靜默不畫(元素仍在)

    const dpr = Math.min(2, window.devicePixelRatio || 1);
    cv.width = W * dpr; cv.height = H * dpr;
    ctx.scale(dpr, dpr);

    const cx = W / 2, cy = H / 2;
    const ps = Array.from({ length: N }, () => spawn());

    const paint = () => {
      ctx.clearRect(0, 0, W, H);
      // 核心微光:重力中心,讓塵埃有個「朝著誰去」
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, 30);
      g.addColorStop(0, "rgba(248,240,216,.34)");
      g.addColorStop(1, "rgba(248,240,216,0)");
      ctx.fillStyle = g;
      ctx.fillRect(cx - 34, cy - 34, 68, 68);

      for (const p of ps) {
        const t = 1 - Math.min(1, p.r / R0);          // 越近核心越亮越大
        ctx.globalAlpha = Math.min(1, 0.1 + t * 0.85) * p.z;
        ctx.fillStyle = t > 0.72 ? "#f8f0d8" : "#d8c9a4";
        ctx.beginPath();
        ctx.arc(cx + Math.cos(p.a) * p.r * XS, cy + Math.sin(p.a) * p.r,
                (R_MIN + t * (R_MAX - R_MIN)) * p.z, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    };

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      paint();                                // 減動:一張靜止的雲,不轉不聚
      return;
    }

    let raf = 0;
    const tick = () => {
      for (const p of ps) {
        const t = 1 - Math.min(1, p.r / R0);
        p.r -= p.vr * (0.3 + t * 1.6);        // 重力:越近落越快
        p.a += 0.9 / Math.max(14, p.r);       // 角動量守恆:r 越小轉越快
        if (p.r <= CORE) Object.assign(p, spawn(R0));
      }
      paint();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={ref} data-testid="collapsing" className="cloud-collapse" aria-hidden
    style={{ width, height: (width * H) / W }} />;
}
