import { useEffect, useRef, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type RecentSession, type SessionRow, type Work } from "./api";
import { toggleDayNight, useThemeState } from "./theme";
import Icon, { type IconName } from "./Icon";
import Logo from "./Logo";
import { useLang, useT } from "./i18n";
import type { Talk as TalkState } from "./useTalk";
import type { ShelfMode } from "./useShelf";
import { dotState, useSeen } from "./useSeen";
import { whenLabel } from "./when";

const FILTER_FROM = 7;   // 作品超過 6 篇才出篩選框
const SHOWN = 3;         // 目前這篇露幾局

/** 張力指紋的 polyline points:x 平均鋪滿 w,intensity 0–1 由下往上;少於兩點不畫。 */
export function fpPoints(curve: number[], w: number, h: number): string {
  if (curve.length < 2) return "";
  const r = (n: number) => Math.round(n * 10) / 10;
  return curve.map((v, i) => `${r(i * w / (curve.length - 1))},${r((1 - v) * h)}`).join(" ");
}

const span = (v: SessionRow["versions"]) => !v ? "" : v[0] === v[1] ? `v${v[0]}` : `v${v[0]}–${v[1]}`;

/** 目前這篇的局:新到舊只露 3 局,多的收成「⋯」;最後「開一局」。串流中不能換局。 */
function Sessions({ talk, onDone }: { talk: TalkState; onDone?: () => void }) {
  const t = useT();
  const [all, setAll] = useState(false);
  const busy = talk.streaming !== null;
  const rows = all ? talk.sessions : talk.sessions.slice(0, SHOWN);
  const more = talk.sessions.length - rows.length;
  return (
    <ul className="shelf-sess" aria-label={t("session.list")}>
      {rows.map(r => (
        <li key={r.session}>
          <button type="button" disabled={busy} aria-current={r.session === talk.session ? "true" : undefined}
            onClick={() => { talk.open(r.session); onDone?.(); }}>
            <Icon name="talk" /><span className="shelf-st">{r.preview}</span><span className="shelf-vr">{span(r.versions)}</span>
          </button>
          <IB icon="box" label={t("session.archive")} className="ib shelf-x" disabled={busy} onClick={() => void talk.archive(r.session)} />
        </li>
      ))}
      {more > 0 && (
        <li><button type="button" aria-label={t("shelf.more", { n: more })} title={t("shelf.more", { n: more })}
          onClick={() => setAll(true)}><Icon name="dots" /></button></li>
      )}
      <li><button type="button" disabled={busy} aria-label={t("shelf.fresh")} title={t("shelf.fresh")}
        onClick={() => { talk.fresh(); onDone?.(); }}><Icon name="plus" /></button></li>
    </ul>
  );
}

/** 沒綁作品的局:最近的在上;+ 開一局新的純聊天。 */
function Chats({ talk, onChat }: { talk: TalkState; onChat: (id: string | null) => void }) {
  const t = useT();
  const lang = useLang();
  const [rows, setRows] = useState<RecentSession[]>([]);
  const busy = talk.streaming !== null;
  useEffect(() => {
    let live = true;
    api.recentSessions(20).then(rs => { if (live) setRows(rs.filter(r => r.slug === null)); }, () => {});
    return () => { live = false; };
  }, [talk.session, talk.turns.length]);
  const now = Date.now() / 1000;
  return (
    <section className="shelf-chats" aria-label={t("shelf.chats")}>
      <div className="shelf-chats-h">
        <b>{t("shelf.chats")}</b>
        <IB icon="plus" label={t("shelf.newChat")} disabled={busy} onClick={() => onChat(null)} />
      </div>
      <ul className="shelf-sess">
        {rows.map(r => (
          <li key={r.session}>
            <button type="button" disabled={busy} aria-current={r.session === talk.session ? "true" : undefined}
              onClick={() => onChat(r.session)}>
              <Icon name="talk" /><span className="shelf-st">{r.preview}</span>
              <span className="shelf-vr">{whenLabel(r.last_at, now, lang)}</span>
            </button>
            <IB icon="box" label={t("session.archive")} className="ib shelf-x" disabled={busy}
              onClick={() => void talk.archive(r.session).then(ok => { if (ok) setRows(rs => rs.filter(x => x.session !== r.session)); })} />
          </li>
        ))}
      </ul>
    </section>
  );
}

