import { useEffect, useRef, type KeyboardEvent } from "react";
import type { Turn } from "./api";
import Avatar from "./Avatar";
import { errorMessage, localized, useLang, useT } from "./i18n";
import PickCompanion from "./PickCompanion";
import { useThemeState } from "./theme";
import { useCharacters } from "./useCharacters";
import type { Talk as TalkState } from "./useTalk";

/** 對話欄:選人 → 逐字稿(標說話者、換人有分隔)→ 輸入。 */
export default function Talk({ talk, hasWork, quotes, onDropQuote, onSent, onCollapse }: {
  talk: TalkState; hasWork: boolean; quotes: string[];
  onDropQuote: (i: number) => void; onSent: () => void; onCollapse: () => void;
}) {
  const t = useT();
  const lang = useLang();
  const { mode } = useThemeState();
  const chars = useCharacters();
  const log = useRef<HTMLDivElement>(null);
  const { turns, streaming, pending, whoId, draft, setDraft, error } = talk;
  const me = chars.byId(whoId);
  const nameOf = (id: string | null, m?: string | null) => localized(chars.byId(id, m).name, lang);

  useEffect(() => {
    const el = log.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, streaming, pending]);

  if (!talk.chosen) return <PickCompanion onPick={talk.setWho} />;

  const submit = async () => {
    const text = draft.trim();
    if (!text || streaming !== null) return;
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
        <div key={i} className="talk-me">
          {turn.quotes.map((q, j) => <blockquote key={j} className="talk-quote">{q}</blockquote>)}
          <p>{turn.text}</p>
        </div>
      );
    }
    const c = chars.byId(turn.character, turn.mode);
    const divider = last !== null && last !== c.id;
    last = c.id;
    return (
      <div key={i}>
        {divider && <div className="talk-switch" role="separator">{t("talk.switched", { name: localized(c.name, lang) })}</div>}
        <div className="talk-turn">
          <p className="talk-who"><Avatar character={c} size={22} /><b style={{ color: c.colors[mode].text }}>{localized(c.name, lang)}</b></p>
          <p className="talk-text">{turn.text}</p>
        </div>
      </div>
    );
  });

  return (
    <div className="talk">
      <header className="talk-head">
        <div className="talk-roster" role="group" aria-label={t("talk.who")}>
          {chars.list.map(c => (
            <button key={c.id} type="button" className="talk-pick" aria-pressed={c.id === whoId}
              aria-label={localized(c.name, lang)} title={localized(c.name, lang)}
              onClick={() => talk.setWho(c.id)}>
              <Avatar character={c} size={26} />
            </button>
          ))}
        </div>
        <button type="button" className="talk-collapse" aria-label={t("talk.collapse")} onClick={onCollapse}>›</button>
      </header>
      <div className="talk-log" ref={log} role="log" aria-live="polite" aria-busy={streaming !== null}>
        {!hasWork || (!turns.length && !pending) ? <p className="talk-empty">{hasWork ? t("talk.start", { name: nameOf(whoId) }) : t("talk.empty")}</p> : null}
        {rows}
        {pending && (
          <div className="talk-me">
            {pending.quotes.map((q, j) => <blockquote key={j} className="talk-quote">{q}</blockquote>)}
            <p>{pending.text}</p>
          </div>
        )}
        {streaming !== null && (
          <div className="talk-turn">
            <p className="talk-who"><Avatar character={me} size={22} /><b style={{ color: me.colors[mode].text }}>{nameOf(whoId)}</b></p>
            {streaming ? <p className="talk-text">{streaming}</p> : <p className="talk-wait" role="status">{t("talk.waiting", { name: nameOf(whoId) })}</p>}
          </div>
        )}
      </div>
      {error && <p className="talk-error" role="alert">{t(errorMessage(error.code))}</p>}
      <form className="talk-form" onSubmit={e => { e.preventDefault(); void submit(); }}>
        {quotes.map((q, i) => (
          <div key={i} className="talk-carry">
            <blockquote className="talk-quote">{q}</blockquote>
            <button type="button" aria-label={t("talk.dropQuote")} onClick={() => onDropQuote(i)}>×</button>
          </div>
        ))}
        <textarea value={draft} rows={2} disabled={!hasWork} aria-label={t("talk.input")}
          placeholder={t("talk.placeholder", { name: nameOf(whoId) })}
          onChange={e => setDraft(e.target.value)} onKeyDown={onKey} />
        <button type="submit" className="talk-send" disabled={!hasWork || !draft.trim() || streaming !== null}>{t("talk.send")}</button>
      </form>
    </div>
  );
}
