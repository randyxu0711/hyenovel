import { useEffect, useState } from "react";
import Skeleton from "../viz/Skeleton";
import { getUsageAll, getViz } from "../data/client";
import type { IndexEntry, UsageAll, UsageStory, VizData } from "../types";

// 用量星圖:獨立一層。星的大小 = 花費(面積正比);年輪 = 重跑次數;暖紅 = 機器重試過。
// hover 綻開成那具骨 + 浮出每節點單價。點星 → 進該篇用量。
const R_MIN = 7, R_MAX = 19;

function fmtUsd(n: number) { return "$" + n.toFixed(2); }
function fmtK(n: number) { return n < 1000 ? String(n) : (n / 1000).toFixed(0) + "k"; }
function fmtMin(ms: number) { return Math.round(ms / 60000) + " 分鐘"; }

// 面積正比於花費 → 半徑取根號(直接拿花費當半徑會誇大差距)
function radius(cost: number, max: number) {
  if (max <= 0) return R_MIN;
  return Math.max(R_MIN, R_MAX * Math.sqrt(cost / max));
}

// 均分一圈(橢圓,呼應軌道);起相位朝上
function pos(i: number, n: number) {
  const a = (i / Math.max(1, n)) * 2 * Math.PI - Math.PI / 2;
  return { left: `${50 + Math.cos(a) * 36}%`, top: `${50 + Math.sin(a) * 31}%` };
}

function Star(
  { s, entry, maxCost, i, n, onPick }:
  { s: UsageStory; entry?: IndexEntry; maxCost: number; i: number; n: number;
    onPick: (slug: string) => void },
) {
  const [viz, setViz] = useState<VizData | null>(null);
  const r = radius(s.cost_usd, maxCost);
  const nodes = entry?.nodes ?? 0;
  // 分子=最後一次 critique 的錢,分母=最新那具骨的節點數(兩者對齊;不然重跑過的會被高估)
  const unit = nodes > 0 ? s.last_run_cost_usd / nodes : 0;

  // hover 才抓 viz(骨):不預載,五篇不必一開就打五個請求
  const bloom = () => { if (!viz) getViz(s.slug).then(v => v && setViz(v)).catch(() => {}); };

  return (
    <div className="ustar" data-slug={s.slug} style={pos(i, n)} onClick={() => onPick(s.slug)}
      onMouseEnter={bloom} role="button" tabIndex={0} onFocus={bloom}
      onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(s.slug); } }}>
      <div className="ucore-wrap">
        {/* 年輪:你重跑過幾次 */}
        {Array.from({ length: s.runs }, (_, k) => (
          <span key={k} className="uring"
            style={{ width: `${(r + 6 + k * 5) * 2}px`, height: `${(r + 6 + k * 5) * 2}px`,
                     animationDelay: `${1.05 + k * 0.12}s` }} />
        ))}
        {/* 疤:機器重試過(閘門擋下幻覺引用而重派) */}
        {s.retry_count > 0 && (
          <span className="uscar"
            style={{ width: `${(r + 6 + s.runs * 5) * 2}px`, height: `${(r + 6 + s.runs * 5) * 2}px`,
                     animationDelay: `${1.05 + s.runs * 0.12}s` }} />
        )}
        {/* 星:大小 = 花費 */}
        <span className="udot" style={{ width: `${r * 2}px`, height: `${r * 2}px`,
                                        animationDelay: `${0.62 + i * 0.09}s` }} />
        {/* hover:綻成那具骨 */}
        {viz && <span className="ubone"><Skeleton viz={viz} width={120} /></span>}
      </div>
      <div className="uname">{entry?.title ?? s.slug}</div>
      <div className="ucost">{fmtUsd(s.cost_usd)}</div>
      <div className="uunit">
        {nodes > 0 ? `${nodes} 節點 · $${unit.toFixed(3)} / 節點` : `${fmtK(s.tokens)} tokens`}
        {s.runs > 1 && ` · 重跑 ${s.runs} 次`}
      </div>
    </div>
  );
}

