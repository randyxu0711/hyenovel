import { useEffect, useRef } from "react";

// 入口標題:畫在 canvas 上(從第一幀就是它,不換替身)。點火 → 把畫好的字取樣成一堆粒子,
// 每顆各自往左飛散 + 淡出(靠右的先起飛=風由右往左)。不用 mask/SVG 濾鏡 —— 真的一顆顆飛走。
const W = 600, H = 320;
const SERIF = '52px "Source Han Serif TC","Noto Serif TC","Songti TC",serif';
const SANS = '15px "Inter","Noto Sans TC",sans-serif';

type P = { x: number; y: number; r: number; g: number; b: number; a: number; vx: number; vy: number; delay: number };

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath(); ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

// jsdom/測試環境的 getContext 會拋錯而非回 null → 包起來
function get2d(c: HTMLCanvasElement): CanvasRenderingContext2D | null {
  try { return c.getContext("2d"); } catch { return null; }
}

// 只畫字、不清畫布 —— burst 時拿來當「淡出的原字」疊在粒子之上,把材質切換的突兀感抹掉
function paintTitle(ctx: CanvasRenderingContext2D) {
  ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
  const ls = (v: string) => { (ctx as unknown as { letterSpacing: string }).letterSpacing = v; };
  ls("12px"); ctx.fillStyle = "#f3ecd6"; ctx.font = SERIF; ctx.fillText("鬣文", W / 2, 126);
  ls("7.5px"); ctx.fillStyle = "#8c8265"; ctx.font = SANS; ctx.fillText("HYENOVEL", W / 2, 170);
  ls("0px"); ctx.strokeStyle = "rgba(220,200,150,.3)"; ctx.lineWidth = 1;
  roundRect(ctx, 230, 222, 140, 46, 23); ctx.stroke();
  ls("3px"); ctx.fillStyle = "#b9ad88"; ctx.font = SANS; ctx.fillText("進入 ⟶", W / 2, 251);
  ls("0px");
}

function drawTitle(ctx: CanvasRenderingContext2D) {
  ctx.clearRect(0, 0, W, H);
  paintTitle(ctx);
}

const REVEAL = 240;   // 原字在此毫秒內淡出,和粒子起飛交疊 → 溶解而非硬切

export default function TitleBurst({ igniting, onEnter }: { igniting: boolean; onEnter: () => void }) {
  const cvs = useRef<HTMLCanvasElement>(null);
  const raf = useRef(0);
  const dpr = Math.min(2, (typeof window !== "undefined" && window.devicePixelRatio) || 1);

  useEffect(() => {
    const c = cvs.current; if (!c) return;
    c.width = W * dpr; c.height = H * dpr;
    const ctx = get2d(c); if (!ctx || !ctx.scale) return;   // jsdom/測試環境無 canvas → 靜默略過
    ctx.scale(dpr, dpr);
    drawTitle(ctx);
    let live = true;
    (document as unknown as { fonts?: { ready: Promise<unknown> } }).fonts?.ready.then(() => { if (live) drawTitle(ctx); });
    return () => { live = false; };
  }, [dpr]);

  useEffect(() => {
    if (!igniting) return;
    const c = cvs.current; if (!c) return;
    const ctx = get2d(c); if (!ctx || !ctx.getImageData) return;
    const img = ctx.getImageData(0, 0, c.width, c.height).data;
    const parts: P[] = [];
    const step = 2;   // 取樣越密顆粒越細、字越清楚(step2≈step3 的 2.25 倍粒子,一次性 burst 吃得下)
    for (let y = 0; y < H; y += step) for (let x = 0; x < W; x += step) {
      const i = (Math.floor(y * dpr) * c.width + Math.floor(x * dpr)) * 4;
      const a = img[i + 3];
      if (a > 40) parts.push({
        x, y, r: img[i], g: img[i + 1], b: img[i + 2], a: a / 255,
        vx: -(1.2 + Math.random() * 2.6), vy: (Math.random() - 0.5) * 1.1,
        delay: ((W - x) / W) * 450,       // 靠右的先起飛 → 風由右往左
      });
    }
    const start = performance.now();
    const tick = (now: number) => {
      const t = now - start;
      ctx.clearRect(0, 0, W, H);
      let alive = 0;
      for (const p of parts) {
        ctx.fillStyle = `rgb(${p.r},${p.g},${p.b})`;
        if (t < p.delay) { ctx.globalAlpha = p.a; ctx.fillRect(p.x, p.y, 1.6, 1.6); alive++; continue; }
        const dt = (t - p.delay) / 1000;
        const a = p.a * (1 - dt / 1.1);
        if (a > 0.02) {
          ctx.globalAlpha = a;
          ctx.fillRect(p.x + p.vx * dt * 60, p.y + p.vy * dt * 60, 1.6, 1.6);
          alive++;
        }
      }
      ctx.globalAlpha = 1;
      // 開場疊一層正在淡出的原字:眼睛看到的是字「溶」成粒子,不是瞬間換成點陣
      if (t < REVEAL) { ctx.globalAlpha = 1 - t / REVEAL; paintTitle(ctx); ctx.globalAlpha = 1; }
      if (alive > 0) raf.current = requestAnimationFrame(tick);
    };
    cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [igniting, dpr]);

  return (
    <div className={`ov-canvas-wrap${igniting ? " igniting" : ""}`} style={{ position: "relative", width: W, height: H }}>
      <canvas ref={cvs} style={{ width: W, height: H, display: "block" }} aria-hidden />
      <button className="ov-enter-hit" aria-label="進入" onClick={onEnter}
        style={{ position: "absolute", left: 230, top: 222, width: 140, height: 46 }} />
    </div>
  );
}
