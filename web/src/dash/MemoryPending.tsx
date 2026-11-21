import { useEffect, useRef, useState } from "react";
import { api, DashError, type MemoryCandidate, type MemoryScope } from "./api";
import { errorMessage, useLang, useT } from "./i18n";
import Icon from "./Icon";
import { MAX_CHAT } from "./useTalk";
import { whenLabel } from "./when";

const SHOWN = 5;
const LEAVE_MS = 220;

type Done = { kind: "saved"; scope: MemoryScope; memory: number } | { kind: "skipped" };
export type Saved = { group: string; memory: number };

const still = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? true;

function Slip({ c, leaving, onDone, focus }: {
  c: MemoryCandidate; leaving: boolean; focus: boolean;
  onDone: (kind: "saved" | "skipped", scope: MemoryScope, text?: string) => Promise<void>;
}) {
  const t = useT();
  const lang = useLang();
  const [draft, setDraft] = useState<string | null>(null);
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (focus) first.current?.focus(); }, [focus]);
  const layers: MemoryScope[] = c.slug === null ? ["author"] : c.scope === "work" ? ["work", "author"] : ["author", "work"];
  const text = draft ?? undefined;
  const blank = draft !== null && !draft.trim();
  return (
    <li className="dash-pend-item" data-leaving={leaving || undefined}>
      <p className="dash-pend-src">
        <span className="dash-pend-work">{c.title ? `〈${c.title}〉` : t("pend.chatOnly")}</span>
        <span className="dash-pend-when">{whenLabel(c.at, Date.now() / 1000, lang)}</span>
      </p>
      {draft === null ? <p className="dash-pend-text">{c.text}</p> : (
        <textarea aria-label={t("memory.text")} rows={2} maxLength={MAX_CHAT} value={draft} autoFocus
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Escape") { e.preventDefault(); setDraft(null); }
            else if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              if (!blank) void onDone("saved", layers[0], text);
            }
          }} />
      )}
      {c.quote.trim() !== c.text.trim() && <blockquote className="dash-quote">{c.quote}</blockquote>}
      <div className="dash-pend-bar">
        {layers.map((l, i) => (
          <button key={l} ref={i === 0 ? first : undefined} type="button" className={`dash-pend-act${i === 0 ? " yes" : ""}`} disabled={blank}
            onClick={() => void onDone("saved", l, text)}>{t(l === "work" ? "pend.toWork" : "pend.toAuthor")}</button>
        ))}
        <button type="button" className="dash-pend-act" onClick={() => void onDone("skipped", "author")}>{t("pend.skip")}</button>
        {draft === null
          ? <button type="button" className="ib" aria-label={t("memory.edit")} title={t("memory.edit")} onClick={() => setDraft(c.text)}><Icon name="edit" /></button>
          : <button type="button" className="ib" aria-label={t("memory.cancel")} title={t("memory.cancel")} onClick={() => setDraft(null)}><Icon name="close" /></button>}
      </div>
    </li>
  );
}

function Receipt({ c, done, onUndo, onGoto }: { c: MemoryCandidate; done: Done; onUndo: () => void; onGoto: (s: Saved) => void }) {
  const t = useT();
  return (
    <li className="dash-pend-done">
      {done.kind === "saved" ? <>
        <span aria-hidden="true">✓</span>
        <span className="dash-pend-gist">{c.text}</span>
        <span aria-hidden="true">→</span>
        <button type="button" className="dash-pend-lnk dash-pend-to"
          onClick={() => onGoto({ group: done.scope === "work" ? c.slug! : "", memory: done.memory })}>
          {done.scope === "work" ? `〈${c.title}〉` : t("pend.layer.author")}
        </button>
      </> : <>
        <span>{t("pend.skipped")}</span>
        <span className="dash-pend-gist">{c.text}</span>
      </>}
      <button type="button" className="dash-pend-lnk" onClick={onUndo}>{t("pend.undo")}</button>
    </li>
  );
}

