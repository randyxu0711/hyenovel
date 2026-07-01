import { useEffect, useState } from "react";
import { getViz } from "../data/client";
import BoneStage from "./BoneStage";
import NodeTalk from "./NodeTalk";
import Dust from "../journey/Dust";
import type { VizData } from "../types";
import "./lab.css";

const SLUGS = ["s01", "s02", "s03", "s04"];
type Mode = "calm" | "axis" | "chain";
const MODES: { k: Mode; label: string }[] = [
  { k: "calm", label: "骨（安靜）" }, { k: "axis", label: "文本軸" }, { k: "chain", label: "因果鏈" },
];
const VAR: Record<string, string> = {
  technique: "var(--c-technique)", effect: "var(--c-effect)", theme: "var(--c-theme)",
  motif: "var(--c-motif)", beat: "var(--c-beat)", character: "var(--c-character)",
};
const FLAG: Record<string, string> = { orphan: "孤兒技法", overloaded: "過載", hollow: "單薄" };
const flagOf = (viz: VizData | null, id: string | null) =>
  (viz && id ? (viz.diag[id] ?? []).map(d => FLAG[d]).filter(Boolean).join("·") : "");

export default function Lab() {
  const [slug, setSlug] = useState("s01");
  const [viz, setViz] = useState<VizData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("axis");   // 進單篇預設=完整解剖;calm 留給目錄剪影
  const [hover, setHover] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    setViz(null); setErr(null); setHover(null); setSelected(null);
    getViz(slug).then(setViz).catch(e => setErr(String(e instanceof Error ? e.message : e)));
  }, [slug]);

  const hn = hover && viz ? viz.nodes.find(n => n.id === hover) ?? null : null;
  const quote = hn?.evidence.find(e => e.quote)?.quote ?? "";
  const sn = selected && viz ? viz.nodes.find(n => n.id === selected) ?? null : null;
  const snKp = sn && viz?.feedback
    ? [...viz.feedback.key_points, ...viz.feedback.strengths].find(p => p.refs.includes(sn.id)) ?? null
    : null;

  return (
    <div className={`lab ${sn ? "discussing" : ""}`}>
      <Dust />
      <div className="lab-bar">
        <span className="lab-tag">/lab · 一具骨換姿勢 · A↔B 翻面</span>
        <div className="lab-seg">
          {MODES.map(m => (
            <button key={m.k} className={m.k === mode ? "on" : ""} onClick={() => setMode(m.k)}>{m.label}</button>
          ))}
        </div>
        <div className="lab-slugs">
          {SLUGS.map(s => (
            <button key={s} className={s === slug ? "on" : ""} onClick={() => setSlug(s)}>{s}</button>
          ))}
        </div>
      </div>

      <div className="lab-stage">
        {err && <div className="lab-msg">讀不到 {slug}：{err}</div>}
        {!err && !viz && <div className="lab-msg">載入中…</div>}
        {viz && <>
          <div className="lab-title">{viz.title}</div>
          <BoneStage viz={viz} mode={mode} hover={hover} onHover={setHover}
            selected={selected} onSelect={setSelected} />
        </>}
      </div>

      {/* 固定讀出條:hover 預覽(釘住討論時讓位) */}
      <div className={`lab-readout ${hn && !sn ? "on" : ""}`}>
        {hn && <>
          <span className="ro-type" style={{ color: VAR[hn.type], borderColor: VAR[hn.type] }}>{viz!.cn[hn.type] ?? hn.type}</span>
          <span className="ro-label">{hn.label}</span>
          {flagOf(viz, hn.id) && <span className="ro-flag">⚑ {flagOf(viz, hn.id)}</span>}
          {hn.intensity != null && <span className="ro-meter"><i style={{ width: `${Math.round(hn.intensity * 100)}%`, background: VAR[hn.type] }} /></span>}
          {quote && <span className="ro-quote">「{quote}」</span>}
        </>}
      </div>

      {/* 沉浸討論:從節點長出來的發光對話(非側欄盒子) */}
      {sn && viz && (
        <NodeTalk slug={slug} node={sn} typeName={viz.cn[sn.type] ?? sn.type} color={VAR[sn.type]}
          flag={flagOf(viz, sn.id)} kp={snKp} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
