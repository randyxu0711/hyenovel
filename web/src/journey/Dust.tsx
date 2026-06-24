import { useEffect, useRef } from "react";

export default function Dust() {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    const ctx = cv.getContext("2d"); if (!ctx) return;
    let W = 0, H = 0, raf = 0;
    let motes: { x: number; y: number; r: number; a: number; s: number }[] = [];
    const init = () => {
      W = cv.width = window.innerWidth; H = cv.height = window.innerHeight;
      motes = Array.from({ length: 50 }, () => ({
        x: Math.random() * W, y: Math.random() * H,
        r: Math.random() * 1.1 + 0.2, a: Math.random(), s: Math.random() * 0.1 + 0.015,
      }));
    };
    init();
    window.addEventListener("resize", init);
    const loop = () => {
      ctx.clearRect(0, 0, W, H);
      for (const d of motes) {
        d.y -= d.s; if (d.y < -2) d.y = H + 2; d.a += 0.015;
        const tw = 0.5 + 0.5 * Math.sin(d.a);
        ctx.beginPath(); ctx.arc(d.x, d.y, d.r, 0, 7);
        ctx.fillStyle = `rgba(228,210,160,${0.1 + tw * 0.26})`; ctx.fill();
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", init); };
  }, []);
  return <canvas ref={ref} className="dust" />;
}
