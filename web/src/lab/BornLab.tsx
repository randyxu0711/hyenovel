import { useEffect, useRef, useState } from "react";
import Camera from "../journey/Camera";
import Catalog from "../journey/Catalog";
import Orbits from "../journey/Orbits";
import Dust from "../journey/Dust";
import { getIndex } from "../data/client";
import { WORLD, worldPos } from "../lib/camera";
import type { Gestation, IndexEntry } from "../types";
import "../journey/journey.css";
import "./lab.css";

// /lab/born —— 誕生儀式 + 停拍(paused/failed)的看板。真 Camera / Orbits / Catalog / CloudCollapse /
// Skeleton / viz,只有「孕育狀態」是手動餵的:這裡看到的就是真畫面(不畫替身)。
// 真跑一次要幾分鐘 + 燒訂閱($0.7–0.9),jsdom 又不跑動畫、測試看不見視覺 → 這裡補那道缺口。

const CONFIRM_MS = 1800;

// 按拍子走,不是按後端 step:使用者要讀的是敘事,而 step 只是後端跑到哪格。
// vizReady 由拍子推導,不給手動亂配——step2 沒有真骨是現實中幾乎不存在的狀態
//(viz 在 criticizer 開跑前 0.15 秒就落檔了),讓人按得出來只會誤導。
type Beat = "collapse" | "form" | "weigh" | "born";
const BEATS: { k: Beat; label: string; sub: string }[] = [
  { k: "collapse", label: "① 凝聚", sub: "analyst 跑中 · 分鐘級 · 真的還沒資料" },
  { k: "form", label: "② 核心點火", sub: "analyst 交件 + viz 0.15s · 瞬間 · 骨從中心向外亮起" },
  { k: "weigh", label: "③ 秤出輕重", sub: "criticizer 跑中 · 分鐘級 · 光沿脊椎掃,掃到哪掂哪" },
  { k: "born", label: "④ 完成", sub: "render + done · 秒級 · 確認波" },
];
// 拍子 → 後端 step(Catalog 的階段詞吃它)
const STEP_OF: Record<Beat, number> = { collapse: 1, form: 2, weigh: 2, born: 0 };

// 停拍:paused/failed × 卡在哪(analyst=還沒骨→凍雲、criticizer=已有骨→靜骨)。四個組合都看得到。
type Dorm = { status: "paused" | "failed"; stage: "analyst" | "criticizer"; reason?: string };
const DORMS: { d: Dorm; label: string; sub: string }[] = [
  { d: { status: "paused", stage: "analyst" }, label: "⏸ 藍雲", sub: "paused · 卡 analyst · 還沒骨 → 凍住的藍雲(慢呼吸)" },
  { d: { status: "paused", stage: "criticizer" }, label: "⏸ 藍骨", sub: "paused · 卡 criticizer · 冷藍靜骨(慢呼吸)· 時間交給右下 banner" },
  { d: { status: "failed", stage: "analyst", reason: "crash" }, label: "⚠ 紅雲", sub: "failed · 卡 analyst · 熄火的紅雲(全靜、暗)· 已中斷 · 出錯" },
  { d: { status: "failed", stage: "criticizer", reason: "gate" }, label: "⚠ 紅骨", sub: "failed · 卡 criticizer · 鏽紅靜骨 · 已中斷 · 未通過檢核" },
];

