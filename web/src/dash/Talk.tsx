import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type KeyboardEvent, type RefObject } from "react";
import Markdown from "react-markdown";
import { useNavigate } from "react-router-dom";
import type { Attachment, Turn } from "./api";
import type { Character } from "./api";
import Figure, { type FigureState } from "./Figure";
import Icon, { type IconName } from "./Icon";
import { errorMessage, localized, useLang, useT } from "./i18n";
import { quoted } from "./Iq";
import Prior from "./Prior";
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
const ARM_MS = 4000;

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

/** 壓縮摘要:一小張紙,預設露幾行、點了全開。 */
function Summary({ text, past, label }: { text: string; past: boolean; label: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="chat-sum" data-past={past || undefined} data-open={open || undefined} role="button" tabIndex={0}
      aria-expanded={open} aria-label={label}
      onClick={() => setOpen(o => !o)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(o => !o); } }}>
      <Markdown>{text}</Markdown>
    </div>
  );
}

/** 最後一個清空/壓縮標記的 index;它之前的逐字讀伴看不到(沒有標記 = -1)。 */
export function lastCut(turns: Turn[]): number {
  for (let i = turns.length - 1; i >= 0; i--) if (turns[i].role === "clear" || turns[i].role === "compact") return i;
  return -1;
}

export const REACT_MS = 1800;

