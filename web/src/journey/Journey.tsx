import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getIndex, getUsageAll } from "../data/client";
import { worldPos, WORLD, type Stage } from "../lib/camera";
import Camera from "./Camera";
import Chrome from "./Chrome";
import Dust from "./Dust";
import Overview from "./Overview";
import Catalog from "./Catalog";
import Orbits from "./Orbits";
import AddStory from "./AddStory";
import NascentStar from "./NascentStar";
import UsageMap from "./UsageMap";
import Single from "./Single";
import { useGestations } from "./useGestations";
import { formatResetTime } from "./usageLimit";
import HyenaSweat from "./HyenaSweat";
import type { IndexEntry } from "../types";
import "./journey.css";

export default function Journey() {
  const { slug } = useParams();
  const nav = useNavigate();
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [entered, setEntered] = useState(false);
  const [adding, setAdding] = useState(false);
  const [dropFile, setDropFile] = useState<File | null>(null);
  const [dropping, setDropping] = useState(false);
  const [flying, setFlying] = useState<string | null>(null);
  const [bursting, setBursting] = useState(false);
  const [hatching, setHatching] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [usageOpen, setUsageOpen] = useState(false);
  const [usageFrom, setUsageFrom] = useState<{ x: number; y: number } | undefined>();
  const [spend, setSpend] = useState<number | null>(null);   // 入口上的累計小數字;讀不到就不顯示
  const flyTimers = useRef<number[]>([]);
  const hatchTimer = useRef<number>();
  const orderRef = useRef<string[]>([]);

  const refresh = useCallback(() => getIndex().then(i => setEntries(i.stories)).catch(() => {}), []);
  // 誕生:重整列表,並把這篇標成「新成形」→ 柔金暈常駐(閱讀優先);點進或 refresh 後卸下
  const onBorn = useCallback(async (s: string) => {
    await refresh();
    setFresh(f => new Set(f).add(s));
  }, [refresh]);
  const { gestations, begin, cancel, usageLimitResetAt, dismissUsageLimit } = useGestations(onBorn);

  useEffect(() => {
    getIndex().then(i => setEntries(i.stories))
      .catch(e => setErr(String(e instanceof Error ? e.message : e)))
      .finally(() => setLoaded(true));
  }, []);
  useEffect(() => {
    let live = true;
    getUsageAll().then(a => { if (live && !a.empty) setSpend(a.total.cost_usd); }).catch(() => {});
    return () => { live = false; };
  }, []);
  useEffect(() => { if (slug) setEntered(true); }, [slug]);
  // 重整後若還有胚胎在孕育,直接落在 catalog
  useEffect(() => { if (gestations.size) setEntered(true); }, [gestations.size]);
  useEffect(() => () => { flyTimers.current.forEach(clearTimeout); clearTimeout(hatchTimer.current); }, []);

  // 點已誕生的星:那具骨飛向中心+放大爆散,飛抵才進單篇
  const pick = (s: string) => {
    setFresh(f => { if (!f.has(s)) return f; const n = new Set(f); n.delete(s); return n; });
    flyTimers.current.forEach(clearTimeout);
    setFlying(s); setBursting(false);
    flyTimers.current = [
      window.setTimeout(() => setBursting(true), 1150),
      window.setTimeout(() => nav(`/story/${s}`), 1500),
      window.setTimeout(() => { setFlying(null); setBursting(false); }, 2300),
    ];
  };

  // 新故事落 source.md 完成 → 開始孕育 + 從中心飛到軌道空位(hatching);不自動潛入單篇
  const onCreated = (s: string, t: string) => {
    setAdding(false); setDropFile(null);
    begin(s, t);
    setHatching(s);
    clearTimeout(hatchTimer.current);
    hatchTimer.current = window.setTimeout(() => setHatching(null), 1200);
  };

  if (err) return <div className="loadmsg">讀不到故事列表:{err}<br />先在 repo 根跑 <code>python index.py</code>。</div>;

  const stage: Stage = slug ? "single" : entered ? "catalog" : "overview";

  // 穩定槽位:所有見過的 slug 依首見順序固定,狀態變不重排 → 誕生不跳位
  const present = [...entries.map(e => e.slug), ...gestations.keys()];
  for (const s of present) if (!orderRef.current.includes(s)) orderRef.current.push(s);
  const ordered = orderRef.current.filter(s => present.includes(s));

  const oidx = slug ? ordered.indexOf(slug) : -1;
  const focus = oidx >= 0 ? worldPos(oidx, WORLD, ordered.length) : undefined;
  const title = slug ? entries.find(e => e.slug === slug)?.title : undefined;

  const canDrop = stage === "catalog";
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
    <div className={`journey stage-${stage} ${dropping ? "drop-active" : ""} ${flying ? "flying" : ""} ${usageLimitResetAt !== undefined ? "toasting" : ""}`} data-testid="home"
      onDragOver={onDragOver} onDragLeave={() => setDropping(false)} onDrop={onDrop}>
      <Dust />
      <div className={`fog ${stage === "overview" ? "thick" : ""}`} />
      <Camera stage={stage} focus={focus}>
        {stage !== "overview" && <Orbits count={Math.max(1, ordered.length)} />}
        <Catalog entries={entries} ordered={ordered} loading={!loaded} flying={flying} bursting={bursting}
          gestations={gestations} hatching={hatching} fresh={fresh} onPick={pick} onCancel={cancel} />
      </Camera>
      {/* 星圖開著就收起:.nascent 在畫面正中、z-index 比 .umap 高 → 會壓在中央總額上還能點 */}
      {stage === "catalog" && !usageOpen && <NascentStar onOpen={() => setAdding(true)} />}
      {stage === "catalog" && (
        // 點它 → 這行小字本身飛到中心、放大成總計(它就是同一個數字)
        <button className="usage-entry" onClick={e => {
          const r = (e.currentTarget.querySelector("b") ?? e.currentTarget).getBoundingClientRect();
          setUsageFrom({ x: r.left + r.width / 2, y: r.top + r.height / 2 });
          setUsageOpen(true);
        }}>
          用量{spend !== null && <b>${spend.toFixed(2)}</b>}
        </button>
      )}
      {usageOpen && (
        <UsageMap entries={entries} from={usageFrom} onClose={() => setUsageOpen(false)}
          onPick={s => { setUsageOpen(false); nav(`/story/${s}`, { state: { tab: "usage" } }); }} />
      )}
      {stage === "overview" && <Overview onEnter={() => setEntered(true)} />}
      {stage === "single" && <div className="single-overlay"><Single /></div>}
      <AddStory open={adding} initialFile={dropFile}
        onClose={() => { setAdding(false); setDropFile(null); }}
        onCreated={onCreated} />
      <Chrome stage={stage} title={title} onBack={() => nav("/")} />
      {usageLimitResetAt !== undefined && (
        <div className="usage-toast" role="status">
          <HyenaSweat />
          <div className="usage-toast-body">
            <span className="usage-toast-lead">訂閱用量上限</span>
            {formatResetTime(usageLimitResetAt)
              ? <span className="usage-toast-reset"><b className="usage-toast-time">{formatResetTime(usageLimitResetAt)}</b> 重置</span>
              : <span className="usage-toast-reset">稍後再試</span>}
          </div>
          <button className="usage-toast-x" onClick={dismissUsageLimit} aria-label="關閉">×</button>
        </div>
      )}
    </div>
  );
}