export default function MemoryPending({ onChange, onCount, onSaved, onGoto, focus = false }: {
  onChange: () => void; onCount: (n: number) => void;
  onSaved?: (s: Saved) => void; onGoto?: (s: Saved) => void;
  focus?: boolean;
}) {
  const t = useT();
  const [list, setList] = useState<MemoryCandidate[] | null>(null);
  const [done, setDone] = useState<Record<number, Done>>({});
  const [order, setOrder] = useState<number[]>([]);
  const [leaving, setLeaving] = useState<number | null>(null);
  const [older, setOlder] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const busy = useRef(false);
  const sec = useRef<HTMLElement>(null);
  useEffect(() => { api.candidates().then(setList, () => setList([])); }, []);
  const left = list ? list.filter(c => !done[c.id]) : null;
  useEffect(() => { if (left !== null) onCount(left.length); }, [left?.length, onCount]);
  const ready = !!list && list.length > 0;
  useEffect(() => { if (focus && ready) sec.current?.scrollIntoView?.({ block: "start" }); }, [focus, ready]);

  const run = async (fn: () => Promise<unknown>, onFail?: (code: string) => void) => {
    if (busy.current) return null;
    busy.current = true; setCode(null);
    try { return { v: await fn() }; } catch (e) {
      const code = e instanceof DashError ? e.code : "unknown";
      setCode(code); onFail?.(code); return null;
    } finally { busy.current = false; }
  };
  const finish = async (c: MemoryCandidate, kind: "saved" | "skipped", scope: MemoryScope, text?: string) => {
    const r = await run(() => kind === "saved" ? api.saveCandidate(c.id, scope, text) : api.skipCandidate(c.id));
    if (!r) return;
    const d: Done = kind === "saved" ? { kind, scope, memory: (r.v as { id: number }).id } : { kind };
    const settle = () => {
      setLeaving(null);
      setDone(m => ({ ...m, [c.id]: d }));
      setOrder(o => [...o, c.id]);
      if (d.kind === "saved") { onChange(); onSaved?.({ group: d.scope === "work" ? c.slug! : "", memory: d.memory }); }
    };
    if (still()) settle();
    else { setLeaving(c.id); window.setTimeout(settle, LEAVE_MS); }
  };
  const undo = async (c: MemoryCandidate) => {
    const was = done[c.id];
    const gone = (code: string) => {
      if (code !== "unknown-memory-candidate") return;
      setList(l => l && l.filter(x => x.id !== c.id));
      setDone(m => { const n = { ...m }; delete n[c.id]; return n; });
      setOrder(o => o.filter(x => x !== c.id));
    };
    if (!(await run(() => api.undoCandidate(c.id), gone))) return;
    setDone(m => { const n = { ...m }; delete n[c.id]; return n; });
    setOrder(o => o.filter(x => x !== c.id));
    if (was?.kind === "saved") onChange();
  };

  if (!list || !left || list.length === 0) return null;
  const byId = new Map(list.map(c => [c.id, c]));
  const slip = (c: MemoryCandidate, i: number) =>
    <Slip key={c.id} c={c} leaving={leaving === c.id} focus={focus && i === 0} onDone={(k, s, text) => finish(c, k, s, text)} />;
  return (
    <section ref={sec} className="dash-pend-sec" aria-label={t("pend.title")}>
      <h2><span className="dash-pend-dot" aria-hidden="true" />{t("pend.title")} <span className="dash-dm">{left.length}</span></h2>
      {code && <p role="alert" className="dash-pend-err">{t(errorMessage(code))}</p>}
      {left.length > 0 && <ul className="dash-pend-list">{left.slice(0, SHOWN).map(slip)}</ul>}
      {left.length > SHOWN && (
        <>
          <button type="button" className="dash-pend-lnk dash-pend-older" aria-expanded={older} onClick={() => setOlder(o => !o)}>
            {t("pend.older", { n: left.length - SHOWN })}
          </button>
          {older && <ul className="dash-pend-list">{left.slice(SHOWN).map((c, i) => slip(c, i + SHOWN))}</ul>}
        </>
      )}
      {order.length > 0 && (
        <ul className="dash-pend-receipts">
          {order.map(id => <Receipt key={id} c={byId.get(id)!} done={done[id]} onUndo={() => void undo(byId.get(id)!)} onGoto={s => onGoto?.(s)} />)}
        </ul>
      )}
    </section>
  );
}