export default function BornLab() {
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [beat, setBeat] = useState<Beat>("collapse");
  const [dorm, setDorm] = useState<Dorm | null>(null);   // 非 null 時蓋過 beat,畫停拍態
  const [vizReady, setVizReady] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const timers = useRef<number[]>([]);

  // 只留一篇:旁邊擺別的骨只會搶戲,這裡要看的是這一顆怎麼長出來
  useEffect(() => { getIndex().then(i => setEntries(i.stories.slice(0, 1))).catch(() => {}); }, []);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const ordered = entries.map(e => e.slug);
  const target = ordered[0];

  const clear = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  const at = (ms: number, fn: () => void) => timers.current.push(window.setTimeout(fn, ms));

  const go = (k: Beat) => {
    clear();
    setDorm(null);
    setBeat(k);
    setConfirming(null);
    setFresh(k === "born" ? new Set([target]) : new Set());
    if (k === "collapse") { setVizReady(false); return; }
    if (k === "form") {
      // 先卸再掛:StoryBone 重新掛載才會重播 reassemble(骨聚成的那一下要能反覆看)
      setVizReady(false);
      requestAnimationFrame(() => setVizReady(true));
      return;
    }
    setVizReady(true);
    if (k === "born") { setConfirming(target); at(CONFIRM_MS, () => setConfirming(null)); }
  };

  const goDorm = (d: Dorm) => { clear(); setConfirming(null); setFresh(new Set()); setDorm(d); };

  // 整條跑一遍:真實時長 ①②分鐘級、③秒級,這裡壓成秒只為看節奏
  const runAll = () => {
    go("collapse");
    at(2600, () => go("form"));
    at(5600, () => go("weigh"));
    at(8200, () => go("born"));
  };

  const gestations: Map<string, Gestation> = !target
    ? new Map()
    : dorm
      ? new Map([[target, {
          step: dorm.stage === "criticizer" ? 2 : 1,
          status: dorm.status,
          title: entries[0]?.title ?? target,
          vizReady: dorm.stage === "criticizer",
          reason: dorm.reason,
        }]])
      : beat !== "born"
        ? new Map([[target, { step: STEP_OF[beat], status: "running", title: entries[0]?.title ?? target, vizReady }]])
        : new Map();

  // 卡在 analyst 的停拍「還沒骨」——但 lab 借的是已完成故事(has_viz=true)。覆蓋成 false 才走凍雲路徑。
  const catalogEntries = dorm?.stage === "analyst" ? entries.map(e => ({ ...e, has_viz: false })) : entries;

  const sub = dorm
    ? DORMS.find(x => x.d.status === dorm.status && x.d.stage === dorm.stage)!.sub
    : BEATS.find(b => b.k === beat)!.sub;

  return (
    <div className="lab born-lab">
      <Dust />
      <div className="lab-bar">
        <span className="lab-tag">/lab/born · 誕生 + 停拍 · 真元件,手動餵孕育狀態</span>
        <div className="lab-seg">
          {BEATS.map(b => (
            <button key={b.k} className={!dorm && beat === b.k ? "on" : ""} onClick={() => go(b.k)}>{b.label}</button>
          ))}
        </div>
        <div className="lab-seg">
          {DORMS.map(x => (
            <button key={`${x.d.status}-${x.d.stage}`}
              className={dorm?.status === x.d.status && dorm?.stage === x.d.stage ? "on" : ""}
              onClick={() => goDorm(x.d)}>{x.label}</button>
          ))}
        </div>
        <div className="lab-slugs">
          {!target && <span className="lab-tag">讀不到 index.json</span>}
          <button onClick={runAll}>整條跑一遍</button>
        </div>
      </div>
      <div className="born-sub">{sub}</div>
      {/* stage=single + 對焦那顆槽位:catalog 焦距(~0.75×)下粒子會掉進次像素,看不出動畫。
          真的孕育發生在 catalog 焦距——參數仍以那個尺度為準(見 CloudCollapse 的 R_MIN/R_MAX),
          這裡只是把鏡頭推近好讓人眼判。 */}
      <Camera stage="single" count={Math.max(1, ordered.length)} focus={worldPos(0, WORLD, 1)}>
        <Orbits count={Math.max(1, ordered.length)} />
        <Catalog entries={catalogEntries} ordered={ordered} gestations={gestations} fresh={fresh}
          confirming={confirming} onPick={() => {}} onCancel={() => {}}
          onResume={() => go("collapse")} onReanalyze={() => go("collapse")} />
      </Camera>
    </div>
  );
}
