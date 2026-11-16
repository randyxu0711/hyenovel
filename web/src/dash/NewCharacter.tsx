import { useCallback, useEffect, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent } from "react";
import { api, DashError, type CardDraft, type Candidate, type CandidateAgain, type Character } from "./api";
import Figure, { type FigureState } from "./Figure";
import CardEditor, { candidateLimits } from "./CardEditor";
import { clock } from "./clock";
import Icon from "./Icon";
import { errorMessage, localized, useLang, useT, type Lang, type MsgKey } from "./i18n";
import type { FigureSpec, Pose } from "./figure/poses";
import { WORDS } from "./questionnaire";
import { aborted, draft, drop, keep, running, start, takeMissed, watch, type Answers, type Job } from "./newCharacterDraft";

const GRAY = { fill: "var(--dash-paper-ink-2)", text: "var(--dash-paper-ink-2)" };
const character = (seed: string, figure: FigureSpec): Character => ({
  id: seed, version: 1, origin: "created", archived: false, name: {}, line: {}, avatar: { kind: "figure", seed },
  figure, colors: { light: GRAY, dark: GRAY }, voice: "", mark: "pencil", reading: "", examples: "", depth_prompt: null,
});
const placeholder = (seed: string, pose: Pose) => character(seed, { pose, parts: [], main: "bone", second: "bone" });
const look = (c: Candidate): FigureSpec => ({ parts: c.figure.parts, eyes: c.figure.eyes, mouth: c.figure.mouth, main: c.figure.main, second: c.figure.second });
const figureOf = (c: Candidate, lang: Lang) => character(c.name["zh-Hant"] ?? localized(c.name, lang), look(c));
const lookKey = (c: Candidate | undefined) => (c ? JSON.stringify(c.figure) : "");

const SLOTS: Pose[][] = [["perch", "quad", "long"], ["mound", "upright", "frame"], ["wisp", "long", "perch"]];
const SKETCH = 4200;
const SPEAK = 1200;
const DRAWN = 3200;
const FIG = 168;
const still = () => {
  try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch { return false; }
};

function useElapsed(on: boolean) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!on) return;
    const started = running()?.started ?? Date.now();
    const tick = () => setElapsed((Date.now() - started) / 1000);
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [on]);
  return elapsed;
}

function FormingSlip({ slot }: { slot: number }) {
  const poses = SLOTS[slot];
  const [k, setK] = useState(0);
  useEffect(() => {
    if (still()) return;
    let id: ReturnType<typeof setInterval> | undefined;
    const first = setTimeout(() => {
      setK(n => n + 1);
      id = setInterval(() => setK(n => n + 1), SKETCH);
    }, SKETCH + slot * 250);
    return () => { clearTimeout(first); clearInterval(id); };
  }, [slot]);
  const pose = poses[k % poses.length];
  return (
    <div className="nc-card nc-ghost">
      <span className="char-stage">
        <span key={k} className="nc-ghost-fig" style={k === 0 ? { animationDelay: `${slot * 0.25}s`, "--nc-d": `${slot * 0.25}s` } as CSSProperties : undefined}>
          <Figure character={placeholder(`slot${slot}-${pose}`, pose)} size={FIG} />
        </span>
      </span>
      <span className="nc-blank" />
    </div>
  );
}

export function NewSlot({ onOpen }: { onOpen: () => void }) {
  const t = useT();
  const [, setTick] = useState(0);
  const job = running();
  const batch = draft()?.batch;
  const elapsed = useElapsed(job?.kind === "generate");
  useEffect(() => {
    if (!job) return;
    let on = true;
    job.done.catch(() => {}).finally(() => { if (on) setTick(n => n + 1); });
    return () => { on = false; };
  }, [job]);
  const kept = job?.kind === "generate" ? t("set.card.newRunning") : batch ? t("set.card.newKept") : undefined;
  return (
    <button type="button" className="char-new-slot" aria-label={kept} title={kept} onClick={onOpen}>
      {job?.kind === "generate" ? (
        <span className="nc-mini nc-ghost" aria-hidden="true">
          <Figure character={placeholder("mini", "perch")} size={28} />
          <span className="dash-dm">{clock(elapsed)}</span>
        </span>
      ) : batch ? (
        <span className="nc-mini" aria-hidden="true">{batch.map((c, i) => <Figure key={i} character={figureOf(c, "zh-Hant")} size={28} />)}</span>
      ) : <span aria-hidden="true"><Icon name="plus" /></span>}
      {t("set.card.new")}
    </button>
  );
}

