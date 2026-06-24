import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getStory } from "../data/client";
import TextAxis from "../viz/TextAxis";
import IntentionChain from "../viz/IntentionChain";
import Dock from "../dock/Dock";
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

  useEffect(() => {
    if (!slug) return;
    setData(null); setErr(null); setSel(null); setTab("source");
    getStory(slug).then(setData).catch(e => setErr(String(e instanceof Error ? e.message : e)));
  }, [slug]);

  if (err) return <div className="single"><div className="loadmsg">讀不到「{slug}」的分析:{err}</div></div>;
  if (!data) return <div className="single"><div className="loadmsg">載入中…</div></div>;
  const { viz, source } = data;
  const fb = viz.feedback;

  return (
    <div className="single">
      <div className="single-top">
        <h2>{viz.title}</h2>
      </div>
      <div className="single-body">
        <div className="single-main">
          <div className="tabs">
            {TABS.map(t => (
              <button key={t.k} className={`tab ${tab === t.k ? "on" : ""}`} onClick={() => setTab(t.k)}>{t.label}</button>
            ))}
          </div>
          <div className="pages">
            {tab === "source" && <div className="src">{source}</div>}
            {tab === "axis" && <TextAxis viz={viz} onPick={setSel} />}
            {tab === "chain" && <IntentionChain viz={viz} selected={sel} onPick={setSel} />}
            {tab === "feedback" && (fb
              ? <div className="fb">
                  <div className="dock-lab">這篇在做什麼</div><p>{fb.read}</p>
                  {fb.key_points.map((p, i) => <div key={i}>
                    <div className="dock-lab">{p.title}</div><p>{p.body}</p>
                    {p.question && <div className="q">{p.question}</div>}</div>)}
                  <div className="dock-lab">如果只能改一件事</div><p>{fb.one_line}</p>
                </div>
              : <p className="loadmsg">這篇還沒有編輯回饋。</p>)}
          </div>
        </div>
        <Dock viz={viz} selected={sel} />
      </div>
    </div>
  );
}
