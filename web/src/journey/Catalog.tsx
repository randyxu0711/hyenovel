import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Skeleton from "../viz/Skeleton";
import { getViz } from "../data/client";
import { worldPos, WORLD, fitScale, zoomFor } from "../lib/camera";
import { useViewport } from "../lib/useViewport";
import type { IndexEntry, VizData } from "../types";

type XY = { x: number; y: number };
const POS_KEY = "hyenovel:catalog-pos";
const loadPos = (): Record<string, XY> => {
  try { return JSON.parse(localStorage.getItem(POS_KEY) || "{}"); } catch { return {}; }
};

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
  const vp = useViewport();
  const scale = zoomFor("catalog", fitScale(WORLD, vp.w, vp.h)); // 螢幕px → 世界px 的換算
  const [pos, setPos] = useState<Record<string, XY>>(loadPos);
  const drag = useRef<{ slug: string; sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null);

  // 拖過就記住位置(下次開還在原地)
  useEffect(() => { try { localStorage.setItem(POS_KEY, JSON.stringify(pos)); } catch { /* ignore */ } }, [pos]);

  if (loading) return <div className="field" />;
  if (entries.length === 0) return (
    <div className="empty-state"><div className="es-big">這裡還沒有故事</div>
      <div className="es-add">＋ 放進第一篇(下一階段)</div></div>
  );

  const down = (ev: React.PointerEvent, slug: string, base: XY) => {
    drag.current = { slug, sx: ev.clientX, sy: ev.clientY, ox: base.x, oy: base.y, moved: false };
    (ev.currentTarget as HTMLElement).setPointerCapture?.(ev.pointerId);
  };
  const move = (ev: React.PointerEvent) => {
    const d = drag.current; if (!d) return;
    if (Math.abs(ev.clientX - d.sx) + Math.abs(ev.clientY - d.sy) > 4) d.moved = true;
    if (d.moved) setPos(s => ({ ...s, [d.slug]: { x: d.ox + (ev.clientX - d.sx) / scale, y: d.oy + (ev.clientY - d.sy) / scale } }));
  };
  const up = (ev: React.PointerEvent, slug: string) => {
    const d = drag.current; drag.current = null;
    (ev.currentTarget as HTMLElement).releasePointerCapture?.(ev.pointerId);
    if (d && !d.moved) nav(`/story/${slug}`); // 沒拖動 = 點擊 → 進單篇
  };

  return (
    <div className="field">
      {entries.map((e, i) => {
        const base = pos[e.slug] ?? worldPos(i, WORLD);
        return (
          <div className="story skel-in" data-testid="story" key={e.slug}
            style={{ left: base.x, top: base.y, animationDelay: `${i * 0.12}s` }}
            onPointerDown={ev => down(ev, e.slug, base)}
            onPointerMove={move}
            onPointerUp={ev => up(ev, e.slug)}>
            <StoryBone slug={e.slug} hasViz={e.has_viz} />
            <div className="cap">{e.title}</div>
          </div>
        );
      })}
    </div>
  );
}
