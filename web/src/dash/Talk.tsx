import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Turn } from "./api";
import type { Character } from "./api";
import Blob, { type BlobState } from "./Blob";
import Icon from "./Icon";
import { errorMessage, localized, useLang, useT } from "./i18n";
import { quoted } from "./Iq";
import Reaction from "./Reaction";
import Remember from "./Remember";
import { useLinks } from "./links";
import { bare } from "./Paper";
import { useThemeState } from "./theme";
import { useCharacters } from "./useCharacters";
import { MAX_CHAT, type Talk as TalkState } from "./useTalk";
import WhoPick from "./WhoPick";

const FLASH_MS = 1400;

/** 要在其前畫「第 n 版」分隔的 index:v 與前一個有值的 v 不同;沒 v 的(剛串流進來)沿用前一則。 */
export function versionBreaks(turns: Turn[]): Set<number> {
  const out = new Set<number>();
  let prev: number | undefined;
  turns.forEach((turn, i) => {
    if (turn.v === undefined) return;
    if (prev !== undefined && turn.v !== prev) out.add(i);
    prev = turn.v;
  });
  return out;
}

export function speakerChanges(turns: Turn[], byId: (id: string | null, m?: string | null) => Character): Set<number> {
  const out = new Set<number>();
  let prev: string | null = null;
  turns.forEach((turn, i) => {
    if (turn.role !== "assistant") return;
    const id = byId(turn.character, turn.mode).id;
    if (id !== prev) out.add(i);
    prev = id;
  });
  return out;
}

export function composerState(o: { streaming: boolean; analyzing: boolean }): BlobState {
  return o.streaming ? "speaking" : o.analyzing ? "scanning" : "reading";
}

/** 對話分頁:逐字稿(標說話者、換人有點線分隔、引文可點)→ 輸入。
 *  稿上的痕跡被點時,捲到說那句的訊息並閃一下(onReveal 讓右欄切回對話)。 */
