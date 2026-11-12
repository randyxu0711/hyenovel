import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import { useNavigate } from "react-router-dom";
import type { Attachment, Turn } from "./api";
import type { Character } from "./api";
import Figure, { type FigureState } from "./Figure";
import Icon from "./Icon";
import { errorMessage, localized, useLang, useT } from "./i18n";
import { quoted } from "./Iq";
import Reaction from "./Reaction";
import Remember from "./Remember";
import Voice from "./Voice";
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
    if (turn.v == null) return;
    if (prev !== undefined && turn.v !== prev) out.add(i);
    prev = turn.v;
  });
  return out;
}

export function speakerChanges(turns: Turn[], byId: (id: string | null) => Character): Set<number> {
  const out = new Set<number>();
  let prev: string | null = null;
  turns.forEach((turn, i) => {
    if (turn.role !== "assistant") return;
    const id = byId(turn.character).id;
    if (id !== prev) out.add(i);
    prev = id;
  });
  return out;
}

export const REACT_MS = 1800;

export type SlashCommand = { name: string; label: string; run: () => unknown };

export function slashCommands(draft: string, all: SlashCommand[]): SlashCommand[] {
  const m = /^\/(\S*)$/.exec(draft.trim());
  if (!m) return [];
  return all.filter(c => c.name.startsWith(m[1].toLowerCase()));
}

export function composerState(o: { streaming: string | null; analyzing: boolean; reacting: boolean; typing: boolean }): FigureState {
  if (o.streaming !== null) return o.streaming ? "speaking" : "thinking";
  if (o.reacting) return "reacting";
  if (o.analyzing) return "scanning";
  return o.typing ? "reading" : "idle";
}

export function useReaction(analyzing: boolean): boolean {
  const [on, setOn] = useState(false);
  const was = useRef(analyzing);
  useEffect(() => {
    const finished = was.current && !analyzing;
    was.current = analyzing;
    if (!finished) return;
    setOn(true);
    const id = setTimeout(() => setOn(false), REACT_MS);
    return () => clearTimeout(id);
  }, [analyzing]);
  return on;
}

/** 對話分頁:逐字稿(標說話者、換人有點線分隔、引文可點)→ 輸入。
 *  稿上的痕跡被點時,捲到說那句的訊息並閃一下(onReveal 讓右欄切回對話)。 */