type Fault = { key: MsgKey; card?: number };

export default function NewCharacter({ onClose, onSaved }: { onClose: () => void; onSaved: (id?: string) => Promise<void> }) {
  const t = useT();
  const lang = useLang();
  const [saved] = useState(() => draft());
  const [job] = useState(() => running());
  const [form, setForm] = useState(saved?.form ?? "");
  const [wish, setWish] = useState(saved?.wish ?? "");
  const [round, setRound] = useState<number | null>(null);
  const [asked, setAsked] = useState<Answers | undefined>(saved?.asked);
  const [batch, setBatch] = useState<Candidate[] | null>(saved?.batch ?? null);
  const [batchNo, setBatchNo] = useState(saved?.batchNo ?? 0);
  const [revealed, setRevealed] = useState(saved?.revealed ?? saved?.batchNo ?? 0);
  const [generating, setGenerating] = useState(job?.kind === "generate");
  const [revising, setRevising] = useState<number | null>(job?.kind === "revise" ? job.index : null);
  const [picked, setPicked] = useState<number | null>(saved?.picked ?? null);
  const [using, setUsing] = useState<number | null>(null);
  const [reviseOpen, setReviseOpen] = useState<number | null>(job?.kind === "revise" ? job.index : null);
  const [story, setStory] = useState(saved?.story);
  const [reaction, setReaction] = useState(saved?.reaction ?? "");
  const [feedback, setFeedback] = useState<Record<number, string>>(() => (job?.kind === "revise" && job.index !== null && job.text ? { [job.index]: job.text } : {}));
  const [fold, setFold] = useState<"answers" | "again" | null>(() => (saved?.reaction && job?.kind !== "generate" ? "again" : null));
  const [anim, setAnim] = useState<"fold" | "unfold" | null>(null);
  const [drawn, setDrawn] = useState<{ cards: number[]; stagger: boolean }>({ cards: [], stagger: false });
  const [revised, setRevised] = useState<number | null>(null);
  const [speaking, setSpeaking] = useState<number | null>(null);
  const [err, setErr] = useState<Fault | null>(null);
  const [mirror, setMirror] = useState<{ name: string; line: string } | null>(null);
  const [stuck, setStuck] = useState(false);
  const pin = useRef<HTMLSpanElement>(null);
  const onTitle = useCallback((name: string, line: string) => setMirror({ name, line }), []);
  const live = useRef(true);
  const done = useRef(false);
  const landed = useRef(false);
  const lastFold = useRef(fold);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const formRef = useRef<HTMLInputElement>(null);
  const reactionRef = useRef<HTMLInputElement>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const swapRef = useRef<HTMLButtonElement>(null);
  const useKey = useRef<HTMLButtonElement>(null);
  const reviseKey = useRef<HTMLButtonElement>(null);
  const lastOpen = useRef(reviseOpen);
  const lastUsing = useRef(using);
  const elapsed = useElapsed(generating || revising !== null);

  const failure = (e: unknown): MsgKey => {
    const usage = e instanceof DashError && e.params.reason === "usage-limit";
    return usage ? errorMessage("usage-limit") : errorMessage(e instanceof DashError ? e.code : "unknown");
  };

  const follow = (j: Job, before?: string) => j.done.then(() => {
    if (!live.current) return true;
    const d = draft();
    if (d?.batch) {
      setBatch(d.batch);
      if (j.kind === "generate") {
        setBatchNo(d.batchNo); setStory(d.story); setReaction(d.reaction); setAsked(d.asked); setPicked(null); setFold(null);
        landed.current = true;
      } else if (j.index !== null) {
        if (lookKey(d.batch[j.index]) !== before) setDrawn({ cards: [j.index], stagger: false });
        setRevised(j.index);
      }
    }
    return true;
  }, e => {
    if (!live.current || aborted(e)) return false;
    setErr({ key: failure(e), card: j.kind === "revise" ? j.index ?? undefined : undefined });
    return false;
  }).finally(() => {
    if (!live.current) return;
    if (j.kind === "revise") setRevising(null);
    else setGenerating(false);
  });

  useEffect(() => {
    live.current = true;
    const unwatch = watch();
    const missed = takeMissed();
    if (missed) setErr({ key: failure(missed) });
    const j = running();
    if (j && j === job) void follow(j, j.kind === "revise" && j.index !== null ? lookKey(saved?.batch?.[j.index]) : undefined);
    return () => { live.current = false; unwatch(); };
  }, []);
  useEffect(() => {
    if (done.current) return;
    keep({ form, wish, batch, batchNo, story, reaction, picked, revealed, asked });
  }, [form, wish, batch, batchNo, story, reaction, picked, revealed, asked]);
  useEffect(() => {
    if (generating || !batch || revealed === batchNo) return;
    setRevealed(batchNo);
    setDrawn({ cards: batch.map((_, i) => i), stagger: true });
  }, [generating, batch, batchNo, revealed]);
  useEffect(() => {
    if (drawn.cards.length === 0) return;
    const id = setTimeout(() => setDrawn({ cards: [], stagger: false }), DRAWN);
    return () => clearTimeout(id);
  }, [drawn]);
  useEffect(() => {
    if (picked === null || still()) return;
    setSpeaking(picked);
    const id = setTimeout(() => setSpeaking(null), SPEAK);
    return () => clearTimeout(id);
  }, [picked]);
  useEffect(() => {
    if (generating || !landed.current) return;
    landed.current = false;
    tabs.current[0]?.focus();
  }, [generating]);
  useEffect(() => {
    if (lastOpen.current !== null && reviseOpen === null) reviseKey.current?.focus();
    lastOpen.current = reviseOpen;
  }, [reviseOpen]);
  useEffect(() => {
    if (lastUsing.current !== null && using === null) useKey.current?.focus();
    lastUsing.current = using;
  }, [using]);
  useEffect(() => {
    const was = lastFold.current;
    if (was === fold) return;
    lastFold.current = fold;
    if (fold === "answers") formRef.current?.focus();
    else if (fold === "again") reactionRef.current?.focus();
    else if (was === "answers") editRef.current?.focus();
    else swapRef.current?.focus();
  }, [fold]);

  const home = batch !== null || generating;
  useEffect(() => {
    const el = pin.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => setStuck(!e.isIntersecting));
    io.observe(el);
    return () => io.disconnect();
  }, [home, fold]);
  useEffect(() => { if (using === null) setMirror(null); }, [using]);
  const stale = !!batch && !!asked && !generating && (form.trim() !== asked.form || wish.trim() !== asked.wish);

  const generate = (again?: CandidateAgain) => {
    const answers = { form: form.trim(), wish: wish.trim() };
    setErr(null); setUsing(null); setFold(null); setAnim("fold");
    const j = start("generate", null, async signal => {
      const out = await api.characterCandidates(answers, lang, again, signal);
      return d => ({ ...d, batch: out.candidates, story: out.story, batchNo: d.batchNo + 1, asked: answers, picked: null, reaction: again ? "" : d.reaction });
    });
    setGenerating(true);
    void follow(j);
  };

  const revise = (index: number, e: FormEvent) => {
    e.preventDefault();
    const text = (feedback[index] ?? "").trim();
    if (!text || revising !== null || generating || !batch) return;
    setErr(null); setRevising(index); setRevised(null);
    const target = batch[index];
    void follow(start("revise", index, async signal => {
      const next = await api.reviseCandidate(target, text, lang, signal);
      return d => ({ ...d, batch: d.batch && d.batch.map((c, i) => (i === index ? next : c)) });
    }, text), lookKey(target)).then(ok => { if (ok && live.current) { setFeedback(f => ({ ...f, [index]: "" })); setReviseOpen(null); } });
  };

  const regenerate = (e: FormEvent) => {
    e.preventDefault();
    if (revising !== null || !batch) return;
    generate({ reaction: reaction.trim(), previous: batch.map(c => ({ name: localized(c.name, lang), line: localized(c.line, lang) })) });
  };

  const save = async (index: number, card: CardDraft, confirm: boolean) => {
    const depth = card.depth !== batch![index].depth ? card.depth : undefined;
    const out = await api.createCharacter({ ...batch![index], name: card.name, line: card.line, reading: card.reading }, confirm, depth);
    if (!out.created) return out.warnings ?? [];
    done.current = true;
    drop();
    await onSaved(out.character?.id);
    return [];
  };

  const choose = (i: number) => {
    if (i !== picked) { setUsing(null); setRevised(null); if (revising === null) setReviseOpen(null); }
    setPicked(i);
  };
  const onTabKey = (e: KeyboardEvent<HTMLButtonElement>, i: number) => {
    if (using !== null) return;
    const n = batch?.length ?? 0;
    const to = ({ ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1 } as Record<string, number>)[e.key];
    if (to === undefined) return;
    e.preventDefault();
    choose(to);
    tabs.current[to]?.focus();
  };
  const collapse = (e: KeyboardEvent) => {
    if (e.key !== "Escape" || picked === null || using === picked) return;
    e.stopPropagation();
    const at = picked;
    setPicked(null);
    tabs.current[at]?.focus();
  };
  const stop = () => running()?.stop();
  const openAnswers = () => { setErr(null); setAnim("unfold"); setFold("answers"); };
  const closeFold = () => { setAnim("fold"); setFold(null); };

  const pageAlert = err && err.card === undefined && <p className="nc-err" role="alert">{t(err.key)}</p>;

  const questionnaire = (
    <div className="nc-ans" data-anim={anim === "unfold" ? "unfold" : undefined}
      onKeyDown={e => { if (e.key === "Escape" && home) { e.stopPropagation(); closeFold(); } }}>
      <div className="nc-sheet">
        {home && <button type="button" className="ib nc-fold" aria-label={t("nc.fold")} title={t("nc.fold")} onClick={closeFold}><Icon name="close" /></button>}
        <div className="nc-q nc-form">
          <label htmlFor="nc-form">{t("nc.form")}</label>
          <div className="nc-formline">
            <input id="nc-form" ref={formRef} maxLength={80} autoComplete="off" value={form} aria-describedby="nc-form-hint"
              onChange={e => setForm(e.target.value)} />
            <button type="button" className="ib nc-idea" aria-pressed={round !== null} aria-label={t("nc.noIdea")} title={t("nc.noIdea")}
              onClick={() => setRound(r => (r === null ? 0 : null))}><Icon name="dice" /></button>
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
      {pageAlert}
      <div className="nc-foot">
        <button type="button" className="dash-key" disabled={revising !== null || (!form.trim() && !wish.trim())}
          title={!form.trim() && !wish.trim() ? t("nc.needAnswer") : undefined} onClick={() => generate()}>{t("nc.generate")}</button>
        <span className="nc-note">{t("nc.costs")}</span>
      </div>
    </div>
  );

  const strip = (
    <div className="nc-strip" data-anim={anim === "fold" ? "fold" : undefined} data-stuck={stuck || undefined}>
      <p className="nc-asked">
        {form.trim() || wish.trim()
          ? <>{form.trim() && <b>{form.trim()}</b>}{wish.trim() && <span>{wish.trim()}</span>}</>
          : <span>{t("nc.form")}</span>}
      </p>
      <div className="nc-strip-acts">
        {generating ? (
          <p className="nc-state" role="status">
            <span className="nc-note">{t("nc.leaveOk")}</span>
            {t("nc.generating")} <span className="dash-dm">{clock(elapsed)}</span>
            <button type="button" className="nc-swap nc-stop" onClick={stop}><Icon name="stop" />{t("run.stop")}</button>
          </p>
        ) : fold === "again" ? (
          <button type="button" className="ib" aria-label={t("nc.fold")} title={t("nc.fold")} onClick={closeFold}><Icon name="close" /></button>
        ) : (
          <>
            <button type="button" ref={editRef} className="nc-swap" disabled={using !== null} onClick={openAnswers}><Icon name="edit" />{t("nc.editAnswers")}</button>
            <button type="button" ref={swapRef} className="nc-swap" aria-expanded={false} disabled={revising !== null || using !== null}
              onClick={() => { setErr(null); setFold("again"); }}><Icon name="again" />{t("nc.again")}</button>
          </>
        )}
      </div>
      {fold === "again" && !generating && (
        <form className="nc-again" onSubmit={regenerate} onKeyDown={e => { if (e.key === "Escape") { e.stopPropagation(); closeFold(); } }}>
          <div className="nc-againline">
            <input ref={reactionRef} aria-label={t("nc.reaction")} placeholder={t("nc.reactionExample")} maxLength={300} autoComplete="off" value={reaction}
              onChange={e => setReaction(e.target.value)}
              onKeyDown={e => {
                if (e.key !== "Tab" || e.shiftKey || reaction) return;
                e.preventDefault();
                setReaction(t("nc.reactionExample"));
              }} />
            {!reaction && <kbd aria-hidden="true">Tab</kbd>}
          </div>
          <div className="nc-again-foot">
            <span className="nc-note">{t("nc.costs")}</span>
            <button type="submit" className="dash-key" disabled={revising !== null}><Icon name="again" />{t("nc.again")}</button>
          </div>
        </form>
      )}
      {pageAlert}
    </div>
  );

  const title = (c: Candidate, i: number) => {
    const typed = using === i ? mirror : null;
    const name = typed?.name ?? localized(c.name, lang);
    const line = typed?.line ?? localized(c.line, lang);
    if (name === localized(c.form, lang)) return <b className="nc-name" data-lined="true">{line}</b>;
    return <><b className="nc-name">{name}</b><span className="nc-line">{line}</span></>;
  };

  const figureState = (i: number): FigureState | undefined => (revising === i ? "scanning" : speaking === i ? "speaking" : undefined);

  const panel = (c: Candidate, i: number) => {
    const busy = revising === i;
    const locked = revising !== null;
    const text = feedback[i] ?? "";
    return (
      <section role="tabpanel" id="nc-panel" aria-labelledby={`nc-tab-${i}`} className="nc-panel" data-at={i}>
        {using === i ? (
          <CardEditor key={`${batchNo}-${i}`} sheet draft={c} limits={candidateLimits(lang)} onTitle={onTitle}
            onSave={(d, confirm) => save(i, d, confirm)} onCancel={() => setUsing(null)} />
        ) : (
          <div key={`${i}-${lookKey(c)}-${localized(c.line, lang)}`} className="nc-panel-body" data-fresh={revised === i || undefined}>
            {c.examples.length > 0 && (
              <div className="nc-ex char-ex">
                {story && <p className="char-ex-lead" title={story}>{t("nc.story", { story: story.includes("〉") ? story.slice(0, story.indexOf("〉") + 1) : story })}</p>}
                {c.examples.map((turns, j) => (
                  <ol key={j} className="nc-talk">
                    {turns.map((turn, k) => (
                      <li key={k} data-who={turn.who} className={turn.who === "author" ? "chat-me" : undefined}><p>{turn.text}</p></li>
                    ))}
                  </ol>
                ))}
              </div>
            )}
            <details className="nc-how">
              <summary>{t("nc.reading")}</summary>
              <p>{c.reading}</p>
              {c.sample && <p className="nc-sample">{c.sample}</p>}
            </details>
            {c.warnings.map(w => <p key={w} className="nc-warn" role="note">{t(`card.warn.${w}` as MsgKey)}</p>)}
            <div className="nc-acts">
              {reviseOpen === i ? (
                <form className="nc-again nc-revise" onSubmit={e => revise(i, e)}
                  onKeyDown={e => { if (e.key === "Escape" && !busy && !e.nativeEvent.isComposing) { e.stopPropagation(); setReviseOpen(null); } }}>
                  <div className="nc-againline">
                    <input autoFocus aria-label={t("nc.feedback")} placeholder={t("nc.feedback")} maxLength={300} autoComplete="off" value={text}
                      readOnly={busy} onChange={e => setFeedback(f => ({ ...f, [i]: e.target.value }))} />
                    {!busy && (
                      <button type="button" className="ib" aria-label={t("nc.fold")} title={t("nc.fold")} onClick={() => setReviseOpen(null)}><Icon name="close" /></button>
                    )}
                  </div>
                  {err?.card === i && <p className="nc-err" role="alert">{t(err.key)}</p>}
                  <div className="nc-again-foot">
                    {busy ? (
                      <p className="nc-state" role="status">
                        <span className="dash-dm">{clock(elapsed)}</span>
                        <button type="button" className="nc-swap nc-stop" onClick={e => { if (e.detail <= 1) stop(); }}><Icon name="stop" />{t("run.stop")}</button>
                      </p>
                    ) : (
                      <>
                        <span className="nc-note">{t("nc.costs")}</span>
                        <button type="submit" className="dash-key" disabled={locked || !text.trim()}>{t("nc.reviseSend")}</button>
                      </>
                    )}
                  </div>
                </form>
              ) : (
                <>
                  {err?.card === i && <p className="nc-err" role="alert">{t(err.key)}</p>}
                  <div className="nc-acts-row">
                    <button type="button" ref={reviseKey} className="nc-swap" disabled={locked} onClick={() => { setErr(null); setReviseOpen(i); }}>
                      {t("nc.revise")}
                    </button>
                    <button type="button" ref={useKey} className="dash-key nc-use" disabled={locked} onClick={() => setUsing(i)}>{t("nc.use")}</button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </section>
    );
  };

  const lineup = (
    <div className="nc-lineup" data-stale={stale || undefined} onKeyDown={collapse}>
      {generating || !batch ? (
        <div className="nc-tabs" aria-hidden="true">{[0, 1, 2].map(i => <FormingSlip key={i} slot={i} />)}</div>
      ) : (
        <div className="nc-tabs" role="tablist" aria-label={t("nc.lineup")}>
          {batch.map((c, i) => {
            const draw = drawn.cards.includes(i);
            return (
              <button key={`${batchNo}-${i}`} ref={el => { tabs.current[i] = el; }} type="button" role="tab" id={`nc-tab-${i}`}
                className="nc-card nc-tab" aria-selected={picked === i} aria-controls={picked === i ? "nc-panel" : undefined}
                tabIndex={(picked ?? 0) === i ? 0 : -1} data-draw={draw || undefined} data-retitle={(revised === i && !draw) || undefined}
                disabled={using !== null && using !== i} data-using={using === i || undefined}
                style={draw && drawn.stagger ? { "--nc-d": `${i * 0.3}s` } as CSSProperties : undefined}
                onClick={() => (picked === i && using !== i ? setPicked(null) : choose(i))} onKeyDown={e => onTabKey(e, i)}>
                <span className="char-stage">
                  <span key={lookKey(c)} className="nc-fig"><Figure character={figureOf(c, lang)} size={FIG} state={figureState(i)} /></span>
                </span>
                {title(c, i)}
                {revising === i && <span className="dash-dm nc-clock" aria-hidden="true">{clock(elapsed)}</span>}
              </button>
            );
          })}
        </div>
      )}
      {!generating && batch && picked !== null && batch[picked] && panel(batch[picked], picked)}
    </div>
  );

  return (
    <div className="nc">
      <button type="button" className="nc-back" onClick={onClose}><Icon name="back" />{t("nc.backToList")}</button>
      {home ? (
        <div className="nc-home">
          <span ref={pin} className="nc-pin" aria-hidden="true" />
          {fold === "answers" && !generating ? questionnaire : strip}
          {lineup}
        </div>
      ) : questionnaire}
    </div>
  );
}