export default function Talk({ talk, version, quotes, analyzing, onDropQuote, onSent, onReveal }: {
  talk: TalkState; quotes: string[]; analyzing: boolean;
  /** 正在看的版本號(引文對不到時的說明用)。 */
  version: number;
  onDropQuote: (i: number) => void; onSent: () => void; onReveal: () => void;
}) {
  const t = useT();
  const lang = useLang();
  const { mode } = useThemeState();
  const chars = useCharacters();
  const { registerTalk } = useLinks();
  const log = useRef<HTMLDivElement>(null);
  const [flash, setFlash] = useState<{ i: number; n: number } | null>(null);
  const { markTurn, markMemories, slug, session, turns, streaming, pending, whoId, draft, setDraft, error, legacy } = talk;
  const me = chars.byId(whoId);
  const nameOf = (id: string | null, m?: string | null) => localized(chars.byId(id, m).name, lang);

  useEffect(() => {
    const el = log.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, streaming, pending]);

  // 稿 → 對話:找最後一則引過那句的 assistant 訊息(寬鬆比對,稿給的是原文切片)。
  const turnsRef = useRef(turns);
  turnsRef.current = turns;
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const off = registerTalk(quote => {
      const key = bare(quote);
      const ts = turnsRef.current;
      let i = ts.length - 1;
      while (i >= 0 && !(ts[i].role === "assistant" && ts[i].spans.some(s => bare(s.quote) === key))) i--;
      if (i < 0) return false;
      onReveal();
      setFlash(f => ({ i, n: (f?.n ?? 0) + 1 }));
      clearTimeout(timer);
      timer = setTimeout(() => setFlash(null), FLASH_MS);
      return true;
    });
    return () => { off(); clearTimeout(timer); };
  }, [registerTalk, onReveal]);
  useEffect(() => {
    if (!flash) return;
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    log.current?.querySelector(`[data-turn="${flash.i}"]`)?.scrollIntoView?.({ block: "center", behavior: still ? "auto" : "smooth" });
  }, [flash]);

  const submit = async () => {
    const text = draft.trim();
    if (!text || streaming !== null || legacy) return;
    if (await talk.send(text, quotes)) onSent();
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); }
  };

  const breaks = versionBreaks(turns);
  const who = speakerChanges(turns, chars.byId);
  const whoLine = (c: Character) => (
    <p className="chat-who"><Blob character={c} size={22} /><b style={{ color: c.colors[mode].text }}>{localized(c.name, lang)}</b></p>
  );
  let lastId: string | null = null;
  const rows = turns.map((turn: Turn, i) => {
    const brk = breaks.has(i) && <div key={`v${i}`} className="chat-ver"><Icon name="sheet2" /><span>{t("talk.versionBreak", { n: turn.v! })}</span></div>;
    if (turn.role !== "assistant") {
      return [brk,
        <div key={i} className="chat-me">
          {turn.quotes.map((q, j) => <blockquote key={j} className="chat-quote">{q}</blockquote>)}
          {slug && session && turn.seq !== undefined
            ? <Remember key={`${session}-${turn.seq}`} slug={slug} session={session} seq={turn.seq} text={turn.text}
                initial={turn.memories ?? []} onChange={m => markMemories(session, turn.seq!, m)} />
            : <p>{turn.text}</p>}
        </div>,
      ];
    }
    const c = chars.byId(turn.character, turn.mode);
    lastId = c.id;
    const lit = flash?.i === i;
    return [brk,
      <div key={lit ? `${i}-${flash!.n}` : i} className={lit ? "chat-turn is-flash" : "chat-turn"} data-turn={i}>
        {who.has(i) && whoLine(c)}
        <p className="chat-text">{quoted(turn.text, turn.spans, version)}</p>
        {slug && session && turn.seq !== undefined && (
          <Reaction key={`${session}-${turn.seq}`} slug={slug} session={session} seq={turn.seq} initial={turn.reaction ?? null}
            onChange={r => markTurn(session, turn.seq!, r)} />
        )}
      </div>,
    ];
  });

  return (
    <div className="chat">
      <div className="chat-log" ref={log} role="log" aria-live="polite" aria-busy={streaming !== null}>
        {!turns.length && !pending && <p className="chat-empty">{t("talk.start", { name: nameOf(whoId) })}</p>}
        {rows}
        {pending && (
          <div className="chat-me">
            {pending.quotes.map((q, j) => <blockquote key={j} className="chat-quote">{q}</blockquote>)}
            <p>{pending.text}</p>
          </div>
        )}
        {streaming !== null && (
          <div className="chat-turn">
            {lastId !== me.id && whoLine(me)}
            {streaming ? <p className="chat-text">{streaming}</p>
              : <p className="chat-wait" role="status">{t("talk.waiting", { name: nameOf(whoId) })}</p>}
          </div>
        )}
      </div>
      {error && <p className="chat-error" role="alert">{t(errorMessage(error.code))}</p>}
      {legacy && <p className="chat-error">{t("err.legacy-session")}</p>}
      {quotes.length > 0 && (
        <div className="chat-carries">
          {quotes.map((q, i) => (
            <div key={i} className="chat-carry">
              <blockquote className="chat-quote">{q}</blockquote>
              <button type="button" className="ib" aria-label={t("talk.dropQuote")} title={t("talk.dropQuote")} onClick={() => onDropQuote(i)}><Icon name="close" /></button>
            </div>
          ))}
        </div>
      )}
      <form className="composer" onSubmit={e => { e.preventDefault(); void submit(); }}>
        <div className="who"><Blob character={me} size={54} state={composerState({ streaming: streaming !== null, analyzing })} /></div>
        <textarea value={draft} rows={2} maxLength={MAX_CHAT} disabled={legacy} aria-label={t("talk.input")}
          placeholder={t("talk.placeholder", { name: nameOf(whoId) })}
          onChange={e => setDraft(e.target.value)} onKeyDown={onKey} />
        <div className="bar">
          <WhoPick me={me} onPick={talk.setWho} />
          <button type="submit" className="ib send" aria-label={t("talk.send")} title={t("talk.send")}
            disabled={legacy || !draft.trim() || streaming !== null}><Icon name="send" /></button>
        </div>
      </form>
    </div>
  );
}
