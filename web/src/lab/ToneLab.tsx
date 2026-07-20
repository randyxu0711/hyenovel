import { useEffect, useState } from "react";
import Dust from "../journey/Dust";
import "./lab.css";

// /lab/tone — 字的家法樣張:左欄「舊」用 inline 硬字級重現映射前(不受 type-scale
// 守門測試管,它只掃 .css);右欄「新」吃 --t-* token。使用者目測拍板(spec §4),
// 不上 Playwright。art B 的大氣開關日後擴充在本頁。
const SERIF = "var(--serif)";
const SANS = "var(--sans)";

interface Row {
  tok: string; px: number; role: string; text: string;
  old: { px: number; family: string; ls?: string };
  neo: { family: string; ls?: string };
}
const ROWS: Row[] = [
  { tok: "--t-micro", px: 11, role: "疏排微標(add-lab / dock-t)", text: "編輯 · 討論",
    old: { px: 10.5, family: SANS, ls: ".22em" }, neo: { family: SERIF, ls: ".22em" } },
  { tok: "--t-caption", px: 13, role: "提示 / 次要說明(hint / ghost 鈕)", text: "點一下節點,回饋會錨定到這裡",
    old: { px: 13.5, family: SANS }, neo: { family: SANS } },
  { tok: "--t-body", px: 15, role: "回饋正文 / 氣泡(fb p / bubble)", text: "這一段的沉默,是整篇最大聲的地方。",
    old: { px: 14, family: SANS }, neo: { family: SERIF } },
  { tok: "--t-lead", px: 17, role: "原文(src)", text: "伊共彼句話囥佇心肝底,規暗攏無講。",
    old: { px: 17, family: SERIF }, neo: { family: SERIF } },
  { tok: "--t-title", px: 21, role: "區段題(dock-label / fb-sec)", text: "整體閱讀",
    old: { px: 21, family: SERIF }, neo: { family: SERIF } },
  { tok: "--t-display", px: 27, role: "目錄標題(.cap)", text: "海口的暗暝",
    old: { px: 24, family: SERIF }, neo: { family: SERIF } },
  { tok: "--t-hero", px: 34, role: "單篇大標(single-top h2)", text: "海口的暗暝",
    old: { px: 33, family: SERIF }, neo: { family: SERIF } },
  { tok: "--t-total", px: 46, role: "展示級總額(uc-big)", text: "$0.84",
    old: { px: 46, family: SERIF }, neo: { family: SERIF } },
];

// 舊天(映射前)參考值——僅樣張對照用,正本已改 --sky
const OLD_SKY = "radial-gradient(120% 90% at 50% 34%, #15140f 0%, #0c0b09 52%, #050504 100%)";

// 視差預覽:模擬相機緩慢巡航(sine),讓分層深度看得見;減動不巡航
function useSwayCam(on: boolean) {
  const [cam, setCam] = useState({ x: 0, y: 0 });
  useEffect(() => {
    if (!on || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { setCam({ x: 0, y: 0 }); return; }
    let raf = 0; const t0 = performance.now();
    const loop = (t: number) => {
      const p = ((t - t0) / 6000) * 2 * Math.PI;
      setCam({ x: Math.sin(p) * 700, y: Math.cos(p) * 160 });
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [on]);
  return cam;
}

function SkyPane({ label, sky, cam, grain, halo }:
  { label: string; sky?: string; cam?: { x: number; y: number }; grain: boolean; halo: boolean }) {
  return (
    <div className="tone-sky" style={sky ? { background: sky } : undefined}>
      <Dust cam={cam} />
      {halo && <>
        <span className="tone-star" style={{ left: "30%", top: "40%" }} />
        <span className="tone-star" style={{ left: "68%", top: "58%" }} />
      </>}
      {grain && <div className="grain" aria-hidden />}
      <span className="tone-sky-cap">海口的暗暝</span>
      <span className="tone-sky-lab">{label}</span>
    </div>
  );
}

export default function ToneLab() {
  const [cold, setCold] = useState(true);
  const [par, setPar] = useState(true);
  const [grain, setGrain] = useState(true);
  const [halo, setHalo] = useState(true);
  const cam = useSwayCam(par);
  return (
    <div className="lab tone">
      <div className="lab-top"><span className="lab-tag">/lab/tone · 字的家法樣張 · 左舊右新,目測拍板</span></div>
      <div className="tone-grid">
        <div className="tone-h">舊(映射前)</div>
        <div className="tone-h"></div>
        <div className="tone-h">新(七階 + serif 前傾)</div>
        {ROWS.map(r => (
          <div key={r.tok} style={{ display: "contents" }}>
            <div className="tone-cell" style={{ fontSize: r.old.px, fontFamily: r.old.family, letterSpacing: r.old.ls }}>{r.text}</div>
            <div className="tone-mid">
              <div className="tone-tok">{r.tok} · {r.px}px</div>
              <div className="tone-role">{r.role}</div>
            </div>
            <div className="tone-cell" style={{ fontSize: `var(${r.tok})`, fontFamily: r.neo.family, letterSpacing: r.neo.ls }}>{r.text}</div>
          </div>
        ))}
      </div>
      <div className="tone-sky-bar">
        {([["冷底", cold, setCold], ["視差塵埃", par, setPar],
           ["grain", grain, setGrain], ["星暈", halo, setHalo]] as const).map(([name, v, set]) => (
          <label key={name}><input type="checkbox" checked={v} onChange={e => set(e.target.checked)} />{name}</label>
        ))}
      </div>
      <div className="tone-sky-row">
        <SkyPane label="前(暖 radial)" sky={OLD_SKY} grain={false} halo={false} />
        <SkyPane label="後(冷夜裡的暖光)" sky={cold ? undefined : OLD_SKY}
          cam={par ? cam : undefined} grain={grain} halo={halo} />
      </div>
    </div>
  );
}
