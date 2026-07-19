import { useEffect, useRef, useState } from "react";
import { worldPos, ringRadii, WORLD, RING_XSCALE, fitScale, camTransform, fitContent, BONE } from "../lib/camera";
import { useViewport } from "../lib/useViewport";
import Dust from "../journey/Dust";
import "./lab.css";

// /lab/catalog — 佈局實驗台。fit-to-content 當「開場/回家」預設構圖;之後可滾輪縮放、拖曳平移。
// 幾何同源:fitContent/BONE/MAX_ZOOM 一律 import camera.ts(spec:不許複製再分岔)。
// 假視窗用當下視窗長寬比 → 裁切如實。替身骨=真實尺寸方塊,不打 viz。
const BONE_W = BONE.w, BONE_H = BONE.h;
const COUNTS = [3, 7, 15, 22, 30];
const ZOOM_MIN = 0.1, ZOOM_MAX = 1.3;

type Mode = "current" | "fit";
type View = { s: number; tx: number; ty: number };

export default function CatalogLab() {
  const vp = useViewport();
  const [count, setCount] = useState(7);
  const [mode, setMode] = useState<Mode>("fit");
  const [view, setView] = useState<View | null>(null);   // null = 用預設構圖;非 null = 使用者已縮放/平移
  const frameRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);

  const FW = Math.min(920, vp.w - 380);
  const FH = Math.round(FW * (vp.h / vp.w));

  const baseZoom = mode === "current"
    ? fitScale(WORLD, FW, FH) * 1.04   // 舊固定世界模式(被淘汰的 K.catalog),留作 A/B 對照
    : fitContent(count, FW, FH);
  const baseCam = camTransform(WORLD, FW, FH, baseZoom);
  const eff: View = view ?? { s: baseZoom, tx: baseCam.x, ty: baseCam.y };
  const effRef = useRef(eff); effRef.current = eff;

  // 滾輪縮放朝游標(native listener:才能 preventDefault 擋頁面捲動)
  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const cur = effRef.current;
      const s2 = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, cur.s * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
      const wx = (mx - cur.tx) / cur.s, wy = (my - cur.ty) / cur.s;
      setView({ s: s2, tx: mx - wx * s2, ty: my - wy * s2 });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const onPointerDown = (e: React.PointerEvent) => {
    drag.current = { x: e.clientX, y: e.clientY };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x, dy = e.clientY - drag.current.y;
    drag.current = { x: e.clientX, y: e.clientY };
    const cur = effRef.current;
    setView({ s: cur.s, tx: cur.tx + dx, ty: cur.ty + dy });
  };
  const onPointerUp = () => { drag.current = null; };

  const reset = () => setView(null);
  const pick = (c: number) => { setCount(c); setView(null); };
  const pickMode = (m: Mode) => { setMode(m); setView(null); };

  const rings = ringRadii(count).length;
  const cx = WORLD.w / 2, cy = WORLD.h / 2;

  let clipped = 0;
  const bones = Array.from({ length: count }, (_, i) => {
    const p = worldPos(i, WORLD, count);
    const sx = eff.tx + p.x * eff.s, sy = eff.ty + p.y * eff.s;
    const hw = (BONE_W / 2) * eff.s, hh = (BONE_H / 2) * eff.s;
    const cut = sx - hw < 0 || sx + hw > FW || sy - hh < 0 || sy + hh > FH;
    if (cut) clipped++;
    return { i, p, cut };
  });
  const boneScreenPx = Math.round(BONE_W * eff.s);

  return (
    <div className="lab">
      <Dust />
      <div className="lab-bar">
        <span className="lab-tag">/lab/catalog · fit-to-content 開場 · 滾輪縮放 · 拖曳平移</span>
        <div className="lab-seg">
          <button className={mode === "current" ? "on" : ""} onClick={() => pickMode("current")}>固定世界(現況)</button>
          <button className={mode === "fit" ? "on" : ""} onClick={() => pickMode("fit")}>fit-to-content(A)</button>
        </div>
        <div className="lab-slugs">
          {COUNTS.map(c => (
            <button key={c} className={c === count ? "on" : ""} onClick={() => pick(c)}>{c} 篇</button>
          ))}
          <button onClick={reset} style={{ marginLeft: 8 }}>⟲ 重置視角</button>
        </div>
      </div>

      <div className="lab-stage" style={{ flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", gap: 24, fontSize: 13, opacity: 0.8, letterSpacing: 0.5 }}>
          <span>{rings} 圈</span>
          <span style={{ color: clipped ? "#e88" : "inherit" }}>
            {clipped ? `⚑ ${clipped} 顆出框` : "✓ 全在框內"}
          </span>
          <span>骨寬 {boneScreenPx}px（可讀性代理）</span>
          <span style={{ opacity: 0.5 }}>zoom {eff.s.toFixed(3)}{view ? " · 已手動" : " · 預設"}</span>
        </div>

        <div ref={frameRef}
          onPointerDown={onPointerDown} onPointerMove={onPointerMove}
          onPointerUp={onPointerUp} onPointerLeave={onPointerUp}
          style={{
            width: FW, height: FH, position: "relative", overflow: "hidden",
            border: "1px solid rgba(255,255,255,0.18)", borderRadius: 6,
            cursor: drag.current ? "grabbing" : "grab", touchAction: "none",
            background: "radial-gradient(120% 90% at 50% 45%, rgba(30,34,52,0.55), rgba(8,9,16,0.9))",
          }}>
          <div style={{
            position: "absolute", width: WORLD.w, height: WORLD.h, transformOrigin: "0 0",
            transform: `translate(${eff.tx}px, ${eff.ty}px) scale(${eff.s})`,
          }}>
            {ringRadii(count).map((R, r) => (
              <div key={r} style={{
                position: "absolute", left: cx, top: cy, transform: "translate(-50%,-50%)",
                width: R * RING_XSCALE * 2, height: R * 2, borderRadius: "50%",
                border: "1px solid rgba(150,170,255,0.16)",
              }} />
            ))}
            <div style={{
              position: "absolute", left: cx, top: cy, transform: "translate(-50%,-50%)",
              width: 46, height: 46, borderRadius: "50%",
              background: "radial-gradient(circle, rgba(255,240,200,0.95), rgba(255,190,120,0.15))",
            }} />
            {bones.map(({ i, p, cut }) => (
              <div key={i} style={{
                position: "absolute", left: p.x, top: p.y, transform: "translate(-50%,-50%)",
                width: BONE_W, height: BONE_H, borderRadius: 8,
                border: `1px solid ${cut ? "rgba(255,140,140,0.9)" : "rgba(180,200,255,0.35)"}`,
                background: cut ? "rgba(120,40,40,0.28)" : "rgba(40,48,72,0.4)",
                display: "flex", alignItems: "center", justifyContent: "center",
                color: "rgba(230,236,255,0.9)", fontSize: 34, letterSpacing: 2,
              }}>
                篇{String(i + 1).padStart(2, "0")}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
