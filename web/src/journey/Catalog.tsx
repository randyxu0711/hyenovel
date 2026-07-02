import { useEffect, useState } from "react";
import Skeleton from "../viz/Skeleton";
import { getViz } from "../data/client";
import { worldPos, WORLD } from "../lib/camera";
import type { IndexEntry, VizData } from "../types";

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

export default function Catalog(
  { entries, loading, flying, bursting, onPick }:
  { entries: IndexEntry[]; loading?: boolean; flying?: string | null; bursting?: boolean; onPick: (slug: string) => void },
) {
  // 改用確定性環形佈局:清掉舊的手動拖曳位置記憶,不再讓使用者拖動(拖會弄亂軌道)。
  useEffect(() => { try { localStorage.removeItem("hyenovel:catalog-pos"); } catch { /* ignore */ } }, []);

  if (loading) return <div className="field" />;
  if (entries.length === 0) return (
    <div className="empty-state"><div className="es-big">這片星空還沒有故事</div>
      <div className="es-sub">往下,新增第一篇</div></div>
  );

  return (
    <div className="field">
      {entries.map((e, i) => {
        const base = worldPos(i, WORLD, entries.length);
        const isFly = e.slug === flying;
        const fly = isFly
          ? { transform: `translate(-50%,-50%) translate(${WORLD.w / 2 - base.x}px, ${WORLD.h / 2 - base.y}px) scale(3)` }
          : null;
        return (
          <div className={`story skel-in${isFly ? " flying" : ""}`} data-testid="story" key={e.slug}
            style={{ left: base.x, top: base.y, animationDelay: `${i * 0.12}s`, ...fly }}
            onClick={() => onPick(e.slug)}>
            <StoryBone slug={e.slug} hasViz={e.has_viz} burst={isFly && !!bursting} />
            <div className="cap">{e.title}</div>
          </div>
        );
      })}
    </div>
  );
}
