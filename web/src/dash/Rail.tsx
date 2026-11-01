import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Work } from "./api";
import { useT } from "./i18n";
import { toggleDayNight } from "./theme";
import { dotState, useSeen } from "./useSeen";
import WorksMenu from "./WorksMenu";

/** 左欄。展開(home)列作品;收起(作品頁、設定)只剩圖示鍵,作品從浮層選。 */
export default function Rail({ collapsed, works, current, onOpen, onNew, onSubmitNew }: {
  collapsed: boolean; works: Work[]; current: string | null;
  onOpen: (slug: string) => void; onNew: () => void;
  /** 交新稿;沒給就當成開新對話。 */
  onSubmitNew?: () => void;
}) {
  const t = useT();
  const nav = useNavigate();
  const { seen } = useSeen();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [menu, setMenu] = useState(false);
  return (
    <nav className="dash-rail" aria-label={t("rail.works")} data-collapsed={collapsed ? "true" : "false"}>
      <b className="dash-dm rail-brand">{t("brand")}</b>
      <button type="button" className="rail-btn" aria-label={t("rail.new")} onClick={onNew}>{collapsed ? <span aria-hidden="true">+</span> : t("rail.new")}</button>
      {collapsed ? (
        <button type="button" className="rail-btn" ref={setAnchor} aria-label={t("rail.works")} aria-expanded={menu}
          onClick={() => setMenu(m => !m)}>
          <span aria-hidden="true">≡</span>
        </button>
      ) : (
        <ul className="rail-lists">
          {works.map(w => {
            const s = dotState(w, seen(w.slug));
            return (
              <li key={w.slug}>
                <button type="button" className="rail-work" aria-current={w.slug === current ? "true" : undefined} onClick={() => onOpen(w.slug)}>
                  <span className="rail-title">{w.title}</span>
                  {s !== "none" && <span className="rail-dot" data-state={s} role="img" aria-label={t(s === "busy" ? "rail.busy" : "rail.fresh")} />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {!collapsed && onSubmitNew && <button type="button" className="rail-btn" onClick={onSubmitNew}>{t("menu.submitNew")}</button>}
      <div className="rail-foot">
        <button type="button" className="rail-btn" aria-label={t("rail.settings")} onClick={() => nav("/settings")}>
          {collapsed ? <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M2 5h12M2 11h12" /><circle cx="6" cy="5" r="1.8" fill="var(--dash-desk-2)" /><circle cx="10" cy="11" r="1.8" fill="var(--dash-desk-2)" /></svg> : t("rail.settings")}
        </button>
        <button type="button" className="rail-btn" aria-label={t("rail.dayNight")} onClick={toggleDayNight}>
          {collapsed ? <span aria-hidden="true">◐</span> : t("rail.dayNight")}
        </button>
      </div>
      {menu && anchor && <WorksMenu anchor={anchor} works={works} current={current} onOpen={onOpen}
        onSubmitNew={onSubmitNew ?? onNew} onClose={() => setMenu(false)} />}
    </nav>
  );
}
