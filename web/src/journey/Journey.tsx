import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getIndex, getRunningCritiques } from "../data/client";
import { worldPos, WORLD, type Stage } from "../lib/camera";
import Camera from "./Camera";
import Chrome from "./Chrome";
import Dust from "./Dust";
import Overview from "./Overview";
import Catalog from "./Catalog";
import AddStory from "./AddStory";
import NascentStar from "./NascentStar";
import FormingStar from "./FormingStar";
import Single from "./Single";
import type { IndexEntry } from "../types";
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

  if (err) return <div className="loadmsg">讀不到故事列表:{err}<br />先在 repo 根跑 <code>python index.py</code>。</div>;

  const stage: Stage = slug ? "single" : entered ? "catalog" : "overview";
  const idx = slug ? entries.findIndex(e => e.slug === slug) : -1;
  const focus = idx >= 0 ? worldPos(idx, WORLD) : undefined;
  const title = idx >= 0 ? entries[idx].title : undefined;

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
    <div className={`journey stage-${stage} ${dropping ? "drop-active" : ""}`} data-testid="home"
      onDragOver={onDragOver} onDragLeave={() => setDropping(false)} onDrop={onDrop}>
      <Dust />
      <div className={`fog ${stage === "overview" ? "thick" : ""}`} />
      <Camera stage={stage} focus={focus}>
        <Catalog entries={entries} loading={!loaded} />
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
    </div>
  );
}
