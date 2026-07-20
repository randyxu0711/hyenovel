import { useEffect, useRef } from "react";
import { DUST_LAYERS, layerShift } from "../lib/atmosphere";

// 三層視差塵埃(spec art-immersion §3B)。cam=相機位移目標(cameraPose 的 x/y);
// 不傳 cam(Single/lab)= 無視差,只有緩慢上漂。
// canvas 不吃全域減動 reset → 自守 matchMedia:減動時畫一張靜態幀,不跑 rAF。
const PAD = 200;   // 視差位移的超掃邊界(最大 |cam| × par ≈ 150px)

type Mote = { x: number; y: number; r: number; a: number; s: number; layer: number };

export default function Dust({ cam }: { cam?: { x: number; y: number } }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const camRef = useRef(cam);
  camRef.current = cam;

  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    const ctx = cv.getContext("2d"); if (!ctx) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    let W = 0, H = 0, raf = 0;
    let motes: Mote[] = [];
    const off = DUST_LAYERS.map(() => ({ x: 0, y: 0 }));
    const init = () => {
      W = cv.width = window.innerWidth; H = cv.height = window.innerHeight;
      motes = DUST_LAYERS.flatMap((L, li) =>
        Array.from({ length: L.n }, (): Mote => ({
          x: Math.random() * (W + 2 * PAD) - PAD, y: Math.random() * (H + 2 * PAD) - PAD,
          r: L.rMin + Math.random() * (L.rMax - L.rMin),
          a: Math.random() * 7, s: L.drift * (0.5 + Math.random()), layer: li,
        })));
    };
    const paint = (still: boolean) => {
      ctx.clearRect(0, 0, W, H);
      for (const d of motes) {
        const L = DUST_LAYERS[d.layer], o = off[d.layer];
        if (!still) {
          d.y -= d.s; if (d.y < -PAD) d.y = H + PAD; d.a += 0.015;
        }
        const tw = still ? 0.75 : 0.5 + 0.5 * Math.sin(d.a);
        ctx.beginPath(); ctx.arc(d.x + o.x, d.y + o.y, d.r, 0, 7);
        ctx.fillStyle = `rgba(228,210,160,${L.alpha * (0.35 + 0.65 * tw)})`; ctx.fill();
      }
    };
    const settle = () => {
      const c = camRef.current;
      DUST_LAYERS.forEach((L, i) => {
        const t = c ? layerShift(c, L.par) : { x: 0, y: 0 };
        off[i] = reduce ? t : { x: off[i].x + (t.x - off[i].x) * 0.055, y: off[i].y + (t.y - off[i].y) * 0.055 };
      });
    };
    // resize 必須連帶重畫:init() 對 cv.width 賦值會清空畫布點陣(canvas 規格行為),
    // 非減動模式下下一個 rAF 幀會蓋掉這張靜態幀、無感;但減動模式沒有 rAF loop,
    // 若只 init() 不重畫,畫面會停在「清空後沒人畫」的空白 —— 減動使用者看到的塵埃層會消失。
    const onResize = () => { init(); settle(); paint(true); };
    init();
    window.addEventListener("resize", onResize);
    if (reduce) { settle(); paint(true); }
    else {
      const loop = () => { settle(); paint(false); raf = requestAnimationFrame(loop); };
      raf = requestAnimationFrame(loop);
    }
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); };
  }, []);
  // 減動模式下相機換場(prop 變)→ 直接重畫一張定格(位移到位,不動畫)
  useEffect(() => {
    if (!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    // 觸發 onResize(見上):它會 init+settle+paint,新位移的靜態幀才會真的畫出來
    window.dispatchEvent(new Event("resize"));
  }, [cam?.x, cam?.y]);
  return <canvas ref={ref} className="dust" />;
}

// ⚠️ 減動分支的重畫走 resize 事件會重灑粒子——可接受(靜態幀,使用者看不到「跳」以外的東西,
// 且減動本來就不演)。canvas 座標是螢幕空間(.dust 在 .cam 外),不乘 0.75
//(memory 那條「.cam 內吃 0.75× 縮放」的雷是 .cam 內限定,.dust 在外不適用)。
