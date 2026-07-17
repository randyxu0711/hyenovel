import { useEffect, useRef, useState } from "react";
import Camera from "../journey/Camera";
import Catalog from "../journey/Catalog";
import Orbits from "../journey/Orbits";
import Dust from "../journey/Dust";
import { getIndex } from "../data/client";
import type { IndexEntry } from "../types";
import "../journey/journey.css";
import "./lab.css";

// /lab/born —— 誕生確認波的看板。真 Camera + 真 Orbits + 真 Catalog + 真 viz,
// 只有 confirming 這個 prop 是手動餵的:所以這裡看到的波,就是 onBorn 當下會看到的那一個(不畫替身)。
// 存在理由:真觸發要跑完一次孕育(燒訂閱、要好幾分鐘),而 jsdom 不跑動畫、測試看不見視覺。

const CONFIRM_MS = 1800;   // 與 Journey 的 CONFIRM_MS、CSS bornWave 對齊

export default function BornLab() {
  const [entries, setEntries] = useState<IndexEntry[]>([]);
  const [confirming, setConfirming] = useState<string | null>(null);
  const timer = useRef<number>();

  useEffect(() => { getIndex().then(i => setEntries(i.stories.slice(0, 3))).catch(() => {}); }, []);
  useEffect(() => () => clearTimeout(timer.current), []);

  const ordered = entries.map(e => e.slug);
  // 先卸再掛(隔一幀):同一篇連按兩次,class 沒變動畫就不重跑 —— 要能反覆看才有得調
  const fire = (s: string) => {
    clearTimeout(timer.current);
    setConfirming(null);
    requestAnimationFrame(() => {
      setConfirming(s);
      timer.current = window.setTimeout(() => setConfirming(null), CONFIRM_MS);
    });
  };

  return (
    <div className="lab born-lab">
      <Dust />
      <div className="lab-bar">
        <span className="lab-tag">/lab/born · 誕生確認波 · 真 Catalog,手動餵 confirming</span>
        <div className="lab-slugs">
          {ordered.length === 0 && <span className="lab-tag">讀不到 index.json</span>}
          {ordered.map(s => (
            <button key={s} className={s === confirming ? "on" : ""} onClick={() => fire(s)}>放 {s}</button>
          ))}
        </div>
      </div>
      <Camera stage="catalog">
        <Orbits count={Math.max(1, ordered.length)} />
        <Catalog entries={entries} ordered={ordered} gestations={new Map()} confirming={confirming}
          onPick={() => {}} onCancel={() => {}} />
      </Camera>
    </div>
  );
}
