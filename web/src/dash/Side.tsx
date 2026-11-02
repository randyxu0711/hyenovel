import { useCallback, useState } from "react";
import type { Turn, WorkMap } from "./api";
import ChartTab from "./ChartTab";
import { useT, type MsgKey } from "./i18n";
import NotesTab from "./NotesTab";
import { markId, type Mark } from "./Paper";
import Talk from "./Talk";
import type { Characters } from "./useCharacters";
import type { Talk as TalkState } from "./useTalk";

type Tab = "talk" | "notes" | "chart";
const TABS: [Tab, MsgKey][] = [["talk", "side.talk"], ["notes", "side.notes"], ["chart", "side.chart"]];

/** 每則 assistant 的引文(這一版找得到的)→ 該角色在稿上的痕跡;作者帶的引文不畫。同一位置取最後一筆。 */
export function marksFrom(turns: Turn[], chars: Characters): Mark[] {
  const at = new Map<string, Mark>();
  turns.forEach(turn => {
    if (turn.role !== "assistant") return;
    const character = chars.byId(turn.character, turn.mode).id;
    turn.spans.forEach(s => {
      if (s.start === null || s.end === null) return;
      const key = `${s.start}:${s.end}`;
      at.delete(key);   // 重新插入:順序跟著最後一筆
      at.set(key, { start: s.start, end: s.end, character, id: markId(s.start, s.end, character) });
    });
  });
  return [...at.values()];
}

/** 右欄:對話 | 筆記 | 結構圖。對話一直掛著(切走也不丟草稿、稿上痕跡點得回來),另兩頁切到才畫。 */
export default function Side({ version, map, mapError, state, marks, talk, quotes, onDropQuote, onSent, ob = null, onOb }: {
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
  /** 結構圖選中的觀察。 */
  ob?: string | null; onOb?: (id: string | null) => void;
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
      </header>
      <div className="side-panel" role="tabpanel" id="side-panel-talk" aria-labelledby="side-tab-talk" hidden={tab !== "talk"}>
        <Talk talk={talk} version={version} quotes={quotes} onDropQuote={onDropQuote} onSent={onSent} onReveal={reveal} />
      </div>
      {tab !== "talk" && (
        <div className="side-panel side-scroll" role="tabpanel" id={`side-panel-${tab}`} aria-labelledby={`side-tab-${tab}`}>
          {tab === "notes" ? <NotesTab map={map} state={state} error={mapError} /> : <ChartTab map={map} marks={marks} error={mapError} ob={ob} onOb={onOb} />}
        </div>
      )}
    </div>
  );
}