export default function UsageMap(
  { entries, onPick, onClose, from }:
  { entries: IndexEntry[]; onPick: (slug: string) => void; onClose: () => void;
    from?: { x: number; y: number } },   // 入口那行小字的位置 → 它飛進來、變成中心的大數字
) {
  const [all, setAll] = useState<UsageAll | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getUsageAll().then(a => { if (live) setAll(a); }).catch(() => { if (live) setErr("讀不到用量"); });
    return () => { live = false; };
  }, []);

  const byslug = new Map(entries.map(e => [e.slug, e]));
  const shell = (body: React.ReactNode) => (
    <div className="umap" data-testid="usage-map">
      <button className="umap-x" onClick={onClose} aria-label="關閉">✕</button>
      {body}
    </div>
  );

  if (err) return shell(<div className="umap-msg">{err}</div>);
  if (!all) return shell(<div className="umap-msg">載入中…</div>);
  if (all.empty) return shell(
    <div className="umap-msg">這片星空還沒有用量。<br />跑一次 critique 就有了。</div>);

  const t = all.total;
  const tokens = t.input + t.output + t.cache_creation + t.cache_read;
  const maxCost = Math.max(...all.stories.map(s => s.cost_usd), 0.0001);
  const stars = [...all.stories].sort((a, b) => b.cost_usd - a.cost_usd);
  const ph = (k: string) => all.phases[k];
  const maxPhase = Math.max(...Object.values(all.phases).map(p => p.cost_usd), 0.0001);
  const discuss = ph("discuss");
  const dPct = discuss && t.cost_usd > 0 ? Math.round((discuss.cost_usd / t.cost_usd) * 100) : 0;
  const rPct = t.cost_usd > 0 ? Math.round((all.retry_cost_usd / t.cost_usd) * 100) : 0;

  // 那行小字飛向中心:算它相對於畫面正中的位移(FLIP;沒有 from 就直接就位)
  const fly = from
    ? { ["--fx"]: `${from.x - window.innerWidth / 2}px`,
        ["--fy"]: `${from.y - window.innerHeight / 2}px` } as React.CSSProperties
    : undefined;

  return shell(<>
    <svg className="umap-orbits" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <ellipse cx="50" cy="50" rx="36" ry="31" />
      <ellipse cx="50" cy="50" rx="22" ry="19" />
    </svg>

    <div className={`ucenter${from ? " flyin" : ""}`} style={fly}>
      <span className="uc-halo" />
      <div className="uc-big">{fmtUsd(t.cost_usd)}</div>
      <div className="uc-est">估 算</div>
      <div className="uc-sub">{all.stories.length} 篇 · {fmtK(tokens)} tokens</div>
    </div>

    <div className="ufield">
      {stars.map((s, i) => (
        <Star key={s.slug} s={s} entry={byslug.get(s.slug)} maxCost={maxCost}
          i={i} n={stars.length} onPick={onPick} />
      ))}
    </div>

    {/* ── 星塵:散在黑暗裡,不裝盒子 ── */}
    <div className="udust ud-tl">
      <div className="ud-lab">花在哪格</div>
      {["analyst", "criticizer"].filter(k => ph(k)).map(k => (
        <div className="ud-row" key={k}>
          <span className="ud-key">{k}</span>
          <span className="ud-track">
            <span className="ud-fill" style={{ width: `${(ph(k).cost_usd / maxPhase) * 100}%` }} />
          </span>
          <span className="ud-val">{fmtUsd(ph(k).cost_usd)}</span>
        </div>
      ))}
      {discuss ? (
        <div className="ud-row">
          <span className="ud-key">discuss</span>
          <span className="ud-track">
            <span className="ud-fill" style={{ width: `${(discuss.cost_usd / maxPhase) * 100}%` }} />
          </span>
          <span className="ud-val">{fmtUsd(discuss.cost_usd)}</span>
        </div>
      ) : null}
      <div className="ud-foot">
        {discuss ? `討論 ${discuss.turns} 輪 · 佔 ${dPct}%` : "尚未討論過"}
      </div>
    </div>

    <div className="udust ud-tr">
      <div className="ud-lab scar">重試燒掉</div>
      <div className="ud-big scar">{fmtUsd(all.retry_cost_usd)}</div>
      <div className="ud-foot">{all.retry_count} 次 · 佔總量 {rPct}%</div>
    </div>

    <div className="udust ud-bl">
      <div className="ud-lab">機器讀寫了</div>
      <div className="ud-big">{fmtMin(all.duration_ms)}</div>
    </div>

    <div className="udust ud-br">
      <div className="ud-lab">cache 命中</div>
      <div className="ud-big">{Math.round(all.cache_read_ratio * 100)}%</div>
    </div>
  </>);
}
