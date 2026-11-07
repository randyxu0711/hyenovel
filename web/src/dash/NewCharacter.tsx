import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, DashError, type CardDraft, type Candidate, type CandidateAnswers, type Character } from "./api";
import Blob from "./Blob";
import CardEditor, { candidateLimits } from "./CardEditor";
import CharacterCard from "./CharacterCard";
import { clock } from "./clock";
import Icon from "./Icon";
import { errorMessage, localized, useLang, useT, type MsgKey } from "./i18n";
import { marked, PASSAGE, QUESTIONS, quotesIn, WORDS, type Question, type QuestionId } from "./questionnaire";

type Pick = { option: number | "own"; text: string };
type Picks = Partial<Record<QuestionId, Pick>>;

const GRAY = { fill: "var(--dash-paper-ink-2)", text: "var(--dash-paper-ink-2)" };
const ghost = (seed: string): Character => ({
  id: seed, version: 1, origin: "created", archived: false, name: {}, line: {},
  avatar: { kind: "blob", seed }, colors: { light: GRAY, dark: GRAY }, voice: "", mark: "pencil", reading: "",
});

function Passage({ hover }: { hover: string }) {
  return (
    <p className="nc-passage">
      {marked(PASSAGE, quotesIn(hover)).map((part, i) =>
        part.on ? <span key={i} className="nc-wave">{part.text}</span> : part.text)}
    </p>
  );
}

function Choices({ question, setIdx, pick, onSwap, onPick, onHover }: {
  question: Question; setIdx: number; pick: Pick | undefined;
  onSwap: () => void; onPick: (p: Pick | undefined) => void; onHover: (text: string) => void;
}) {
  const t = useT();
  const lang = useLang();
  const set = question.sets[setIdx];
  const stem = localized(set.stem, lang);
  const edit = (label: string) => (
    <textarea className="nc-edit" rows={2} maxLength={300} aria-label={label} value={pick!.text}
      onChange={e => onPick({ ...pick!, text: e.target.value })} />
  );
  return (
    <fieldset className="nc-q">
      <legend>{stem}</legend>
      <ul className="nc-opts">
        {set.options.map((option, i) => {
          const text = localized(option, lang);
          const on = pick?.option === i;
          return (
            <li key={i} data-on={on} onMouseEnter={() => onHover(on ? pick.text : text)} onMouseLeave={() => onHover("")}
              onFocus={() => onHover(on ? pick.text : text)} onBlur={() => onHover("")}>
              <button type="button" className="nc-opt" aria-pressed={on} aria-label={on ? t("nc.unpick", { text }) : undefined}
                onClick={() => onPick(on ? undefined : { option: i, text })}>
                <span className="nc-mark" aria-hidden="true" />{!on && text}
              </button>
              {on && edit(t("nc.tweak"))}
            </li>
          );
        })}
        <li data-on={pick?.option === "own"}>
          <button type="button" className="nc-opt nc-own" aria-pressed={pick?.option === "own"}
            onClick={() => onPick(pick?.option === "own" ? undefined : { option: "own", text: "" })}>
            <span className="nc-mark" aria-hidden="true" />{pick?.option !== "own" && t("nc.own")}
          </button>
          {pick?.option === "own" && edit(t("nc.own"))}
        </li>
      </ul>
      <button type="button" className="nc-swap" onClick={onSwap}><Icon name="swap" />{t("nc.swapSet")}</button>
    </fieldset>
  );
}

