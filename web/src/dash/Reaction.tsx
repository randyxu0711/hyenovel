import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { api, DashError, type ReactionMark, type TurnReaction } from "./api";
import Icon from "./Icon";
import { errorMessage, useT } from "./i18n";

const MARKS = [
  { mark: "stopped", icon: "pause", label: "reaction.stopped", short: "reaction.stoppedShort" },
  { mark: "misread", icon: "offTarget", label: "reaction.misread", short: "reaction.misread" },
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
  const [open, setOpen] = useState(false);
  const confirmed = useRef(initial);
  const latest = useRef(0);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const box = useRef<HTMLDivElement>(null);
  const key = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => {
      if (box.current?.contains(e.target as Node)) return;
      if (box.current?.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
      setOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [open]);

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

  const close = () => { setOpen(false); key.current?.focus(); };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.nativeEvent.isComposing) { saveComment(); close(); }
  };

  const picked = MARKS.find(m => m.mark === saved?.mark);
  return (
    <div ref={box} className={picked ? "chat-react is-marked" : "chat-react"}
      onKeyDown={e => { if (e.key === "Escape" && open) { e.stopPropagation(); close(); } }}>
      <button ref={key} type="button" className="chat-react-key" aria-haspopup="true" aria-expanded={open}
        aria-label={picked ? t("reaction.flagged", { mark: t(picked.short) }) : t("reaction.flag")}
        title={picked ? undefined : t("reaction.flag")} onClick={() => setOpen(o => !o)}>
        <Icon name={picked ? picked.icon : "flag"} />{picked && <span>{t(picked.short)}</span>}
      </button>
      {open && (
        <div className="dash-float chat-react-menu" role="group" aria-label={t("reaction.flag")}>
          {MARKS.map(m => (
            <button key={m.mark} type="button" className="chat-react-mark" aria-pressed={saved?.mark === m.mark}
              autoFocus={m.mark === (saved?.mark ?? "stopped")} onClick={() => press(m.mark)}>
              <Icon name={m.icon} />{t(m.label)}
            </button>
          ))}
          {saved && (
            <input className="chat-react-note" aria-label={t("reaction.comment")} placeholder={t("reaction.commentHint")}
              maxLength={MAX_COMMENT} value={draft}
              onChange={e => setDraft(e.target.value)} onKeyDown={onKey} onBlur={saveComment} />
          )}
          <p className="chat-react-why">{t("reaction.note")}</p>
        </div>
      )}
      {code && <p className="chat-react-err" role="alert">{t(errorMessage(code))}</p>}
    </div>
  );
}
