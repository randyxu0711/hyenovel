import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getIndex, getUsageAll } from "../data/client";
import { worldPos, WORLD, ringRadii, type Stage } from "../lib/camera";
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
  const [blooming, setBlooming] = useState(false);           // 入口點火後,catalog 真物體(種骨/軌道)綻放入場的一次性窗
  const [returning, setReturning] = useState<string | null>(null);  // 從單篇退場、正飛回軌道槽位的那篇
  const [closing, setClosing] = useState(false);             // 單篇 overlay 向中心收合中
  const [confirming, setConfirming] = useState<string | null>(null); // 剛孕育完、正擴一圈確認波的那篇(一次性)
  const flyTimers = useRef<number[]>([]);
  const hatchTimer = useRef<number>();
  const confirmTimer = useRef<number>();
  const bloomTimer = useRef<number>();
  const returnTimers = useRef<number[]>([]);
  const orderRef = useRef<string[]>([]);
  const OVERLAY_OUT_MS = 460;   // overlay 收合時長,與 CSS overlayOut 對齊
  const CONFIRM_MS = 1800;      // 誕生確認波總長,與 CSS bornWave 對齊(1.4s + 第三環 .32s delay,留餘裕)

  const refresh = useCallback(() => getIndex().then(i => setEntries(i.stories)).catch(() => {}), []);
  // 誕生:重整列表,並把這篇標成「新成形」→ 柔金暈常駐(閱讀優先);點進或 refresh 後卸下。
  // 另擴一圈確認波(confirming):柔金暈是「這篇是新的」的狀態,確認波是「它剛落位」的那一刻——
  // 標記「孕育 → 誕生」這個轉變,一次性,CONFIRM_MS 後自己卸下。
  const onBorn = useCallback(async (s: string) => {
    await refresh();
    setFresh(f => new Set(f).add(s));
    setConfirming(s);
    clearTimeout(confirmTimer.current);
    confirmTimer.current = window.setTimeout(() => setConfirming(null), CONFIRM_MS);
  }, [refresh]);
  const { gestations, begin, cancel, resume, reanalyze, usageLimitResetAt, dismissUsageLimit } = useGestations(onBorn);

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
  useEffect(() => () => { flyTimers.current.forEach(clearTimeout); clearTimeout(hatchTimer.current); clearTimeout(bloomTimer.current); clearTimeout(confirmTimer.current); returnTimers.current.forEach(clearTimeout); }, []);

  // 入口風化吹淨 → 進 catalog,並開一次性 bloom 窗:真的種骨點火、真的軌道從中心綻放(非替身)
  const onEntered = () => {
    setEntered(true); setBlooming(true);
    clearTimeout(bloomTimer.current);
    // 各圈綻放依圈序 delay 0.13s、單圈 .95s → 末圈結束於 (rings-1)*130+950ms;
    // 窗口跟著圈數走,故事再多外圈也不會被截成瞬間彈出(下限 1700 保留少篇時的原節奏)
    const rings = ringRadii(Math.max(1, ordered.length)).length;
    const bloomMs = Math.max(1700, (rings - 1) * 130 + 950);
    bloomTimer.current = window.setTimeout(() => setBlooming(false), bloomMs);
  };

  // 單篇退場:overlay 先向中心收合 → nav 回目錄 → 那篇的骨從中心飛回軌道槽位 → 清除
  const startReturn = () => {
    if (!slug) { nav("/"); return; }
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { nav("/"); return; }
    const s = slug;
    setClosing(true);
    returnTimers.current.forEach(clearTimeout);
    returnTimers.current = [
      window.setTimeout(() => { setClosing(false); setReturning(s); nav("/"); }, OVERLAY_OUT_MS),
      window.setTimeout(() => setReturning(null), OVERLAY_OUT_MS + 1500),   // 蓋過 returnAssemble 1.4s
    ];
  };

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
      <div className="grain" aria-hidden />
      <div className={`fog ${stage === "overview" ? "thick" : ""}`} />
      <Camera stage={stage} count={Math.max(1, ordered.length)} focus={focus}>
        {stage !== "overview" && <Orbits count={Math.max(1, ordered.length)} bloom={blooming} />}
        <Catalog entries={entries} ordered={ordered} loading={!loaded} flying={flying} bursting={bursting}
          gestations={gestations} hatching={hatching} fresh={fresh} returning={returning} confirming={confirming}
          onPick={pick} onCancel={cancel} onResume={resume} onReanalyze={reanalyze} />
      </Camera>
      {/* 星圖開著就收起:.nascent 在畫面正中、z-index 比 .umap 高 → 會壓在中央總額上還能點 */}
      {stage === "catalog" && !usageOpen && <NascentStar onOpen={() => setAdding(true)} igniting={blooming} />}
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
      {stage === "overview" && <Overview onEnter={onEntered} />}
      {stage === "single" && <div className={`single-overlay${closing ? " out" : ""}`}><Single /></div>}
      <AddStory open={adding} initialFile={dropFile}
        onClose={() => { setAdding(false); setDropFile(null); }}
        onCreated={onCreated} />
      <Chrome stage={stage} title={title} onBack={startReturn} />
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
