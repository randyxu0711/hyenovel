import { useEffect, useState } from "react";
import Skeleton from "../viz/Skeleton";
import GestatingStar from "./GestatingStar";
import { getViz } from "../data/client";
import { worldPos, WORLD } from "../lib/camera";
import type { IndexEntry, VizData, Gestation } from "../types";

// 每篇載入自己的 viz.json,畫出資料驅動的星骨指紋(載入中先留空位)。
function StoryBone({ slug, hasViz, burst }: { slug: string; hasViz: boolean; burst?: boolean }) {
  const [viz, setViz] = useState<VizData | null>(null);
  useEffect(() => {
    if (!hasViz) return;
    let live = true;
    getViz(slug).then(v => { if (live) setViz(v); }).catch(() => {});
    return () => { live = false; };
  }, [slug, hasViz]);
  if (!viz) return <div className="bone-ph" style={{ width: 300, height: 184 }} />;
  return <Skeleton viz={viz} width={300} burst={burst} />;
}

const WORD = ["", "凝聚", "長出骨架", "秤出輕重", "成形"];

export default function Catalog(
  { entries, ordered, loading, flying, bursting, gestations, hatching, fresh, onPick, onCancel }:
  {
    entries: IndexEntry[]; ordered: string[]; loading?: boolean; flying?: string | null; bursting?: boolean;
    gestations: Map<string, Gestation>; hatching?: string | null; fresh?: Set<string>;
    onPick: (slug: string) => void; onCancel: (slug: string) => void;
  },
) {
  useEffect(() => { try { localStorage.removeItem("hyenovel:catalog-pos"); } catch { /* ignore */ } }, []);

  if (loading) return <div className="field" />;
  if (ordered.length === 0) return (
    <div className="empty-state"><div className="es-big">這片星空還沒有故事</div>
      <div className="es-sub">往下,新增第一篇</div></div>
  );

  const byslug = new Map(entries.map(e => [e.slug, e]));
  const cx = WORLD.w / 2, cy = WORLD.h / 2;

  return (
    <div className="field">
      {ordered.map((slug, i) => {
        const base = worldPos(i, WORLD, ordered.length);
        const gest = gestations.get(slug);
        const entry = byslug.get(slug);
        const isFly = slug === flying;
        const isHatch = slug === hatching;
        // hatching:用 hatchIn 動畫(靠 --hx/--hy 從中心飛到槽位),不套 skel-in 以免兩動畫互相覆蓋
        const cls = `story ${isHatch ? "hatching" : "skel-in"}${isFly ? " flying" : ""}${gest ? " gestating" : ""}${!gest && fresh?.has(slug) ? " fresh" : ""}`;
        const style: React.CSSProperties = isHatch
          ? { left: base.x, top: base.y, ["--hx"]: `${cx - base.x}px`, ["--hy"]: `${cy - base.y}px` } as React.CSSProperties
          : isFly
            ? { left: base.x, top: base.y, animationDelay: `${i * 0.12}s`,
                transform: `translate(-50%,-50%) translate(${cx - base.x}px, ${cy - base.y}px) scale(3)` }
            : { left: base.x, top: base.y, animationDelay: `${i * 0.12}s` };
        return (
          <div className={cls} data-testid="story" key={slug} style={style}
            onClick={() => { if (!gest) onPick(slug); }}>
            {gest
              ? <GestatingStar step={gest.step} width={300} />
              : <StoryBone slug={slug} hasViz={!!entry?.has_viz} burst={isFly && !!bursting} />}
            <div className="cap">{gest ? gest.title : entry?.title}</div>
            {gest && <div className="gest-word">{WORD[Math.min(4, gest.step)]}</div>}
            {gest && gest.step < 4 && (
              <button className="gest-x" onClick={e => { e.stopPropagation(); onCancel(slug); }}>✕ 取消</button>
            )}
          </div>
        );
      })}
    </div>
  );
}
