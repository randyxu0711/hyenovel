import { useEffect, useState } from "react";
import Skeleton from "../viz/Skeleton";
import CloudCollapse from "./CloudCollapse";
import { getViz } from "../data/client";
import { worldPos, WORLD } from "../lib/camera";
import type { IndexEntry, VizData, Gestation } from "../types";

// 每篇載入自己的 viz.json,畫出資料驅動的星骨指紋(載入中先留空位)。
function StoryBone({ slug, hasViz, burst, reassemble }: { slug: string; hasViz: boolean; burst?: boolean; reassemble?: boolean }) {
  const [viz, setViz] = useState<VizData | null>(null);
  useEffect(() => {
    if (!hasViz) return;
    let live = true;
    getViz(slug).then(v => { if (live) setViz(v); }).catch(() => {});
    return () => { live = false; };
  }, [slug, hasViz]);
  if (!viz) return <div className="bone-ph" style={{ width: 300, height: 184 }} />;
  return <Skeleton viz={viz} width={300} burst={burst} reassemble={reassemble} />;
}

// 階段詞對齊「後端那格實際在幹嘛」,不是「跑完第幾格」:
//   step1 = analyst 跑(分鐘級)→ 凝聚:真的還沒有任何資料
//   step2 = criticizer 跑(分鐘級)→ 秤出輕重:那正是 criticizer 在做的事,骨此時已在場
//   step3 = render 跑(秒級)、step4 = done → 成形
// 「長出骨架」不是一格,是 step1→2 的轉場瞬間(真骨 reassemble 現形那一下),
// 畫面自己會講,不需要字。舊表把每個詞往後掛了一格:criticizer 跑了幾分鐘卻寫著
// 「長出骨架」(骨老早長出來了),而「秤出輕重」只閃在 render 那一兩秒。
const WORD = ["", "凝聚", "秤出輕重", "成形", "成形"];

export default function Catalog(
  { entries, ordered, loading, flying, bursting, gestations, hatching, fresh, returning, confirming, onPick, onCancel }:
  {
    entries: IndexEntry[]; ordered: string[]; loading?: boolean; flying?: string | null; bursting?: boolean;
    gestations: Map<string, Gestation>; hatching?: string | null; fresh?: Set<string>; returning?: string | null;
    confirming?: string | null;
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
        const isReturn = slug === returning;
        // hatching:--hx/--hy 從中心飛到槽位。returning:骨留在自己槽位,退場當下鏡頭正對焦此槽位
        // → 它就在鏡頭正中,零件於此對焦重組,鏡頭再拉遠把它帶回環上(運鏡即逆俯衝)。兩者都不套 skel-in。
        const cls = `story ${isHatch ? "hatching" : isReturn ? "returning" : "skel-in"}${isFly ? " flying" : ""}${gest ? " gestating" : ""}${!gest && fresh?.has(slug) ? " fresh" : ""}`;
        const style: React.CSSProperties = isHatch
          ? { left: base.x, top: base.y, ["--hx"]: `${cx - base.x}px`, ["--hy"]: `${cy - base.y}px` } as React.CSSProperties
          : isReturn
            ? { left: base.x, top: base.y }
            : isFly
              ? { left: base.x, top: base.y, animationDelay: `${i * 0.12}s`,
                  transform: `translate(-50%,-50%) translate(${cx - base.x}px, ${cy - base.y}px) scale(3)` }
              : { left: base.x, top: base.y, animationDelay: `${i * 0.12}s` };
        return (
          <div className={cls} data-testid="story" key={slug} style={style}
            onClick={() => { if (!gest) onPick(slug); }}>
            {/* 誕生確認波:骨真的在場才放(還在孕育就沒有「剛落位」可確認) */}
            {!gest && slug === confirming && <span className="bwave" aria-hidden><i /><i /><i /></span>}
            {/* 孕育中:早出 viz 落檔前是分子雲塌縮(真的還沒資料 → 不畫骨),落檔後直接換真骨——
                零件從四周聚回真座標(reassemble)。塵埃聚成骨那一刻,骨架真的在磁碟上。
                preview 產失敗(skip)也留在塌縮:沒資料就是沒資料,不拿假骨頂替。 */}
            {gest
              ? (gest.vizReady
                  ? <StoryBone slug={slug} hasViz reassemble />
                  : <CloudCollapse width={300} />)
              : <StoryBone slug={slug} hasViz={!!entry?.has_viz} burst={isFly && !!bursting} reassemble={isReturn} />}
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
