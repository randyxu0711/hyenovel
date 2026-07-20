import { useEffect, useState } from "react";
import Skeleton from "../viz/Skeleton";
import { getUsageAll, getViz } from "../data/client";
import { usageLayout, ringRadii, RING_XSCALE } from "../lib/camera";
import { useViewport } from "../lib/useViewport";
import type { IndexEntry, UsageAll, UsageStory, VizData } from "../types";

// 用量星圖:獨立一層。星的大小 = 花費(面積正比);年輪 = 重跑次數;暖紅 = 機器重試過。
// hover 綻開成那具骨 + 浮出每節點單價。點星 → 進該篇用量。
// U1(usage-sky):星落在目錄的真槽位(worldPos),不是自己的花費排序橢圓——
// 兩片天用同一組幾何,使用者才能把「哪顆星在哪」和目錄記憶對上。
const R_MIN = 7, R_MAX = 19;

function fmtUsd(n: number) { return "$" + n.toFixed(2); }
function fmtK(n: number) { return n < 1000 ? String(n) : (n / 1000).toFixed(0) + "k"; }
function fmtMin(ms: number) { return Math.round(ms / 60000) + " 分鐘"; }

// 面積正比於花費 → 半徑取根號(直接拿花費當半徑會誇大差距)
function radius(cost: number, max: number) {
  if (max <= 0) return R_MIN;
  return Math.max(R_MIN, R_MAX * Math.sqrt(cost / max));
}

// 槽位一律 ordered(目錄 orderRef)為準;帳本有、目錄已刪的孤兒排最後,不搶既有位
export function slots(ordered: string[], stories: { slug: string }[]): string[] {
  const extra = stories.map(s => s.slug).filter(s => !ordered.includes(s)).sort();
  return [...ordered, ...extra];
}

function Star(
  { s, entry, maxCost, pt, delay, onPick }:
  { s: UsageStory; entry?: IndexEntry; maxCost: number; pt: { x: number; y: number }; delay: number;
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
    <div className="ustar" data-slug={s.slug} style={{ left: pt.x, top: pt.y }} onClick={() => onPick(s.slug)}
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
                                        animationDelay: `${0.62 + delay * 0.09}s` }} />
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

// 冷星(U3):有槽位、沒燒過錢——極暗餘燼,不消失(「哪幾篇還沒跑過」免費可見)。
// 未完成的不可導航(T8:主動線不進半殘單篇);完成而零用量的(舊 ingest)可點。
function ColdStar({ slug, entry, pt, onPick }:
  { slug: string; entry?: IndexEntry; pt: { x: number; y: number }; onPick: (s: string) => void }) {
  const go = !!(entry?.has_viz && entry?.has_feedback);
  return (
    <div className={`ustar cold${go ? "" : " inert"}`} data-slug={slug} style={{ left: pt.x, top: pt.y }}
      {...(go ? {
        role: "button", tabIndex: 0, onClick: () => onPick(slug),
        onKeyDown: (e: React.KeyboardEvent) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(slug); } },
      } : {})}>
      <div className="ucore-wrap"><span className="cdot" /></div>
      <div className="uname">{entry?.title ?? slug}</div>
      <div className="ucold-note">尚未跑過</div>
    </div>
  );
}

export default function UsageMap(
  { entries, ordered, onPick, onClose, from }:
  { entries: IndexEntry[]; ordered: string[]; onPick: (slug: string) => void; onClose: () => void;
    from?: { x: number; y: number } },   // 入口那行小字的位置 → 它飛進來、變成中心的大數字
) {
  const [all, setAll] = useState<UsageAll | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const vp = useViewport();

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
  const hot = new Map(all.stories.map(s => [s.slug, s]));
  const slotList = slots(ordered, all.stories);
  const { z, pts } = usageLayout(slotList.length, vp.w, vp.h);
  const maxCost = Math.max(...all.stories.map(s => s.cost_usd), 0.0001);   // 冷星無帳,天然不參與
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
    <svg className="umap-orbits" aria-hidden="true">
      {ringRadii(slotList.length).map((R, k) => (
        <ellipse key={k} cx={vp.w / 2} cy={vp.h / 2} rx={R * RING_XSCALE * z} ry={R * z} />
      ))}
    </svg>

    <div className={`ucenter${from ? " flyin" : ""}`} style={fly}>
      <span className="uc-halo" />
      <div className="uc-big">{fmtUsd(t.cost_usd)}</div>
      <div className="uc-est">估 算</div>
      <div className="uc-sub">{all.stories.length} 篇 · {fmtK(tokens)} tokens</div>
    </div>

    <div className="ufield">
      {slotList.map((slug, i) => {
        const s = hot.get(slug);
        return s
          ? <Star key={slug} s={s} entry={byslug.get(slug)} maxCost={maxCost}
              pt={pts[i]} delay={i} onPick={onPick} />
          : <ColdStar key={slug} slug={slug} entry={byslug.get(slug)} pt={pts[i]} onPick={onPick} />;
      })}
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