/** 圖示鈕:可及名稱與 title 同字。 */
function IB({ icon, label, children, ...rest }: { icon: IconName; label: string; children?: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" className="ib" aria-label={label} title={label} {...rest}><Icon name={icon} />{children}</button>;
}

/** 書架。展開:作品(依更新新到舊)→ 目前這篇的局;窄條:工具在上、目前這篇(標題第一個字)在下。 */
export default function Rail({ mode, onToggle, works, current, talk, view, onOpen, onNew, onFind, onChat, settingsNav = null, hidden = false }: {
  mode: ShelfMode; onToggle: () => void;
  works: Work[]; current: string | null; talk: TalkState;
  view: "home" | "work" | "settings";
  onOpen: (slug: string) => void;
  /** 交新稿(回進門並聚焦輸入框)。 */
  onNew: () => void;
  /** 找作品(開 ⌘K 指令框)。 */
  onFind: () => void;
  /** 開一局純聊天(id = null 開新的)。 */
  onChat: (id: string | null) => void;
  /** 在設定頁:書架換成設定分區(不列作品)。 */
  settingsNav?: ReactNode;
  hidden?: boolean;
}) {
  const { mode: themeMode } = useThemeState();
  const t = useT();
  const lang = useLang();
  const nav = useNavigate();
  const { seen } = useSeen();
  const [q, setQ] = useState("");
  const open = mode === "open";
  const now = Date.now() / 1000;
  const cur = works.find(w => w.slug === current);
  const news = works.some(w => w.slug !== current && dotState(w, seen(w.slug)) === "fresh");
  const shown = works.length >= FILTER_FROM && q.trim() ? works.filter(w => w.title.includes(q.trim())) : works;
  return (
    <nav className="dash-rail" aria-label={t("rail.works")} data-shelf={mode} hidden={hidden}>
      <div className="shelf-top">
        <IB icon="panel" label={t(open ? "shelf.collapse" : "shelf.expand")} aria-expanded={open} onClick={onToggle} />
        {open && <Link to="/" className="shelf-brand"><Logo />{t("brand")}</Link>}
        {(!open || settingsNav) && <IB icon="plus" label={t("shelf.newChat")} onClick={onNew} />}
        {!open && (
          <IB icon="find" label={t("shelf.find")} onClick={onFind}>
            {news && <span className="rail-dot rail-news" data-state="fresh" role="img" aria-label={t("rail.fresh")} />}
          </IB>
        )}
        {!open && cur && <CurrentInitial work={cur} talk={talk} />}
      </div>
      {settingsNav}
      {open && !settingsNav && <Chats talk={talk} onChat={onChat} />}
      {open && !settingsNav && works.length >= FILTER_FROM && (
        <label className="shelf-find">
          <Icon name="find" />
          <input type="search" aria-label={t("shelf.filter")} value={q} onChange={e => setQ(e.target.value)} />
        </label>
      )}
      {open && !settingsNav && (
        <ul className="shelf-works">
          {shown.map(w => {
            const s = dotState(w, seen(w.slug));
            const on = w.slug === current;
            const pts = fpPoints(w.curve ?? [], 100, 14);
            return (
              <li key={w.slug} className="shelf-work" data-on={on ? "true" : undefined}>
                <button type="button" aria-current={on ? "true" : undefined} onClick={() => onOpen(w.slug)}>
                  <span className="shelf-title">
                    <span className="shelf-name">{w.title}</span>
                    {s !== "none" && <span className="rail-dot" data-state={s} role="img" aria-label={t(s === "busy" ? "rail.busy" : "rail.fresh")} />}
                  </span>
                  <span className="shelf-when">{whenLabel(w.updated_at, now, lang)}</span>
                  {pts && (
                    <svg className="shelf-fp" viewBox="0 0 100 14" preserveAspectRatio="none" aria-hidden="true">
                      <polyline points={pts} />
                    </svg>
                  )}
                </button>
                {on && <Sessions talk={talk} />}
              </li>
            );
          })}
        </ul>
      )}
      <div className="shelf-foot">
        <IB icon={themeMode === "dark" ? "sun" : "moon"} label={t("palette.dayNight")} onClick={toggleDayNight} />
        <IB icon="gear" label={t("rail.settings")} aria-current={view === "settings" ? "page" : undefined}
          onClick={() => nav("/settings")} />
      </div>
    </nav>
  );
}

/** 窄條上的目前這篇:標題第一個字;分析中右上角跳動點;點了浮層列這篇的局(不跳頁)。 */
function CurrentInitial({ work, talk }: { work: Work; talk: TalkState }) {
  const t = useT();
  const [pop, setPop] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const busy = work.state === "running" || work.state === "notes-running";
  useEffect(() => {
    if (!pop) return;
    const onDown = (e: MouseEvent) => {
      const el = e.target as Node;
      if (!box.current?.contains(el) && !btn.current?.contains(el)) setPop(false);
    };
    document.addEventListener("mousedown", onDown);
    box.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    return () => document.removeEventListener("mousedown", onDown);
  }, [pop]);
  const close = () => { setPop(false); btn.current?.focus(); };
  const r = btn.current?.getBoundingClientRect();
  return (
    <>
      <button type="button" ref={btn} className="ib shelf-cur" aria-label={work.title} title={work.title}
        aria-expanded={pop} onClick={() => setPop(p => !p)}>
        <span className="shelf-ini" aria-hidden="true">{[...work.title][0] ?? ""}</span>
        {busy && <span className="rail-dot rail-news" data-state="busy" role="img" aria-label={t("rail.busy")} />}
      </button>
      {pop && (
        <div ref={box} className="dash-float shelf-pop" role="dialog" aria-label={work.title}
          style={r ? { left: r.right + 8, top: r.top } : undefined}
          onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); close(); } }}>
          <Sessions talk={talk} onDone={close} />
        </div>
      )}
    </>
  );
}
