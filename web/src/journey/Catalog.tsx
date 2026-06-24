import { useNavigate } from "react-router-dom";
import Skeleton from "../viz/Skeleton";
import type { IndexEntry } from "../types";

// 穩定假曲線(待 index.py 補 tension 後換真):slug → 8 點 0.25..0.85
function seedTension(slug: string): number[] {
  let s = [...slug].reduce((a, c) => a + c.charCodeAt(0), 0) || 7;
  const rnd = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
  return Array.from({ length: 8 }, () => 0.25 + rnd() * 0.6);
}
// 散布座標(穩定):後續可改主題聚類
const SPREAD = [["34%","52%"],["64%","42%"],["48%","70%"],["22%","36%"],["78%","60%"],["40%","26%"],["70%","76%"]];

export default function Catalog({ entries }: { entries: IndexEntry[] }) {
  const nav = useNavigate();
  if (entries.length === 0) return (
    <div className="empty-state"><div className="es-big">這裡還沒有故事</div>
      <div className="es-add">＋ 放進第一篇(下一階段)</div></div>
  );
  return (
    <div className="field">
      {entries.map((e, i) => {
        const [x, y] = SPREAD[i % SPREAD.length];
        return (
          <div className="story" data-testid="story" key={e.slug}
            style={{ left: x, top: y }} onClick={() => nav(`/story/${e.slug}`)}>
            <Skeleton beats={seedTension(e.slug)} width={300} />
            <div className="cap">{e.title}</div>
          </div>
        );
      })}
    </div>
  );
}
