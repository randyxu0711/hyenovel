import { useCallback, useEffect, useRef, useState } from "react";
import type { SessionRow, Turn, WorkMap } from "./api";
import Avatar from "./Avatar";
import ChartTab from "./ChartTab";
import { localized, useLang, useT, type MsgKey } from "./i18n";
import NotesTab from "./NotesTab";
import type { Mark } from "./Paper";
import Talk from "./Talk";
import type { Characters } from "./useCharacters";
import { useCharacters } from "./useCharacters";
import type { Talk as TalkState } from "./useTalk";

type Tab = "talk" | "notes" | "chart";
const TABS: [Tab, MsgKey][] = [["talk", "side.talk"], ["notes", "side.notes"], ["chart", "side.chart"]];

/** 每則 assistant 的引文(這一版找得到的)→ 該角色在稿上的痕跡;作者帶的引文不畫。同一位置取最後一筆。 */
export function marksFrom(turns: Turn[], chars: Characters): Mark[] {
  const at = new Map<string, Mark>();
  turns.forEach((turn, i) => {
    if (turn.role !== "assistant") return;
    const character = chars.byId(turn.character, turn.mode).id;
    turn.spans.forEach((s, j) => {
      if (s.start === null || s.end === null) return;
      const key = `${s.start}:${s.end}`;
      at.delete(key);   // 重新插入:順序跟著最後一筆
      at.set(key, { start: s.start, end: s.end, character, id: `${i}-${j}` });
    });
  });
  return [...at.values()];
}

/** 局選單上的時間:今天只寫時分,其他加月/日。 */
export function fmtTime(ts: number, now = new Date()): string {
  const d = new Date(ts * 1000);
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return d.toDateString() === now.toDateString() ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`;
}

/** 右欄:對話 | 筆記 | 結構圖。對話一直掛著(切走也不丟草稿、稿上痕跡點得回來),另兩頁切到才畫。 */
export default function Side({ version, map, mapError, state, marks, talk, quotes, onDropQuote, onSent }: {
  /** 正在看的版本號。 */
  version: number;
  map: WorkMap | null;
  /** 對位資料抓不到時的 den 錯誤碼。 */
  mapError: string | null;
  /** 作品(最新版)的 state:筆記分頁說明為什麼沒有筆記。 */
  state: string;
  marks: Mark[];
  talk: TalkState; quotes: string[];
  onDropQuote: (i: number) => void; onSent: () => void;
}) {
  const t = useT();
  const [tab, setTab] = useState<Tab>("talk");
  const reveal = useCallback(() => setTab("talk"), []);
  return (
    <div className="side">
      <header className="side-head">
        <div className="side-tabs" role="tablist" aria-label={t("side.tabs")}>
          {TABS.map(([k, label]) => (
            <button key={k} type="button" role="tab" id={`side-tab-${k}`} aria-controls={`side-panel-${k}`}
              aria-selected={tab === k} onClick={() => setTab(k)}>{t(label)}</button>
          ))}
        </div>
        {tab === "talk" && <SessionMenu talk={talk} />}
      </header>
      <div className="side-panel" role="tabpanel" id="side-panel-talk" aria-labelledby="side-tab-talk" hidden={tab !== "talk"}>
        <Talk talk={talk} version={version} quotes={quotes} onDropQuote={onDropQuote} onSent={onSent} onReveal={reveal} />
      </div>
      {tab !== "talk" && (
        <div className="side-panel side-scroll" role="tabpanel" id={`side-panel-${tab}`} aria-labelledby={`side-tab-${tab}`}>
          {tab === "notes" ? <NotesTab map={map} state={state} error={mapError} /> : <ChartTab map={map} marks={marks} error={mapError} />}
        </div>
      )}
    </div>
  );
}

/** 局選單:目前這局的參與者徽章 + 時間;點開列出這篇的局(時間、誰、第一句話),最上面「新的一局」。 */
function SessionMenu({ talk }: { talk: TalkState }) {
  const t = useT();
  const lang = useLang();
  const chars = useCharacters();
  const [open, setOpen] = useState(false);
  const toggle = useRef<HTMLButtonElement>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const el = e.target as Node;
      if (!box.current?.contains(el) && !toggle.current?.contains(el)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const who = [...new Set(talk.turns.filter(x => x.role === "assistant").map(x => chars.byId(x.character, x.mode).id))];
  const lastTs = talk.turns.length ? talk.turns[talk.turns.length - 1].ts : null;
  const close = () => { setOpen(false); toggle.current?.focus(); };
  const pick = (row: SessionRow) => { talk.open(row.session); close(); };
  return (
    <div className="side-rounds">
      <button type="button" ref={toggle} className="side-round" aria-haspopup="true" aria-expanded={open}
        title={t("session.menu")} disabled={talk.streaming !== null} onClick={() => setOpen(o => !o)}>
        <span className="side-faces">{who.map(id => <Avatar key={id} character={chars.byId(id)} size={20} />)}</span>
        {talk.session && lastTs !== null ? <span className="dash-dm">{fmtTime(lastTs)}</span> : t("session.new")}
        <span className="side-sr">{t("session.menu")}</span>
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div ref={box} className="dash-float side-rounds-menu" role="group" aria-label={t("session.list")}
          onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); close(); } }}>
          <button type="button" className="side-round-item" autoFocus onClick={() => { talk.fresh(); close(); }}>{t("session.new")}</button>
          {talk.sessions.map(r => {
            const c = chars.byId(r.character, r.mode);
            return (
              <button key={r.session} type="button" className="side-round-item"
                aria-current={r.session === talk.session ? "true" : undefined} onClick={() => pick(r)}>
                <span className="dash-dm">{fmtTime(r.last_at)}</span>
                <Avatar character={c} size={20} /><b>{localized(c.name, lang)}</b>
                <span className="side-preview">{r.preview}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
