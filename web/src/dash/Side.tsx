import { useCallback, useLayoutEffect, useState } from "react";
import type { Compare, Turn, WorkMap } from "./api";
import ChartTab from "./ChartTab";
import { useT, type MsgKey } from "./i18n";
import Icon, { type IconName } from "./Icon";
import NotesTab from "./NotesTab";
import { markId, type Mark } from "./Paper";
import Talk from "./Talk";
import TraceTab from "./TraceTab";
import type { Characters } from "./useCharacters";
import type { Talk as TalkState } from "./useTalk";

type Tab = "talk" | "notes" | "chart";
const TABS: [Tab, MsgKey, IconName][] = [["talk", "side.talk", "talk"], ["notes", "side.notes", "note"], ["chart", "side.chart", "curve"]];

/** 每則 assistant 的引文(這一版找得到的)→ 該角色在稿上的痕跡;作者帶的引文不畫。同一位置取最後一筆。 */
export function marksFrom(turns: Turn[], chars: Characters): Mark[] {
  const at = new Map<string, Mark>();
  turns.forEach(turn => {
    if (turn.role !== "assistant") return;
    const character = chars.byId(turn.character).id;
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
export default function Side({ version, map, mapError, state, marks, talk, quotes, analyzing = false, onDropQuote, onSent, ob = null, onOb, cmp = null, onCompare, onBring }: {
  /** 正在看的版本號。 */
  version: number;
  map: WorkMap | null;
  /** 對位資料抓不到時的 den 錯誤碼。 */
  mapError: string | null;
  /** 作品(最新版)的 state:筆記分頁說明為什麼沒有筆記。 */
  state: string;
  marks: Mark[];
  talk: TalkState; quotes: string[]; analyzing?: boolean;
  onDropQuote: (i: number) => void; onSent: () => void;
  /** 結構圖選中的觀察。 */
  ob?: string | null; onOb?: (id: string | null) => void;
  /** 對照資料:有上一版筆記時筆記分頁換成「去向」。 */
  cmp?: Compare | null;
  /** 筆記眉頭的對照鍵。 */
  onCompare?: (n: number) => void;
  /** 去向卡上的舊版引文帶進對話。 */
  onBring?: (quote: string) => void;
}) {
  const t = useT();
  const [tab, setTab] = useState<Tab>("talk");
  const reveal = useCallback(() => setTab("talk"), []);
  const tracing = cmp?.mode === "notes";
  const comparing = !!cmp;
  useLayoutEffect(() => {
    if (tracing) setTab("notes");
    else if (comparing) setTab(x => (x === "chart" ? "notes" : x));
  }, [tracing, comparing]);
  return (
    <div className="side">
      <header className="side-head">
        <div className="side-tabs" role="tablist" aria-label={t("side.tabs")}>
          {TABS.map(([k, base, baseIcon]) => {
            const [label, icon]: [MsgKey, IconName] = k === "notes" && tracing ? ["side.trace", "compare"] : [base, baseIcon];
            const off = k === "chart" && !!cmp;
            return (
              <button key={k} type="button" role="tab" id={`side-tab-${k}`} aria-controls={`side-panel-${k}`}
                aria-selected={tab === k} aria-label={t(label)} title={off ? t("trace.chartOff") : tab === k ? undefined : t(label)}
                disabled={off}
                data-empty={off || (k === "notes" ? !tracing && !!map && !map.notes : k === "chart" ? !!map && map.analysis_version === null : undefined)}
                onClick={() => setTab(k)}><Icon name={icon} />{tab === k && <span>{t(label)}</span>}</button>
            );
          })}
        </div>
      </header>
      <div className="side-panel" role="tabpanel" id="side-panel-talk" aria-labelledby="side-tab-talk" hidden={tab !== "talk"}>
        <Talk talk={talk} version={version} quotes={quotes} analyzing={analyzing} onDropQuote={onDropQuote} onSent={onSent} onReveal={reveal} />
      </div>
      {tab !== "talk" && (
        <div className="side-panel side-scroll" role="tabpanel" id={`side-panel-${tab}`} aria-labelledby={`side-tab-${tab}`}>
          {tab === "notes" ? (tracing ? <TraceTab cmp={cmp!} onBring={onBring && (q => { onBring(q); setTab("talk"); })} /> : <NotesTab map={map} state={state} error={mapError} onCompare={onCompare} />) : <ChartTab map={map} marks={marks} error={mapError} ob={ob} onOb={onOb} />}
        </div>
      )}
    </div>
  );
}
