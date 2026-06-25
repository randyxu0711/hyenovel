import { useNavigate } from "react-router-dom";
import Skeleton from "../viz/Skeleton";
import { worldPos, WORLD } from "../lib/camera";
import type { IndexEntry } from "../types";

// slug → 穩定數字 seed(決定該篇的骨架身分)
const seedOf = (slug: string) => [...slug].reduce((a, c) => a + c.charCodeAt(0), 0) || 7;

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
            <Skeleton seed={seedOf(e.slug)} width={300} />
            <div className="cap">{e.title}</div>
          </div>
        );
      })}
    </div>
  );
}
