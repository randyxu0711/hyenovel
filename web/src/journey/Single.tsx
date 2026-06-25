import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useParams } from "react-router-dom";
import { getStory } from "../data/client";
import TextAxis from "../viz/TextAxis";
import IntentionChain from "../viz/IntentionChain";
import Dock from "../dock/Dock";
import SourceView from "./SourceView";
import Scene3D from "./Scene3D";
import Bone3D from "../viz/Bone3D";
import type { VizData } from "../types";

const seedOf = (s: string) => [...s].reduce((a, c) => a + c.charCodeAt(0), 0) || 7;

type Tab = "source" | "axis" | "chain" | "feedback";
const TABS: { k: Tab; label: string }[] = [
  { k: "source", label: "原文" }, { k: "axis", label: "文本軸" },
  { k: "chain", label: "意圖鏈" }, { k: "feedback", label: "回饋" },
];
// 每個分頁 = 骨頭的一個面(四分之一圈)
const TAB_ANGLE: Record<Tab, number> = {
  source: 0, axis: Math.PI * 0.5, chain: Math.PI, feedback: Math.PI * 1.5,
};

export default function Single() {
  const { slug } = useParams();
  const [data, setData] = useState<{ viz: VizData; source: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("source");
  const [sel, setSel] = useState<string | null>(null);
  const [openFb, setOpenFb] = useState<Record<string, boolean>>({});
  const toggleFb = (k: string) => setOpenFb(s => ({ ...s, [k]: !s[k] }));
  const [hl, setHl] = useState<{ start: number; end: number } | null>(null);
  const [dolly, setDolly] = useState(0);

  useEffect(() => {
    if (!slug) return;
    setData(null); setErr(null); setSel(null); setTab("source"); setHl(null);
    getStory(slug).then(setData).catch(e => setErr(String(e instanceof Error ? e.message : e)));
  }, [slug]);

  // 換 tab:相機脈衝拉近(431ms 後退開),骨頭轉到該面,文字隨後浮現
  useEffect(() => {
    setDolly(1);
    const t = setTimeout(() => setDolly(0), 430);
    return () => clearTimeout(t);
  }, [tab]);

  if (err) return <div className="single"><div className="loadmsg">讀不到「{slug}」的分析:{err}</div></div>;
  if (!data) return <div className="single"><div className="loadmsg">載入中…</div></div>;
  const { viz, source } = data;
  const fb = viz.feedback;

  return (
    <div className="single">
      <div className="hero3d">
        <Scene3D dolly={dolly}><Bone3D seed={seedOf(viz.slug)} targetRot={TAB_ANGLE[tab]} /></Scene3D>
        <div className="hero-title"><h2>{viz.title}</h2></div>
      </div>
      <div className="single-body">
        <div className="single-main">
          <div className="tabs">
            {TABS.map(t => (
              <button key={t.k} className={`tab ${tab === t.k ? "on" : ""}`} onClick={() => setTab(t.k)}>{t.label}</button>
            ))}
          </div>
          <div className="pages">
            <motion.div key={tab} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, delay: 0.34, ease: "easeOut" }}>
            {tab === "source" && <SourceView source={source} highlight={hl} />}
            {tab === "axis" && <TextAxis viz={viz} onPick={setSel} />}
            {tab === "chain" && <IntentionChain viz={viz} selected={sel} onPick={setSel} />}
            {tab === "feedback" && (fb
              ? <div className="fb">
                  <h3 className="fb-sec">這篇在做什麼</h3>
                  <p className="fb-lead">{fb.read}</p>

                  {fb.key_points.length > 0 && <h3 className="fb-sec">最關鍵的 {fb.key_points.length} 件</h3>}
                  {fb.key_points.map((p, i) => {
                    const k = `kp${i}`, on = !!openFb[k];
                    return (
                      <div className={`acc ${on ? "on" : ""}`} key={k}>
                        <button className="acc-h" onClick={() => toggleFb(k)}>
                          <span className="acc-mk">{on ? "−" : "+"}</span><span className="acc-tt">{p.title}</span>
                        </button>
                        {on && <div className="acc-b"><p>{p.body}</p>
                          {p.question && <div className="q">{p.question}</div>}</div>}
                      </div>
                    );
                  })}

                  {fb.strengths.length > 0 && <h3 className="fb-sec">這篇的強處</h3>}
                  {fb.strengths.map((p, i) => {
                    const k = `st${i}`, on = !!openFb[k];
                    return (
                      <div className={`acc ${on ? "on" : ""}`} key={k}>
                        <button className="acc-h" onClick={() => toggleFb(k)}>
                          <span className="acc-mk">{on ? "−" : "+"}</span><span className="acc-tt">{p.title}</span>
                        </button>
                        {on && <div className="acc-b"><p>{p.body}</p></div>}
                      </div>
                    );
                  })}

                  <h3 className="fb-sec">如果只能改一件事</h3>
                  <p className="fb-lead one">{fb.one_line}</p>
                </div>
              : <p className="loadmsg">這篇還沒有編輯回饋。</p>)}
            </motion.div>
          </div>
        </div>
        <Dock viz={viz} selected={sel} onJump={(s, e) => { setTab("source"); setHl({ start: s, end: e }); }} />
      </div>
    </div>
  );
}
