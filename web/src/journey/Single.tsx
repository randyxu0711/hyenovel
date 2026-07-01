import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getStory } from "../data/client";
import BoneStage from "../lab/BoneStage";
import NodeTalk from "../lab/NodeTalk";
import SourceAnnotated from "./SourceAnnotated";
import Dust from "./Dust";
import type { VizData, FeedbackPoint } from "../types";
import "../lab/lab.css";

type Mode = "calm" | "axis" | "chain";
const MODES: { k: Mode; label: string }[] = [
  { k: "axis", label: "文本軸" }, { k: "chain", label: "因果鏈" },
];
const VAR: Record<string, string> = {
  technique: "var(--c-technique)", effect: "var(--c-effect)", theme: "var(--c-theme)",
  motif: "var(--c-motif)", beat: "var(--c-beat)", character: "var(--c-character)",
};
const FLAG: Record<string, string> = { orphan: "孤兒技法", overloaded: "過載", hollow: "單薄" };
const flagOf = (viz: VizData, id: string) => (viz.diag[id] ?? []).map(d => FLAG[d]).filter(Boolean).join("·");

export default function Single() {
  const { slug } = useParams();
  const [data, setData] = useState<{ viz: VizData; source: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("axis");
  const [hover, setHover] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [text, setText] = useState<null | "source" | "feedback">(null);
  const [hl, setHl] = useState<{ start: number; end: number } | null>(null);
  const [openFb, setOpenFb] = useState<Record<string, boolean>>({});
  const toggleFb = (k: string) => setOpenFb(s => ({ ...s, [k]: !s[k] }));
  const accItems = (prefix: string, pts: FeedbackPoint[], withQ: boolean) => pts.map((p, i) => {
    const k = `${prefix}${i}`, on = !!openFb[k];
    return (
      <div className={`acc ${on ? "on" : ""}`} key={k}>
        <button className="acc-h" onClick={() => toggleFb(k)}><span className="acc-mk">{on ? "−" : "+"}</span><span className="acc-tt">{p.title}</span></button>
        {on && <div className="acc-b"><p>{p.body}</p>{withQ && p.question && <div className="q">{p.question}</div>}</div>}
      </div>
    );
  });

  useEffect(() => {
    if (!slug) return;
    setData(null); setErr(null); setSelected(null); setHover(null); setText(null); setHl(null);
    getStory(slug).then(setData).catch(e => setErr(String(e instanceof Error ? e.message : e)));
  }, [slug]);

  if (err) return <div className="sb"><div className="sb-msg">讀不到「{slug}」的分析:{err}</div></div>;
  if (!data) return <div className="sb"><div className="sb-msg">載入中…</div></div>;
  const { viz, source } = data, fb = viz.feedback;

  const hn = hover ? viz.nodes.find(n => n.id === hover) ?? null : null;
  const hq = hn?.evidence.find(e => e.quote)?.quote ?? "";
  const sn = selected ? viz.nodes.find(n => n.id === selected) ?? null : null;
  const snKp = sn && fb ? [...fb.key_points, ...fb.strengths].find(p => p.refs.includes(sn.id)) ?? null : null;
  const jumpToSource = (s: number, e: number) => { setText("source"); setHl({ start: s, end: e }); };

  return (
    <div className={`sb ${sn ? "discussing" : ""}`}>
      <Dust />
      <div className="sb-bar">
        <div className="sb-seg">
          {MODES.map(m => <button key={m.k} className={m.k === mode ? "on" : ""} onClick={() => { setMode(m.k); setText(null); }}>{m.label}</button>)}
        </div>
        <div className="sb-textabs">
          <button className={text === "source" ? "on" : ""} onClick={() => setText(text === "source" ? null : "source")}>原文</button>
          <button className={text === "feedback" ? "on" : ""} onClick={() => setText(text === "feedback" ? null : "feedback")}>回饋</button>
        </div>
      </div>

      <div className="sb-stage">
        <BoneStage viz={viz} mode={mode} hover={hover} onHover={setHover} selected={selected} onSelect={setSelected} />
      </div>

      {/* hover 讀出 */}
      <div className={`lab-readout ${hn && !sn && !text ? "on" : ""}`}>
        {hn && <>
          <span className="ro-type" style={{ color: VAR[hn.type], borderColor: VAR[hn.type] }}>{viz.cn[hn.type] ?? hn.type}</span>
          <span className="ro-label">{hn.label}</span>
          {flagOf(viz, hn.id) && <span className="ro-flag">⚑ {flagOf(viz, hn.id)}</span>}
          {hn.intensity != null && <span className="ro-meter"><i style={{ width: `${Math.round(hn.intensity * 100)}%`, background: VAR[hn.type] }} /></span>}
          {hq && <span className="ro-quote">「{hq}」</span>}
        </>}
      </div>

      {/* 沒選節點、沒開文字、沒 hover 時的編輯整體話 */}
      {!sn && !text && !hn && fb && (
        <div className="sb-overview"><b>編輯總覽</b>　{fb.one_line}</div>
      )}

      {/* 甲:原文/回饋覆蓋層(點背景 / ✕ / 再按一次同鍵 都可關) */}
      {text && (
        <div className="sb-textview" onClick={() => setText(null)}>
          <button className="sb-close" onClick={() => setText(null)}>✕ 關閉</button>
          <div className="sb-textview-inner" onClick={e => e.stopPropagation()}>
          {text === "source" && <SourceAnnotated source={source} viz={viz} highlight={hl}
            onDiscuss={setSelected} />}
          {text === "feedback" && (fb ? (
            <div className="fb" style={{ maxWidth: 720, margin: "0 auto" }}>
              <h3 className="fb-sec">這篇在做什麼</h3>
              <p className="fb-lead">{fb.read}</p>
              {fb.key_points.length > 0 && <h3 className="fb-sec">最關鍵的 {fb.key_points.length} 件</h3>}
              {accItems("kp", fb.key_points, true)}
              {fb.strengths.length > 0 && <h3 className="fb-sec">這篇的強處</h3>}
              {accItems("st", fb.strengths, false)}
              <h3 className="fb-sec">如果只能改一件事</h3>
              <p className="fb-lead one">{fb.one_line}</p>
            </div>
          ) : <p className="sb-msg">這篇還沒有編輯回饋。</p>)}
          </div>
        </div>
      )}

      {/* 沉浸討論 */}
      {sn && (
        <NodeTalk slug={slug!} node={sn} typeName={viz.cn[sn.type] ?? sn.type} color={VAR[sn.type]}
          flag={flagOf(viz, sn.id)} kp={snKp} source={source} onJump={jumpToSource} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
