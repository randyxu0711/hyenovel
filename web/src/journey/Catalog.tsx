import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Skeleton from "../viz/Skeleton";
import { getViz } from "../data/client";
import { worldPos, WORLD } from "../lib/camera";
import type { IndexEntry, VizData } from "../types";

// 每篇載入自己的 viz.json,畫出資料驅動的星骨指紋(載入中先留空位)。
function StoryBone({ slug, hasViz }: { slug: string; hasViz: boolean }) {
  const [viz, setViz] = useState<VizData | null>(null);
  useEffect(() => {
    if (!hasViz) return;
    let live = true;
    getViz(slug).then(v => { if (live) setViz(v); }).catch(() => {});
    return () => { live = false; };
  }, [slug, hasViz]);
  if (!viz) return <div className="bone-ph" style={{ width: 300, height: 184 }} />;
  return <Skeleton viz={viz} width={300} />;
}

export default function Catalog({ entries, loading }: { entries: IndexEntry[]; loading?: boolean }) {
  const nav = useNavigate();
  if (loading) return <div className="field" />;
  if (entries.length === 0) return (
    <div className="empty-state"><div className="es-big">這裡還沒有故事</div>
      <div className="es-add">＋ 放進第一篇(下一階段)</div></div>
  );
  return (
    <div className="field">
      {entries.map((e, i) => {
        const p = worldPos(i, WORLD);
        return (
          <div className="story skel-in" data-testid="story" key={e.slug}
            style={{ left: p.x, top: p.y, animationDelay: `${i * 0.12}s` }}
            onClick={() => nav(`/story/${e.slug}`)}>
            <StoryBone slug={e.slug} hasViz={e.has_viz} />
            <div className="cap">{e.title}</div>
          </div>
        );
      })}
    </div>
  );
}
