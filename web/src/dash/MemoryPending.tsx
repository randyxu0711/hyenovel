import { useEffect, useRef, useState } from "react";
import { api, DashError, type MemoryCandidate, type MemoryScope } from "./api";
import { errorMessage, useLang, useT } from "./i18n";
import Icon from "./Icon";
import { MAX_CHAT } from "./useTalk";
import { whenLabel } from "./when";

const SHOWN = 5;

type Done = { kind: "saved"; scope: MemoryScope } | { kind: "skipped" };

function Item({ c, done, onDone, onUndo }: {
  c: MemoryCandidate; done: Done | undefined;
  onDone: (d: Done, text?: string) => Promise<void>; onUndo: () => Promise<void>;
}) {
  const t = useT();
  const lang = useLang();
  const [draft, setDraft] = useState<string | null>(null);
  const layers: MemoryScope[] = c.slug === null ? ["author"] : c.scope === "work" ? ["work", "author"] : ["author", "work"];
  const text = draft ?? undefined;
  if (done) {
    return (
      <li className="dash-pend-item" data-done="">
        <p className="dash-pend-done">
          {done.kind === "saved" ? t("pend.savedIn", { layer: t(done.scope === "work" ? "pend.layer.work" : "pend.layer.author") }) : t("pend.skipped")}
          <button type="button" className="dash-pend-lnk" onClick={() => void onUndo()}>{t("pend.undo")}</button>
        </p>
      </li>
    );
  }
  return (
    <li className="dash-pend-item">
      {draft === null ? <p className="dash-pend-text">{c.text}</p> : (
        <textarea aria-label={t("memory.text")} rows={2} maxLength={MAX_CHAT} value={draft} autoFocus
          onChange={e => setDraft(e.target.value)} />
      )}
      <p className="dash-mem-source">「{c.quote}」{c.title ? `〈${c.title}〉` : t("pend.chatOnly")}<span className="dash-pend-when">{whenLabel(c.at, Date.now() / 1000, lang)}</span></p>
      <div className="dash-pend-bar">
        {layers.map((l, i) => (
          <button key={l} type="button" className={`dash-pend-act${i === 0 ? " yes" : ""}`} disabled={draft !== null && !draft.trim()}
            onClick={() => void onDone({ kind: "saved", scope: l }, text)}>{t(l === "work" ? "pend.toWork" : "pend.toAuthor")}</button>
        ))}
        <button type="button" className="dash-pend-act" onClick={() => void onDone({ kind: "skipped" })}>{t("pend.skip")}</button>
        {draft === null
          ? <button type="button" className="ib" aria-label={t("memory.edit")} title={t("memory.edit")} onClick={() => setDraft(c.text)}><Icon name="edit" /></button>
          : <button type="button" className="ib" aria-label={t("memory.cancel")} title={t("memory.cancel")} onClick={() => setDraft(null)}><Icon name="close" /></button>}
      </div>
    </li>
  );
}

export default function MemoryPending({ onChange, onCount }: { onChange: () => void; onCount: (n: number) => void }) {
  const t = useT();
  const [list, setList] = useState<MemoryCandidate[] | null>(null);
  const [done, setDone] = useState<Record<number, Done>>({});
  const [older, setOlder] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const busy = useRef(false);
  useEffect(() => { api.candidates().then(setList, () => setList([])); }, []);
  const left = list ? list.filter(c => !done[c.id]).length : null;
  useEffect(() => { if (left !== null) onCount(left); }, [left, onCount]);

  const run = async (fn: () => Promise<unknown>) => {
    if (busy.current) return false;
    busy.current = true; setCode(null);
    try { await fn(); return true; } catch (e) { setCode(e instanceof DashError ? e.code : "unknown"); return false; } finally { busy.current = false; }
  };
  const finish = async (c: MemoryCandidate, d: Done, text?: string) => {
    const ok = await run(() => d.kind === "saved" ? api.saveCandidate(c.id, d.scope, text) : api.skipCandidate(c.id));
    if (!ok) return;
    setDone(m => ({ ...m, [c.id]: d }));
    if (d.kind === "saved") onChange();
  };
  const undo = async (c: MemoryCandidate) => {
    const was = done[c.id];
    if (!(await run(() => api.undoCandidate(c.id)))) return;
    setDone(m => { const n = { ...m }; delete n[c.id]; return n; });
    if (was?.kind === "saved") onChange();
  };

  if (!list || list.length === 0) return null;
  const item = (c: MemoryCandidate) =>
    <Item key={c.id} c={c} done={done[c.id]} onDone={(d, text) => finish(c, d, text)} onUndo={() => undo(c)} />;
  return (
    <section className="dash-pend" aria-label={t("pend.title")}>
      <h2><span className="dash-pend-dot" aria-hidden="true" />{t("pend.title")} <span className="dash-dm">{left}</span></h2>
      {code && <p role="alert" className="dash-pend-err">{t(errorMessage(code))}</p>}
      <ul>{list.slice(0, SHOWN).map(item)}</ul>
      {list.length > SHOWN && (
        <>
          <button type="button" className="dash-pend-lnk dash-pend-older" aria-expanded={older} onClick={() => setOlder(o => !o)}>
            {t("pend.older", { n: list.length - SHOWN })}
          </button>
          {older && <ul>{list.slice(SHOWN).map(item)}</ul>}
        </>
      )}
    </section>
  );
}