function CandidateSlip({ candidate, busy, locked, elapsed, onHover, onRevise, onUse }: {
  candidate: Candidate; busy: boolean; locked: boolean; elapsed: number; onHover: (text: string) => void;
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
    <CharacterCard character={ghost(candidate.name["zh-Hant"] ?? name)} name={name} sub={localized(candidate.form, lang)} scanning={busy}
      onMouseEnter={() => onHover(candidate.sample)} onMouseLeave={() => onHover("")}
      onFocus={() => onHover(candidate.sample)} onBlur={() => onHover("")}>
      <p className="nc-sample" tabIndex={0}>{candidate.sample}</p>
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
  const [blankOk, setBlankOk] = useState(false);
  const [picks, setPicks] = useState<Picks>({});
  const [sets, setSets] = useState<Record<QuestionId, number>>({ attention: 0, returns: 0, response: 0 });
  const [instance, setInstance] = useState("");
  const [hover, setHover] = useState("");
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

  const answer = (id: QuestionId) => picks[id]?.text.trim() ?? "";
  const answers: CandidateAnswers = {
    form: form.trim(), attention: answer("attention"), returns: answer("returns"),
    response: answer("response"), instance: instance.trim(),
  };
  const ready = blankOk || Object.values(answers).some(Boolean);

  const failure = (e: unknown): MsgKey => {
    const usage = e instanceof DashError && e.params.reason === "usage-limit";
    return usage ? errorMessage("usage-limit") : errorMessage(e instanceof DashError ? e.code : "unknown");
  };

  const generate = async () => {
    setErr(null); setHover(""); setUsing(null); setPhase("busy");
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
        <div className="nc-blobs" aria-hidden="true">
          {["a", "b", "c"].map(seed => <Blob key={seed} character={ghost(seed)} state="scanning" size={56} />)}
        </div>
        <p>{t("nc.generating")} <span className="dash-dm">{clock(elapsed)}</span></p>
      </div>
    );
  }

  if (phase === "results" && batch) {
    return (
      <div className="nc nc-results" ref={resultsRef} tabIndex={-1}>
        {back}
        <div className="nc-pinned"><Passage hover={hover} /></div>
        <div className="char-cards">
          {batch.map((c, i) => (i === using
            ? <CardEditor key={`${batchNo}-${i}`} draft={c} limits={candidateLimits(lang)}
                onSave={(draft, confirm) => save(i, draft, confirm)} onCancel={() => setUsing(null)} />
            : <CandidateSlip key={`${batchNo}-${i}`} candidate={c} busy={revising === i} locked={revising !== null} elapsed={elapsed}
                onHover={setHover} onRevise={feedback => revise(i, feedback)} onUse={() => setUsing(i)} />))}
        </div>
        {alert}
        <div className="nc-foot">
          <button type="button" className="dash-key" disabled={revising !== null} onClick={() => void generate()}><Icon name="swap" />{t("nc.again")}</button>
          <span className="nc-note">{t("nc.costs")}</span>
          <span className="nc-note">{t("nc.grayNote")}</span>
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
              onClick={() => { setBlankOk(true); setRound(r => (r === null ? 0 : null)); }}>{t("nc.noIdea")}</button>
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
        <div className="nc-group">
          <div className="nc-pinned"><Passage hover={hover} /></div>
          {QUESTIONS.map(q => (
            <Choices key={q.id} question={q} setIdx={sets[q.id]} pick={picks[q.id]} onHover={setHover}
              onPick={p => setPicks(all => ({ ...all, [q.id]: p }))}
              onSwap={() => {
                setSets(s => ({ ...s, [q.id]: (s[q.id] + 1) % q.sets.length }));
                setPicks(all => ({ ...all, [q.id]: undefined }));
              }} />
          ))}
        </div>
        <details className="nc-q nc-instance">
          <summary>{t("nc.instance")}</summary>
          <textarea className="nc-edit" rows={3} maxLength={500} aria-label={t("nc.instance")} value={instance}
            onChange={e => setInstance(e.target.value)} />
        </details>
      </div>
      {alert}
      <div className="nc-foot">
        <button type="button" className="dash-key" disabled={!ready || revising !== null} onClick={() => void generate()}>{t("nc.generate")}</button>
        <span className="nc-note">{t("nc.costs")}</span>
      </div>
    </div>
  );
}
