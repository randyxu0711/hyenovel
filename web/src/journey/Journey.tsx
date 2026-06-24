import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getIndex } from "../data/client";
import { worldPos, WORLD, type Stage } from "../lib/camera";
import Camera from "./Camera";
import Chrome from "./Chrome";
import Dust from "./Dust";
import Overview from "./Overview";
import Catalog from "./Catalog";
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

  useEffect(() => {
    getIndex().then(i => setEntries(i.stories))
      .catch(e => setErr(String(e instanceof Error ? e.message : e)))
      .finally(() => setLoaded(true));
  }, []);
  // 深連結 /story/:slug 直接視為已進入
  useEffect(() => { if (slug) setEntered(true); }, [slug]);

  if (err) return <div className="loadmsg">讀不到故事列表:{err}<br />先在 repo 根跑 <code>python index.py</code>。</div>;

  const stage: Stage = slug ? "single" : entered ? "catalog" : "overview";
  const idx = slug ? entries.findIndex(e => e.slug === slug) : -1;
  const focus = idx >= 0 ? worldPos(idx, WORLD) : undefined;
  const title = idx >= 0 ? entries[idx].title : undefined;

  return (
    <div className={`journey stage-${stage}`} data-testid="home">
      <Dust />
      <div className={`fog ${stage === "overview" ? "thick" : ""}`} />
      <Camera stage={stage} focus={focus}>
        <Catalog entries={entries} loading={!loaded} />
      </Camera>
      {stage === "overview" && <Overview onEnter={() => setEntered(true)} />}
      {stage === "single" && <div className="single-overlay"><Single /></div>}
      <Chrome stage={stage} title={title} onBack={() => nav("/")} />
    </div>
  );
}
