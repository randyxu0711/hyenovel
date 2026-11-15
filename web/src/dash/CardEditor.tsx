import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { DashError, type CardDraft } from "./api";
import { errorMessage, localized, useLang, useT, type Lang, type MsgKey } from "./i18n";
import PlistWords from "./Plist";
import { composePlist, parsePlist, speechLabel, type Plist } from "./plistFormat";

export type CardLimits = { name: number; line: number; reading: number; examples?: number; depth?: number; lineRequired?: boolean };
export const SAVED_LIMITS: CardLimits = { name: 64, line: 200, reading: 6000, examples: 3000, depth: 600 };
export const candidateLimits = (lang: Lang): CardLimits =>
  lang === "en" ? { name: 32, line: 80, reading: 600, depth: 600, lineRequired: true } : { name: 16, line: 40, reading: 600, depth: 600, lineRequired: true };

export default function CardEditor({ draft, limits, onSave, onCancel, onChange, sheet = false, selectName = false }: {
  draft: Omit<CardDraft, "examples" | "depth"> & { examples?: unknown; depth?: unknown }; limits: CardLimits;
  /** 回傳要作者確認的 warnings;空陣列 = 存好了。 */
  onSave: (draft: CardDraft, confirm: boolean) => Promise<string[]>;
  onCancel: () => void;
  onChange?: (card: { name: string; line: string }) => void;
  sheet?: boolean;
  selectName?: boolean;
}) {
  const t = useT();
  const lang = useLang();
  const [name, setName] = useState(() => localized(draft.name, lang));
  const [line, setLine] = useState(() => localized(draft.line, lang));
  const [reading, setReading] = useState(draft.reading);
  const withExamples = limits.examples !== undefined && typeof draft.examples === "string";
  const [examples, setExamples] = useState(typeof draft.examples === "string" ? draft.examples : "");
  const withDepth = limits.depth !== undefined && typeof draft.depth === "string";
  const [depth, setDepth] = useState(typeof draft.depth === "string" ? draft.depth : "");
  const [plist, setPlist] = useState<Plist | null>(() => depth.trim() === "" ? { traits: [], label: speechLabel(lang), speech: [] } : parsePlist(depth));
  const [warnings, setWarnings] = useState<string[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [err, setErr] = useState<MsgKey | null>(null);
  const [saving, setSaving] = useState(false);
  const [pending, setPending] = useState(false);
  const [asking, setAsking] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const keepRef = useRef<HTMLButtonElement>(null);
  const [start] = useState(() => ({ name, line, reading, examples, depth }));
  const dirty = pending || name !== start.name || line !== start.line || reading !== start.reading || examples !== start.examples || depth !== start.depth;
  const onPending = useCallback((p: boolean) => setPending(p), []);
  useEffect(() => { if (selectName) nameRef.current?.select(); }, [selectName]);
  useEffect(() => { if (asking) keepRef.current?.focus(); }, [asking]);
  const leave = () => { if (dirty) setAsking(true); else onCancel(); };
  const keys = (e: KeyboardEvent<HTMLFormElement>) => {
    if (!sheet || e.key !== "Escape" || e.nativeEvent.isComposing) return;
    e.stopPropagation();
    if (asking) setAsking(false);
    else leave();
  };
  const ready = name.trim() && reading.trim() && (!limits.lineRequired || line.trim());

  const edit = (set: (value: string) => void) => (value: string) => { set(value); setWarnings([]); };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || saving) return;
    setSaving(true); setErr(null); setProblems([]);
    const next = { name: { ...draft.name, [lang]: name.trim() }, line: { ...draft.line, [lang]: line.trim() }, reading, ...(withExamples ? { examples } : {}), ...(withDepth ? { depth } : {}) };
    try {
      setWarnings(await onSave(next, warnings.length > 0));
    } catch (e) {
      setWarnings([]);
      if (e instanceof DashError && Array.isArray(e.params.errors)) setProblems(e.params.errors as string[]);
      else setErr(errorMessage(e instanceof DashError ? e.code : "unknown"));
    } finally {
      setSaving(false);
    }
  };

  const field = (key: MsgKey, control: ReactNode, long = false) => (
    <label className={long && sheet ? "char-reading char-edit-long" : undefined}>
      <span className={sheet && !long ? "vh" : "char-edit-k"}>{t(key)}</span>
      {control}
    </label>
  );

  return (
    <form className={sheet ? "char-edit is-sheet" : "char-card char-edit"} onSubmit={e => void save(e)} onKeyDown={keys}>
      {field("card.name", <input ref={nameRef} className="nc-edit char-edit-name" autoFocus={sheet} maxLength={limits.name} autoComplete="off" value={name} onChange={e => { edit(setName)(e.target.value); onChange?.({ name: e.target.value, line }); }} />)}
      {field("card.line", <input className="nc-edit char-edit-line" maxLength={limits.line} autoComplete="off" value={line} onChange={e => { edit(setLine)(e.target.value); onChange?.({ name, line: e.target.value }); }} />)}
      {field("card.reading", <textarea className="nc-edit" rows={4} maxLength={limits.reading} value={reading} onChange={e => edit(setReading)(e.target.value)} />, true)}
      {withExamples && field("card.examples", <textarea className="nc-edit" rows={8} maxLength={limits.examples} value={examples} onChange={e => edit(setExamples)(e.target.value)} />, true)}
      {withDepth && (plist
        ? (
          <section className={sheet ? "char-reading" : "char-edit-plist"} aria-label={t("card.depth")}>
            <h3 className="char-edit-k">{t("card.depth")}</h3>
            <PlistWords plist={plist} limit={limits.depth} onPending={onPending} onChange={next => { setPlist(next); edit(setDepth)(composePlist(next)); }} />
          </section>
        )
        : field("card.depth", <textarea className="nc-edit" rows={3} maxLength={limits.depth} value={depth} onChange={e => edit(setDepth)(e.target.value)} />, true))}
      {warnings.map(w => <p key={w} className="nc-warn" role="note">{t(`card.warn.${w}` as MsgKey)}</p>)}
      {problems.length > 0 && <ul role="alert">{problems.map(p => <li key={p}>{t(`card.err.${p}` as MsgKey)}</li>)}</ul>}
      {err && <p className="nc-warn" role="alert">{t(err)}</p>}
      <div className="char-edit-foot" data-asking={asking || undefined}>
        {asking ? (
          <>
            <span className="char-edit-ask" role="alert">{t("card.discard.ask")}</span>
            <button type="button" ref={keepRef} className={sheet ? "dash-key" : undefined} onClick={() => setAsking(false)}>{t("card.discard.keep")}</button>
            <button type="button" onClick={onCancel}>{t("card.discard")}</button>
          </>
        ) : (
          <>
            <button type="submit" className={sheet ? "dash-key" : undefined} disabled={!ready || saving}>{t(warnings.length > 0 ? "card.saveAnyway" : "card.save")}</button>
            <button type="button" onClick={leave}>{t("set.card.cancel")}</button>
          </>
        )}
      </div>
    </form>
  );
}
