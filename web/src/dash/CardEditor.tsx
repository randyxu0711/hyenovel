import { useState, type FormEvent } from "react";
import { DashError, type CardDraft } from "./api";
import { errorMessage, localized, useLang, useT, type Lang, type MsgKey } from "./i18n";

export type CardLimits = { name: number; line: number; reading: number; lineRequired?: boolean };
export const SAVED_LIMITS: CardLimits = { name: 64, line: 200, reading: 6000 };
export const candidateLimits = (lang: Lang): CardLimits =>
  lang === "en" ? { name: 32, line: 80, reading: 600, lineRequired: true } : { name: 16, line: 40, reading: 600, lineRequired: true };

export default function CardEditor({ draft, limits, onSave, onCancel }: {
  draft: CardDraft; limits: CardLimits;
  /** 回傳要作者確認的 warnings;空陣列 = 存好了。 */
  onSave: (draft: CardDraft, confirm: boolean) => Promise<string[]>;
  onCancel: () => void;
}) {
  const t = useT();
  const lang = useLang();
  const [name, setName] = useState(() => localized(draft.name, lang));
  const [line, setLine] = useState(() => localized(draft.line, lang));
  const [reading, setReading] = useState(draft.reading);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const [err, setErr] = useState<MsgKey | null>(null);
  const [saving, setSaving] = useState(false);
  const ready = name.trim() && reading.trim() && (!limits.lineRequired || line.trim());

  const edit = (set: (value: string) => void) => (value: string) => { set(value); setWarnings([]); };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!ready || saving) return;
    setSaving(true); setErr(null); setProblems([]);
    const next = { name: { ...draft.name, [lang]: name.trim() }, line: { ...draft.line, [lang]: line.trim() }, reading };
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

  return (
    <form className="char-card char-edit" onSubmit={e => void save(e)}>
      <label>{t("card.name")}
        <input className="nc-edit" maxLength={limits.name} autoComplete="off" value={name} onChange={e => edit(setName)(e.target.value)} />
      </label>
      <label>{t("card.line")}
        <input className="nc-edit" maxLength={limits.line} autoComplete="off" value={line} onChange={e => edit(setLine)(e.target.value)} />
      </label>
      <label>{t("card.reading")}
        <textarea className="nc-edit" rows={4} maxLength={limits.reading} value={reading} onChange={e => edit(setReading)(e.target.value)} />
      </label>
      {warnings.map(w => <p key={w} className="nc-warn" role="note">{t(`card.warn.${w}` as MsgKey)}</p>)}
      {problems.length > 0 && <ul role="alert">{problems.map(p => <li key={p}>{t(`card.err.${p}` as MsgKey)}</li>)}</ul>}
      {err && <p className="nc-warn" role="alert">{t(err)}</p>}
      <div className="char-edit-foot">
        <button type="submit" disabled={!ready || saving}>{t(warnings.length > 0 ? "card.saveAnyway" : "card.save")}</button>
        <button type="button" onClick={onCancel}>{t("set.card.cancel")}</button>
      </div>
    </form>
  );
}
