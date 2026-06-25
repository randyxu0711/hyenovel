import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { useParams } from "react-router-dom";
import { getStory } from "../data/client";
import TextAxis from "../viz/TextAxis";
import IntentionChain from "../viz/IntentionChain";
import Dock from "../dock/Dock";
import SourceView from "./SourceView";
import Skeleton from "../viz/Skeleton";
import type { VizData } from "../types";

type Tab = "source" | "axis" | "chain" | "feedback";
const TABS: { k: Tab; label: string }[] = [
  { k: "source", label: "原文" }, { k: "axis", label: "文本軸" },
  { k: "chain", label: "意圖鏈" }, { k: "feedback", label: "回饋" },
];
export default function Single() {
  const { slug } = useParams();
  const [data, setData] = useState<{ viz: VizData; source: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("source");
  const [sel, setSel] = useState<string | null>(null);
  const [openFb, setOpenFb] = useState<Record<string, boolean>>({});
  const toggleFb = (k: string) => setOpenFb(s => ({ ...s, [k]: !s[k] }));
  const [hl, setHl] = useState<{ start: number; end: number } | null>(null);
  const [heroMin, setHeroMin] = useState(false); // 收起星骨 → 把垂直空間讓給密集的內容

  useEffect(() => {
    if (!slug) return;
    setData(null); setErr(null); setSel(null); setTab("source"); setHl(null);
    getStory(slug).then(setData).catch(e => setErr(String(e instanceof Error ? e.message : e)));
  }, [slug]);

  if (err) return <div className="single"><div className="loadmsg">讀不到「{slug}」的分析:{err}</div></div>;
  if (!data) return <div className="single"><div className="loadmsg">載入中…</div></div>;
  const { viz, source } = data;
  const fb = viz.feedback;

  return (
    <div className={`single ${heroMin ? "hero-min" : ""}`}>
      <div className="hero3d">
        {/* key 含 heroMin → 收合/展開或換頁都重跑「拉近→重繪→退開」 */}
        <div className="hero-bone" key={`${tab}-${heroMin}`}>
          <Skeleton viz={viz} width={heroMin ? 150 : 420} />
        </div>
        <div className="hero-title"><h2>{viz.title}</h2></div>
      </div>
      <div className="single-body">
        <div className="single-main">
          <div className="tabs">
            {TABS.map(t => (
              <button key={t.k} className={`tab ${tab === t.k ? "on" : ""}`} onClick={() => setTab(t.k)}>{t.label}</button>
            ))}
            <button className="hero-toggle" onClick={() => setHeroMin(m => !m)}
              title={heroMin ? "展開上方星骨" : "收起上方星骨,讓內容更寬敞"}>
              {heroMin ? "▾ 展開" : "▴ 收起"}
            </button>
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
