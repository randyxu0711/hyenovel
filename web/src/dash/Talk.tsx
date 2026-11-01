import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Turn } from "./api";
import Avatar from "./Avatar";
import { errorMessage, localized, useLang, useT } from "./i18n";
import { quoted } from "./Iq";
import { useLinks } from "./links";
import { bare } from "./Paper";
import { useThemeState } from "./theme";
import { useCharacters } from "./useCharacters";
import { MAX_CHAT, type Talk as TalkState } from "./useTalk";
import WhoPick from "./WhoPick";

const FLASH_MS = 1400;

/** 對話分頁:逐字稿(標說話者、換人有點線分隔、引文可點)→ 輸入。
 *  稿上的痕跡被點時,捲到說那句的訊息並閃一下(onReveal 讓右欄切回對話)。 */
export default function Talk({ talk, version, quotes, onDropQuote, onSent, onReveal }: {
  talk: TalkState; quotes: string[];
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
  const { turns, streaming, pending, whoId, draft, setDraft, error, legacy } = talk;
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

  // 逐則標說話者;與上一位 assistant 不同人時,前面插一條「換 X 來讀」。
  let last: string | null = null;
  const rows = turns.map((turn: Turn, i) => {
    if (turn.role !== "assistant") {
      return (
        <div key={i} className="chat-me">
          {turn.quotes.map((q, j) => <blockquote key={j} className="chat-quote">{q}</blockquote>)}
          <p>{turn.text}</p>
        </div>
      );
    }
    const c = chars.byId(turn.character, turn.mode);
    const divider = last !== null && last !== c.id;
    last = c.id;
    const lit = flash?.i === i;
    return (
      <div key={lit ? `${i}-${flash!.n}` : i}>
        {divider && <div className="chat-switch" role="separator">{t("talk.switched", { name: localized(c.name, lang) })}</div>}
        <div className={lit ? "chat-turn is-flash" : "chat-turn"} data-turn={i}>
          <p className="chat-who"><Avatar character={c} size={22} /><b style={{ color: c.colors[mode].text }}>{localized(c.name, lang)}</b></p>
          <p className="chat-text">{quoted(turn.text, turn.spans, version)}</p>
        </div>
      </div>
    );
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
            <p className="chat-who"><Avatar character={me} size={22} /><b style={{ color: me.colors[mode].text }}>{nameOf(whoId)}</b></p>
            {streaming ? <p className="chat-text">{streaming}</p>
              : <p className="chat-wait" role="status"><span>{t("talk.waiting", { name: nameOf(whoId) })}</span><i className="chat-pen" aria-hidden="true" /></p>}
          </div>
        )}
      </div>
      {error && <p className="chat-error" role="alert">{t(errorMessage(error.code))}</p>}
      {legacy && <p className="chat-error">{t("err.legacy-session")}</p>}
      <form className="dash-float chat-form" onSubmit={e => { e.preventDefault(); void submit(); }}>
        {quotes.map((q, i) => (
          <div key={i} className="chat-carry">
            <blockquote className="chat-quote">{q}</blockquote>
            <button type="button" aria-label={t("talk.dropQuote")} onClick={() => onDropQuote(i)}>×</button>
          </div>
        ))}
        <textarea value={draft} rows={2} maxLength={MAX_CHAT} disabled={legacy} aria-label={t("talk.input")}
          placeholder={t("talk.placeholder", { name: nameOf(whoId) })}
          onChange={e => setDraft(e.target.value)} onKeyDown={onKey} />
        <div className="chat-row">
          <WhoPick me={me} onPick={talk.setWho} />
          <button type="submit" className="dash-key chat-send" disabled={legacy || !draft.trim() || streaming !== null}>{t("talk.send")}</button>
        </div>
      </form>
    </div>
  );
}
