import { useEffect, useRef } from "react";
import type { Work } from "./api";
import { useT } from "./i18n";
import { dotState, useSeen } from "./useSeen";

/** 收起的左欄裡「作品」鍵彈出的浮層:列作品與狀態;Esc 或點外面關閉。 */
export default function WorksMenu({ anchor, below = false, works, current, onOpen, onSubmitNew, onClose }: {
  anchor: HTMLElement; works: Work[]; current: string | null;
  /** 開在錨的下方(稿窗格的標題);預設開在右側(收起的左欄)。 */
  below?: boolean;
  onOpen: (slug: string) => void; onSubmitNew: () => void; onClose: () => void;
}) {
  const t = useT();
  const { seen } = useSeen();
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    const onDown = (e: MouseEvent) => {
      const el = e.target as Node;
      if (!box.current?.contains(el) && !anchor.contains(el)) onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("mousedown", onDown); };
  }, [anchor, onClose]);
  useEffect(() => {
    box.current?.querySelector("button")?.focus();
    return () => anchor.focus();   // 關閉(Esc/選取/點外面)時把焦點還給錨
  }, [anchor]);

  const r = anchor.getBoundingClientRect();
  return (
    <div ref={box} className="dash-float works-menu" role="dialog" aria-label={t("rail.works")}
      style={below ? { left: r.left, top: r.bottom + 6 } : { left: r.right + 8, top: r.top }}>
      <ul>
        {works.map(w => {
          const s = dotState(w, seen(w.slug));
          return (
            <li key={w.slug}>
              <button type="button" className="works-item" aria-current={w.slug === current ? "true" : undefined}
                onClick={() => { onOpen(w.slug); onClose(); }}>
                <span className="rail-title">{w.title}</span>
                {s !== "none" && <span className="works-state">{t(s === "busy" ? "rail.busy" : "rail.fresh")}</span>}
              </button>
            </li>
          );
        })}
      </ul>
      <button type="button" className="works-new" onClick={() => { onSubmitNew(); onClose(); }}>{t("menu.submitNew")}</button>
    </div>
  );
}
