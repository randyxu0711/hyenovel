import { useEffect, useRef, useState } from "react";
import Camera from "../journey/Camera";
import Catalog from "../journey/Catalog";
import Orbits from "../journey/Orbits";
import Dust from "../journey/Dust";
import { getIndex } from "../data/client";
import type { Gestation, IndexEntry } from "../types";
import "../journey/journey.css";
import "./lab.css";

// /lab/born —— 誕生儀式的看板。真 Camera / Orbits / Catalog / Skeleton / viz,
// 只有「孕育狀態」是手動餵的:所以這裡看到的就是真誕生會看到的(不畫替身)。
// 存在理由:真跑一次要幾分鐘 + 燒訂閱($0.7–0.9),而 jsdom 不跑動畫、測試看不見視覺。
// 「整條跑一遍」把分鐘級的真實時長壓成秒——只為看節奏,不代表真實步調。

const CONFIRM_MS = 1800;
const WORD = ["誕生", "① 凝聚", "② 秤出輕重", "③ 成形", "④ done"];

export default function BornLab() {
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [step, setStep] = useState(1);            // 0 = 已誕生(不再孕育)
  const [vizReady, setVizReady] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const timers = useRef<number[]>([]);

  useEffect(() => { getIndex().then(i => setEntries(i.stories.slice(0, 3))).catch(() => {}); }, []);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const ordered = entries.map(e => e.slug);
  const target = ordered[0];                       // 拿第一篇當「正在孕育」的那顆

  const clear = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  const at = (ms: number, fn: () => void) => timers.current.push(window.setTimeout(fn, ms));

  const born = () => {
    setStep(0);
    setFresh(new Set([target]));
    setConfirming(target);
    at(CONFIRM_MS, () => setConfirming(null));
  };

  // 真實時長:① 分鐘級(analyst)② 分鐘級(criticizer)③④ 秒級。這裡壓成秒看節奏。
  const runAll = () => {
    clear();
    setStep(1); setVizReady(false); setFresh(new Set()); setConfirming(null);
    at(2200, () => { setStep(2); setVizReady(true); });   // analyst 交件 → 早出 viz → 真骨現形
    at(5200, () => setStep(3));
    at(5800, () => setStep(4));
    at(6200, born);
  };

  const gestations: Map<string, Gestation> = step > 0 && target
    ? new Map([[target, { step, status: "running", title: entries[0]?.title ?? target, vizReady }]])
    : new Map();

  return (
    <div className="lab born-lab">
      <Dust />
      <div className="lab-bar">
        <span className="lab-tag">/lab/born · 誕生儀式 · 真元件,手動餵孕育狀態</span>
        <div className="lab-seg">
          {[1, 2, 3, 4].map(s => (
            <button key={s} className={step === s ? "on" : ""}
              onClick={() => { clear(); setStep(s); }}>{WORD[s]}</button>
          ))}
          <button className={step === 0 ? "on" : ""} onClick={() => { clear(); born(); }}>{WORD[0]}</button>
        </div>
        <div className="lab-slugs">
          {!target && <span className="lab-tag">讀不到 index.json</span>}
          <button className={vizReady ? "on" : ""} onClick={() => setVizReady(v => !v)}>
            {vizReady ? "真骨(早出 viz 已落檔)" : "塌縮(還沒資料)"}
          </button>
          <button onClick={runAll}>整條跑一遍</button>
        </div>
      </div>
      <Camera stage="catalog">
        <Orbits count={Math.max(1, ordered.length)} />
        <Catalog entries={entries} ordered={ordered} gestations={gestations} fresh={fresh}
          confirming={confirming} onPick={() => {}} onCancel={() => {}} />
      </Camera>
    </div>
  );
}
