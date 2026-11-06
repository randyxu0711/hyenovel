import { useRef, useState, type KeyboardEvent } from "react";
import { api, DashError, type ReactionMark, type TurnReaction } from "./api";
import Icon from "./Icon";
import { errorMessage, useT } from "./i18n";

const MARKS = [
  { mark: "stopped", icon: "pause", label: "reaction.stopped" },
  { mark: "misread", icon: "offTarget", label: "reaction.misread" },
] as const;
const MAX_COMMENT = 500;

export default function Reaction({ slug, session, seq, initial, onChange }: {
  slug: string; session: string; seq: number; initial: TurnReaction | null;
  onChange: (reaction: TurnReaction | null) => void;
}) {
  const t = useT();
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState(initial?.comment ?? "");
  const [code, setCode] = useState<string | null>(null);
  const confirmed = useRef(initial);
  const latest = useRef(0);
  const queue = useRef<Promise<void>>(Promise.resolve());

  const show = (next: TurnReaction | null, nextDraft: string) => {
    setSaved(next); setDraft(nextDraft); onChange(next);
  };

  const commit = (next: TurnReaction | null, nextDraft: string) => {
    const mine = ++latest.current;
    show(next, nextDraft); setCode(null);
    queue.current = queue.current.then(async () => {
      try {
        await (next
          ? api.setReaction(slug, session, seq, next.mark, next.comment ?? undefined)
          : api.clearReaction(slug, session, seq));
        confirmed.current = next;
      } catch (e) {
        if (mine !== latest.current) return;
        show(confirmed.current, confirmed.current?.comment ?? "");
        setCode(e instanceof DashError ? e.code : "unknown");
      }
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
