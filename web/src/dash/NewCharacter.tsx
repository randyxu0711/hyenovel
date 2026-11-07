import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, DashError, type CardDraft, type Candidate, type CandidateAnswers, type Character } from "./api";
import Figure from "./Figure";
import CardEditor, { candidateLimits } from "./CardEditor";
import CharacterCard from "./CharacterCard";
import { clock } from "./clock";
import Icon from "./Icon";
import { errorMessage, localized, useLang, useT, type MsgKey } from "./i18n";
import type { FigureSpec, Pose } from "./figure/poses";
import { WORDS } from "./questionnaire";

const GRAY = { fill: "var(--dash-paper-ink-2)", text: "var(--dash-paper-ink-2)" };
const character = (seed: string, figure: FigureSpec): Character => ({
  id: seed, version: 1, origin: "created", archived: false, name: {}, line: {}, avatar: { kind: "figure", seed },
  figure, colors: { light: GRAY, dark: GRAY }, voice: "", mark: "pencil", reading: "",
});
const placeholder = (pose: Pose) => character(pose, { pose, parts: [], main: "bone", second: "bone" });
const look = (c: Candidate): FigureSpec => ({ pose: c.figure.pose, parts: c.figure.traits, main: c.figure.main, second: c.figure.second });

function CandidateSlip({ candidate, busy, locked, elapsed, onRevise, onUse }: {
  candidate: Candidate; busy: boolean; locked: boolean; elapsed: number;
  onRevise: (feedback: string) => Promise<boolean>; onUse: () => void;
}) {
  const t = useT();
  const lang = useLang();
  const [feedback, setFeedback] = useState("");
  const name = localized(candidate.name, lang);
  const send = async (e: FormEvent) => {
    e.preventDefault();
    if (locked || !feedback.trim()) return;
    if (await onRevise(feedback.trim())) setFeedback("");
  };
  return (
    <CharacterCard character={character(candidate.name["zh-Hant"] ?? name, look(candidate))} name={name} sub={localized(candidate.form, lang)} scanning={busy}>
      {candidate.sample && <p className="nc-sample">{candidate.sample}</p>}
      <p className="nc-line">{localized(candidate.line, lang)}</p>
      <details>
        <summary>{t("nc.reading")}</summary>
        <p>{candidate.reading}</p>
      </details>
      {candidate.warnings.map(w => <p key={w} className="nc-warn" role="note">{t(`card.warn.${w}` as MsgKey)}</p>)}
      <form className="nc-revise" onSubmit={e => void send(e)}>
        <input aria-label={t("nc.feedback")} placeholder={t("nc.feedback")} maxLength={300} autoComplete="off" value={feedback}
          disabled={busy} onChange={e => setFeedback(e.target.value)} />
        <div className="nc-revise-foot">
          <button type="submit" disabled={locked || !feedback.trim()}>{t("nc.revise")}</button>
          <span className="nc-note">{busy ? clock(elapsed) : t("nc.costs")}</span>
        </div>
      </form>
      <button type="button" className="nc-use" disabled={busy} onClick={onUse}>{t("nc.use")}</button>
    </CharacterCard>
  );
}