export default function Talk({ talk, version, quotes, analyzing, onDropQuote, onSent, onReveal, longText, onFile, above, inputRef, placeholder, whoSize = 72 }: {
  talk: TalkState; quotes: string[]; analyzing: boolean;
  /** 正在看的版本號(引文對不到時的說明用)。 */
  version: number;
  onDropQuote: (i: number) => void; onSent: () => void; onReveal: () => void;
  /** 進門用:超過門檻的文字(貼上或按 Enter)交給它,不當聊天送出。 */
  longText?: { min: number; take: (text: string) => void };
  /** 進門用:拖進來的檔交給它,不當附件。 */
  onFile?: (f: File) => void;
  above?: ReactNode;
  inputRef?: RefObject<HTMLTextAreaElement>;
  placeholder?: string;
  whoSize?: number;
}) {
  const t = useT();
  const lang = useLang();
  const { mode } = useThemeState();
  const chars = useCharacters();
  const { registerTalk } = useLinks();
  const log = useRef<HTMLDivElement>(null);
  const [flash, setFlash] = useState<{ i: number; n: number } | null>(null);
  const [editing, setEditing] = useState<{ seq: number; text: string } | null>(null);
  useEffect(() => setEditing(null), [talk.session]);
  const { markTurn, markMemories, markVoice, redoing, session, turns, streaming, pending, whoId, draft, setDraft, error, legacy,
    attachments, bound, staged, working } = talk;
  const navigate = useNavigate();
  const picker = useRef<HTMLInputElement>(null);
  const free = bound === null;
  const reacting = useReaction(analyzing);
  const me = chars.byId(whoId);
  const nameOf = (id: string | null) => localized(chars.byId(id).name, lang);

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

  const live = turns.some(x => x.role === "user" || x.role === "assistant");
  const idle = !session || streaming !== null || working;
  const commands = slashCommands(draft, [
    { name: "clear", label: t("talk.clear"), run: talk.clear },
    { name: "compact", label: t("talk.compactCost"), run: talk.compact },
  ]);
  const [pick, setPick] = useState(0);
  const chosen = commands[Math.min(pick, commands.length - 1)];
  const usable = !idle && live;
  const exact = chosen !== undefined && draft.trim().toLowerCase() === `/${chosen.name}`;
  const runCommand = (c: SlashCommand) => {
    if (!usable) return;
    setDraft("");
    setPick(0);
    void c.run();
  };

  const submit = async () => {
    const text = draft.trim();
    if (!text || streaming !== null || legacy) return;
    if (chosen) {
      if (exact) runCommand(chosen); else setDraft(`/${chosen.name}`);
      return;
    }
    if (longText && text.length > longText.min) { longText.take(text); setDraft(""); return; }
    if (await talk.send(text, quotes)) onSent();
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (commands.length > 0) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const step = e.key === "ArrowDown" ? 1 : -1;
        setPick(i => (Math.min(i, commands.length - 1) + step + commands.length) % commands.length);
        return;
      }
      if (e.key === "Tab") { e.preventDefault(); setDraft(`/${chosen.name}`); return; }
      if (e.key === "Escape") { e.preventDefault(); setDraft(""); return; }
    }
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(); }
  };

  const adopt = async (n: number) => {
    const r = await talk.adopt(n);
    if (r && session) navigate(`/w/${encodeURIComponent(r.slug)}?s=${encodeURIComponent(session)}`);
  };
  const onPaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = e.clipboardData.getData("text");
    if (longText && pasted.trim().length > longText.min) { e.preventDefault(); longText.take(pasted); }
  };
  const drop = (files: FileList | null) => { const f = files?.[0]; if (f) void talk.attach(f); };
  const onDrop = (e: DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    const f = e.dataTransfer.files[0];
    if (f && onFile) onFile(f); else drop(e.dataTransfer.files);
  };
  const bySeq = new Map<number, Attachment[]>();
  for (const a of attachments) bySeq.set(a.seq, [...(bySeq.get(a.seq) ?? []), a]);
  const card = (a: Attachment) => (
    <div key={`a${a.n}`} className="chat-att">
      <Icon name="sheet2" /><b>{a.name}</b><span>{t("talk.chars", { n: a.chars })}</span>
      {free && !a.adopted && (
        <button type="button" className="chat-att-adopt" disabled={working || streaming !== null}
          onClick={() => void adopt(a.n)}><Icon name="new" />{t("talk.adopt")}</button>
      )}
    </div>
  );
  const placed = new Set<number>();
  const before = (turn: Turn) => {
    if (turn.seq === undefined || placed.has(turn.seq)) return null;
    placed.add(turn.seq);
    return bySeq.get(turn.seq)?.map(card) ?? null;
  };

  const saveEdit = async (turn: Turn) => {
    if (!editing) return;
    if (editing.text.trim() === turn.text.trim()) { setEditing(null); return; }
    const r = await talk.editReply(editing.seq, editing.text);
    if (r !== null) setEditing(null);
  };
  const onEditKey = (e: KeyboardEvent<HTMLTextAreaElement>, turn: Turn) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setEditing(null); }
    else if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void saveEdit(turn); }
  };
  const still = legacy || streaming !== null || working;
  const lastTurn = turns[turns.length - 1];
  const acts = (turn: Turn) => {
    if (!session || turn.seq === undefined) return null;
    const seq = turn.seq;
    const n = turn.variant?.n ?? 1;
    const total = turn.variant?.total ?? 1;
    const last = lastTurn === turn;
    return (
      <div className="chat-acts">
        <Reaction key={`${session}-${seq}-${n}`} session={session} seq={seq} initial={turn.reaction ?? null}
          onChange={r => markTurn(session, seq, r)} />
        <Voice key={`v-${session}-${seq}-${n}`} session={session} seq={seq} initial={!!turn.voice}
          onChange={v => markVoice(session, seq, v)} />
        <button type="button" className="chat-act" aria-label={t("reply.edit")} title={t("reply.edit")} disabled={still}
          onClick={() => setEditing({ seq, text: turn.text })}><Icon name="edit" /></button>
        {last && (
          <button type="button" className="chat-act" aria-label={t("reply.redo")} title={t("reply.redo")} disabled={still}
            onClick={() => { setEditing(null); void talk.regenerate(seq); }}><Icon name="again" /></button>
        )}
        {last && total > 1 && (
          <span className="chat-flip" role="group" aria-label={t("reply.variant", { n, total })}>
            <button type="button" className="chat-act" aria-label={t("reply.prev")} title={t("reply.prev")} disabled={still || n <= 1}
              onClick={() => void talk.pickVariant(seq, n - 1)}><Icon name="prev" /></button>
            <span className="chat-flip-n">{n}/{total}</span>
            <button type="button" className="chat-act" aria-label={t("reply.next")} title={t("reply.next")} disabled={still || n >= total}
              onClick={() => void talk.pickVariant(seq, n + 1)}><Icon name="next" /></button>
          </span>
        )}
        {turn.edited && <span className="chat-edited" title={t("reply.editedNote")}>{t("reply.edited")}</span>}
      </div>
    );
  };

  const breaks = versionBreaks(turns);
  const who = speakerChanges(turns, chars.byId);
  const whoLine = (c: Character) => (
    <p className="chat-who"><Figure character={c} size={36} /><b style={{ color: c.colors[mode].text }}>{localized(c.name, lang)}</b></p>
  );
  let lastId: string | null = null;
  const rows = turns.map((turn: Turn, i) => {
    const brk = breaks.has(i) && <div key={`v${i}`} className="chat-ver"><Icon name="sheet2" /><span>{t("talk.versionBreak", { n: turn.v! })}</span></div>;
    if (turn.role === "clear") {
      return [<div key={i} className="chat-cut" role="separator" title={t("talk.cleared")} aria-label={t("talk.cleared")}><Icon name="wipe" /></div>];
    }
    if (turn.role === "compact") {
      return [
        <details key={i} className="chat-cut is-compact">
          <summary title={t("talk.compacted")} aria-label={t("talk.compacted")}><Icon name="squeeze" /></summary>
          <p>{turn.text}</p>
        </details>,
      ];
    }
    const att = before(turn);
    if (turn.role !== "assistant") {
      return [brk, att,
        <div key={i} className="chat-me">
          {turn.quotes.map((q, j) => <blockquote key={j} className="chat-quote">{q}</blockquote>)}
          {session && turn.seq !== undefined
            ? <Remember key={`${session}-${turn.seq}`} slug={bound} session={session} seq={turn.seq} text={turn.text}
                initial={turn.memories ?? []} onChange={m => markMemories(session, turn.seq!, m)} />
            : <p>{turn.text}</p>}
        </div>,
      ];
    }
    const c = chars.byId(turn.character);
    lastId = c.id;
    const lit = flash?.i === i;
    const redo = redoing !== null && turn.seq === redoing;
    const open = editing !== null && editing.seq === turn.seq;
    return [brk, att,
      <div key={lit ? `${i}-${flash!.n}` : i} className={lit ? "chat-turn is-flash" : "chat-turn"} data-turn={i}>
        {who.has(i) && whoLine(c)}
        {redo
          ? (streaming ? <p className="chat-text">{streaming}</p>
            : <p className="chat-wait" role="status">{t("talk.waiting", { name: nameOf(c.id) })}</p>)
          : open
            ? (
              <div className="chat-edit">
                <textarea autoFocus aria-label={t("reply.editBox")} value={editing.text}
                  onChange={e => setEditing({ seq: turn.seq!, text: e.target.value })} onKeyDown={e => onEditKey(e, turn)} />
                <div className="chat-edit-bar">
                  <button type="button" className="chat-edit-btn" onClick={() => setEditing(null)}>{t("reply.cancel")}</button>
                  <button type="button" className="chat-edit-btn is-save" disabled={still || !editing.text.trim()}
                    onClick={() => void saveEdit(turn)}>{t("reply.save")}</button>
                </div>
              </div>
            )
            : <p className="chat-text">{quoted(turn.text, turn.spans, version)}</p>}
        {!redo && !open && acts(turn)}
      </div>,
    ];
  });

  return (
    <div className="chat" onDragOver={free || onFile ? e => e.preventDefault() : undefined} onDrop={free || onFile ? onDrop : undefined}>
      {session && (
        <div className="chat-tools">
          <button type="button" className="ib" disabled={idle || !live} aria-label={t("talk.clear")} title={t("talk.clear")}
            onClick={() => void talk.clear()}><Icon name="wipe" /></button>
          <button type="button" className="ib" disabled={idle || !live} aria-label={t("talk.compact")} title={t("talk.compactCost")}
            onClick={() => void talk.compact()}><Icon name="squeeze" /></button>
        </div>
      )}
      <div className="chat-log" ref={log} role="log" aria-live="polite" aria-busy={streaming !== null}>
        {rows}
        {pending && (
          <div className="chat-me">
            {pending.quotes.map((q, j) => <blockquote key={j} className="chat-quote">{q}</blockquote>)}
            <p>{pending.text}</p>
          </div>
        )}
        {streaming !== null && redoing === null && (
          <div className="chat-turn">
            {lastId !== me.id && whoLine(me)}
            {streaming ? <p className="chat-text">{streaming}</p>
              : <p className="chat-wait" role="status">{t("talk.waiting", { name: nameOf(whoId) })}</p>}
          </div>
        )}
      </div>
      {error && <p className="chat-error" role="alert">{t(errorMessage(error.code))}</p>}
      {legacy && <p className="chat-error">{t("err.legacy-session")}</p>}
      {staged && (
        <div className="chat-carries">
          <div className="chat-carry">
            <div className="chat-att"><Icon name="sheet2" /><b>{staged.name}</b></div>
            <button type="button" className="ib" aria-label={t("talk.dropAttach")} title={t("talk.dropAttach")} onClick={talk.dropStaged}><Icon name="close" /></button>
          </div>
        </div>
      )}
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
      {above}
      <form className="composer" onSubmit={e => { e.preventDefault(); void submit(); }}>
        {commands.length > 0 && (
          <ul className="slash-menu" role="listbox" aria-label={t("talk.commands")}>
            {commands.map(c => (
              <li key={c.name} role="option" aria-selected={c === chosen} aria-disabled={!usable}>
                <button type="button" disabled={!usable} onMouseDown={e => e.preventDefault()} onClick={() => runCommand(c)}>
                  <b>/{c.name}</b><span>{c.label}</span>
                </button>
              </li>
            ))}
            {!usable && <li className="slash-note" role="status">{t(streaming !== null || working ? "err.busy" : "talk.cmdIdle")}</li>}
          </ul>
        )}
        <WhoPick me={me} onPick={talk.setWho} size={whoSize} state={composerState({ streaming, analyzing, reacting, typing: draft.trim() !== "" })} />
        <textarea ref={inputRef} value={draft} rows={2} maxLength={MAX_CHAT} disabled={legacy} aria-label={t("talk.input")}
          placeholder={placeholder ?? t("talk.placeholder", { name: nameOf(whoId) })}
          onChange={e => { setDraft(e.target.value); setPick(0); }} onKeyDown={onKey} onPaste={onPaste} />
        <div className="bar">
          {free && (
            <>
              <input ref={picker} type="file" accept=".md,.txt" hidden aria-label={t("talk.attach")}
                onChange={e => { drop(e.target.files); e.target.value = ""; }} />
              <button type="button" className="ib" aria-label={t("talk.attach")} title={t("talk.attach")}
                disabled={streaming !== null || working || !!staged} onClick={() => picker.current?.click()}><Icon name="clip" /></button>
            </>
          )}
          <button type="submit" className="ib send" aria-label={t("talk.send")} title={t("talk.send")}
            disabled={legacy || !draft.trim() || streaming !== null}><Icon name="send" /></button>
        </div>
      </form>
    </div>
  );
}
