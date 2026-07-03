import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getIndex, getRunningCritiques } from "../data/client";
import { worldPos, WORLD, type Stage } from "../lib/camera";
import Camera from "./Camera";
import Chrome from "./Chrome";
import Dust from "./Dust";
import Overview from "./Overview";
import Catalog from "./Catalog";
import Orbits from "./Orbits";
import AddStory from "./AddStory";
import NascentStar from "./NascentStar";
import FormingStar from "./FormingStar";
import Single from "./Single";
import type { IndexEntry, Gestation } from "../types";
import "./journey.css";

export default function Journey() {
  const { slug } = useParams();
  const nav = useNavigate();
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [entered, setEntered] = useState(false); // overview→catalog
  const [adding, setAdding] = useState(false);
  const [dropFile, setDropFile] = useState<File | null>(null);
  const [forming, setForming] = useState<{ slug: string; title: string } | null>(null);
  const [dropping, setDropping] = useState(false);
  const [flying, setFlying] = useState<string | null>(null); // 正飛向中心的那篇
  const [bursting, setBursting] = useState(false);            // 飛抵中心後零件爆散
  const [demo, setDemo] = useState<{ slug: string; step: number } | null>(null);
  const flyTimers = useRef<number[]>([]);
  const orderRef = useRef<string[]>([]);

  const refresh = () =>
    getIndex().then(i => setEntries(i.stories)).catch(() => {});
  useEffect(() => {
    getIndex().then(i => setEntries(i.stories))
      .catch(e => setErr(String(e instanceof Error ? e.message : e)))
      .finally(() => setLoaded(true));
  }, []);
  // 深連結 /story/:slug 直接視為已進入
  useEffect(() => { if (slug) setEntered(true); }, [slug]);

  // 重整後復原:後端若還有 critique 在跑,重新接上成形動畫(不在單篇頁時)
  useEffect(() => {
    if (slug) return;
    getRunningCritiques().then(rs => {
      if (rs.length) { setEntered(true); setForming(f => f ?? { slug: rs[0].slug, title: rs[0].title }); }
    });
  }, [slug]);

  // 點一篇故事:那具骨先飛向中心+放大發光(骨自己飛,非相機平移),飛到了才進單篇。
  const pick = (s: string) => {
    flyTimers.current.forEach(clearTimeout);
    setFlying(s); setBursting(false);
    flyTimers.current = [
      window.setTimeout(() => setBursting(true), 1150),                     // 飛抵中心 → 零件爆散+亮閃
      window.setTimeout(() => nav(`/story/${s}`), 1500),                    // 爆散中 → 進單篇,overlay 凝定落位接住
      window.setTimeout(() => { setFlying(null); setBursting(false); }, 2300), // overlay 蓋住後才收
    ];
  };
  useEffect(() => () => flyTimers.current.forEach(clearTimeout), []);

  if (err) return <div className="loadmsg">讀不到故事列表:{err}<br />先在 repo 根跑 <code>python index.py</code>。</div>;

  const stage: Stage = slug ? "single" : entered ? "catalog" : "overview";
  const idx = slug ? entries.findIndex(e => e.slug === slug) : -1;
  const focus = idx >= 0 ? worldPos(idx, WORLD, entries.length) : undefined;
  const title = idx >= 0 ? entries[idx].title : undefined;

  // demo(dev only):把假胚胎併進 gestations,不碰後端。真實孕育在 Task 4 接上。
  const shown: Map<string, Gestation> = demo
    ? new Map<string, Gestation>().set(demo.slug, { step: demo.step, status: "running", title: "示範" })
    : new Map<string, Gestation>();
  // 穩定槽位:所有見過的 slug 依首見順序固定,狀態變不重排 → 誕生不跳位。
  const present = [...entries.map(e => e.slug), ...shown.keys()];
  for (const s of present) if (!orderRef.current.includes(s)) orderRef.current.push(s);
  const ordered = orderRef.current.filter(s => present.includes(s));

  // 整片星空當投放區:拖一個檔進來就開始擲入
  const canDrop = stage === "catalog" && !forming;
  const onDragOver = (e: React.DragEvent) => {
    if (!canDrop || !Array.from(e.dataTransfer.types).includes("Files")) return;
    e.preventDefault(); setDropping(true);
  };
  const onDrop = (e: React.DragEvent) => {
    if (!canDrop) return;
    e.preventDefault(); setDropping(false);
    const f = e.dataTransfer.files?.[0];
    if (f) { setDropFile(f); setAdding(true); }
  };

  return (
    <div className={`journey stage-${stage} ${dropping ? "drop-active" : ""} ${flying ? "flying" : ""}`} data-testid="home"
      onDragOver={onDragOver} onDragLeave={() => setDropping(false)} onDrop={onDrop}>
      <Dust />
      <div className={`fog ${stage === "overview" ? "thick" : ""}`} />
      <Camera stage={stage} focus={focus}>
        {stage !== "overview" && <Orbits count={Math.max(1, ordered.length)} />}
        <Catalog entries={entries} ordered={ordered} loading={!loaded} flying={flying} bursting={bursting}
          gestations={shown} hatching={null} onPick={pick} onCancel={() => setDemo(null)} />
      </Camera>
      {stage === "catalog" && !forming && <NascentStar onOpen={() => setAdding(true)} />}
      {forming && (
        <FormingStar slug={forming.slug} title={forming.title}
          onDone={s => { setForming(null); refresh(); nav(`/story/${s}`); }}
          onAbort={() => { setForming(null); refresh(); }} />
      )}
      {stage === "overview" && <Overview onEnter={() => setEntered(true)} />}
      {stage === "single" && <div className="single-overlay"><Single /></div>}
      <AddStory open={adding} initialFile={dropFile}
        onClose={() => { setAdding(false); setDropFile(null); }}
        onForming={(s, t) => { setAdding(false); setDropFile(null); setForming({ slug: s, title: t }); }} />
      <Chrome stage={stage} title={title} onBack={() => nav("/")} />
      {import.meta.env.DEV && stage === "catalog" && (
        <div className="demo-panel">
          {!demo && <button onClick={() => setDemo({ slug: "__demo", step: 1 })}>demo 胚胎</button>}
          {demo && <>
            <span>step {demo.step}</span>
            <button onClick={() => setDemo(d => d && { ...d, step: Math.max(1, d.step - 1) })}>−</button>
            <button onClick={() => setDemo(d => d && { ...d, step: Math.min(4, d.step + 1) })}>＋</button>
            <button onClick={() => setDemo(null)}>清除</button>
          </>}
        </div>
      )}
    </div>
  );
}