export default function NewCharacter({ onClose, onSaved }: { onClose: () => void; onSaved: () => Promise<void> }) {
  const t = useT();
  const lang = useLang();
  const [form, setForm] = useState("");
  const [round, setRound] = useState<number | null>(null);
  const [wish, setWish] = useState("");
  const [phase, setPhase] = useState<"form" | "busy" | "results">("form");
  const [batch, setBatch] = useState<Candidate[] | null>(null);
  const [batchNo, setBatchNo] = useState(0);
  const [revising, setRevising] = useState<number | null>(null);
  const [using, setUsing] = useState<number | null>(null);
  const [err, setErr] = useState<MsgKey | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const live = useRef(true);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  const spending = phase === "busy" || revising !== null;
  useEffect(() => {
    if (!spending) return;
    const started = Date.now();
    setElapsed(0);
    const id = setInterval(() => setElapsed((Date.now() - started) / 1000), 1000);
    return () => clearInterval(id);
  }, [spending]);
  useEffect(() => { if (phase === "results") resultsRef.current?.focus(); }, [phase]);

  const answers: CandidateAnswers = { form: form.trim(), wish: wish.trim() };

  const failure = (e: unknown): MsgKey => {
    const usage = e instanceof DashError && e.params.reason === "usage-limit";
    return usage ? errorMessage("usage-limit") : errorMessage(e instanceof DashError ? e.code : "unknown");
  };

  const generate = async () => {
    setErr(null); setUsing(null); setPhase("busy");
    try {
      const out = await api.characterCandidates(answers, lang);
      if (!live.current) return;
      setBatch(out.candidates);
      setBatchNo(n => n + 1);
      setPhase("results");
    } catch (e) {
      if (!live.current) return;
      setErr(failure(e));
      setPhase(batch ? "results" : "form");
    }
  };

  const revise = async (index: number, feedback: string) => {
    setErr(null); setRevising(index);
    try {
      const next = await api.reviseCandidate(batch![index], feedback, lang);
      if (!live.current) return false;
      setBatch(all => all!.map((c, i) => (i === index ? next : c)));
      return true;
    } catch (e) {
      if (live.current) setErr(failure(e));
      return false;
    } finally {
      if (live.current) setRevising(null);
    }
  };

  const save = async (index: number, draft: CardDraft, confirm: boolean) => {
    const out = await api.createCharacter({ ...batch![index], ...draft }, confirm);
    if (!out.created) return out.warnings ?? [];
    await onSaved();
    return [];
  };

  const back = (
    <button type="button" className="nc-back" onClick={phase === "results" ? () => { setErr(null); setPhase("form"); } : onClose}>
      <Icon name="back" />{t(phase === "results" ? "nc.backToAnswers" : "nc.backToList")}
    </button>
  );
  const alert = err && <p className="nc-err" role="alert">{t(err)}</p>;

  if (phase === "busy") {
    return (
      <div className="nc-busy" role="status">
        <div className="nc-figs" aria-hidden="true">
          {(["perch", "mound", "wisp"] as const).map(pose => <Figure key={pose} character={placeholder(pose)} state="scanning" size={56} />)}
        </div>
        <p>{t("nc.generating")} <span className="dash-dm">{clock(elapsed)}</span></p>
      </div>
    );
  }

  if (phase === "results" && batch) {
    return (
      <div className="nc nc-results" ref={resultsRef} tabIndex={-1}>
        {back}
        <div className="char-cards">
          {batch.map((c, i) => (i === using
            ? <CardEditor key={`${batchNo}-${i}`} draft={c} limits={candidateLimits(lang)}
                onSave={(draft, confirm) => save(i, draft, confirm)} onCancel={() => setUsing(null)} />
            : <CandidateSlip key={`${batchNo}-${i}`} candidate={c} busy={revising === i} locked={revising !== null} elapsed={elapsed}
                onRevise={feedback => revise(i, feedback)} onUse={() => setUsing(i)} />))}
        </div>
        {alert}
        <div className="nc-foot">
          <button type="button" className="dash-key" disabled={revising !== null} onClick={() => void generate()}><Icon name="swap" />{t("nc.again")}</button>
          <span className="nc-note">{t("nc.costs")}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="nc">
      {back}
      <div className="nc-sheet">
        <div className="nc-q nc-form">
          <label htmlFor="nc-form">{t("nc.form")}</label>
          <div className="nc-formline">
            <input id="nc-form" maxLength={80} autoComplete="off" value={form} aria-describedby="nc-form-hint"
              onChange={e => setForm(e.target.value)} />
            <button type="button" className="nc-idea" aria-pressed={round !== null}
              onClick={() => setRound(r => (r === null ? 0 : null))}>{t("nc.noIdea")}</button>
          </div>
          <p id="nc-form-hint" className="nc-hint">{t("nc.formHint")}</p>
          {round !== null && (
            <div className="nc-words">
              {WORDS.map((row, i) => {
                const word = localized(row[(round + i) % row.length], lang);
                return <button key={i} type="button" onClick={() => { setForm(word); setRound(null); }}>{word}</button>;
              })}
              <button type="button" className="ib" aria-label={t("nc.swapWords")} title={t("nc.swapWords")}
                onClick={() => setRound(r => (r ?? 0) + 1)}><Icon name="swap" /></button>
            </div>
          )}
        </div>
        <div className="nc-q nc-wish">
          <label htmlFor="nc-wish">{t("nc.wish")}</label>
          <textarea id="nc-wish" className="nc-edit" rows={2} maxLength={300} value={wish}
            onChange={e => setWish(e.target.value)} />
        </div>
      </div>
      {alert}
      <div className="nc-foot">
        <button type="button" className="dash-key" disabled={revising !== null} onClick={() => void generate()}>{t("nc.generate")}</button>
        <span className="nc-note">{t("nc.costs")}</span>
      </div>
    </div>
  );
}
