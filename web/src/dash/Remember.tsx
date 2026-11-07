import { useRef, useState } from "react";
import { api, DashError, type MemoryScope, type TurnMemory } from "./api";
import Icon from "./Icon";
import { errorMessage, useT } from "./i18n";
import { useSelectionQuote } from "./useSelectionQuote";
import { MAX_CHAT } from "./useTalk";

const LAYERS = [
  { scope: "work", label: "memory.work" },
  { scope: "author", label: "memory.author" },
] as const;
const LAYER_LABEL = { work: "memory.work", author: "memory.author" } as const;

type Form = { quote: string; text: string; scope: MemoryScope };

/** 作者的一則發言:選一段或整則記成記憶。內容可改,來源引文固定是原話。 */
export default function Remember({ slug, session, seq, text, initial, onChange }: {
  slug: string; session: string; seq: number; text: string; initial: TurnMemory[];
  onChange: (memories: TurnMemory[]) => void;
}) {
  const t = useT();
  const words = useRef<HTMLParagraphElement>(null);
  const { quote: selected, clear } = useSelectionQuote(words);
  const [saved, setSaved] = useState(initial);
  const [form, setForm] = useState<Form | null>(null);
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [peek, setPeek] = useState<number | null>(null);

  const latest = useRef(initial);
  const undoing = useRef(new Set<number>());
  const show = (next: TurnMemory[]) => { latest.current = next; setSaved(next); onChange(next); };
  const fail = (e: unknown) => setCode(e instanceof DashError ? e.code : "unknown");

  const open = () => {
    const quote = selected ?? text;
    setForm({ quote, text: quote, scope: "work" });
    setCode(null);
    clear();
  };

  const submit = async () => {
    if (!form || busy) return;
    setBusy(true);
    try {
      const m = await api.remember({ scope: form.scope, text: form.text, slug, session, seq, quote: form.quote });
      show([...latest.current, { id: m.id, scope: form.scope }]);
      setForm(null); setCode(null);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const undo = async (id: number) => {
    if (undoing.current.has(id)) return;
    undoing.current.add(id);
    try {
      await api.archiveMemory(id);
      show(latest.current.filter(m => m.id !== id));
      setCode(null);
    } catch (e) { fail(e); } finally { undoing.current.delete(id); }
  };

  return (
    <>
      <p ref={words}>{text}</p>
      <div className="chat-mem">
        {saved.map(m => (
          <span key={m.id} className="chat-mem-mark">
            <button type="button" className="chat-mem-on" aria-expanded={peek === m.id}
              aria-label={t("memory.savedIn", { layer: t(LAYER_LABEL[m.scope]) })} title={t("memory.savedIn", { layer: t(LAYER_LABEL[m.scope]) })}
              onClick={() => setPeek(p => (p === m.id ? null : m.id))}><Icon name="memoryOn" /></button>
            {peek === m.id && <button type="button" className="chat-mem-undo" onClick={() => void undo(m.id)}>{t("memory.undo")}</button>}
          </span>
        ))}
        {!form && (
          <button type="button" className="chat-mem-open" aria-label={t("memory.remember")} title={t("memory.remember")}
            onMouseDown={e => e.preventDefault()} onClick={open}><Icon name="memory" /></button>
        )}
        {form && (
          <form className="chat-mem-form" onSubmit={e => { e.preventDefault(); void submit(); }}>
            <textarea aria-label={t("memory.text")} rows={2} maxLength={MAX_CHAT} value={form.text}
              onChange={e => setForm({ ...form, text: e.target.value })} />
            <div className="chat-mem-bar">
              {LAYERS.map(l => (
                <button key={l.scope} type="button" className="chat-mem-layer" aria-pressed={form.scope === l.scope}
                  onClick={() => setForm({ ...form, scope: l.scope })}>{t(l.label)}</button>
              ))}
              <button type="button" className="ib" aria-label={t("memory.cancel")} title={t("memory.cancel")}
                onClick={() => { setForm(null); setCode(null); }}><Icon name="close" /></button>
              <button type="submit" className="chat-mem-save" disabled={busy || !form.text.trim()}>{t("memory.save")}</button>
            </div>
          </form>
        )}
        {code && <p className="chat-mem-err" role="alert">{t(errorMessage(code))}</p>}
      </div>
    </>
  );
}
