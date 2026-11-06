import { useRef, useState, type KeyboardEvent } from "react";
import { api, DashError, type ReactionMark, type TurnReaction } from "./api";
import Icon from "./Icon";
import { errorMessage, useT } from "./i18n";

const MARKS = [
  { mark: "stopped", icon: "pause", label: "reaction.stopped" },
  { mark: "misread", icon: "offTarget", label: "reaction.misread" },
] as const;
const MAX_COMMENT = 500;

export default function Reaction({ slug, session, seq, initial }: {
  slug: string; session: string; seq: number; initial: TurnReaction | null;
}) {
  const t = useT();
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState(initial?.comment ?? "");
  const [code, setCode] = useState<string | null>(null);
  const latest = useRef(0);

  const commit = (next: TurnReaction | null, nextDraft: string) => {
    const before = saved, beforeDraft = draft;
    const mine = ++latest.current;
    setSaved(next); setDraft(nextDraft); setCode(null);
    const done: Promise<unknown> = next
      ? api.setReaction(slug, session, seq, next.mark, next.comment ?? undefined)
      : api.clearReaction(slug, session, seq);
    done.catch((e: unknown) => {
      if (mine !== latest.current) return;
      setSaved(before); setDraft(beforeDraft);
      setCode(e instanceof DashError ? e.code : "unknown");
    });
  };

  const press = (mark: ReactionMark) =>
    saved?.mark === mark ? commit(null, "") : commit({ mark, comment: null }, "");

  const saveComment = () => {
    if (!saved) return;
    const comment = draft.trim() || null;
    if (comment !== saved.comment) commit({ mark: saved.mark, comment }, draft);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.nativeEvent.isComposing) saveComment();
  };

  return (
    <div className="chat-react">
      {MARKS.map(m => (
        <button key={m.mark} type="button" className="chat-react-mark" aria-pressed={saved?.mark === m.mark}
          aria-label={t(m.label)} title={t(m.label)} onClick={() => press(m.mark)}>
          <Icon name={m.icon} />
        </button>
      ))}
      {saved && (
        <input className="chat-react-note" aria-label={t("reaction.comment")} maxLength={MAX_COMMENT} value={draft}
          onChange={e => setDraft(e.target.value)} onKeyDown={onKey} onBlur={saveComment} />
      )}
      {code && <p className="chat-react-err" role="alert">{t(errorMessage(code))}</p>}
    </div>
  );
}
