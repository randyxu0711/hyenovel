import { useEffect, useMemo, useRef, useState } from "react";
import { spline, type Pt } from "../lib/spline";
import Skeleton from "../viz/Skeleton";
import { streamCritique, getViz, cancelCritique } from "../data/client";
import type { VizData } from "../types";

const W = 310, H = 190;
// 象徵性脊椎:分析途中還沒有真資料,先給一根有起伏的骨(render 完才 snap 成真實星骨)
const SP: Pt[] = [[18, 98], [70, 66], [120, 118], [170, 72], [214, 112], [262, 80], [292, 100]];

type Rib = { x: number; y: number; ex: number; ey: number; r: number; gold: boolean };

function onPoly(p: Pt[], f: number) {
  const seg = f * (p.length - 1);
  const i = Math.min(p.length - 2, Math.floor(seg));
  const t = seg - i;
  const [x1, y1] = p[i], [x2, y2] = p[i + 1];
  let tx = x2 - x1, ty = y2 - y1; const l = Math.hypot(tx, ty) || 1; tx /= l; ty /= l;
  return { x: x1 + (x2 - x1) * t, y: y1 + (y2 - y1) * t, nx: -ty, ny: tx };
}

function buildRibs(): Rib[] {
  const specs = [
    { f: .12, up: true, gold: true, len: 38 }, { f: .22, up: false, gold: false, len: 26 },
    { f: .34, up: true, gold: false, len: 30 }, { f: .44, up: false, gold: true, len: 46 },
    { f: .55, up: true, gold: false, len: 34 }, { f: .66, up: false, gold: false, len: 24 },
    { f: .76, up: true, gold: true, len: 42 }, { f: .85, up: false, gold: false, len: 28 },
    { f: .93, up: true, gold: false, len: 30 },
  ];
  return specs.map(s => {
    const o = onPoly(SP, s.f);
    let nx = o.nx, ny = o.ny;
    if (s.up ? ny > 0 : ny < 0) { nx = -nx; ny = -ny; }     // 主題朝上、意象朝下
    return { x: o.x, y: o.y, ex: o.x + nx * s.len, ey: o.y + ny * s.len, r: s.gold ? 4 : 2.6, gold: s.gold };
  });
}

// 相位 → 生長階(單調遞增):1 脊椎描出、2 肋抽長、3 金節綻放、4 成形(snap 真實星骨)
const WORD = ["凝聚", "凝聚", "讀出結構", "聽見重音", "成形"];

export default function FormingStar(
  { slug, title, onDone, onAbort }:
  { slug: string; title: string; onDone: (slug: string) => void; onAbort: () => void },
) {
  const d = useMemo(() => spline(SP), []);
  const ribs = useMemo(buildRibs, []);
  const [step, setStep] = useState(1);
  const [real, setReal] = useState<VizData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const started = useRef(false);
  const alive = useRef(true);

  const bump = (n: number) => setStep(s => Math.max(s, n));

  const run = async () => {
    setErr(null); setStep(1); setReal(null);
    try {
      // 帶 title:後端 Run 會記住,重整後 /running 才有名字可重接
      for await (const ev of streamCritique(slug, title)) {
        if (!alive.current) return;
        if (ev.event === "phase") {
          const { name, status } = ev.data;
          if (name === "analyst") bump(status === "ok" ? 2 : 1);
          else if (name === "criticizer") bump(status === "ok" ? 3 : 2);
          else if (name === "render") bump(status === "ok" ? 4 : 3);
        } else if (ev.event === "done") {
          try { const v = await getViz(slug); if (alive.current) setReal(v); } catch { /* 仍會跳轉 */ }
          bump(4);
        } else if (ev.event === "error") {
          if (ev.data.where === "cancel") { onAbort(); return; }   // 使用者取消 → 安靜收掉
          setErr(`${ev.data.where}:${ev.data.message}`); return;
        }
      }
    } catch (e) {
      if (alive.current) setErr(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    alive.current = true;
    if (!started.current) { started.current = true; run(); }
    return () => { alive.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 成形完成:讓真實星骨亮一下,再潛進那篇
  useEffect(() => {
    if (step >= 4) {
      const t = setTimeout(() => onDone(slug), real ? 1500 : 700);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, real]);

  if (err) return (
    <div className="forming">
      <svg className="forming-sym dim" viewBox={`0 0 ${W} ${H}`} width={300} height={(300 * H) / W}>
        <path d={d} fill="none" stroke="var(--bone)" strokeWidth={2.2} strokeLinecap="round" opacity={0.25} />
      </svg>
      <div className="forming-cap">{title}</div>
      <p className="add-err" style={{ textAlign: "center", maxWidth: 320 }}>成形中斷:{err}</p>
      <div className="forming-acts">
        <button className="add-ghost" onClick={onAbort}>擱置</button>
        <button className="add-go" onClick={() => { started.current = true; run(); }}>再試一次</button>
      </div>
    </div>
  );

  return (
    <div className={`forming ${step >= 4 ? "settled" : ""}`}>
      <div className="forming-halo" />
      <svg className={`forming-sym ${real ? "fade" : ""}`} viewBox={`0 0 ${W} ${H}`} width={300} height={(300 * H) / W}
        style={{ filter: "drop-shadow(0 0 6px rgba(240,228,200,.32)) drop-shadow(0 0 20px rgba(214,196,150,.16))" }}>
        <path className="f-spine" d={d} pathLength={1} fill="none" stroke="var(--bone)"
          strokeWidth={2.2} strokeLinecap="round" style={{ strokeDashoffset: step >= 1 ? 0 : 1 }} />
        {ribs.map((b, i) => (
          <line key={`r${i}`} className="f-rib" x1={b.x} y1={b.y} x2={b.ex} y2={b.ey} pathLength={1}
            stroke="#dccfae" strokeWidth={1.1} strokeLinecap="round"
            style={{ strokeDashoffset: step >= 2 ? 0 : 1, opacity: step >= 2 ? 0.76 : 0, transitionDelay: `${i * 0.1}s` }} />
        ))}
        {ribs.map((b, i) => (
          <circle key={`c${i}`} cx={b.ex} cy={b.ey} r={step >= 2 ? b.r : 0}
            fill={b.gold && step >= 3 ? "#ecc98a" : "#f3ead2"} style={{ transitionDelay: `${0.2 + i * 0.1}s` }} />
        ))}
      </svg>
      {real && <div className="forming-real"><Skeleton viz={real} width={300} /></div>}
      <div className="forming-cap">{title}</div>
      <div className="forming-word">{WORD[Math.min(4, step)]}<span className="forming-dots" /></div>
      {step < 4 && (
        <button className="add-ghost forming-cancel" onClick={() => cancelCritique(slug)}>取消</button>
      )}
    </div>
  );
}
