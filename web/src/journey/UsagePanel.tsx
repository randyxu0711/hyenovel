import { useEffect, useState } from "react";
import { getUsage } from "../data/client";
import type { UsageAggregate } from "../types";

const PHASE_ORDER = ["analyst", "criticizer", "discuss"] as const;

function fmtK(n: number) { return n < 1000 ? String(n) : (n / 1000).toFixed(1).replace(/\.0$/, "") + "k"; }
function fmtUsd(n: number) { return "$" + n.toFixed(2); }

export default function UsagePanel({ slug }: { slug: string }) {
  const [agg, setAgg] = useState<UsageAggregate | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setAgg(null); setErr(null);
    getUsage(slug).then(a => { if (live) setAgg(a); }).catch(() => { if (live) setErr("讀不到用量"); });
    return () => { live = false; };
  }, [slug]);

  if (err) return <div className="u-msg">{err}</div>;
  if (!agg) return <div className="u-msg">載入中…</div>;
  if (agg.empty) return <div className="u-msg">尚無用量,重跑一次 critique 才有。</div>;

  const t = agg.total;
  const tokens = t.input + t.output + t.cache_creation + t.cache_read;
  const cachePct = Math.round(agg.cache_read_ratio * 100);
  const phases = PHASE_ORDER.filter(p => agg.phases[p]);
  const maxCost = Math.max(...phases.map(p => agg.phases[p].cost_usd), 0.0001);

  return (
    <div className="u">
      <div className="u-sec">花了多少</div>
      <div className="u-hero">
        <span className="big">{fmtUsd(t.cost_usd)}</span>
        <span className="sub">{fmtK(tokens)} tokens<br />cache 命中 {cachePct}%</span>
      </div>

      <div className="u-sec">花在哪格</div>
      {phases.map(p => {
        const ph = agg.phases[p];
        const label = p === "discuss" ? `discuss · ${ph.turns} 輪` : p;
        const w = Math.round((ph.cost_usd / maxCost) * 100);
        return (
          <div className="prow" key={p}>
            <span className="pk">{label}</span>
            <span className="track"><span className="fill" style={{ width: `${w}%` }} /></span>
            <span className="pv">{fmtUsd(ph.cost_usd)}</span>
          </div>
        );
      })}

      <div className="u-sec">效率</div>
      <div className="u-eff">
        <div><span className="lab">cache 省下</span><span className="n">~{fmtK(t.cache_read)} token</span></div>
        <div><span className="lab">重試</span><span className="n">{agg.retry_count} 次 · {fmtUsd(agg.retry_cost_usd)}</span></div>
      </div>
    </div>
  );
}