export type SlashCommand = { name: string; label: string; icon: IconName; note?: string; run: () => unknown };

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
export default function Talk({ talk, version, quotes, analyzing, onDropQuote, onSent, onReveal, longText, inputRef, placeholder, whoSize = 72, onMemory }: {
  talk: TalkState; quotes: string[]; analyzing: boolean;
  /** 正在看的版本號(引文對不到時的說明用)。 */
  version: number;
  onDropQuote: (i: number) => void; onSent: () => void; onReveal: () => void; onMemory?: () => void;
  /** 進門用:超過門檻的文字(貼上或按 Enter)交給它,不當聊天送出。 */
  longText?: { min: number; take: (text: string) => void };
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
  const [asking, setAsking] = useState(false);
  const [peek, setPeek] = useState<Set<number>>(new Set());
  const [arming, setArming] = useState(false);
  useEffect(() => {
    if (!arming) return;
    const id = setTimeout(() => setArming(false), ARM_MS);
    return () => clearTimeout(id);
  }, [arming]);
  const togglePeek = (n: number) => setPeek(p => { const q = new Set(p); if (q.has(n)) q.delete(n); else q.add(n); return q; });
  const editBox = useRef<HTMLTextAreaElement>(null);
  const keepRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { setEditing(null); setPeek(new Set()); }, [talk.session]);
  useEffect(() => { setAsking(false); }, [editing?.seq]);
  useEffect(() => {
    const el = editBox.current;
    if (!el) return;
    el.focus({ preventScroll: true });
    el.setSelectionRange(el.value.length, el.value.length);
  }, [editing?.seq]);
  useEffect(() => { if (asking) keepRef.current?.focus(); }, [asking]);
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
    { name: "clear", label: t("talk.clear"), icon: "wipe", run: talk.clear },
    { name: "compact", label: t("talk.compact"), icon: "squeeze", note: t("nc.costs"), run: talk.compact },
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
    if ((!text && !staged) || streaming !== null || legacy) return;
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
    drop(e.dataTransfer.files);
  };
  const bySeq = new Map<number, Attachment[]>();
  for (const a of attachments) bySeq.set(a.seq, [...(bySeq.get(a.seq) ?? []), a]);
  const card = (a: Attachment, past: boolean) => (
    <div key={`a${a.n}`} className="chat-att" data-past={past || undefined}>
      <button type="button" className="chat-att-name" aria-expanded={peek.has(a.n)} onClick={() => togglePeek(a.n)}>
        <Icon name="sheet2" /><b>{a.name}</b><span>{t("talk.chars", { n: a.chars })}</span>
      </button>
      {peek.has(a.n) && a.head && <p className="chat-att-head">{a.head}</p>}
      {free && !a.adopted && (
        <button type="button" className="chat-att-adopt" disabled={working || streaming !== null}
          onClick={() => void adopt(a.n)}><Icon name="new" />{t("talk.adopt")}</button>
      )}
    </div>
  );
  const placed = new Set<number>();
  const before = (turn: Turn, past: boolean) => {
    if (turn.seq === undefined || placed.has(turn.seq)) return null;
    placed.add(turn.seq);
    return bySeq.get(turn.seq)?.map(a => card(a, past)) ?? null;
  };

  const saveEdit = async (turn: Turn) => {
    if (!editing) return;
    if (editing.text.trim() === turn.text.trim()) { setEditing(null); return; }
    const r = await talk.editReply(editing.seq, editing.text);
    if (r !== null) setEditing(null);
  };
  const leaveEdit = (turn: Turn) => {
    if (editing && editing.text !== turn.text) setAsking(true);
    else setEditing(null);
  };
  const keepEditing = () => { setAsking(false); editBox.current?.focus({ preventScroll: true }); };
  const onEditKey = (e: KeyboardEvent<HTMLElement>, turn: Turn) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); if (asking) keepEditing(); else leaveEdit(turn); }
    else if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !asking) { e.preventDefault(); void saveEdit(turn); }
  };
  const still = legacy || streaming !== null || working;
  const lastTurn = turns[turns.length - 1];
  const editBar = (turn: Turn) => (
    <div className="chat-acts chat-edit-bar" data-asking={asking || undefined}>
      {asking ? (
        <>
          <span className="chat-edit-ask" role="alert">{t("card.discard.ask")}</span>
          <button type="button" ref={keepRef} className="chat-edit-btn is-save" onClick={keepEditing}>{t("card.discard.keep")}</button>
          <button type="button" className="chat-edit-btn" onClick={() => setEditing(null)}>{t("card.discard")}</button>
        </>
      ) : (
        <>
          <button type="button" className="chat-edit-btn is-save" disabled={still || !editing?.text.trim() || editing?.text === turn.text}
            title={`${t("reply.save")} (⌘↵)`} onClick={() => void saveEdit(turn)}>{t("reply.save")}</button>
          <button type="button" className="chat-edit-btn" onClick={() => leaveEdit(turn)}>{t("reply.cancel")}</button>
        </>
      )}
    </div>
  );
  const acts = (turn: Turn) => {
    if (!session || turn.seq === undefined) return null;
    const seq = turn.seq;
    const n = turn.variant?.n ?? 1;
    const total = turn.variant?.total ?? 1;
    const last = lastTurn === turn;
    const held = still || editing !== null;
    return (
      <div className="chat-acts">
        <button type="button" className="chat-act" aria-label={t("reply.edit")} title={t("reply.edit")} disabled={held}
          onClick={() => setEditing({ seq, text: turn.text })}><Icon name="edit" /></button>
        {last && (
          <button type="button" className="chat-act" aria-label={t("reply.redo")} title={t("reply.redo")} disabled={held}
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
        <span className="chat-acts-mark">
          <Voice key={`v-${session}-${seq}-${n}`} session={session} seq={seq} initial={!!turn.voice}
            onChange={v => markVoice(session, seq, v)} />
          <Reaction key={`${session}-${seq}-${n}`} session={session} seq={seq} initial={turn.reaction ?? null}
            onChange={r => markTurn(session, seq, r)} />
        </span>
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
  const cut = lastCut(turns);
  const rows = turns.map((turn: Turn, i) => {
    const past = i < cut || undefined;
    const brk = breaks.has(i) && <div key={`v${i}`} className="chat-ver"><Icon name="sheet2" /><span>{t("talk.versionBreak", { n: turn.v! })}</span></div>;
    if (turn.role === "clear") {
      return [<div key={i} className="chat-cut" role="separator" aria-label={t("talk.cleared")}><Icon name="wipe" /><span>{t("talk.cleared")}</span></div>];
    }
    if (turn.role === "compact") {
      return [
        <div key={i} className="chat-cut is-compact" role="separator" aria-label={t("talk.compacted")}><Icon name="squeeze" /><span>{t("talk.compacted")}</span></div>,
        <Summary key={`s${i}`} text={turn.text} past={!!past} label={t("talk.compacted")} />,
      ];
    }
    const att = before(turn, !!past);
    if (turn.role !== "assistant") {
      return [brk, att,
        <div key={i} className="chat-me" data-past={past}>
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
      <div key={lit ? `${i}-${flash!.n}` : i} className={lit ? "chat-turn is-flash" : "chat-turn"} data-turn={i} data-last={lastTurn === turn || undefined} data-past={past}
        data-editing={open || undefined} onKeyDown={open ? e => onEditKey(e, turn) : undefined}>
        {who.has(i) && whoLine(c)}
        {redo
          ? (streaming ? <p className="chat-text">{streaming}</p>
            : <p className="chat-wait" role="status">{t("talk.waiting", { name: nameOf(c.id) })}</p>)
          : open
            ? <textarea ref={editBox} className="chat-text chat-text-edit" aria-label={t("reply.editBox")} value={editing.text} readOnly={asking}
                onChange={e => setEditing({ seq: turn.seq!, text: e.target.value })} />
            : <p className="chat-text">{quoted(turn.text, turn.spans, version)}</p>}
        {redo && streaming !== null && (
          <div className="chat-acts">
            <button type="button" className="chat-act is-stop" aria-label={t("talk.stop")} title={t("talk.stop")}
              onClick={e => { if (e.detail <= 1) talk.stop(); }}><Icon name="stop" /></button>
          </div>
        )}
        {!redo && (open ? editBar(turn) : acts(turn))}
      </div>,
    ];
  });

  return (
    <div className="chat" onDragOver={free ? e => e.preventDefault() : undefined} onDrop={free ? onDrop : undefined}>
      <div className="chat-log" ref={log} role="log" aria-live="polite" aria-busy={streaming !== null}>
        {bound && !session && <Prior mode="live" slug={bound} skipped={talk.skipPrior} onSkip={talk.setSkipPrior} onGoto={talk.open} onMemory={onMemory} busy={streaming !== null} />}
        {bound && session && <Prior key={session} mode="snapshot" session={session} snapshot={talk.prior} onGoto={talk.open} busy={streaming !== null || working} />}
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
        {commands.length > 0 && (
          <ul className="slash-menu" role="listbox" aria-label={t("talk.commands")}>
            {commands.map(c => (
              <li key={c.name} role="option" aria-selected={c === chosen} aria-disabled={!usable}>
                <button type="button" disabled={!usable} onMouseDown={e => e.preventDefault()} onClick={() => runCommand(c)}>
                  <Icon name={c.icon} /><b>/{c.name}</b><span>{c.label}</span>{c.note && <small>{c.note}</small>}
                </button>
              </li>
            ))}
            {!usable && <li className="slash-note" role="status">{t(streaming !== null || working ? "err.busy" : "talk.cmdIdle")}</li>}
          </ul>
        )}
        {staged && (
          <div className="chat-staged">
            <Icon name="sheet2" /><b>{staged.name}</b><span>{t("talk.chars", { n: [...staged.text.trim()].length })}</span>
            <button type="button" className="ib" aria-label={t("talk.dropAttach")} title={t("talk.dropAttach")} onClick={talk.dropStaged}><Icon name="close" /></button>
          </div>
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
          {session && (
            <>
              <span className="bar-sep" aria-hidden="true" />
              <button type="button" className="ib" disabled={idle || !live} aria-label={t("talk.clear")} title={`${t("talk.clear")} · /clear`}
                onClick={() => void talk.clear()}><Icon name="wipe" /></button>
              <button type="button" className={arming ? "ib bar-arm" : "ib"} disabled={idle || !live} aria-label={t("talk.compact")}
                title={`${t("talk.compactCost")} · /compact`} onBlur={() => setArming(false)}
                onClick={() => { if (!arming) { setArming(true); return; } setArming(false); void talk.compact(); }}>
                <Icon name="squeeze" />{arming && <span>{t("talk.compactSure")}</span>}
              </button>
            </>
          )}
          {streaming !== null
            ? <button key="stop" type="button" className="ib send" aria-label={t("talk.stop")} title={t("talk.stop")}
              onClick={e => { if (e.detail <= 1) talk.stop(); }}><Icon name="stop" /></button>
            : <button key="send" type="submit" className="ib send" aria-label={t("talk.send")} title={t("talk.send")}
              disabled={legacy || (!draft.trim() && !staged)}><Icon name="send" /></button>}
        </div>
      </form>
    </div>
  );
}
